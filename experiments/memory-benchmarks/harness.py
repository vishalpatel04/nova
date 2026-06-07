"""Local memory retrieval benchmark harness (experimental)."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

SAMPLE_QUERIES = [
    "Where are my Lund documents?",
    "Find my Sweden exchange reimbursement files.",
    "What did we merge yesterday?",
    "Which projects involved Darshan?",
    "What broke Ollama last time?",
    "What decisions did we make for NOVA voice privacy?",
    "Continue working on NOVA.",
]


@dataclass
class BenchmarkResult:
    query: str
    strategy: str
    latency_ms: float
    hit_count: int


async def run_benchmark() -> list[BenchmarkResult]:
    results: list[BenchmarkResult] = []
    for query in SAMPLE_QUERIES:
        for strategy in ("keyword", "vector", "hybrid", "hybrid_graph"):
            start = time.perf_counter()
            await asyncio.sleep(0.001)
            latency = (time.perf_counter() - start) * 1000
            results.append(
                BenchmarkResult(
                    query=query,
                    strategy=strategy,
                    latency_ms=latency,
                    hit_count=0,
                )
            )
    return results


def main() -> None:
    results = asyncio.run(run_benchmark())
    print(f"Ran {len(results)} benchmark cells across {len(SAMPLE_QUERIES)} queries.")
    for row in results[:4]:
        print(f"  [{row.strategy}] {row.query[:40]}… {row.latency_ms:.2f}ms")


if __name__ == "__main__":
    main()
