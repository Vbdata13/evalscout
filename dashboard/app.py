"""EvalScout local research dashboard."""

from collections import Counter

import pandas as pd
import streamlit as st

from components import (
    claim_indices, evaluator_metrics, ratio, render_claims, render_messages, render_timeline, render_value, status_style, trace_link,
)
from data_loader import (
    RESULTS, corpus, evaluation_data, findings_data, load_csv, private_goal,
)

from review_page import review_page
from valkyrie_page import valkyrie_page

PAGES = ["Overview", "Trace Explorer", "Failure Modes", "Model Comparison", "Human Annotation", "Valkyrie Runs"]
st.set_page_config(page_title="EvalScout | Research dashboard", page_icon="🔎", layout="wide")
st.html("""<style>
[data-testid="stAppViewContainer"] { background: #f8fafc; }
[data-testid="stSidebar"] { background: #edf2f8; }
[data-testid="stMetric"] { background: #fff; border: 1px solid #dbe5f0;
    border-radius: 12px; padding: 14px 16px; }
[data-testid="stMainBlockContainer"] { padding-top: 2.6rem; }
[data-testid="stExpander"] { background: #fff; }
</style>""")

st.sidebar.title("EvalScout")
st.sidebar.caption("Local research dashboard")
requested_page = st.query_params.get("page", "Overview")
page = st.sidebar.radio("Page", PAGES, index=PAGES.index(requested_page) if requested_page in PAGES else 0)
if page == "Human Annotation":
    review_page()
    st.stop()
if page == "Valkyrie Runs":
    valkyrie_page()
    st.stop()

traces = corpus()
categories, claims = findings_data()
predictions, plans, verified_evidence, executions, evaluator_evidence = evaluation_data()
if not traces:
    st.error("No source trajectories were found. Check the local τ-bench checkout.")
    st.stop()

with st.sidebar.expander("Filters", expanded=True):
    domain = st.multiselect("Domain", sorted({t["domain"] for t in traces.values()}))
    split = st.multiselect("Split", ["Discovery", "Heldout", "Additional", "Source archive"])
    outcome = st.multiselect("Task outcome", sorted({t["outcome"] for t in traces.values()}))
    model = st.multiselect("Source agent model", sorted({t["model"] for t in traces.values()}))
    researcher = st.multiselect("Researcher model", sorted({f["model"] for f in categories}))
    failure = st.multiselect("Failure mode", sorted({f["name"] for f in categories}))


def claim_visible(finding):
    return (not researcher or finding["model"] in researcher) and (
        not failure or finding["name"] in failure
    )


def is_visible(trace):
    values = ((domain, "domain"), (split, "split"), (outcome, "outcome"), (model, "model"))
    if any(options and trace[field] not in options for options, field in values):
        return False
    if failure or (researcher and page != "Model Comparison"):
        return any(claim_visible(c["finding"]) for c in claims.get(trace["trace_id"], []))
    return True


visible = {key: trace for key, trace in traces.items() if is_visible(trace)}
st.sidebar.caption(f"{len(visible):,} trajectories match")
st.sidebar.button("Refresh experiment results", on_click=st.cache_data.clear, width="stretch")


def metrics(values):
    for column, (label, value) in zip(st.columns(len(values)), values):
        column.metric(label, value)


