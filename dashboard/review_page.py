"""Human annotation and taxonomy editing for the loopback dashboard."""
import hashlib
import json

import streamlit as st

from components import render_value
from review_store import (
    REVIEW, ROOT, SEVERITY, STATUS, add_comment, approve, decide_proposal, mark, read,
    reject, restructure, save_group, suggest_groups,
)

SOURCE = ROOT / "data_sources/tau-bench"


@st.cache_data
def review_data():
    manifest = json.loads((REVIEW / "manifest.json").read_text())
    raw = (SOURCE / manifest["source_file"]).read_bytes()
    if hashlib.sha256(raw).hexdigest() != manifest["source_sha256"]:
        raise ValueError("The frozen annotation source hash does not match.")
    runs = json.loads(raw)
    messages = {}
    for row in manifest["traces"]:
        run = runs[row["source_row"]]
        if (run["task_id"], run["trial"], run["reward"]) != (row["task_id"], row["trial"], row["reward"]):
            raise ValueError("A source row no longer matches annotation provenance.")
        messages[row["trace_id"]] = [m for m in run["traj"] if m["role"] != "system"]
    policy = (SOURCE / "tau_bench/envs/retail/wiki.md").read_text()
    return manifest, messages, policy


def run_action(action, *args):
    try:
        action(*args)
    except ValueError as error:
        st.error(str(error))
    else:
        st.rerun()


def composer(trace_id, event, call, comments, status):
    for row in comments:
        if row["event"] == event and row["call"] == call:
            st.caption(f"Saved human comment · {row['severity']}")
            st.text(row["body"])
    if status == STATUS[1]:
        st.caption("Change the trace status to Needs review before adding a comment.")
        return
    target = f"{trace_id}-{event}-{call}"
    text_key = f"comment-{target}"
    severity_key = f"severity-{target}"

    def save():
        add_comment(trace_id, event, call, st.session_state[text_key], st.session_state[severity_key])
        st.session_state[text_key] = ""

    st.selectbox("Severity", SEVERITY, key=severity_key)
    st.text_area("Comment", key=text_key, height=76, on_change=save,
                 placeholder="What went wrong? Click outside the field or press ⌘↵ to save.")


def annotate(manifest, traces, policy, comments, statuses):
    rows = manifest["traces"]
    ids = [row["trace_id"] for row in rows]
    completed = sum(statuses.get(key, STATUS[0]) != STATUS[0] for key in ids)
    st.progress(completed / len(ids), text=f"{completed} / {len(ids)} traces reviewed · {len(comments)} saved comments")
    if "review_trace" not in st.session_state:
        st.session_state.review_trace = next((i for i in ids if statuses.get(i, STATUS[0]) == STATUS[0]), ids[0])

    active = st.session_state.review_trace
    index = ids.index(active)
    row = rows[index]
    status = statuses.get(active, STATUS[0])
    for column, label, adjacent in zip(st.columns(2), ("← Previous", "Next →"), (index - 1, index + 1)):
        if 0 <= adjacent < len(ids):
            column.button(label, on_click=lambda key=ids[adjacent]: st.session_state.update(review_trace=key))
        else:
            column.button(label, disabled=True)

    st.selectbox("Trace", ids, key="review_trace", format_func=lambda key: (
        f"{key} · {rows[ids.index(key)]['split']} · {statuses.get(key, STATUS[0])}"
    ))
    st.caption(f"{active} · {row['split']} · Sierra task {row['task_id']} · {index + 1}/{len(ids)}")
    local = [c for c in comments if c["trace_id"] == active]
    status_key = f"status-{active}"

    def save_status():
        try:
            mark(active, st.session_state[status_key])
        except ValueError as error:
            st.session_state[status_key] = status
            st.session_state.review_status_error = str(error)

    st.selectbox("Trace status", STATUS, index=STATUS.index(status), key=status_key, on_change=save_status)
    if error := st.session_state.pop("review_status_error", None):
        st.error(error)
    st.caption("Click Comment on a message or tool call. Comments save when you leave the text field. "
               "Sierra outcomes and hidden goals stay out of the annotation view.")

    transcript, rules = st.columns([3, 2])
    with rules:
        with st.expander("Retail policy", expanded=True):
            with st.container(height=550):
                st.markdown(policy)
    with transcript:
        for event, message in enumerate(traces[active], 1):
            role = message["role"]
            calls = message.get("tool_calls") or []
            label = {"user": "Customer", "assistant": "Assistant", "tool": "Tool result"}[role]
            if role == "tool":
                label += f" · {message['name']}"
            with st.container(border=True):
                st.markdown(f"**m{event:02} · {label}**")
                content = message.get("content")
                if content is not None:
                    if role == "tool":
                        with st.expander(f"Result payload · m{event:02}"):
                            render_value(content)
                    else:
                        st.text(content)
                with st.popover(f"Comment · m{event:02}"):
                    composer(active, event, None, local, status)
                for call_no, call in enumerate(calls, 1):
                    fn = call["function"]
                    with st.expander(f"Tool call {call_no} · {fn['name']}"):
                        st.caption(call["id"])
                        render_value(fn["arguments"])
                    with st.popover(f"Comment · m{event:02} call {call_no}"):
                        composer(active, event, call_no, local, status)
                saved = sum(c["event"] == event for c in local)
                if saved:
                    st.caption(f"{saved} saved {'comment' if saved == 1 else 'comments'}")


