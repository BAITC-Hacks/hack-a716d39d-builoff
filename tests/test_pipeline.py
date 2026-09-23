import tempfile
import unittest
from pathlib import Path

import pandas as pd

import pipeline


DATA = Path(__file__).resolve().parents[1] / "data"


class PipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nodes, cls.edges, cls.tx = pipeline.load_validate(DATA)
        cls.graph, cls.frame = pipeline.build_features(cls.nodes, cls.edges)
        cls.cluster_of = pipeline.cluster_graph(cls.graph, cls.frame)
        pipeline.assign_roles(cls.frame)
        pipeline.rank_nodes(cls.frame)
        cls.outputs = pipeline.exports(cls.graph, cls.frame, cls.cluster_of)

    def test_real_data_and_exports(self):
        self.assertEqual((len(self.nodes), len(self.edges), len(self.tx)), (2248, 3119, 4840))
        pipeline.validate_outputs(self.outputs, self.frame)
        self.assertEqual(sum(self.graph.degree(gid) == 0 for gid in self.graph), 19)
        self.assertEqual(int(self.frame.truncated_by_depth.sum()), 444)
        self.assertFalse(((self.frame.role == "terminal") & self.frame.truncated_by_depth).any())
        self.assertEqual(len(self.outputs["top_nodes.csv"]), 20)
        self.assertEqual(sum(self.outputs["clusters.csv"].n_nodes), 2248)

    def test_viewer_graph_preserves_directed_edges(self):
        data = pipeline.graph_export(self.graph, self.frame)
        pipeline.validate_graph(data, self.frame, self.graph)
        self.assertEqual((len(data["nodes"]), len(data["edges"])), (2248, 3119))
        for edge in data["edges"]:
            self.assertTrue(self.graph.has_edge(int(edge["source"]), int(edge["target"])))

    def test_three_roles_explained_by_thresholds(self):
        for role in ("coordinator", "transit", "terminal"):
            row = self.frame.loc[self.frame.role == role].iloc[0]
            self.assertIn("Получает от {}".format(row.in_deg), row.evidence)
            self.assertIn("отправляет {}".format(row.out_deg), row.evidence)
            if role == "coordinator":
                self.assertGreaterEqual(row.in_deg, 5)
                self.assertGreaterEqual(row.out_deg, 10)
                self.assertGreaterEqual(row.n_reaching_seed, 2)
            elif role == "transit":
                self.assertTrue(0.8 <= row.pass_through <= 1.2)
            else:
                self.assertLess(row.depth, 4)
                self.assertEqual(row.out_deg, 0)

    def test_bad_aggregate_rejected_without_outputs(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            self.nodes.to_parquet(path / "nodes.parquet")
            self.tx.to_parquet(path / "transactions.parquet")
            corrupt = self.edges.copy()
            corrupt.loc[0, "n_tx"] += 1
            corrupt.to_parquet(path / "edges.parquet")
            with self.assertRaisesRegex(pipeline.DataError, "V-03"):
                pipeline.load_validate(path)
            self.assertFalse((path / "out").exists())


if __name__ == "__main__":
    unittest.main()