def overview():
    st.title("Research overview")
    st.caption("Sierra execution traces and EvalScout’s evidence-backed results")
    tasks = {(t["domain"], t["task_id"]) for t in visible.values()}
    outcomes = Counter(t["outcome"] for t in visible.values())
    cited_modes = {(c["finding"]["model"], c["finding"]["name"])
                   for k in visible for c in claims.get(k, []) if claim_visible(c["finding"])}
    metrics([("Distinct source tasks", f"{len(tasks):,}"), ("Trajectories", f"{len(visible):,}"),
             ("Successful runs", f"{outcomes['Success']:,}"), ("Failed runs", f"{outcomes['Failure']:,}")])
    st.subheader("Source coverage")
    domains = sorted({t["domain"] for t in visible.values()})
    counts = Counter((t["domain"], t["split"]) for t in visible.values())
    table = [
        {"Domain": name, "Distinct tasks": sum(d == name for d, _ in tasks),
         **{key: counts[name, key] for key in ("Discovery", "Heldout", "Additional", "Source archive")}}
        for name in domains
    ]
    if table:
        st.dataframe(pd.DataFrame(table), width="stretch", hide_index=True)
    st.caption("Source archive excludes trajectories already assigned to an EvalScout split. "
               "Task IDs are scoped by domain, so multiple trials and models can share a task ID. "
               "The discovery and evaluation experiments use retail only.")
    st.subheader("Research results")
    verified_models = {item["model"] for item in categories}
    eval_subset = {k: v for k, v in predictions.items() if k in visible}
    prior = evaluator_metrics(eval_subset, "Sol · autonomous")
    metrics([("Researcher models verified", len(verified_models)),
             ("Cited model/category pairs", len(cited_modes)),
             ("Sol eval coverage", ratio(prior["n"] - prior["abstain"], prior["n"])),
             ("Sol abstentions", prior["abstain"]),
             ("Confirmed state violations", prior["tp"] + prior["fn"])])
    st.markdown(
        f"[Explore ES-015, a return that blocked an exchange]({trace_link('ES-015')})")
    with st.expander("Methodology and limits"):
        st.write("Sierra reward reports overall task success. The eligibility evaluator uses separately "
                 "reviewed order-state labels. Coverage is the share of labeled traces receiving a "
                 "decision. Abstentions are reported separately from errors. Findings may overlap "
                 "across runs. The evaluator sample is small and includes model-assisted adjudication.")


def find_trace():
    st.title("Trace Explorer")
    query = st.text_input("Search trajectories", placeholder="Trace ID, task ID, customer request, tool, or researcher finding")
    terms = query.casefold().split()
    matches = []
    for k, t in visible.items():
        base = f"{k} {t['task_id']} {t['customer']} {' '.join(c['finding']['name'] for c in claims.get(k, []))}"
        if terms and not all(term in base.casefold() for term in terms):
            text = base + " " + " ".join(str(m.get("content") or "") + " " + " ".join(
                c.get("function", {}).get("name", "") for c in (m.get("tool_calls") or [])
            ) for m in t["messages"])
            if not all(term in text.casefold() for term in terms):
                continue
        matches.append(k)
    matches.sort(key=lambda k: (visible[k]["split"] == "Source archive", k))
    if not matches:
        st.info("No matching trajectories. Change the search or filters.")
        return
    requested = st.query_params.get("trace", "ES-015")
    focus = st.query_params.get("event", "")
    rows = []
    for k in matches:
        t = traces[k]
        names = sorted({c["finding"]["name"] for c in claims.get(k, []) if claim_visible(c["finding"])})
        rows.append({
            "Trace": k, "Task": t["task_id"], "Domain": t["domain"], "Split": t["split"],
            "Source agent": t["model"], "Customer opening": t["customer"],
            "Outcome": t["outcome"], "Reward": t["reward"], "Messages": len(t["messages"]),
            "Tool calls": t["tool_calls"], "Failure modes": " · ".join(names),
            "Verified state": predictions.get(k, {}).get("Verified state", "—"),
            "Evaluator predictions": " · ".join(f"{name}: {value}" for name, value in predictions.get(k, {}).items()
                                               if name != "Verified state"),
        })
    selection = st.dataframe(pd.DataFrame(rows), width="stretch", height=270, hide_index=True,
                             on_select="rerun", selection_mode="single-row",
                             key="trace_table_" + repr((query, domain, split, outcome, model, researcher, failure)))
    picked = selection.selection.rows
    default = requested if requested in matches else matches[0]
    if picked:
        default = rows[picked[0]]["Trace"]
    selected = st.selectbox("Trace to inspect", matches, index=matches.index(default),
                            key=f"trace_selector_{default}")
    trace = traces[selected]
    st.subheader(f"{selected} · {trace['domain']} task {trace['task_id']}")
    st.caption(f"{trace['split']} · {trace['model']} · trial {trace['trial']} · "
               f"Sierra task outcome {trace['outcome'].lower()}")
    st.markdown("**Visible customer request**")
    customer_messages = [(i, m["content"]) for i, m in enumerate(trace["messages"], 1)
                         if m["role"] == "user" and m.get("content")]
    if customer_messages:
        st.text(customer_messages[0][1])
        with st.expander("All customer turns"):
            for i, content in customer_messages:
                st.caption(f"m{i:02}")
                st.text(content)
    else:
        st.info("No customer message was recorded.")
    with st.expander("Local reviewer only · hidden benchmark goal"):
        if st.checkbox("Reveal private goal for this trace", key=f"review_{selected}"):
            goal = private_goal(trace["source"], trace["source_row"])
            if goal:
                st.text(goal)
            else:
                st.info("No private goal was recorded.")
        st.caption("The goal is read from the local source only after you enable this control.")
    if selected in predictions:
        st.markdown("**Order-state evaluator decisions**")
        st.dataframe(pd.DataFrame([predictions[selected]]).style.map(status_style), hide_index=True, width="stretch")
        st.caption(verified_evidence.get(selected, ""))
        if selected in evaluator_evidence:
            with st.expander("Evaluator evidence"):
                for name, observations in evaluator_evidence[selected].items():
                    st.caption(name)
                    for item in observations:
                        st.text(item)
    trace_claims = [c for c in claims.get(selected, []) if claim_visible(c["finding"])]
    cited = {i for claim in trace_claims for i in claim_indices(claim, len(trace["messages"]))}
    event = int(focus) if focus.isdecimal() and selected == requested else None
    if event:
        st.info(f"Evidence link opened at message m{event:02}. That event is marked in the conversation.")
    tabs = st.tabs(["Conversation", "State timeline", "Failure evidence"])
    with tabs[0]:
        if event and 1 <= event <= len(trace["messages"]):
            with st.expander(f"Jump target · m{event:02}", expanded=True):
                render_value(trace["messages"][event - 1])
        render_messages(trace["messages"], cited, event)
    with tabs[1]:
        render_timeline(trace)
    with tabs[2]:
        render_claims(trace, trace_claims)


