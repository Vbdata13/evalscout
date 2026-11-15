import asyncio
import json
from types import SimpleNamespace

import pytest

from evalscout_benchmark_service.benchmark_service import EvalScoutBenchmark, FILES, TASK
from evalscout_benchmark_service.grader import parse_predictions, parse_submission, score
from evalscout_benchmark_service.isolation import evaluate_code


def fixture():
    def anchor(key, trace, concept, event):
        return {"anchor_id": key, "trace_id": trace, "concept": concept,
                "match_events": [event], "severity": "Critical"}
    return {
        "concepts": {"scope": "whole order", "auth": "auth bypass"},
        "discovery": [anchor("D", "dev", "scope", 1)],
        "execution": [anchor("E", "test", "scope", 1)],
        "negative_discovery": [{"trace_id": "dev", "concept": "auth", "match_events": [1]}],
        "negative_execution": [],
    }


def test_deduplication_and_verified_only():
    dev, test = {"dev": [{}]}, {"test": [{}], "unknown": [{}]}
    c = {"id": "F01", "name": "whole order", "definition": "whole order scope",
         "evidence": [{"trace_id": "dev", "events": [1], "severity": "critical",
                       "observation": "whole order cancellation"}] * 2}
    categories = parse_submission(json.dumps({"categories": [c]}), dev)
    rows = "\n".join(json.dumps({"trace_id": key, "predictions": [
        {"category_id": "F01", "verdict": verdict, "events": [1] if verdict == "present" else []}]})
        for key, verdict in (("test", "present"), ("unknown", "uncertain")))
    parsed = parse_predictions(rows, test, categories)
    result = score(categories, parsed, fixture(), True)
    assert result["score"] == 100 and result["resolved"]
    assert result["discovery_claims"] == 1
    assert result["global_precision"] is None
    parsed["unknown"]["F01"] = {"verdict": "present", "events": [1]}
    bad = score(categories, parsed, fixture(), True)
    assert bad["blanket_categories"] == 1 and bad["verified_unseen_matches"] == 0
    assert not bad["resolved"] and bad["critical_misses"] == 1


def test_reject_wrong_id_and_positions():
    with pytest.raises(ValueError):
        parse_predictions('{"trace_id":"wrong","predictions":[]}', {"test": [{}]}, {})
    with pytest.raises(ValueError):
        parse_submission('{"categories":[{"id":"F01","name":"scope","definition":"scope",'
                         '"evidence":[{"trace_id":"dev","events":[2],"observation":"x",'
                         '"severity":"minor"}]}]}', {"dev": [{}]})


def test_service_upload_allowlist_and_aggregation():
    async def run():
        bench = object.__new__(EvalScoutBenchmark)
        bench.datasets = {"default": {TASK: {"inputs": {name: name.encode() for name in FILES},
                                              "test": b"private marker", "reference": {}}}}

        class Sandbox:
            files = {}

            async def exec(self, command):
                return SimpleNamespace(exit_code=0)

            async def upload_file(self, path, data):
                self.files[path] = data

        mock = Sandbox()
        chunks = [chunk async for chunk in bench.setup_task(TASK, mock, "default")]
        assert chunks[-1].data["status"] == "ok"
        assert set(mock.files) == {f"/workspace/input/{name}" for name in FILES}
        assert all(b"private marker" not in data for data in mock.files.values())
        response = await bench.retrieve_task(TASK, dataset="default")
        assert response.egress.evaluation == []
        assert response.egress.run == ["api.openai.com", "api.anthropic.com"]
        final = await bench.calculate_final_score({TASK: {"score": 73, "resolved": True}}, "default")
        assert final.score == 73 and final.metadata["scored_tasks"] == 1

    asyncio.run(run())


def test_offline_python_container():
    import os
    if os.environ.get("EVALSCOUT_TEST_DOCKER") != "1":
        pytest.skip("Opt in to the Linux isolation smoke test")
    source = b"""import os, socket, sys
assert not os.environ.get('OPENAI_API_KEY')
try:
    socket.create_connection(('1.1.1.1', 443), 1)
except OSError:
    pass
else:
    raise AssertionError('network permitted')
try:
    open('/root/labels.json')
except OSError:
    pass
else:
    raise AssertionError('private data mounted')
sys.stdout.write(sys.stdin.read())
"""
    assert asyncio.run(evaluate_code(source, b'{"sample":1}\n')) == b'{"sample":1}\n'
