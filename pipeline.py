#!/usr/bin/env python3
"""Deterministic analysis of the supplied directed transfer network (Python 3.9)."""

import argparse
import math
import os
import sys
import tempfile
import time
from pathlib import Path

import networkx as nx
import numpy as np
import pandas as pd

ROLES = ("coordinator", "consolidator", "distributor", "transit", "terminal", "peripheral")
ROLE_WEIGHT = dict(zip(ROLES, (1.0, 0.9, 0.8, 0.6, 0.3, 0.1)))
ROLE_PHRASES = {
    "coordinator": "Признаки координации",
    "consolidator": "Признаки консолидации",
    "distributor": "Признаки распределения",
    "transit": "Признаки транзита",
    "terminal": "Признаки наблюдаемого завершения",
    "peripheral": "Без явной роли",
}
SCHEMAS = {
    "nodes.parquet": ("gid", "depth", "is_seed"),
    "edges.parquet": ("src", "dst", "sum_kzt", "n_tx", "depth"),
    "transactions.parquet": ("src", "dst", "date", "sum_kzt"),
}


class DataError(ValueError):
    pass


def clip(value):
    return min(1.0, max(0.0, float(value)))


def amount_text(value):
    if value >= 1_000_000:
        return "{} млн KZT".format("{:.2f}".format(value / 1_000_000).replace(".", ","))
    if value >= 1_000:
        return "{} тыс. KZT".format("{:.1f}".format(value / 1_000).replace(".", ","))
    return "{:.0f} KZT".format(value)


def count_form(number, one, few, many):
    if number % 100 in (11, 12, 13, 14):
        return many
    if number % 10 == 1:
        return one
    if number % 10 in (2, 3, 4):
        return few
    return many


def describe_node(row, role):
    text = "Получает от {} {} ({}), отправляет {} {}".format(
        row.in_deg, count_form(row.in_deg, "плательщика", "плательщиков", "плательщиков"),
        amount_text(row.in_kzt), row.out_deg,
        count_form(row.out_deg, "получателю", "получателям", "получателям")
    )
    if row.truncated_by_depth:
        pass
    elif row.in_kzt > 0 and not row.is_seed:
        text += " {:.0f}% полученного".format(100 * row.pass_through)
    else:
        text += " ({})".format(amount_text(row.out_kzt))
    text += "; достижим от {} seed; связь с {} кластерами. {}.".format(
        row.n_reaching_seed, row.n_other_clusters, ROLE_PHRASES[role]
    )
    if row.truncated_by_depth:
        text += " 4-е колено, исходящие не наблюдаются — конечность не доказана."
    if row.is_seed:
        text += " У seed вход неполон."
    return text


def load_validate(data_dir):
    tables = {}
    for filename, columns in SCHEMAS.items():
        path = data_dir / filename
        if not path.is_file():
            raise DataError("V-01: missing " + str(path))
        try:
            table = pd.read_parquet(path)
        except Exception as exc:
            raise DataError("V-01: cannot read {}: {}".format(path, exc)) from exc
        missing = set(columns) - set(table.columns)
        if missing or table.empty or table[list(columns)].isna().any().any():
            raise DataError("V-01: invalid {} (missing columns: {})".format(filename, sorted(missing)))
        tables[filename] = table
    nodes, edges, tx = (tables[name] for name in SCHEMAS)
    for filename, table, columns in (
        ("nodes.parquet", nodes, ("gid", "depth")),
        ("edges.parquet", edges, ("src", "dst", "n_tx", "depth")),
        ("transactions.parquet", tx, ("src", "dst")),
    ):
        for column in columns:
            if not pd.api.types.is_integer_dtype(table[column]):
                raise DataError("V-01: {}.{} must be integer".format(filename, column))
    if not pd.api.types.is_bool_dtype(nodes.is_seed):
        raise DataError("V-01: nodes.parquet.is_seed must be boolean")
    for filename, table in (("edges.parquet", edges), ("transactions.parquet", tx)):
        if not pd.api.types.is_numeric_dtype(table.sum_kzt) or not np.isfinite(table.sum_kzt).all():
            raise DataError("V-01: {}.sum_kzt must be finite numeric".format(filename))
        if (table.sum_kzt < 5000).any():
            raise DataError("BR-01: {} contains amount below 5000 KZT".format(filename))
    if nodes.gid.duplicated().any() or edges.duplicated(["src", "dst"]).any():
        raise DataError("V-02: duplicate gid or edge pair")
    gids = set(nodes.gid)
    if not (set(edges.src) | set(edges.dst) | set(tx.src) | set(tx.dst)) <= gids:
        raise DataError("V-02: unknown edge/transaction endpoint")
    if not nodes.depth.between(0, 4).all() or not edges.depth.between(1, 4).all():
        raise DataError("V-02: depth outside 0..4")
    if not (nodes.is_seed == (nodes.depth == 0)).all():
        raise DataError("V-02: seed/depth mismatch")
    if (edges.n_tx < 1).any():
        raise DataError("V-03: n_tx must be positive")
    try:
        dates = pd.to_datetime(tx.date, errors="raise")
    except Exception as exc:
        raise DataError("V-02: invalid transactions.parquet.date") from exc
    if not dates.between(pd.Timestamp("2026-07-01"), pd.Timestamp("2026-07-31")).all():
        raise DataError("V-02: transaction date outside July 2026")
    agg = tx.groupby(["src", "dst"], as_index=False).agg(sum_kzt=("sum_kzt", "sum"), n_tx=("sum_kzt", "size"))
    joined = edges.merge(agg, on=["src", "dst"], how="outer", suffixes=("_edge", "_tx"), indicator=True)
    if (joined._merge != "both").any() or (joined.n_tx_edge != joined.n_tx_tx).any() or not np.allclose(
        joined.sum_kzt_edge, joined.sum_kzt_tx, rtol=1e-9, atol=0.01
    ):
        raise DataError("V-03: edges disagree with transactions by pair, count or amount")
    return nodes, edges, tx


