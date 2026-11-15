# Submission contract

Write three UTF-8 files in `/workspace/submission`:

- `findings.json` is an object with a `categories` array of up to 20 objects.
  Each category has a unique `id` such as `F01`, a `name`, a reusable
  `definition`, and an `evidence` array. Each evidence entry has
  `trace_id`, `events` (one or more 1-based message positions),
  `observation` (specific behavior and consequence), and `severity`
  (`critical`, `major`, `minor`, or `unsure`).
- `evaluator.py` runs as `python3 evaluator.py` with no third-party
  dependencies. It reads stdin JSONL, each row containing `trace_id` and
  `messages`. For each row in input order, write one stdout JSONL object
  containing `trace_id` and `predictions`. Each prediction has
  `category_id`, `verdict` (`present`, `absent`, or `uncertain`), and
  `events` (1-based message positions, required for present). Output one
  prediction per declared category, per trace. Diagnostic output goes to
  stderr. The evaluator runs without network or external files.
- `recommendations.md` explains changes to the support agent, how you tested
  and refined the evaluators, and their limitations.

One message may contain assistant text, one or more `tool_calls`, or a tool
result. Tool calls have an ID and function name and arguments. A result has
`tool_call_id`, `name`, and `content`. IDs may be reused after a result, so
match the preceding unmatched call. Tool content can be plain text or an
encoded JSON string. The policy is supplied separately and does not count as
a trace message.

Example output shape (illustrative IDs):
```json
{"trace_id":"example","predictions":[{"category_id":"F01","verdict":"uncertain","events":[]}]}
```
