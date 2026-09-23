"""Deterministic July 2026 transaction timing signals (Python 3.9)."""

from collections import Counter, defaultdict
from datetime import timedelta

import pandas as pd


def _short_date(day):
    return day.strftime("%d.%m")


def _day_word(count):
    if count % 100 in (11, 12, 13, 14):
        return "дней"
    if count % 10 == 1:
        return "день"
    if count % 10 in (2, 3, 4):
        return "дня"
    return "дней"


def compute_temporal(nodes, tx):
    incoming_days = defaultdict(set)
    outgoing_rows = defaultdict(list)
    sync = defaultdict(lambda: {"payers": set(), "sum": 0.0})
    activity = defaultdict(Counter)
    for row in tx.itertuples(index=False):
        day = pd.Timestamp(row.date).date()
        src, dst, amount = int(row.src), int(row.dst), float(row.sum_kzt)
        incoming_days[dst].add(day)
        outgoing_rows[src].append((day, amount))
        sync[(dst, day)]["payers"].add(src)
        sync[(dst, day)]["sum"] += amount
        activity[src][day] += 1
        activity[dst][day] += 1

    sync_by_gid = defaultdict(list)
    for (gid, day), item in sync.items():
        if len(item["payers"]) >= 2:
            sync_by_gid[gid].append((day, len(item["payers"]), item["sum"]))

    records = []
    for gid in nodes.gid:
        gid = int(gid)
        fast = []
        for day, amount in sorted(outgoing_rows[gid]):
            matches = [day - timedelta(days=days) for days in (1, 2)
                       if day - timedelta(days=days) in incoming_days[gid]]
            if matches:
                fast.append((min(matches), day, amount))
        sync_days = sync_by_gid[gid]
        peak_sync = sorted(sync_days, key=lambda item: (-item[1], item[0]))[0] if sync_days else None
        counts = activity[gid]
        mean_daily = sum(counts.values()) / 31.0
        burst_days = [(day, count) for day, count in counts.items()
                      if count >= 3 and count >= 3 * mean_daily]
        peak_burst = sorted(burst_days, key=lambda item: (-item[1], item[0]))[0] if burst_days else None

        details, brief = [], []
        if fast:
            first = fast[0]
            details.append("Быстрый транзит: {} исходящих переводов через 1–2 дня после входа; "
                           "пример {}→{}, исходящая сумма {:.2f} KZT.".format(
                               len(fast), first[0], first[1], sum(item[2] for item in fast)))
            brief.append("1–2д: {} исх. {}→{}".format(len(fast), _short_date(first[0]), _short_date(first[1])))
        if peak_sync:
            details.append("Синхронные входы: {} {}; максимум {} плательщика {} "
                           "на {:.2f} KZT.".format(len(sync_days), _day_word(len(sync_days)),
                                                   peak_sync[1], peak_sync[0], peak_sync[2]))
            brief.append("синхр.: {} пл. {}".format(peak_sync[1], _short_date(peak_sync[0])))
        if peak_burst:
            details.append("Всплеск: {} {}; максимум {} операций {} при среднем {:.2f} в день за июль.".format(
                len(burst_days), _day_word(len(burst_days)), peak_burst[1], peak_burst[0], mean_daily))
            brief.append("вспл.: {} оп. {} (ср.{:.1f}/д)".format(
                peak_burst[1], _short_date(peak_burst[0]), mean_daily))
        records.append({
            "gid": gid, "fast_out_count": len(fast), "fast_out_kzt": round(sum(item[2] for item in fast), 2),
            "fast_in_date": str(fast[0][0]) if fast else "", "fast_out_date": str(fast[0][1]) if fast else "",
            "sync_days": len(sync_days), "sync_max_payers": peak_sync[1] if peak_sync else 0,
            "sync_date": str(peak_sync[0]) if peak_sync else "", "sync_kzt": round(peak_sync[2], 2) if peak_sync else 0.0,
            "burst_days": len(burst_days), "burst_max_count": peak_burst[1] if peak_burst else 0,
            "burst_date": str(peak_burst[0]) if peak_burst else "", "burst_daily_mean": round(mean_daily, 2),
            "temporal_evidence": " ".join(details), "temporal_brief": "; ".join(brief),
        })
    return pd.DataFrame(records)