def build_features(nodes, edges):
    graph = nx.DiGraph()
    graph.add_nodes_from(int(gid) for gid in nodes.gid)
    for row in edges.itertuples(index=False):
        graph.add_edge(int(row.src), int(row.dst), sum_kzt=float(row.sum_kzt), n_tx=int(row.n_tx))
    frame = nodes[["gid", "depth", "is_seed"]].copy().sort_values("gid").reset_index(drop=True)
    for name, values, integer in (
        ("in_deg", dict(graph.in_degree()), True),
        ("out_deg", dict(graph.out_degree()), True),
        ("in_kzt", dict(graph.in_degree(weight="sum_kzt")), False),
        ("out_kzt", dict(graph.out_degree(weight="sum_kzt")), False),
        ("in_tx", dict(graph.in_degree(weight="n_tx")), True),
        ("out_tx", dict(graph.out_degree(weight="n_tx")), True),
    ):
        frame[name] = frame.gid.map(values).astype(int if integer else float)
    frame["pagerank"] = frame.gid.map(nx.pagerank(graph, weight="sum_kzt"))
    frame["pass_through"] = np.where(frame.in_kzt > 0, frame.out_kzt / frame.in_kzt.replace(0, np.nan), np.nan)
    frame["truncated_by_depth"] = (frame.depth == 4) & (frame.out_deg == 0)
    reaching = {gid: 0 for gid in graph}
    for seed in sorted(int(gid) for gid in frame.loc[frame.is_seed, "gid"]):
        for gid in nx.descendants(graph, seed):
            reaching[gid] += 1
    frame["n_reaching_seed"] = frame.gid.map(reaching).astype(int)
    between = {}
    top_five = set()
    for component in nx.weakly_connected_components(graph):
        subgraph = graph.subgraph(component)
        scores = nx.betweenness_centrality(subgraph, normalized=True, weight=None)
        between.update(scores)
        top_five.update(sorted(component, key=lambda gid: (-scores[gid], gid))[:math.ceil(0.05 * len(component))])
    frame["betweenness"] = frame.gid.map(between)
    frame["top_betweenness"] = frame.gid.isin(top_five)
    return graph, frame


def cluster_graph(graph, frame):
    projection = nx.Graph()
    projection.add_nodes_from(graph.nodes)
    for src, dst, data in graph.edges(data=True):
        if projection.has_edge(src, dst):
            projection[src][dst]["weight"] += data["sum_kzt"]
        else:
            projection.add_edge(src, dst, weight=data["sum_kzt"])
    communities = nx.community.louvain_communities(projection, weight="weight", seed=42)
    communities.sort(key=lambda group: min(group))
    cluster_of = {gid: idx for idx, group in enumerate(communities) for gid in group}
    frame["cluster_id"] = frame.gid.map(cluster_of).astype(int)
    other_clusters = {}
    for gid in graph:
        neighbors = set(graph.predecessors(gid)) | set(graph.successors(gid))
        other_clusters[gid] = len({cluster_of[other] for other in neighbors if cluster_of[other] != cluster_of[gid]})
    frame["n_other_clusters"] = frame.gid.map(other_clusters).astype(int)
    return cluster_of


