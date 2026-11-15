"""Read-only trace, evidence and metric components."""

from collections import Counter
import json
import re
from urllib.parse import urlencode

import streamlit as st

from data_loader import message_indices, trace_timeline

BAD = {"violation", "failed"}
NEUTRAL = {"indeterminate", "inapplicable", "manual_review", "Unreviewed"}


def trace_link(trace_id, event=None):
    params = {"page": "Trace Explorer", "trace": trace_id}
    if event:
        params["event"] = event
    return "?" + urlencode(params)


def render_value(value):
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (ValueError, TypeError):
            st.text(value)
            return
    if isinstance(value, (dict, list)):
        st.json(value, expanded=False)
    elif value is not None:
        st.text(str(value))


def render_messages(messages, cited, focus):
    options = ["All events", "Conversation", "Tool activity", "Cited evidence"]
    selection = st.segmented_control("Event filter", options, default="All events", key="event_filter")
    for index, msg in enumerate(messages, 1):
        role = msg["role"]
        calls = (msg.get("tool_calls") or [])
        if selection == "Conversation" and (role == "tool" or not msg.get("content")):
            continue
        if selection == "Tool activity" and role != "tool" and not calls:
            continue
        if selection == "Cited evidence" and index not in cited:
            continue
        st.html(f'<span id="event-{index}"></span>')
        title = f"m{index:02} · " + {"user": "Customer", "assistant": "Assistant", "tool": "Tool result"}.get(role, role)
        if role == "tool":
            title += f" · {msg.get('name', 'unknown tool')}"
        if isinstance(msg.get("content"), str) and msg["content"].startswith("Error:"):
            title += " · ERROR"
        if index in cited:
            title += " · CITED"
        if role == "tool":
            with st.expander(title, expanded=index == focus):
                if msg.get("tool_call_id"):
                    st.caption(msg["tool_call_id"])
                render_value(msg.get("content"))
            continue
        with st.container(border=True):
            if index == focus:
                st.warning(title)
            else:
                st.markdown(f"**{title}**")
            content = msg.get("content")
            if content:
                st.text(content)
            for call in calls:
                fn = call.get("function", {})
                with st.expander(f"Tool call · {fn.get('name', '')}", expanded=index == focus):
                    if call.get("id"):
                        st.caption(call["id"])
                    render_value(fn.get("arguments"))


def render_timeline(trace):
    events = list(trace_timeline(trace["messages"]))
    if not events:
        st.info("No tracked mutation, order-state result, or explicit tool error in this trace.")
    for index, event, detail in events:
        link = trace_link(trace["trace_id"], index)
        if event == "Tool error":
            st.error(f"m{index:02} · {detail}")
            st.markdown(f"[Inspect message]({link})")
        else:
            st.markdown(f"[m{index:02}]({link}) · **{event}**")
            st.text(detail)


def claim_indices(claim, length):
    indices = message_indices(claim["positions"], length)
    if indices:
        return indices
    cues = re.findall(r"(?:\bm(?=\d)|\bmessages?\s+)(\d+(?:\s*[–-]\s*\d+)?)",
                      claim["observation"], re.I)
    return message_indices(" ".join(cues), length)


def status_style(value):
    if value in BAD:
        return "background-color: #ffe4e6; color: #881337; font-weight: 700"
    if value in NEUTRAL:
        return "background-color: #e8edf4; color: #334155"
    if value == "clear":
        return "background-color: #ddf5e8; color: #14532d"
    return ""


def render_claims(trace, claims):
    if not claims:
        st.info("No researcher citations are recorded for this trace.")
    for claim in claims:
        finding = claim["finding"]
        with st.expander(f"{finding['severity'].title()} · {finding['name']}"):
            st.caption(f"{finding['model']} · {finding['run']} · {claim['review']}")
            st.text(claim["observation"])
            indices = claim_indices(claim, len(trace["messages"]))
            if indices:
                st.markdown(" · ".join(f"[m{i:02}]({trace_link(trace['trace_id'], i)})" for i in indices))
            if claim["verified_evidence"]:
                st.caption("Independent review")
                st.text(claim["verified_evidence"])
            st.caption("Researcher’s inferred cause")
            st.text(finding["root_cause_assessment"])


def evaluator_metrics(matrix, model):
    counts = Counter()
    for row in matrix.values():
        predicted = row.get(model)
        truth = row.get("Verified state")
        if predicted is None or truth not in {"violation", "clear", "inapplicable"}:
            continue
        counts["n"] += 1
        if predicted == "indeterminate":
            counts["abstain"] += 1
        elif predicted == "violation":
            counts["tp" if truth == "violation" else "fp"] += 1
        else:
            counts["fn" if truth == "violation" else "tn"] += 1
    return counts


def ratio(number, denominator):
    return f"{number / denominator:.1%}" if denominator else "N/A"