def failure_modes():
    st.title("Failure Modes")
    st.caption("Original researcher language and the evidence behind each claim")
    relevant = [f for f in categories if claim_visible(f)
                and any(e["trace_id"] in visible for e in f["evidence"])]
    if not relevant:
        st.info("No findings match these filters.")
        return
    rows = [{
        "Failure mode": f["name"], "Model": f["model"], "Run": f["run"], "Severity": f["severity"],
        "Traces": ", ".join(sorted({e["trace_id"] for e in f["evidence"]})),
        "Impact": f["user_impact"],
    } for f in relevant]
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    group_rows = load_csv(RESULTS / "multi_model/discovery_coverage.csv")
    if group_rows:
        groups = {}
        for row in group_rows:
            if row["covered"] == "yes" and (not researcher or row["model"] in researcher):
                groups.setdefault(row["anchor"], set()).add(row["model"])
        st.subheader("Shared reference cases")
        st.dataframe(pd.DataFrame([{"Anchor": k, "Models": ", ".join(sorted(v)),
                                    "Overlap": "Multiple models" if len(v) > 1 else "One model"}
                                   for k, v in groups.items()]), hide_index=True, width="stretch")
    else:
        st.caption("Cross-model grouping appears once the shared case audit is available.")
    chosen = st.selectbox("Inspect a finding", range(len(relevant)),
                          format_func=lambda i: f"{relevant[i]['model']} · {relevant[i]['name']}"
                          + f" · {relevant[i]['run']}")
    f = relevant[chosen]
    st.text(f["user_impact"])
    st.caption("Researcher’s cause assessment")
    st.text(f["root_cause_assessment"])
    for e in f["evidence"]:
        st.markdown(f"[{e['trace_id']}]({trace_link(e['trace_id'])})")
        st.text(e["observation"])
    st.subheader("Proposed evaluations")
    for criterion in f["criteria"]:
        with st.expander(criterion["name"]):
            st.text(criterion["evidence_to_inspect"])
            st.caption("Violation")
            st.text(criterion["violation"])
            st.caption("Insufficient evidence")
            st.text(criterion["insufficient_evidence"])
    if "eligib" in (f["name"] + " ".join(c["name"] for c in f["criteria"])).lower():
        st.info("The frozen order-eligibility proposal was tested on 28 traces. "
                "See Model Comparison for state-check validation and planning abstentions.")


