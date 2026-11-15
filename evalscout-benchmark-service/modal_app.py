"""Deploy the authenticated benchmark service to the organizer's Modal workspace."""
from pathlib import Path
import sys

import modal

SERVICE = Path(__file__).resolve().parent
ROOT = SERVICE.parent
PRIVATE = ROOT / "private/valkyrie"
APP = modal.App("evalscout-benchmark")
image = modal.Image.debian_slim(python_version="3.12").apt_install("git").pip_install(
    "create-benchmark-service @ git+https://github.com/vals-ai/create-benchmark-service.git@v0.76.1"
)
if modal.is_local():
    image = (
        image.add_local_dir(SERVICE / "src", "/opt/evalscout/src", ignore=["**/__pycache__/**"])
        .add_local_dir(ROOT / "benchmark/workspace", "/opt/evalscout/public")
        .add_local_file(PRIVATE / "test.jsonl", "/opt/evalscout/private/test.jsonl")
        .add_local_file(PRIVATE / "grading_reference.json", "/opt/evalscout/private/grading_reference.json")
    )


@APP.function(
    image=image, min_containers=1, max_containers=2, timeout=180,
    secrets=[modal.Secret.from_name("evalscout-service-auth")],
    env={"AUTH_REQUIRED": "true", "EVALSCOUT_RUNTIME": "modal",
         "EVALSCOUT_PUBLIC": "/opt/evalscout/public",
         "EVALSCOUT_PRIVATE": "/opt/evalscout/private"},
)
@modal.concurrent(max_inputs=12)
@modal.asgi_app()
def service():
    sys.path.insert(0, "/opt/evalscout/src")
    from benchmark_service import BenchmarkServiceApp
    from evalscout_benchmark_service.benchmark_service import EvalScoutBenchmark

    return BenchmarkServiceApp(EvalScoutBenchmark)
