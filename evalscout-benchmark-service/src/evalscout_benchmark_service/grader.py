"""Deterministic, evidence-anchored score; private references live outside source."""
from __future__ import annotations

import json
import re


def parse_traces(data):
    return {item["trace_id"]: item["messages"] for item in map(json.loads, data.splitlines())}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def valid_events(events, size):
    return (isinstance(events, list) and len(events) <= size and
            all(type(i) is int and 1 <= i <= size for i in events) and len(set(events)) == len(events))


def parse_submission(raw, development):
    payload = json.loads(raw)
    categories = payload.get("categories") if isinstance(payload, dict) else None
    require(isinstance(categories, list) and 1 <= len(categories) <= 20, "Invalid category count")
    result = {}
    for item in categories:
        require(isinstance(item, dict), "Invalid category")
        key = item.get("id")
        require(isinstance(key, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,32}", key)
                and key not in result, "Invalid or repeated category ID")
        for field in ("name", "definition"):
            value = item.get(field)
            require(isinstance(value, str) and 0 < len(value.strip()) <= 2000, "Invalid category text")
        evidence = item.get("evidence")
        require(isinstance(evidence, list) and 1 <= len(evidence) <= 20, "Invalid evidence list")
        for claim in evidence:
            require(isinstance(claim, dict) and isinstance(claim.get("trace_id"), str)
                    and claim["trace_id"] in development, "Evidence must cite a development trace")
            events = claim.get("events")
            require(valid_events(events, len(development[claim["trace_id"]])) and bool(events),
                    "Invalid discovery evidence positions")
            observation = claim.get("observation")
            require(isinstance(observation, str) and 0 < len(observation.strip()) <= 2500,
                    "Invalid evidence description")
            require(claim.get("severity") in ("critical", "major", "minor", "unsure"), "Invalid severity")
        result[key] = item
    return result


def parse_predictions(raw, traces, categories):
    records = [json.loads(line) for line in raw.splitlines()]
    require(len(records) == len(traces), "Prediction count mismatch")
    predictions = {}
    for (trace_id, messages), record in zip(traces.items(), records, strict=True):
        require(isinstance(record, dict) and record.get("trace_id") == trace_id, "Prediction ID mismatch")
        rows = record.get("predictions")
        require(isinstance(rows, list) and len(rows) == len(categories), "Missing or extra predictions")
        by_category = {}
        for row in rows:
            require(isinstance(row, dict) and isinstance(row.get("category_id"), str), "Invalid prediction")
            key = row["category_id"]
            require(key in categories and key not in by_category, "Unknown or duplicate prediction category")
            verdict, events = row.get("verdict"), row.get("events")
            require(verdict in ("present", "absent", "uncertain")
                    and valid_events(events, len(messages))
                    and (verdict != "present" or bool(events)), "Invalid prediction verdict or evidence")
            by_category[key] = row
        predictions[trace_id] = by_category
    return predictions


def score(categories, predictions, reference, recommendations_valid):
    patterns = reference["concepts"]
    declarations = {key: item["name"] + "\n" + item["definition"] for key, item in categories.items()}
    matches, claimed_pairs, contradicted = {}, set(), set()
    for key, item in categories.items():
        for claim in item["evidence"]:
            identity = (claim["trace_id"], tuple(sorted(claim["events"])), claim["observation"])
            claimed_pairs.add(identity)
            cited = set(claim["events"])
            text = declarations[key] + "\n" + claim["observation"]
            for anchor in reference["discovery"] + reference["negative_discovery"]:
                if (claim["trace_id"] != anchor["trace_id"] or not cited.intersection(anchor["match_events"])
                        or not re.search(patterns[anchor["concept"]], text, re.I)):
                    continue
                if "anchor_id" not in anchor:
                    contradicted.add(identity)
                    continue
                exact = claim["severity"] == anchor["severity"].casefold()
                previous = matches.get(anchor["anchor_id"], (False, anchor["concept"]))
                matches[anchor["anchor_id"]] = (previous[0] or exact, anchor["concept"])
    # A blanket assertion is non-selective, irrespective of unobserved labels.
    blanket = set()
    if predictions:
        blanket = {key for key in categories if all(row[key]["verdict"] == "present"
                                                   for row in predictions.values())}
    hits, negative_flags = set(), set()
    if predictions:
        for anchor in reference["execution"] + reference["negative_execution"]:
            for key, prediction in predictions[anchor["trace_id"]].items():
                if (prediction["verdict"] == "present" and
                        set(prediction["events"]).intersection(anchor["match_events"]) and
                        re.search(patterns[anchor["concept"]], declarations[key], re.I)):
                    if "anchor_id" not in anchor:
                        negative_flags.add((anchor["trace_id"], anchor["concept"]))
                    elif key not in blanket:
                        hits.add(anchor["anchor_id"])
    discovery = reference["discovery"]
    execution = reference["execution"]
    distinct = len({concept for _, concept in matches.values()})
    total_distinct = len({row["concept"] for row in discovery})
    dev_critical = {row["anchor_id"] for row in discovery if row["severity"].casefold() == "critical"}
    test_critical = {row["anchor_id"] for row in execution if row["severity"].casefold() == "critical"}
    parts = {
        "discovery": 25 * len(matches) / len(discovery),
        "breadth": 15 * distinct / total_distinct,
        "severity": 10 * sum(exact for exact, _ in matches.values()) / len(discovery),
        "valid_execution": 10 if predictions is not None else 0,
        "unseen_detection": 30 * len(hits) / len(execution),
        "recommendations_present": 5 if recommendations_valid else 0,
        "selectivity": 5 if predictions and not blanket and
                       any(item["verdict"] == "present" for row in predictions.values() for item in row.values()) else 0,
        "verified_contradictions": -min(15, 3 * (len(contradicted) + len(negative_flags))),
    }
    value = round(max(0, sum(parts.values())), 2)
    guardrail_missed = len(dev_critical - matches.keys()) + len(test_critical - hits)
    if guardrail_missed:
        value = min(79, value)
    return {"score": value, "resolved": predictions is not None and value >= 70 and not guardrail_missed,
            "components": parts, "discovery_matches": len(matches), "discovery_total": len(discovery),
            "verified_unseen_matches": len(hits), "verified_unseen_total": len(execution),
            "verified_contradictions": len(contradicted) + len(negative_flags),
            "discovery_claims": len(claimed_pairs), "blanket_categories": len(blanket),
            "critical_misses": guardrail_missed, "unsupported_unlabeled_scoring": "unmeasured",
            "global_precision": None}
