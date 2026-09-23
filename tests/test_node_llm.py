import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from node_llm import generate_node_cards, node_facts, validate_cards, NodeCardError


class FakeResponses:
    def __init__(self, payload):
        self.payload = payload
        self.request = None

    def create(self, **kwargs):
        self.request = kwargs
        return SimpleNamespace(status="completed", output_text=json.dumps(self.payload, ensure_ascii=False))


class NodeLLMTests(unittest.TestCase):
    def setUp(self):
        self.frame = pd.DataFrame([{
            "gid": 100000000000000101, "role": "coordinator", "cluster_id": 7,
            "depth": 2, "in_deg": 5, "out_deg": 10, "in_kzt": 12345.67,
            "out_kzt": 9000.0, "n_reaching_seed": 3, "priority_score": 0.8,
            "truncated_by_depth": False, "is_seed": False,
        }])
        facts = node_facts(self.frame)[0]
        self.payload = {"cards": [{
            "gid": facts["gid"],
            "summary": "Признаки координации потоков требуют дополнительной проверки.",
            "metrics_used": {key: facts[key] for key in (
                "role", "cluster_id", "depth", "in_deg", "out_deg",
                "in_kzt", "out_kzt", "n_reaching_seed"
            )},
        }]}

    def test_verified_card_uses_env_model_and_strict_schema(self):
        with tempfile.TemporaryDirectory() as folder:
            env = Path(folder) / ".env"
            env.write_text("OPENAI_API_KEY=fake_for_test\nOPENAI_MODEL=model_from_env\n")
            responses = FakeResponses(self.payload)
            result, status = generate_node_cards(
                self.frame, env, SimpleNamespace(responses=responses)
            )
        self.assertIn("verified: 1/1", status)
        self.assertEqual(responses.request["model"], "model_from_env")
        self.assertTrue(responses.request["text"]["format"]["strict"])
        self.assertEqual(result.iloc[0].node_summary_source, "llm_verified")

    def test_unknown_gid_and_changed_amount_rejected(self):
        facts = node_facts(self.frame)
        self.payload["cards"][0]["gid"] = "100000000000000999"
        with self.assertRaisesRegex(NodeCardError, "gid"):
            validate_cards(self.payload, facts)
        self.payload["cards"][0]["gid"] = facts[0]["gid"]
        self.payload["cards"][0]["metrics_used"]["in_kzt"] = 99999.0
        with self.assertRaisesRegex(NodeCardError, "numeric"):
            validate_cards(self.payload, facts)

    def test_missing_key_keeps_numeric_card(self):
        with tempfile.TemporaryDirectory() as folder:
            result, status = generate_node_cards(self.frame, Path(folder) / ".env")
        self.assertIn("skipped", status)
        self.assertEqual(result.iloc[0].node_summary, "")
        self.assertEqual(result.iloc[0].node_summary_source, "deterministic")

    def test_rejected_model_card_keeps_numeric_card(self):
        with tempfile.TemporaryDirectory() as folder:
            env = Path(folder) / ".env"
            env.write_text("OPENAI_API_KEY=fake_for_test\nOPENAI_MODEL=model_from_env\n")
            self.payload["cards"][0]["metrics_used"]["out_kzt"] = 1.0
            result, status = generate_node_cards(
                self.frame, env, SimpleNamespace(responses=FakeResponses(self.payload))
            )
        self.assertIn("DEGRADED", status)
        self.assertEqual(result.iloc[0].node_summary, "")


if __name__ == "__main__":
    unittest.main()
