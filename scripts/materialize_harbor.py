"""Copy the public task and the organizer's private verifier inputs into staging."""
import argparse
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
TASK = "evalscout-retail"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    target = args.output / TASK
    source = ROOT / "benchmark/workspace"
    private = ROOT / "private/valkyrie"
    shutil.copytree(ROOT / "harbor" / TASK, target)
    shutil.copyfile(source / "TASK.md", target / "instruction.md")
    shutil.copytree(source, target / "environment/input")
    tests = target / "tests"
    shutil.copyfile(source / "traces.jsonl", tests / "development.jsonl")
    grader = ROOT / "evalscout-benchmark-service/src/evalscout_benchmark_service/grader.py"
    shutil.copyfile(grader, tests / "grader.py")
    (tests / "private").mkdir(mode=0o700)
    for name in ("test.jsonl", "grading_reference.json"):
        shutil.copyfile(private / name, tests / "private" / name)
    print(f"Staged {TASK}. Keep its private verifier directory outside Git.")


if __name__ == "__main__":
    main()
