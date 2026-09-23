"""Optional deterministic graph diagnostics; never changes roles or ranking."""

from collections import Counter

import networkx as nx
import pandas as pd


def pattern_counts(graph, tx):
    """Count distinct structural motifs involving each node."""
    cycles = Counter()
    for cycle in nx.simple_cycles(graph, length_bound=6):
        if len(cycle) >= 2:
            cycles.update(cycle)

    repeated_chains = Counter()
    for middle in graph:
        incoming = [src for src in graph.predecessors(middle) if graph[src][middle]["n_tx"] >= 2]
        outgoing = [dst for dst in graph.successors(middle) if graph[middle][dst]["n_tx"] >= 2]
        for src in incoming:
            for dst in outgoing:
                if len({src, middle, dst}) == 3:
                    repeated_chains.update((src, middle, dst))

    narrow = tx.loc[tx.sum_kzt.between(5000, 6000, inclusive="both"), ["src", "dst", "date"]].copy()
    narrow["date"] = pd.to_datetime(narrow.date).dt.normalize()
    groups = narrow.groupby(["dst", "date"], sort=False).size()
    split_transfers = Counter()
    for (dst, _date), count in groups.items():
        if count >= 3:
            split_transfers[int(dst)] += int(count)
    return cycles, repeated_chains, split_transfers


def add_pattern_counts(frame, graph, tx):
    cycles, chains, splits = pattern_counts(graph, tx)
    counts = (("cycle_count", cycles),
              ("repeat_chain_count", chains),
              ("split_tx_count", splits))
    for column, values in counts:
        frame[column] = frame.gid.map(lambda gid: values[int(gid)]).astype(int)
    return cycles, chains, splits


def robustness(graph, frame, removal_sizes=(5, 10, 20)):
    """Path loss relative to the unchanged graph and role assignments."""
    seeds = sorted(int(gid) for gid in frame.loc[frame.is_seed, "gid"])
    targets = set(int(gid) for gid in frame.loc[frame.role.isin(("consolidator", "coordinator")), "gid"])
    ordered = frame.sort_values(["priority_score", "gid"], ascending=[False, True]).gid.astype(int).tolist()

    def reaching(g):
        available = targets & set(g)
        reached = set()
        for seed in seeds:
            if seed not in g:
                continue
            if set(nx.descendants(g, seed)) & available:
                reached.add(seed)
            elif seed in available and any(nx.has_path(g, neighbor, seed) for neighbor in g.successors(seed)):
                reached.add(seed)  # A directed cycle back to the seed has positive length.
        return reached

    initial = reaching(graph)
    rows = []
    for n in removal_sizes:
        remaining = graph.copy()
        remaining.remove_nodes_from(ordered[:n])
        after = reaching(remaining)
        lost = len(initial - after)
        rows.append({"top_removed": n,
                     "components": nx.number_weakly_connected_components(remaining),
                     "seeds_with_path_before": len(initial),
                     "seeds_with_path_after": len(after),
                     "seeds_lost_path": lost,
                     "share_all_seeds_lost_pct": round(100 * lost / len(seeds), 2) if seeds else 0.0})
    return pd.DataFrame(rows)


def completeness(frame, tx):
    truncated = int(frame.truncated_by_depth.sum())
    lower = pd.to_datetime(tx.date).min().strftime("%Y-%m-%d")
    upper = pd.to_datetime(tx.date).max().strftime("%Y-%m-%d")
    narrow = int(tx.sum_kzt.between(5000, 6000, inclusive="both").sum())
    return ("# Полнота наблюдения\n\n"
            "Выгрузка охватывает {}–{} и только переводы от 5 000 KZT. "
            "Переводы ниже порога, за пределами периода и вне банка отсутствуют. "
            "В диапазоне 5 000–6 000 KZT наблюдаются {} переводов, но ниже 5 000 KZT данных нет.\n\n"
            "У {} узлов на глубине 4 нет наблюдаемого исходящего ребра: это обрыв обхода, "
            "а не доказательство конечного получателя. Входящие переводы seed также неполны.\n\n"
            "## Следующий запрос аналитику\n\n"
            "Запросить у владельца выгрузки исходящие переводы для этих {} gid, "
            "чтобы проверить 5-е колено, а также входящие переводы для {} seed; расширить период до и после "
            "{}–{} и включить операции ниже 5 000 KZT, если они доступны. "
            "Отдельно уточнить, можно ли получить межбанковские переводы. "
            "После дополнения пересчитать достижимость, роли и устойчивость; нынешние оценки "
            "относятся только к наблюдаемой сети.\n".format(
                lower, upper, narrow, truncated, truncated, int(frame.is_seed.sum()), lower, upper))