def assign_roles(frame):
    roles, scores, evidence = [], [], []
    for row in frame.itertuples(index=False):
        candidate = (
            row.in_deg >= 5 and row.out_deg >= 10 and row.n_reaching_seed >= 2
            and (row.n_other_clusters >= 2 or row.top_betweenness)
        )
        if candidate:
            role = "coordinator"
            strength = (clip(row.in_deg / 10) + clip(row.out_deg / 20)) / 2
        elif row.in_deg >= 5:
            role, strength = "consolidator", clip(row.in_deg / 10)
        elif row.out_deg >= 10:
            role, strength = "distributor", clip(row.out_deg / 20)
        elif not row.is_seed and row.in_deg > 0 and row.out_deg > 0 and 0.8 <= row.pass_through <= 1.2:
            role, strength = "transit", clip(1 - abs(row.pass_through - 1) / 0.4)
        elif row.depth < 4 and row.in_deg > 0 and row.out_deg == 0:
            role, strength = "terminal", clip(row.in_deg / 5)
        else:
            role, strength = "peripheral", 0.2
        score = clip(strength - 0.2 * row.truncated_by_depth - 0.2 * (row.is_seed and role in ("coordinator", "consolidator", "terminal")))
        explanation = describe_node(row, role)
        roles.append(role)
        scores.append(score)
        evidence.append(explanation)
    frame["role"] = roles
    frame["role_score"] = scores
    frame["evidence"] = evidence


def rank_nodes(frame):
    max_kzt = float(frame.in_kzt.max())
    max_between = float(frame.betweenness.max())
    denominator = math.log1p(max_kzt) if max_kzt > 0 else 0
    k = np.log1p(frame.in_kzt) / denominator if denominator else 0
    b = frame.betweenness / max_between if max_between else 0
    frame["priority_score"] = (
        0.25 * np.minimum(1, frame.in_deg / 10)
        + 0.20 * k + 0.20 * b
        + 0.20 * np.minimum(1, frame.n_reaching_seed / 10)
        + 0.15 * frame.role.map(ROLE_WEIGHT)
        - 0.20 * frame.truncated_by_depth.astype(float)
    ).clip(0, 1)


def exports(graph, frame, cluster_of):
    roles = frame[["gid", "role", "role_score", "cluster_id", "priority_score", "evidence",
                   "in_deg", "out_deg", "in_kzt", "out_kzt", "in_tx", "out_tx", "pagerank",
                   "pass_through", "betweenness", "n_reaching_seed", "n_other_clusters",
                   "depth", "is_seed", "truncated_by_depth"]].copy()
    roles[["role_score", "priority_score"]] = roles[["role_score", "priority_score"]].round(3)
    ordered = frame.sort_values(["priority_score", "gid"], ascending=[False, True]).reset_index(drop=True)
    ranked = ordered.head(20)
    top = ranked[["gid", "role", "priority_score"]].copy().reset_index(drop=True)
    top["priority_score"] = top.priority_score.round(3)
    top.insert(0, "rank", range(1, len(top) + 1))
    reasons = []
    for index, row in enumerate(ranked.itertuples(index=False)):
        following = ordered.iloc[index + 1]
        gap = row.priority_score - following.priority_score
        comparison = (
            "При равном приоритете выше следующего по gid."
            if gap < 1e-12 else
            "Выше следующего на {:.4f} по приоритету; вклад: вход {} плательщиков, {:.2f} KZT, {} seed, роль {}.".format(
                gap, row.in_deg, row.in_kzt, row.n_reaching_seed, row.role
            )
        )
        reasons.append(row.evidence + " " + comparison)
    top["why"] = reasons
    internal = {idx: 0.0 for idx in set(cluster_of.values())}
    for src, dst, data in graph.edges(data=True):
        if cluster_of[src] == cluster_of[dst]:
            internal[cluster_of[src]] += data["sum_kzt"]
    clusters = []
    for cluster_id, group in frame.groupby("cluster_id", sort=True):
        leaders = group.sort_values(["priority_score", "gid"], ascending=[False, True]).head(5)
        leader = leaders.iloc[0]
        turnover = internal[cluster_id]
        clusters.append({
            "cluster_id": int(cluster_id), "n_nodes": len(group), "n_seed": int(group.is_seed.sum()),
            "sum_kzt_internal": round(turnover, 2),
            "top_gids": ",".join(str(gid) for gid in leaders.gid),
            "hypothesis": "Признаки группы для проверки: {} узлов, {} seed, внутренний оборот {}; "
                          "консолидаторов {}, распределителей {}; крупнейший по приоритету gid {} ({}).".format(
                len(group), int(group.is_seed.sum()), amount_text(turnover),
                int((group.role == "consolidator").sum()), int((group.role == "distributor").sum()),
                int(leader.gid), leader.role
            ),
        })
    return {"nodes_roles.csv": roles, "clusters.csv": pd.DataFrame(clusters), "top_nodes.csv": top}


