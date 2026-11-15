"""Official starter adapter for the EvalScout retail investigation."""
import hmac
import json
import os
from pathlib import Path
import stat

from benchmark_service import BenchmarkService, ImageSource, Resources
from benchmark_service.schemas import (
    BenchmarkEgressPlan, FinalScoreResult, RetrieveTaskResponse,
    StreamMessageChunk, StreamResultChunk,
)
from benchmark_service.v1_schemas import V1Task

from .grader import parse_predictions, parse_submission, parse_traces, score
from .isolation import evaluate_code

TASK = "evalscout-retail"
ROOT = Path(__file__).resolve().parents[3]
FILES = ("TASK.md", "CONTRACT.md", "retail_policy.md", "traces.jsonl")
LIMITS = {"findings.json": 200_000, "evaluator.py": 100_000, "recommendations.md": 80_000}


class EvalScoutBenchmark(BenchmarkService):
    async def check_auth(self, headers):
        token = os.environ.get("EVALSCOUT_SERVICE_TOKEN")
        return bool(token and hmac.compare_digest(headers.get("authorization", ""), f"Bearer {token}"))

    async def load_datasets(self):
        public = Path(os.environ.get("EVALSCOUT_PUBLIC", ROOT / "benchmark/workspace"))
        hidden = Path(os.environ.get("EVALSCOUT_PRIVATE", ROOT / "private/valkyrie"))
        inputs = {name: (public / name).read_bytes() for name in FILES}
        test = (hidden / "test.jsonl").read_bytes()
        development, heldout = parse_traces(inputs["traces.jsonl"]), parse_traces(test)
        if len(development) != 10 or len(heldout) != 10 or set(development) & set(heldout):
            raise ValueError("Invalid benchmark split")
        reference = json.loads((hidden / "grading_reference.json").read_bytes())
        return {"default": {TASK: {"inputs": inputs, "test": test, "development": development,
                                  "heldout": heldout, "reference": reference}}}

    async def list_tasks(self, dataset=None):
        return [V1Task(id=key, question=task["inputs"]["TASK.md"].decode())
                for key, task in self.get_dataset(dataset).items()]

    async def retrieve_task(self, task_id, skip_validation=False, dataset=None):
        if not skip_validation:
            await self.validate_task_ids([task_id], dataset=dataset)
        return RetrieveTaskResponse(
            source=ImageSource(image=os.environ.get("EVALSCOUT_AGENT_IMAGE", "node:22-bookworm")),
            cwd="/workspace", problem_path="/workspace/input/TASK.md", agent_timeout=1800,
            resources=Resources(vcpu=2, memory=4, disk=12),
            egress=BenchmarkEgressPlan(setup_task=[], run=["api.openai.com", "api.anthropic.com"],
                                       evaluation=[]),
        )

    async def setup_task(self, task_id, sandbox, dataset=None):
        task = self.get_dataset(dataset)[task_id]
        result = await sandbox.exec("mkdir -p /workspace/input /workspace/submission")
        if result.exit_code:
            raise RuntimeError("Could not create the EvalScout workspace")
        for name in FILES:
            await sandbox.upload_file(f"/workspace/input/{name}", task["inputs"][name])
        yield StreamResultChunk(type="result", data={"status": "ok"})

    async def evaluate_instance(self, task_id, sandbox, dataset=None):
        task = self.get_dataset(dataset)[task_id]
        files = {}
        for name, limit in LIMITS.items():
            path = f"/workspace/submission/{name}"
            # Prevent symlink reads and oversized downloads; file paths and limits are fixed.
            probe = await sandbox.exec(f"test -f {path} && test ! -L {path} && test $(wc -c < {path}) -le {limit}")
            if probe.exit_code == 0:
                files[name] = await sandbox.download_file(path)
        try:
            categories = parse_submission(files.get("findings.json", b""), task["development"])
        except (ValueError, TypeError):
            yield StreamResultChunk(type="result", data={"resolved": False, "score": 0, "status": "invalid_findings"})
            return
        predictions = None
        status = "missing_evaluator"
        if files.get("evaluator.py"):
            try:
                output = await evaluate_code(files["evaluator.py"], task["test"])
                predictions = parse_predictions(output, task["heldout"], categories)
                status = "completed"
            except (ValueError, OSError, TimeoutError, TypeError):
                status = "invalid_or_failed_evaluator"
        yield StreamMessageChunk(type="message", data=f"Private evaluator execution: {status}")
        result = score(categories, predictions, task["reference"], bool(files.get("recommendations.md", b"").strip()))
        yield StreamResultChunk(type="result", data={**result, "status": status})

    async def evaluate_response(self, request, dataset=None):
        raise ValueError("EvalScout grades files through evaluate_instance")

    async def calculate_final_score(self, evaluation_results, dataset=None):
        total = len(self.get_dataset(dataset))
        results = [result for key, result in evaluation_results.items()
                   if key in self.get_dataset(dataset) and isinstance(result, dict)]
        return FinalScoreResult(score=sum(r.get("score", 0) for r in results) / (total or 1),
                                metadata={"total_tasks": total, "scored_tasks": len(results),
                                          "resolved_tasks": sum(bool(r.get("resolved")) for r in results)})
