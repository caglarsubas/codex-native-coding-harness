"""Bounded native response counters, separate from legacy context-display counters.

Only numeric usage and exact identity metadata enter this read-only calculation.
It neither repairs logs nor grants authority, and never adds the two counter streams.
"""
from .core import canonical, require
from .observations import TOKENS, token_vector


def record(value, identity):
    if not isinstance(value, dict):
        return None
    if value.get("thread_id") != identity or value.get("session_id") != identity:
        return None
    if not all(isinstance(value.get(k), str) and 0 < len(value[k]) <= 256
               for k in ("response_id", "turn_id", "root_turn_id")):
        return None
    vectors = [token_vector(value.get(k)) for k in ("thread_token_usage", "usage", "turn_token_usage")]
    if any(v is None for v in vectors):
        return None
    # Cache writes, when reported, are a subset, never another additive charge.
    for name in ("thread_token_usage", "usage", "turn_token_usage"):
        write = value[name].get("cache_write_input_tokens", 0)
        if type(write) is not int or not 0 <= write <= value[name]["input_tokens"]:
            return None
    total, usage, turn = vectors
    if any(usage[k] > turn[k] or turn[k] > total[k] for k in TOKENS):
        return None
    return {"response": value["response_id"], "turn": value["turn_id"],
            "rootTurn": value["root_turn_id"], "total": total, "last": usage,
            "turnTotal": turn,
            "cacheWrites": [value[name].get("cache_write_input_tokens", 0)
                            for name in ("thread_token_usage", "usage", "turn_token_usage")]}


