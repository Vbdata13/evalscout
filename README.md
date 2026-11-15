# EvalScout

> **AUTHOR INTRODUCTION PLACEHOLDER**
>
> Replace this block with your personally written introductory paragraph.

EvalScout measures whether an agent can investigate support conversations,
find meaningful failures, and turn those insights into executable tests that
work on new traces.

## Demo

1. Read the [task](benchmark/workspace/TASK.md),
   [retail policy](benchmark/workspace/retail_policy.md), and
   [submission contract](benchmark/workspace/CONTRACT.md).
2. Open the local Streamlit dashboard using the
   [dashboard instructions](dashboard/README.md). The original author
   workspace has the full annotated dataset and model results.
3. See [local model results](benchmark/LOCAL_RESULTS.md) for the original
   Astra, Sol, and Terra experiment. Results from Valkyrie are tracked
   separately in [SUBMISSION_CHECKLIST.md](SUBMISSION_CHECKLIST.md).

![Local discovery coverage](benchmark/figures/discovery.png)
![Local unseen-test results](benchmark/figures/unseen.png)

## Run the versioned Harbor dataset

The hackathon path uses the hosted, versioned Harbor dataset
`evalscout-harbor/retail@v2`. Valkyrie uses Modal for the agent and the separate
verifier. Your account must be in the organization that owns the dataset.

```sh
valkyrie run start --agent codex-evalscout-py312 \
  --dataset evalscout-harbor/retail@v2 --model openai/gpt-6.1-sol \
  --provider modal -s OPENAI_API_KEY openai-api-key --concurrency 1 --connect
```

To publish a copy in your own organization, supply the private review bundle
as described below and run `python3 scripts/materialize_harbor.py
private/valkyrie/harbor-copy`. Then push that directory with
`valkyrie dataset push evalscout-harbor/retail private/valkyrie/harbor-copy
--tag v2`. The [Harbor task template](harbor/evalscout-retail) declares
exactly three submission artifacts. Its verifier uses the same scoring
code as the custom service. The private data stays in the verifier build
context. Keep the materialized copy outside Git.

## Alternate route: authenticated custom service

The service was generated with the official
[create-benchmark-service starter](https://github.com/vals-ai/create-benchmark-service).
Install Docker, uv, and the [Valkyrie CLI](https://docs.valkyrie.vals.ai/).
Use the official [conversion guide](https://docs.valkyrie.vals.ai/benchmarks/convert-a-benchmark)
for tunnel and provider setup. The private evaluation bundle must be
provided by the organizer separately. It contains `test.jsonl` and
`grading_reference.json`. A rejected or incomplete run does not establish
an integration result.

```sh
docker pull --platform linux/amd64 python:3.12-slim
cd evalscout-benchmark-service
uv sync
EVALSCOUT_TEST_DOCKER=1 uv run pytest -q
```

Set `EVALSCOUT_PRIVATE` to the private bundle directory. Start the service
with `AUTH_REQUIRED=true` and `EVALSCOUT_SERVICE_TOKEN` supplied in its
environment. The service expects the exact `Bearer TOKEN` header value.
Save that header value as a Valkyrie organization secret and register the
tunnel URL using `valkyrie benchmark service set evalscout URL --auth-secret
SECRET_REFERENCE`. Store model and sandbox-provider credentials in Valkyrie.

```sh
uv run uvicorn main:app --host 127.0.0.1 --port 8001

valkyrie run start --benchmark evalscout --dataset default \
  --task-ids evalscout-retail --agent codex-v1.0.0 \
  --model openai/gpt-6.1-sol --provider modal --concurrency 1 \
  --secret OPENAI_API_KEY openai-key --connect
```

Use a second terminal for the run and keep the service and tunnel running.
If the stock Codex harness selects Python 3.15 and fails to install tiktoken,
run `python3 scripts/prepare_codex_harness.py` from the repository root and
repeat with `--agent codex-evalscout-py312`. This copies the existing harness
and pins its dependency installation to Python 3.12.
Use `valkyrie run results`, `valkyrie run errors`, and
`valkyrie run outputs` to save the results locally.

## Host the service on Modal

Authenticate with Modal locally. In your Modal workspace, create the
`evalscout-service-auth` secret with the same `EVALSCOUT_SERVICE_TOKEN`
used for the Valkyrie benchmark registration. The private bundle must be
at `private/valkyrie/` in the organizer workspace. From
`evalscout-benchmark-service/`, run `uv run modal deploy modal_app.py::APP`.
Register the returned HTTPS URL with Valkyrie using the existing service
secret reference. This replaces the local tunnel. Grading runs in a
separate Modal sandbox with networking disabled.

## Reproduce the dashboard

Clone the pinned upstream τ-bench archive into `data_sources/tau-bench`.
Then install Streamlit as described in [dashboard/README.md](dashboard/README.md).
A clean submission checkout can browse the upstream archive. Full experiment
overlays and the annotation workflow require the author's local artifacts,
which contain private data and stay out of Git.

See [methodology, provenance, and limitations](benchmark/METHODOLOGY.md) for
the frozen task and grading rules. The source attribution and MIT terms are
in [SIERRA_LICENSE](benchmark/SIERRA_LICENSE).
