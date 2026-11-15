"""Local annotation storage. No model or network access."""

from collections import Counter
from contextlib import closing, contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sqlite3
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
REVIEW = ROOT / "private/human_review"
DATABASE = REVIEW / "review.sqlite3"
STATUS = ("Needs review", "No meaningful issues", "Reviewed with issues")
SEVERITY = ("Unspecified", "Critical", "Major", "Minor", "Unsure")


def now():
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def connect():
    with closing(sqlite3.connect(DATABASE)) as connection, connection:
        connection.row_factory = sqlite3.Row
        connection.executescript("""
            CREATE TABLE IF NOT EXISTS comments (
                id TEXT PRIMARY KEY, trace_id TEXT, event INTEGER, call INTEGER,
                body TEXT, severity TEXT, created_at TEXT, provenance TEXT
            );
            CREATE TABLE IF NOT EXISTS reviews (
                trace_id TEXT PRIMARY KEY, status TEXT, updated_at TEXT, provenance TEXT
            );
            CREATE TABLE IF NOT EXISTS proposals (
                id TEXT PRIMARY KEY, name TEXT, members TEXT, provenance TEXT,
                created_at TEXT, decision TEXT
            );
            CREATE TABLE IF NOT EXISTS groups (
                id TEXT PRIMARY KEY, name TEXT, members TEXT, approved_at TEXT,
                sources TEXT, updated_at TEXT
            );
        """)
        yield connection


def read(table, order):
    with connect() as db:
        return [dict(r) for r in db.execute(f"SELECT * FROM {table} ORDER BY {order}")]


def add_comment(trace, event, call, body, severity):
    if not body.strip():
        return
    with connect() as db:
        db.execute("INSERT INTO comments VALUES (?,?,?,?,?,?,?,?)",
                   (uuid4().hex, trace, event, call, body, severity, now(), "human"))


def mark(trace, status):
    if status not in STATUS:
        raise ValueError("Unknown review status")
    with connect() as db:
        if status != STATUS[0]:
            count = db.execute("SELECT count(*) FROM comments WHERE trace_id=?", (trace,)).fetchone()[0]
            if (status == STATUS[1] and count) or (status == STATUS[2] and not count):
                raise ValueError("Review status must agree with saved comments.")
        db.execute("INSERT OR REPLACE INTO reviews VALUES (?,?,?,?)", (trace, status, now(), "human"))


def suggest_groups(eligible):
    """Local lexical proposals from exact human comment text. Never edits comments."""
    comments = [row for row in read("comments", "created_at, id") if row["id"] in eligible]
    stop = set("the a an to of and is was it on for in they this that with had has agent user "
               "assistant customer should did not tool then but said would could from after before".split())
    buckets = []
    for comment in comments:
        tokens = set(re.findall(r"[a-z]{3,}", comment["body"].lower())) - stop
        close = next((group for group in buckets if len(tokens & group[0]) >= 2
                      and len(tokens & group[0]) / len(tokens | group[0]) >= 0.25), None)
        if close:
            close[1].append(comment)
        else:
            buckets.append((tokens, [comment]))
    with connect() as db:
        existing = {row[0] for row in db.execute("SELECT members FROM proposals")}
        for _, items in buckets:
            ids = json.dumps(sorted(row["id"] for row in items))
            if ids in existing:
                continue
            words = Counter(word for row in items for word in
                            re.findall(r"[a-z]{3,}", row["body"].lower()) if word not in stop)
            name = " / ".join(word for word, _ in words.most_common(3)) or "Review comment"
            db.execute("INSERT INTO proposals VALUES (?,?,?,?,?,?)",
                       (uuid4().hex, name, ids, "local_lexical_suggestion", now(), "pending"))


def decide_proposal(proposal_id, accept):
    with connect() as db:
        proposal = db.execute("SELECT * FROM proposals WHERE id=? AND decision='pending'",
                              (proposal_id,)).fetchone()
        if proposal is None:
            return
        if accept:
            db.execute("INSERT INTO groups VALUES (?,?,?,?,?,?)",
                       (uuid4().hex, proposal["name"], proposal["members"], None,
                        json.dumps([proposal_id]), now()))
        db.execute("UPDATE proposals SET decision=? WHERE id=?",
                   ("copied_to_draft" if accept else "human_rejected", proposal_id))


def save_group(name, members, group_id=None):
    if not name.strip() or not members:
        raise ValueError("A group needs a name and at least one comment.")
    with connect() as db:
        if group_id:
            db.execute("UPDATE groups SET name=?, members=?, approved_at=NULL, updated_at=? WHERE id=?",
                       (name.strip(), json.dumps(members), now(), group_id))
        else:
            db.execute("INSERT INTO groups VALUES (?,?,?,?,?,?)",
                       (uuid4().hex, name.strip(), json.dumps(members), None, "[]", now()))


def approve(group_id):
    with connect() as db:
        group = db.execute("SELECT * FROM groups WHERE id=?", (group_id,)).fetchone()
        if not group or not group["name"].strip() or not json.loads(group["members"]):
            raise ValueError("Name the group and select evidence before approving.")
        db.execute("UPDATE groups SET approved_at=?, updated_at=? WHERE id=?", (now(), now(), group_id))


def reject(group_id):
    with connect() as db:
        db.execute("DELETE FROM groups WHERE id=?", (group_id,))


def restructure(group_ids, name, split_members=None):
    if not name.strip():
        raise ValueError("Enter a name for the new group.")
    with connect() as db:
        groups = [db.execute("SELECT * FROM groups WHERE id=?", (key,)).fetchone() for key in group_ids]
        members = list(dict.fromkeys(member for group in groups for member in json.loads(group["members"])))
        sources = list(dict.fromkeys(source for group in groups for source in json.loads(group["sources"])))
        if split_members is not None:
            if not split_members or not set(split_members) < set(members):
                raise ValueError("Select some of the comments, leaving at least one in the original.")
            remaining = [member for member in members if member not in split_members]
            db.execute("UPDATE groups SET members=?, approved_at=NULL, updated_at=? WHERE id=?",
                       (json.dumps(remaining), now(), group_ids[0]))
            members = split_members
        else:
            db.executemany("DELETE FROM groups WHERE id=?", [(key,) for key in group_ids])
        db.execute("INSERT INTO groups VALUES (?,?,?,?,?,?)",
                   (uuid4().hex, name.strip(), json.dumps(members), None, json.dumps(sources), now()))