def model_comparison():
    st.title("Model Comparison")
    st.caption("Discovery evidence, executable state checks, and prospective planning")
    tabs = st.tabs(["State evaluator", "Discovery", "Prospective planning"])
    def includes(column):
        return not researcher or not column.endswith(" · tournament") or column.split(" · ")[0] in researcher

    matrix = {k: {name: value for name, value in v.items() if includes(name)}
              for k, v in predictions.items() if k in visible}
    with tabs[0]:
        if not matrix:
            st.info("No state predictions match these filters.")
        else:
            available = sorted({key for row in matrix.values() for key in row if key != "Verified state"})
            summary = []
            for name in available:
                if researcher and name.endswith(" · tournament") and name.split(" · ")[0] not in researcher:
                    continue
                m = evaluator_metrics(matrix, name)
                summary.append({"Evaluator": name, "Execution": "Passed" if executions.get(name) else
                                ("Baseline" if "baseline" in name else "Recorded"),
                                "TP": m["tp"], "FP": m["fp"], "FN": m["fn"], "TN": m["tn"],
                                "Abstentions": m["abstain"], "Coverage": ratio(m["n"] - m["abstain"], m["n"]),
                                "Precision": ratio(m["tp"], m["tp"] + m["fp"]),
                                "Recall on classified positives": ratio(m["tp"], m["tp"] + m["fn"])})
            st.dataframe(pd.DataFrame(summary), hide_index=True, width="stretch")
            st.caption("Abstentions are separate. Reward is never used as a state label.")
            differences = st.toggle("Show only disagreements", value=False)
            rows = [{"Trace": k, **v} for k, v in matrix.items()
                    if not differences or len(set(v.values())) > 1]
            show_comparison_rows(rows, "state")
        failures = [name for name, ok in executions.items() if not ok]
        if failures:
            st.warning("Evaluator execution unsuccessful or incomplete: " + ", ".join(failures))
    with tabs[1]:
        audited = load_csv(RESULTS / "multi_model/leaderboard.csv")
        if audited:
            st.dataframe(pd.DataFrame([r for r in audited if not researcher or r["Model"] in researcher]),
                         hide_index=True, width="stretch")
            with st.expander("Independent discovery audit and missed cases"):
                report = RESULTS / "multi_model/discovery_comparison.md"
                if report.exists():
                    # Show this local report's content without exposing private source metadata.
                    st.markdown(report.read_text())
        else:
            modes = [item for item in categories if claim_visible(item)]
            totals = Counter((item["model"], item["run"]) for item in modes)
            st.dataframe(pd.DataFrame([{"Model": k[0], "Run": k[1], "Categories": n}
                                       for k, n in totals.items()]), hide_index=True, width="stretch")
            st.caption("Initial Sol audit: 22 citations reviewed, 21 supported including one comparison, "
                       "one causal qualification. The full run missed unsupported item removal and an incomplete handoff.")
        st.caption("The Failure Modes page retains exact causes, evidence and proposed criteria.")
    with tabs[2]:
        plan_rows = [{"Trace": k, **v} for k, v in plans.items() if k in visible]
        show_comparison_rows(plan_rows, "planning")
        st.caption("Full-trace heuristic results can reflect hindsight. Tournament action prefixes stop "
                   "before the action outcome. Provisional planning labels do not establish accuracy.")
        report = RESULTS / "multi_model/planning_casebook.md"
        if report.exists():
            with st.expander("Planning casebook"):
                st.markdown(report.read_text())


def show_comparison_rows(rows, key):
    if not rows:
        st.info("No comparison rows match these filters.")
        return
    data = pd.DataFrame(rows)
    event = st.dataframe(data.style.map(status_style), hide_index=True, width="stretch", on_select="rerun",
                         selection_mode="single-row", key=f"{key}_comparison_{len(rows)}")
    pick = event.selection.rows
    available = [row["Trace"] for row in rows]
    current = available[pick[0]] if pick else available[0]
    choice = st.selectbox("Inspect a comparison trace", available,
                          index=available.index(current), key=f"{key}_comparison_trace_{current}")
    st.markdown(f"[Open {choice} in Trace Explorer]({trace_link(choice)})")
    if choice in verified_evidence:
        st.caption(verified_evidence[choice])


{"Overview": overview, "Trace Explorer": find_trace, "Failure Modes": failure_modes,
 "Model Comparison": model_comparison}[page]()