def session_usage(rows, legacy, compactions, identity, start, brain, session_starts, gaps):
    """Require a consistent response journal; corrupt new records never fall back."""
    samples, seen, invalid, compact = [], {}, [], {}
    for at, value in rows:
        item = record(value, identity)
        if at is None or item is None:
            invalid.append(at)
            if at is None or not brain or at >= start:
                gaps.append("invalid_response_usage_record")
            # Keep known same-session cumulative consumption even with a bad
            # call/turn breakdown. Never retain foreign counters as our usage.
            total = token_vector(value.get("thread_token_usage")) if isinstance(value, dict) else None
            if at is not None and total and value.get("thread_id") == identity and value.get("session_id") == identity:
                samples.append((at, total, None, None))
            continue
        fingerprint = canonical(item)
        previous = seen.get(item["response"])
        if previous:
            if previous[1] != fingerprint:
                invalid.append(at)
                if not brain or at >= start:
                    gaps.append("conflicting_token_response")
                samples.append((at, item["total"], None, None))
            elif at < previous[0]:
                # Duplicate archive/continuation bytes cannot renew sample time.
                samples.remove(previous[2])
                sample = (at, item["total"], item["last"], item)
                samples.append(sample)
                seen[item["response"]] = (at, fingerprint, sample)
            continue
        sample = (at, item["total"], item["last"], item)
        samples.append(sample)
        seen[item["response"]] = (at, fingerprint, sample)
    for at, response, value in compactions:
        item = record(value, identity)
        source = seen.get(response) if isinstance(response, str) else None
        if at is None or not item or item["response"] != response or not source or source[0] > at or source[1] != canonical(item):
            if at is None or not brain or at >= start:
                gaps.append("unreconciled_compaction_usage")
            continue
        compact[response] = (min(at, compact.get(response, (at,))[0]), item)
    ordered = sorted(samples, key=lambda e: (e[0], e[1]["total_tokens"]))
    require(ordered, "No valid native response counters for registered task")
    zero = dict.fromkeys(TOKENS, 0)
    before = [e for e in ordered if e[0] < start] if brain else []
    if before:
        baseline = before[-1][1]
        if any(at is None or before[-1][0] <= at < start for at in invalid):
            gaps.append("invalid_response_usage_record")
    else:
        require((not brain or session_starts and min(session_starts) >= start)
                and ordered[0][1] == ordered[0][2],
                "Native response usage prefix/baseline missing")
        baseline = zero
    selected = [e for e in ordered if e[0] >= start] if brain else ordered
    require(selected, "No native response sample inside the measured interval")
    high_water, previous, previous_turn = dict(baseline), before[-1] if before else None, {}
    if previous and previous[3]:
        previous_turn[previous[3]["turn"]] = previous[3]["turnTotal"]
    for sample in selected:
        at, total, usage, item = sample
        if any(total[k] < high_water[k] for k in TOKENS):
            gaps.append("counter_reset_or_regression")
        if previous and (usage is None or any(total[k] - previous[1][k] != usage[k] for k in TOKENS)):
            gaps.append("response_usage_discontinuity")
        if item:
            prior_turn = previous_turn.get(item["turn"])
            if prior_turn and any(item["turnTotal"][k] - prior_turn[k] != usage[k] for k in TOKENS):
                gaps.append("response_usage_discontinuity")
            previous_turn[item["turn"]] = item["turnTotal"]
        high_water = {k: max(high_water[k], total[k]) for k in TOKENS}
        previous = sample

    # Legacy counters describe model-context display, omitting the separately
    # recorded compaction response. Reconcile exact paired records, not merely
    # a similar total or a conveniently adjacent compaction marker.
    index, latest, compact_index = 0, None, 0
    compact_ordered = sorted(compact.values(), key=lambda e: e[0])
    offsets = dict(zero)
    for at, info in sorted(legacy, key=lambda e: e[0] if e[0] is not None else -1):
        if at is None:
            gaps.append("invalid_token_record")
            continue
        while index < len(ordered) and ordered[index][0] <= at:
            latest = ordered[index]; index += 1
        while compact_index < len(compact_ordered) and compact_ordered[compact_index][0] <= at:
            usage = compact_ordered[compact_index][1]["last"]
            offsets = {k: offsets[k] + usage[k] for k in TOKENS}
            compact_index += 1
        if brain and at < start:
            continue
        total, last = token_vector(info.get("total_token_usage")), token_vector(info.get("last_token_usage"))
        if not total:
            gaps.append("invalid_token_record")
            continue
        # An unpaired newer display sample is a gap, not a refund of its known
        # cumulative amount. Align only proven compaction offsets; never sum
        # whole independent streams. The report remains gapped until reconciled.
        high_water = {k: max(high_water[k], total[k] + offsets[k]) for k in TOKENS}
        item = latest[3] if latest else None
        paired = item and all(item["total"][k] - offsets[k] == total[k] for k in TOKENS)
        raw_last, window = info.get("last_token_usage"), info.get("model_context_window")
        context_estimate = (item and item["response"] in compact and compact[item["response"]][0] <= at
                            and isinstance(raw_last, dict) and type(window) is int and window > 0
                            and type(raw_last.get("total_tokens")) is int and 0 < raw_last["total_tokens"] <= window
                            and all(type(raw_last.get(k)) is int and raw_last[k] == 0 for k in TOKENS if k != "total_tokens")
                            and type(raw_last.get("cache_write_input_tokens", 0)) is int
                            and raw_last.get("cache_write_input_tokens", 0) == 0)
        call_matches = item is not None and last == item["last"]
        if not paired or not (call_matches or context_estimate):
            gaps.append("unmatched_legacy_token_record" if last else "invalid_token_record")

    compaction_items = [s[3] for s in selected if s[3] and s[3]["response"] in compact]
    last = selected[-1]
    return {"sessionId": identity, "tokens": {k: max(0, high_water[k] - baseline[k]) for k in TOKENS},
            "sampleAt": last[0], "calls": len({s[3]["response"] for s in selected if s[3]}),
            "lastInputTokens": last[2]["input_tokens"] if last[2] else None,
            "gaps": sorted(set(gaps)), "counterSource": "native_response_usage_v1",
            "compactionCalls": len(compaction_items),
            "compactionTokens": {k: sum(i["last"][k] for i in compaction_items) for k in TOKENS}}
