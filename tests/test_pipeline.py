import tempfile
import unittest
from pathlib import Path

import pandas as pd

import pipeline
from temporal import compute_temporal
from structural import add_pattern_evidence, completeness, pattern_counts, robustness
import networkx as nx


DATA = Path(__file__).resolve().parents[1] / "data"


class PipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nodes, cls.edges, cls.tx = pipeline.load_validate(DATA)
        cls.graph, cls.frame = pipeline.build_features(cls.nodes, cls.edges)
        cls.cluster_of = pipeline.cluster_graph(cls.graph, cls.frame)
        cls.frame = cls.frame.merge(compute_temporal(cls.nodes, cls.tx), on="gid", validate="one_to_one")
        pipeline.assign_roles(cls.frame)
        pipeline.rank_nodes(cls.frame)
        add_pattern_evidence(cls.frame, cls.graph, cls.tx)
        cls.frame["node_summary"] = ""
        cls.frame["node_summary_source"] = "deterministic"
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

    def test_temporal_signals_against_transactions(self):
        gid = 100000000343175100
        row = self.frame.loc[self.frame.gid == gid].iloc[0]
        self.assertEqual((row.fast_out_count, row.sync_days, row.burst_days), (28, 1, 3))
        source = self.tx.loc[self.tx.dst == gid].copy()
        source["date"] = pd.to_datetime(source.date)
        same_day = source.loc[source.date == pd.Timestamp("2026-07-18")]
        self.assertEqual((same_day.src.nunique(), same_day.sum_kzt.sum()), (2, 20000.0))
        outgoing = self.tx.loc[self.tx.src == gid].copy()
        outgoing["date"] = pd.to_datetime(outgoing.date)
        self.assertTrue((source.date == pd.Timestamp("2026-07-01")).any())
        self.assertTrue((outgoing.date == pd.Timestamp("2026-07-02")).any())
        daily_incident = int((source.date == pd.Timestamp("2026-07-19")).sum() +
                             (outgoing.date == pd.Timestamp("2026-07-19")).sum())
        self.assertEqual(daily_incident, 7)

    def test_temporal_one_day_lag_excludes_same_day(self):
        nodes = pd.DataFrame({"gid": [1, 2, 3, 4]})
        tx = pd.DataFrame([
            (2, 1, "2026-07-01", 6000.0),
            (3, 1, "2026-07-01", 7000.0),
            (1, 4, "2026-07-01", 5000.0),
            (1, 4, "2026-07-02", 8000.0),
        ], columns=["src", "dst", "date", "sum_kzt"])
        row = compute_temporal(nodes, tx).set_index("gid").loc[1]
        self.assertEqual(row.fast_out_count, 1)
        self.assertEqual(row.sync_max_payers, 2)
        self.assertEqual(row.burst_max_count, 3)

    def test_structural_patterns_on_small_graph(self):
        graph = nx.DiGraph()
        graph.add_edges_from([(1, 2, {"n_tx": 3}), (2, 3, {"n_tx": 2}),
                              (3, 1, {"n_tx": 1}), (2, 4, {"n_tx": 1})])
        tx = pd.DataFrame([(src, 2, "2026-07-02", amount) for src, amount in
                           ((1, 5000), (3, 5500), (4, 6000))] +
                          [(1, 2, "2026-07-03", 5500)],
                          columns=["src", "dst", "date", "sum_kzt"])
        cycles, chains, splits = pattern_counts(graph, tx)
        self.assertEqual([cycles[i] for i in (1, 2, 3, 4)], [1, 1, 1, 0])
        self.assertEqual([chains[i] for i in (1, 2, 3, 4)], [1, 1, 1, 0])
        self.assertEqual([splits[i] for i in (1, 2, 3, 4)], [0, 3, 0, 0])
        long_cycle = nx.DiGraph((i, i + 1) for i in range(10, 16))
        long_cycle.add_edge(16, 10)
        nx.set_edge_attributes(long_cycle, 1, "n_tx")
        self.assertEqual(pattern_counts(long_cycle, tx)[0], {})
        frame = pd.DataFrame({"gid": [1, 2, 3, 4], "evidence": ["Признак."] * 4,
                              "in_deg": [1] * 4, "out_deg": [1] * 4,
                              "n_reaching_seed": [1] * 4, "n_other_clusters": [0] * 4,
                              "role": ["transit"] * 4,
                              "truncated_by_depth": [False] * 4, "is_seed": [False] * 4})
        add_pattern_evidence(frame, graph, tx)
        self.assertIn("Цикл≤6: 1", frame.loc[0, "evidence"])
        self.assertIn("Дробление, tx: 3", frame.loc[1, "evidence"])
        self.assertNotIn("Цикл≤6", frame.loc[3, "evidence"])

    def test_robustness_path_loss_uses_original_targets(self):
        graph = nx.DiGraph([(1, 2), (2, 3), (4, 3)])
        frame = pd.DataFrame({"gid": [1, 2, 3, 4], "is_seed": [True, False, False, True],
                              "role": ["peripheral", "transit", "consolidator", "peripheral"],
                              "priority_score": [0.1, 0.9, 0.8, 0.2]})
        result = robustness(graph, frame, (1,)).iloc[0]
        self.assertEqual((result.components, result.seeds_with_path_before,
                          result.seeds_with_path_after, result.seeds_lost_path), (2, 2, 1, 1))
        self.assertEqual(result.share_all_seeds_lost_pct, 50.0)
        lone = nx.DiGraph()
        lone.add_node(7)
        lone_frame = pd.DataFrame({"gid": [7], "is_seed": [True],
                                   "role": ["coordinator"], "priority_score": [0.9]})
        self.assertEqual(robustness(lone, lone_frame, (0,)).iloc[0].seeds_with_path_before, 0)
        lone.add_edge(7, 7)
        self.assertEqual(robustness(lone, lone_frame, (0,)).iloc[0].seeds_with_path_before, 1)

    def test_optional_exports_and_completeness(self):
        self.assertTrue(self.frame.evidence.str.len().le(200).all())
        self.assertTrue(self.outputs["clusters.csv"].hypothesis.str.contains("узлов: ").all())
        self.assertIn("444", completeness(self.frame, self.tx))
        self.assertIn("5 000 KZT", completeness(self.frame, self.tx))
        result = robustness(self.graph, self.frame)
        self.assertEqual(result.top_removed.tolist(), [5, 10, 20])
        self.assertTrue(result.seeds_lost_path.is_monotonic_increasing)

    def test_three_roles_explained_by_thresholds(self):
        for role in ("coordinator", "transit", "terminal"):
            row = self.frame.loc[self.frame.role == role].iloc[0]
            self.assertTrue("Получает от {}".format(row.in_deg) in row.evidence or
                            "Вх:{}".format(row.in_deg) in row.evidence)
            self.assertTrue("отправляет {}".format(row.out_deg) in row.evidence or
                            "вых:{}".format(row.out_deg) in row.evidence)
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