def validate_outputs(outputs, frame):
    roles, clusters, top = (outputs[name] for name in ("nodes_roles.csv", "clusters.csv", "top_nodes.csv"))
    if len(roles) != len(frame) or roles.gid.duplicated().any() or set(roles.gid) != set(frame.gid):
        raise DataError("output: node coverage failed")
    if not roles.role.isin(ROLES).all() or not roles.role_score.between(0, 1).all() or not roles.priority_score.between(0, 1).all():
        raise DataError("output: invalid roles or scores")
    if not roles.evidence.str.len().between(1, 200).all() or set(roles.cluster_id) != set(clusters.cluster_id):
        raise DataError("output: evidence or cluster references invalid")
    if clusters.n_nodes.sum() != len(frame) or clusters.n_seed.sum() != int(frame.is_seed.sum()) or (clusters.sum_kzt_internal < 0).any():
        raise DataError("output: cluster summary invalid")
    if len(top) < 20 or top.gid.duplicated().any() or top["why"].isna().any() or list(top["rank"]) != list(range(1, len(top) + 1)):
        raise DataError("output: top ranking invalid")
    expected = frame.sort_values(["priority_score", "gid"], ascending=[False, True]).head(len(top)).gid.tolist()
    if top.gid.tolist() != expected:
        raise DataError("output: top order invalid")


def write_outputs(outputs, out_dir):
    out_dir.mkdir(parents=True, exist_ok=True)
    pending = []
    try:
        for filename, table in outputs.items():
            fd, temporary = tempfile.mkstemp(prefix=".pipeline-", suffix=".csv", dir=out_dir)
            with os.fdopen(fd, "w", encoding="utf-8", newline="") as stream:
                table.to_csv(stream, index=False)
            pending.append((temporary, out_dir / filename))
        for temporary, destination in pending:
            os.replace(temporary, destination)
    finally:
        for temporary, _ in pending:
            if os.path.exists(temporary):
                os.unlink(temporary)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Analyse the July 2026 transfer network")
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--out", type=Path, default=Path("out"))
    args = parser.parse_args(argv)
    started = time.perf_counter()
    try:
        nodes, edges, tx = load_validate(args.data)
        graph, frame = build_features(nodes, edges)
        cluster_of = cluster_graph(graph, frame)
        assign_roles(frame)
        rank_nodes(frame)
        result = exports(graph, frame, cluster_of)
        validate_outputs(result, frame)
        write_outputs(result, args.out)
    except (DataError, OSError, nx.NetworkXException) as exc:
        print("ERROR: {}".format(exc), file=sys.stderr)
        return 1
    print("nodes={} edges={} transactions={} seeds={}".format(len(nodes), len(edges), len(tx), int(nodes.is_seed.sum())))
    print("clusters={} isolated={} truncated={} terminal_truncated={}".format(
        len(result["clusters.csv"]), sum(1 for gid in graph if graph.degree(gid) == 0),
        int(frame.truncated_by_depth.sum()), int(((frame.role == "terminal") & frame.truncated_by_depth).sum())
    ))
    print("wrote: {}".format(", ".join(str(args.out / name) for name in result)))
    print("elapsed_seconds={:.3f}".format(time.perf_counter() - started))
    return 0


if __name__ == "__main__":
    sys.exit(main())
