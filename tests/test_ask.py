import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ask import Results, main, verify_answer


class AnalystToolsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        folder = Path(self.temp.name)
        rows = [
            {"gid": "100000000000000001", "role": "peripheral", "cluster_id": 3,
             "priority_score": 0.2, "in_deg": 0, "out_deg": 1, "in_kzt": 0,
             "out_kzt": 100, "is_seed": True, "depth": 0},
            {"gid": "100000000000000002", "role": "consolidator", "cluster_id": 16,
             "priority_score": 0.9, "in_deg": 1, "out_deg": 1, "in_kzt": 100,
             "out_kzt": 75, "is_seed": False, "depth": 1},
            {"gid": "100000000000000003", "role": "terminal", "cluster_id": 16,
             "priority_score": 0.1, "in_deg": 1, "out_deg": 0, "in_kzt": 75,
             "out_kzt": 0, "is_seed": False, "depth": 2},
        ]
        with (folder / "nodes_roles.csv").open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=rows[0]); writer.writeheader(); writer.writerows(rows)
        with (folder / "clusters.csv").open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["cluster_id", "n_nodes"])
            writer.writeheader(); writer.writerows([{"cluster_id": 3, "n_nodes": 1}, {"cluster_id": 16, "n_nodes": 2}])
        (folder / "graph.json").write_text(json.dumps({"nodes": [], "edges": [
            {"source": rows[0]["gid"], "target": rows[1]["gid"], "sum_kzt": 100, "n_tx": 2},
            {"source": rows[1]["gid"], "target": rows[2]["gid"], "sum_kzt": 75, "n_tx": 1},
        ]}))
        self.data = Results(folder)

    def test_six_tools_without_model(self):
        gid = "100000000000000002"
        node = self.data.call("find_node", {"gid": gid})
        self.assertTrue(node["found"])
        adjacent = self.data.call("neighbors", {"gid": gid, "direction": "both"})
        self.assertEqual(adjacent["count"], 2)
        self.assertEqual({e["direction"] for e in adjacent["edges"]}, {"in", "out"})
        top = self.data.call("top_by_role", {"role": "consolidator", "n": 5})
        self.assertEqual([r["gid"] for r in top["nodes"]], [gid])
        paths = self.data.call("paths_from_seeds", {"gid": "100000000000000003", "max_len": 2})
        self.assertEqual(paths["paths"], [["100000000000000001", gid, "100000000000000003"]])
        members = self.data.call("cluster_members", {"cluster_id": 16})
        self.assertEqual(len(members["members"]), 2)
        matched = self.data.call("search_by_metric", {"field": "in_kzt", "min": 80, "max": 120})
        self.assertEqual([r["gid"] for r in matched["nodes"]], [gid])

    def test_grounding_rejects_unknown_gid_and_number(self):
        result = self.data.call("find_node", {"gid": "100000000000000002"})
        self.assertEqual(verify_answer("gid 100000000000000002: 100 KZT", [result])[1:], (set(), set()))
        self.assertEqual(verify_answer("100 KZT", [{"amount": 100.0}])[1:], (set(), set()))
        marked, gids, numbers = verify_answer("gid 999999999999999999 получил 987654321 KZT", [result])
        self.assertTrue(marked.endswith("[не подтверждено]"))
        self.assertEqual(gids, {"999999999999999999"})
        self.assertIn("987654321", numbers)

    def test_missing_key_exits_zero(self):
        with patch.dict("os.environ", {"OPENAI_API_KEY": ""}, clear=True):
            with patch("ask.dotenv_values", return_value={}):
                self.assertEqual(main(["вопрос", "--out", self.temp.name]), 0)


if __name__ == "__main__":
    unittest.main()
