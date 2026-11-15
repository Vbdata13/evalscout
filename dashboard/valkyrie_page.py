"""Local read-only view of the EvalScout runs in the connected Valkyrie account."""
import json
import re
import shutil
import subprocess
from uuid import UUID

import streamlit as st


def valkyrie(*arguments):
    cli = shutil.which("valkyrie")
    if cli is None:
        raise ValueError("Install the Valkyrie CLI to view live runs.")
    try:
        result = subprocess.run([cli, "run", *arguments], capture_output=True,
                                check=False, timeout=8, text=True)
    except subprocess.TimeoutExpired as error:
        raise ValueError("Valkyrie did not respond. The next refresh will retry.") from error
    if result.returncode:
        raise ValueError("Valkyrie is unavailable. Check the local CLI connection.")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise ValueError("Valkyrie returned an unreadable response.") from error


@st.fragment(run_every="10s")
def live_runs():
    try:
        runs = valkyrie("list", "--benchmark-name", "evalscout", "--all", "--format", "json")["benchmarks"]
    except ValueError as error:
        st.warning(str(error))
        return
    if not runs:
        st.info("There are no EvalScout runs in the connected organization.")
        return

    rows = [{"Harness": r["agent_name"], "Model": r["model"], "Status": r["status"].replace("_", " "),
             "Phase counts": ", ".join(f"{key}: {count}" for key, count in r["task_state_counts"].items()),
             "Score / 100": r["final_score"], "Run ID": r["id"]} for r in runs]
    st.dataframe(rows, hide_index=True, width="stretch")
    ids = {r["id"]: f"{r['agent_name']} · {r['id'][:8]} · {r['status']}" for r in runs}
    chosen = st.selectbox("Inspect a run", ids, format_func=ids.get)
    try:
        task = valkyrie("task", str(UUID(chosen)), "evalscout-retail", "--format", "json")
    except ValueError as error:
        st.warning(str(error))
        return
    st.metric("Task phase", task["status"].replace("_", " ").title())
    if task.get("failure_category"):
        st.caption(f"Failure category · {task['failure_category']}")
    if error := task.get("error_message"):
        safe = re.sub(r"(?i)(?:sk-|Bearer )[A-Za-z0-9_.*-]+", "[redacted]", error)
        st.error(safe[:700])
    result = task.get("evaluation_result")
    if isinstance(result, dict):
        st.json(result, expanded=False)
    st.code(f"valkyrie run fetch {chosen} --connect", language="sh")


def valkyrie_page():
    st.title("Valkyrie Runs")
    st.caption("Live status for the EvalScout benchmark · updates every 10 seconds")
    live_runs()
