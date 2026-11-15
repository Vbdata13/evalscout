"""Harbor entry point. Execute submitted code as an unprivileged process."""
import json
import os
from pathlib import Path
import resource
import signal
import subprocess
import sys
from tempfile import TemporaryDirectory

sys.path.insert(0, "/tests")
from grader import parse_predictions, parse_submission, parse_traces, score

SUBMISSION = Path("/workspace/submission")
PRIVATE = Path("/tests/private")
LOGS = Path("/logs/verifier")


def submitted(name, limit):
    path = SUBMISSION / name
    if not path.is_file() or path.is_symlink():
        return b""
    with path.open("rb") as file:
        data = file.read(limit + 1)
    if len(data) > limit:
        raise ValueError("Submission file exceeds its limit")
    return data


def restrict():
    os.setgroups([])
    os.setgid(65534)
    os.setuid(65534)
    resource.setrlimit(resource.RLIMIT_CPU, (20, 20))
    resource.setrlimit(resource.RLIMIT_FSIZE, (512_000, 512_000))
    resource.setrlimit(resource.RLIMIT_NPROC, (32, 32))


def execute(code, test):
    with TemporaryDirectory() as folder, open(LOGS / "prediction.tmp", "w+b") as output:
        path = Path(folder)
        path.chmod(0o755)
        script = path / "evaluator.py"
        script.write_bytes(code)
        script.chmod(0o444)
        with subprocess.Popen([sys.executable, "-IB", str(script)], cwd=folder,
                              env={"LANG": "C.UTF-8"}, stdin=subprocess.PIPE, stdout=output,
                              stderr=subprocess.DEVNULL, start_new_session=True,
                              preexec_fn=restrict) as proc:
            try:
                proc.communicate(test, timeout=35)
            finally:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            if proc.returncode:
                raise ValueError("Evaluator exited unsuccessfully")
        output.seek(0)
        return output.read()


def main():
    reference = json.loads((PRIVATE / "grading_reference.json").read_text())
    development = parse_traces(Path("/tests/development.jsonl").read_bytes())
    test = (PRIVATE / "test.jsonl").read_bytes()
    try:
        categories = parse_submission(submitted("findings.json", 200_000), development)
    except (ValueError, OSError, TypeError):
        result = {"score": 0, "status": "invalid_findings", "resolved": False}
    else:
        predictions = None
        status = "invalid_or_failed_evaluator"
        try:
            code = submitted("evaluator.py", 100_000)
            if code:
                predictions = parse_predictions(execute(code, test), parse_traces(test), categories)
                status = "completed"
        except (ValueError, OSError, subprocess.SubprocessError, TypeError):
            pass
        try:
            recommendations = bool(submitted("recommendations.md", 80_000).strip())
        except (ValueError, OSError):
            recommendations = False
        result = {**score(categories, predictions, reference, recommendations), "status": status}
    (LOGS / "prediction.tmp").unlink(missing_ok=True)
    (LOGS / "details.json").write_text(json.dumps(result, indent=2) + "\n")
    (LOGS / "reward.txt").write_text(f"{result['score'] / 100:.4f}\n")


if __name__ == "__main__":
    main()
