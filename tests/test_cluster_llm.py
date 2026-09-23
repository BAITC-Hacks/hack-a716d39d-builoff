import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from cluster_llm import cluster_facts, generate_hypotheses, validate_hypotheses, HypothesisError


class FakeResponses:
    def __init__(self, payload):
        self.payload = payload
        self.request = None

    def create(self, **kwargs):
        self.request = kwargs
        return SimpleNamespace(status="completed", output_text=json.dumps(self.payload, ensure_ascii=False))


class ClusterLLMTests(unittest.TestCase):
    def setUp(self):
        self.clusters = pd.DataFrame([{
            "cluster_id": 7, "n_nodes": 3, "n_seed": 2, "sum_kzt_internal": 12345.67,
            "top_gids": "100000000000000101,100000000000000102",
            "hypothesis": "Признаки группы для проверки: 3 узла, 2 seed, оборот 12345.67 KZT.",
        }])
        self.frame = pd.DataFrame({
            "gid": [100000000000000101, 100000000000000102, 100000000000000103],
            "cluster_id": [7, 7, 7],
            "role": ["consolidator", "distributor", "peripheral"],
        })
        self.facts = cluster_facts(self.clusters, self.frame)
        self.payload = {"hypotheses": [{
            "cluster_id": 7,
            "hypothesis": "Признаки распределения внутри группы требуют проверки.",
            "supporting_gids": ["100000000000000101"],
            "metrics_used": {key: self.facts[0][key] for key in (
                "n_nodes", "n_seed", "sum_kzt_internal", "n_consolidators", "n_distributors"
            )},
        }]}

    def test_valid_structured_output_and_env_model(self):
        with tempfile.TemporaryDirectory() as folder:
            env = Path(folder) / ".env"
            env.write_text("OPENAI_API_KEY=fake_for_test\nOPENAI_MODEL=model_from_env\n")
            responses = FakeResponses(self.payload)
            result, status = generate_hypotheses(
                self.clusters, self.frame, env, SimpleNamespace(responses=responses)
            )
        self.assertIn("verified: 1/1", status)
        self.assertEqual(responses.request["model"], "model_from_env")
        self.assertTrue(responses.request["text"]["format"]["strict"])
        self.assertEqual(result.iloc[0].hypothesis_source, "llm_verified")
        self.assertEqual(result.iloc[0].supporting_gids, "100000000000000101")

    def test_invalid_gid_and_number_rejected(self):
        self.payload["hypotheses"][0]["supporting_gids"] = ["100000000000000999"]
        with self.assertRaisesRegex(HypothesisError, "gid"):
            validate_hypotheses(self.payload, self.facts)
        self.payload["hypotheses"][0]["supporting_gids"] = ["100000000000000101"]
        self.payload["hypotheses"][0]["metrics_used"]["n_nodes"] = 4
        with self.assertRaisesRegex(HypothesisError, "numeric"):
            validate_hypotheses(self.payload, self.facts)

    def test_missing_key_keeps_deterministic_hypothesis(self):
        with tempfile.TemporaryDirectory() as folder:
            result, status = generate_hypotheses(self.clusters, self.frame, Path(folder) / ".env")
        self.assertIn("skipped", status)
        self.assertEqual(result.iloc[0].hypothesis, self.clusters.iloc[0].hypothesis)
        self.assertEqual(result.iloc[0].hypothesis_source, "deterministic")

    def test_rejected_model_facts_keep_deterministic_hypothesis(self):
        with tempfile.TemporaryDirectory() as folder:
            env = Path(folder) / ".env"
            env.write_text("OPENAI_API_KEY=fake_for_test\nOPENAI_MODEL=model_from_env\n")
            self.payload["hypotheses"][0]["metrics_used"]["n_seed"] = 9
            result, status = generate_hypotheses(
                self.clusters, self.frame, env, SimpleNamespace(responses=FakeResponses(self.payload))
            )
        self.assertIn("DEGRADED", status)
        self.assertEqual(result.iloc[0].hypothesis, self.clusters.iloc[0].hypothesis)


if __name__ == "__main__":
    unittest.main()
