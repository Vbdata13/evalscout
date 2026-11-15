"""Benchmark service entry point."""

from benchmark_service import BenchmarkServiceApp

from evalscout_benchmark_service.benchmark_service import EvalScoutBenchmark

app = BenchmarkServiceApp(EvalScoutBenchmark)