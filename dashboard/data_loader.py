"""Read EvalScout's local research artifacts without changing them."""

from collections import defaultdict
import csv
import json
from pathlib import Path
import re

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
SOURCE = ROOT / "data_sources/tau-bench/historical_trajectories"
SOURCES = {
    f"{name}-{domain.lower()}.json": (name, domain)
    for name in ("gpt-4o", "sonnet-35-new")
    for domain in ("Retail", "Airline")
}
POSITIONS = re.compile(r"\b(\d+)(?:\s*[–-]\s*(\d+))?")


def load_json(path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def load_jsonl(path):
    if not path.is_file():
        return []
    try:
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    except json.JSONDecodeError:
        return []


def load_csv(path):
    if not path.is_file():
        return []
    with path.open(encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


@st.cache_resource
def corpus():
    labels = load_json(ROOT / "private/labels.json", {})
    origin = Path(labels.get("provenance", {}).get("trajectory_file", "")).name
    mappings = {
        (origin, row["source_row"]): (trace_id, row["split"].capitalize())
        for trace_id, row in labels.get("traces", {}).items()
    }
    for trace_id, row in load_json(RESULTS / "autonomous_eval/additional_provenance.json", {}).items():
        mappings[(origin, row["source_row"])] = (trace_id, "Additional")
    traces = {}
    for filename, (model, domain) in SOURCES.items():
        for row_number, run in enumerate(load_json(SOURCE / filename, [])):
            trace_id, split = mappings.get((filename, row_number),
                (f"{domain[0]}-{model}-{run['task_id']}-{run['trial']}", "Source archive"))
            messages = [m for m in run["traj"] if m["role"] != "system"]
            user = next((m.get("content") for m in messages if m["role"] == "user"), None)
            reward = run.get("reward")
            traces[trace_id] = {
                "trace_id": trace_id, "split": split, "domain": domain, "model": model,
                "task_id": run["task_id"], "trial": run["trial"], "reward": reward,
                "outcome": {1.0: "Success", 0.0: "Failure"}.get(reward, "Unscored"),
                "messages": messages, "customer": user or "",
                "tool_calls": sum(len((m.get("tool_calls") or [])) for m in messages),
                "source": filename, "source_row": row_number,
            }
    return traces


@st.cache_data(ttl=300, max_entries=32)
def private_goal(source, row):
    """Read a hidden goal only on explicit reviewer request."""
    runs = load_json(SOURCE / source, [])
    if 0 <= row < len(runs):
        return (runs[row].get("info") or {}).get("task", {}).get("instruction")
    return None


def message_indices(text, count):
    output = set()
    for match in POSITIONS.finditer(text):
        first, last = match.groups()
        if 1 <= int(first) <= count:
            output.update(range(int(first), min(int(last or first), count) + 1))
    return sorted(output)


@st.cache_data(ttl=5)
def findings_data():
    audit_rows = load_csv(RESULTS / "assessment/evidence_audit.csv")
    anchor = {(r["finding"], r["trace_id"], r["model_claim"]): r for r in audit_rows}
    tournament = RESULTS / "multi_model"
    tournament_audit = {
        (r["model"], r["finding"], r["trace_id"], r["observation"]): r
        for r in load_csv(tournament / "discovery_evidence_audit.csv")
    }
    runs = []
    full = RESULTS / "full"
    meta = load_json(full / "run_metadata.json", {})
    if meta.get("status") == "completed":
        runs.append((meta["model"], "Initial discovery", full / "researcher_findings.json"))
    for phase in sorted(tournament.glob("*/discovery*/metadata.json")):
        meta = load_json(phase, {})
        if meta.get("status") == "completed":
            runs.append((meta["model"], "Tournament discovery", phase.parent / "findings.json"))
    categories, by_trace = [], defaultdict(list)
    for model, run_name, path in runs:
        results = load_json(path, {})
        for mode in results.get("failure_modes", []):
            criteria = [c for c in results.get("evaluation_criteria", [])
                        if mode["name"] in c["failure_modes_addressed"]]
            item = {**mode, "model": model, "run": run_name, "criteria": criteria}
            categories.append(item)
            for evidence in mode["evidence"]:
                checked = anchor.get((mode["name"], evidence["trace_id"], evidence["observation"]), {})
                record = tournament_audit.get(
                    (model, mode["name"], evidence["trace_id"], evidence["observation"]), {}
                ) if run_name == "Tournament discovery" else {}
                by_trace[evidence["trace_id"]].append({
                    "finding": item, "observation": evidence["observation"],
                    "positions": record.get("corrected_positions") or checked.get("message_positions_1_based", ""),
                    "review": (f"{record['verdict']} · model-assisted audit" if record else
                               checked.get("assessment", "Researcher claim · review unavailable")),
                    "verified_evidence": record.get("review_note") or checked.get("independent_evidence", ""),
                })
    return categories, dict(by_trace)


@st.cache_data(ttl=5)
def evaluation_data():
    base = RESULTS / "autonomous_eval"
    rows = load_csv(base / "comparison.csv")
    inputs = {}
    plans = {}
    for row in rows:
        trace_id = row["trace_id"]
        inputs[trace_id] = {
            "Verified state": row["verified_state"], "Sol · autonomous": row["sol"],
            "Codex · frozen": row["codex"], "Rejected-call baseline": row["rejected_call_baseline"],
        }
        plans[trace_id] = {
            "Sol · full trace": row["sol_planning"],
            "Earlier planning review": row["previous_planning_review"] or "Unreviewed",
        }
    specifics = {r["trace_id"]: r["verified_evidence"] for r in rows}
    details = defaultdict(dict)
    for row in load_jsonl(base / "generated_stdout.jsonl"):
        details[row["trace_id"]]["Sol · autonomous"] = row.get("evidence", [])
    statuses = {"Sol · autonomous": load_json(base / "execution_metadata.json", {}).get("returncode") == 0}
    for path in sorted((RESULTS / "multi_model").glob("*/evaluation/metadata.json")):
        label = path.parent.parent.name + " · tournament"
        meta = load_json(path, {})
        statuses[label] = meta.get("status") == "completed"
        if statuses[label]:
            for row in load_jsonl(path.parent / "predictions.jsonl"):
                inputs.setdefault(row["trace_id"], {})[label] = row["state_prediction"]
                details[row["trace_id"]][label] = row.get("evidence", [])
            for row in load_csv(path.parent / "planning.csv"):
                plans.setdefault(row["trace_id"], {})[label + " · action prefix"] = row["action_prediction"]
                plans[row["trace_id"]][label + " · immediate result"] = row["result_prediction"]
                plans[row["trace_id"]]["Provisional prefix label"] = row["label"]
    return inputs, plans, specifics, statuses, dict(details)


def trace_timeline(messages):
    states = {}
    for index, message in enumerate(messages, 1):
        if message["role"] == "tool":
            content = message.get("content")
            if isinstance(content, str) and content.startswith("Error:"):
                yield index, "Tool error", content
                continue
            try:
                result = json.loads(content or "")
            except (ValueError, TypeError):
                continue
            if isinstance(result, dict) and result.get("order_id") and result.get("status"):
                order_id, status = result["order_id"], result["status"]
                previous = states.get(order_id)
                if previous != status:
                    yield index, "State transition" if previous else "State observed", (
                        f"{order_id} · {previous} → {status}" if previous else f"{order_id} · {status}"
                    )
                states[order_id] = status
        for call in (message.get("tool_calls") or []):
            function = call.get("function", {})
            name = function.get("name", "")
            if name.startswith(("modify_", "exchange_", "return_", "cancel_", "transfer_")):
                yield index, "Action attempt", name
