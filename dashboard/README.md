# EvalScout local dashboard

Run from the EvalScout project directory:

```sh
.venv/bin/python -m streamlit run dashboard/app.py --server.address 127.0.0.1 --server.port 8501 --server.headless true --browser.gatherUsageStats false --theme.base light
```

If you need to recreate the environment, use `uv venv .venv` and
`uv pip install --python .venv/bin/python 'streamlit>=1.67,<2'`.

The dashboard joins EvalScout trace IDs to original Sierra source rows using
the pinned provenance. Sierra Retail and Airline source rows are searchable.
Only Retail trajectories are assigned to EvalScout discovery, held-out, or
additional evaluation splits. Source archive rows exclude those already
assigned to an experiment split. Counts deduplicate task IDs within domains.
Tasks may have multiple trials and source models.

The sidebar filters the corpus. Select a trace from the searchable table or
picker, then use the Conversation, State timeline, and Failure evidence tabs.
The local reviewer control reveals one private benchmark goal at a time. Model
Comparison includes order-state results, discovery findings, and planning
predictions when completed artifacts are available. Use **Refresh experiment
results** to invalidate cached summaries.

The server binds to loopback and reads experiment files without modifying
them. The annotation and research views make no model calls. The Valkyrie
view uses the locally authenticated CLI for read-only run status. Sierra rewards describe tasks overall. Criterion-specific
state decisions use reviewed transcript evidence.

## Human annotation

Open [Human Annotation](http://127.0.0.1:8501/?page=Human+Annotation).
A new browser session starts on the first unreviewed trace. Click **Comment**
beside a message or an individual tool call. Choose severity before entering
the note. Blurring the text field or pressing Command+Enter saves it. Add as
many notes as needed and set the trace status when finished.

The frozen manifest and SQLite review database are under
`private/human_review/`. The manifest records the upstream commit, file hash,
row, task ID, and trial. The 20 distinct task IDs were excluded from all
previous discovery and evaluation samples. Each split contains five source
successes and five source failures. Rewards and private goals are hidden in
the annotation view. The source rewards describe entire tasks.

Use **Group Failure Modes** to draft categories from development comments.
The optional local word-overlap suggestions have separate provenance and
need explicit copying and approval. You can also build groups manually,
rename them, edit memberships, merge, split, or reject them. Edits to an
approved group reopen it as a draft. Hidden-test notes are held out from all
grouping. Sidebar downloads export original comments and review decisions,
approved taxonomy, and machine suggestions separately. Back up the entire
private review directory to retain local work. Keep it outside any benchmark
researcher input bundle.

## Valkyrie runs

Open [Valkyrie Runs](http://127.0.0.1:8501/?page=Valkyrie+Runs) to see task
phases and scores for EvalScout in the connected Valkyrie organization. The
local dashboard refreshes every ten seconds while this page is open.