def grouping(comments, traces):
    # Keep hidden test feedback out of taxonomy construction.
    available = {c["id"]: c for c in comments if c["trace_id"].startswith("HR-D")}
    st.caption("Build the taxonomy from development comments. Hidden-test comments remain available "
               "in the annotation view and human export.")
    if not available:
        st.info("Save at least one development comment to start grouping.")
        return

    def label(key):
        row = available[key]
        return f"{row['trace_id']} m{row['event']:02} · {row['body'][:90]}"

    def evidence(members):
        for key in members:
            row = available[key]
            event = row["event"]
            call = row["call"]
            with st.container(border=True):
                st.caption(f"{row['trace_id']} · m{event:02}" + (f" · call {call}" if call else "")
                           + f" · Human · {row['severity']}")
                st.text(row["body"])
                event_data = traces[row["trace_id"]][event - 1]
                render_value(event_data["tool_calls"][call - 1] if call else event_data)

    if st.button("Suggest clusters from development comments"):
        run_action(suggest_groups, set(available))
    st.caption("Suggestions use local word overlap. They never change or approve your labels.")
    proposals = [r for r in read("proposals", "created_at") if r["decision"] == "pending"
                 and set(json.loads(r["members"])) <= available.keys()]
    for row in proposals:
        with st.expander(f"Suggested · {row['name']}"):
            evidence(json.loads(row["members"]))
            accept, decline = st.columns(2)
            if accept.button("Copy to draft", key=f"accept-{row['id']}"):
                run_action(decide_proposal, row["id"], True)
            if decline.button("Reject suggestion", key=f"decline-{row['id']}"):
                run_action(decide_proposal, row["id"], False)

    with st.expander("Create a group"):
        name = st.text_input("New group name")
        members = st.multiselect("Development comments", list(available), format_func=label)
        if st.button("Create draft"):
            run_action(save_group, name, members)

    groups = read("groups", "name, id")
    if not groups:
        return
    names = {g["id"]: g["name"] for g in groups}
    with st.expander("Merge groups"):
        selected = st.multiselect("Groups to merge", list(names), format_func=names.get)
        merged = st.text_input("Merged group name")
        if st.button("Merge into a draft", disabled=len(selected) < 2):
            run_action(restructure, selected, merged)
    active = st.selectbox("Group to review", list(names), format_func=names.get)
    group = next(g for g in groups if g["id"] == active)
    members = json.loads(group["members"])
    revision = group["updated_at"]
    st.caption("Human approved" if group["approved_at"] else "Draft")
    name = st.text_input("Group name", group["name"], key=f"name-{active}-{revision}")
    chosen = st.multiselect("Group evidence", list(available), default=members, format_func=label,
                            key=f"members-{active}-{revision}")
    dirty = name.strip() != group["name"] or chosen != members
    save, confirm, remove = st.columns(3)
    if save.button("Save edits", disabled=not dirty):
        run_action(save_group, name, chosen, active)
    if confirm.button("Approve group", disabled=dirty or bool(group["approved_at"])):
        run_action(approve, active)
    if remove.button("Reject group"):
        run_action(reject, active)

    with st.expander("Split group"):
        moved = st.multiselect("Move comments into a new group", members, format_func=label,
                               key=f"split-{active}-{revision}")
        title = st.text_input("Split group name", key=f"split-name-{active}-{revision}")
        if st.button("Split into drafts", disabled=not moved or len(moved) == len(members)):
            run_action(restructure, [active], title, moved)
    evidence(members)


def review_page():
    st.title("Human Annotation")
    try:
        manifest, traces, policy = review_data()
    except (OSError, ValueError) as error:
        st.error(f"Review dataset unavailable: {error}")
        return

    comments = read("comments", "created_at, id")
    reviews = read("reviews", "trace_id")
    statuses = {row["trace_id"]: row["status"] for row in reviews}
    view = st.segmented_control("Workflow", ["Annotate traces", "Group Failure Modes"],
                                default="Annotate traces")
    if view == "Group Failure Modes":
        grouping(comments, traces)
    else:
        annotate(manifest, traces, policy, comments, statuses)

    st.sidebar.subheader("Review exports")
    export = {"manifest": manifest, "comments": comments, "trace_statuses": reviews}
    st.sidebar.download_button("Human annotations", json.dumps(export, indent=2, ensure_ascii=False),
                                "human_annotations.json", "application/json")
    approved = [{**group, "members": json.loads(group["members"]),
                 "sources": json.loads(group["sources"]), "provenance": "human_approved"}
                for group in read("groups", "name") if group["approved_at"]]
    st.sidebar.download_button("Approved taxonomy", json.dumps({"groups": approved}, indent=2),
                                "approved_taxonomy.json", "application/json", disabled=not approved)
    proposals = [{**row, "members": json.loads(row["members"])} for row in read("proposals", "created_at")]
    st.sidebar.download_button("Grouping suggestions", json.dumps({"proposals": proposals}, indent=2),
                                "grouping_suggestions.json", "application/json", disabled=not proposals)
