#!/usr/bin/env python3
"""Dummy workload for exercising the profiler.

Runs through a few distinct phases (idle, CPU burn, memory growth, mixed) so the
generated charts show clearly different regions for CPU usage, frequency, power,
and memory. Total runtime is ~20s by default.

Usage:
    python3 analyzer.py dummy_workload.py -- --seconds 5 --workers 4
"""
import argparse
import math
import time
from multiprocessing import Process


def _cpu_burn(seconds):
    """Peg a single core with pointless float math for `seconds`."""
    end = time.time() + seconds
    x = 0.0
    while time.time() < end:
        for _ in range(100_000):
            x += math.sqrt(12345.678) * math.sin(x)
    return x


def phase_idle(seconds):
    print(f"[phase] idle for {seconds}s (baseline)")
    time.sleep(seconds)


def phase_cpu(seconds, workers):
    print(f"[phase] CPU burn on {workers} worker(s) for {seconds}s")
    procs = [Process(target=_cpu_burn, args=(seconds,)) for _ in range(workers)]
    for p in procs:
        p.start()
    for p in procs:
        p.join()


def phase_memory(seconds):
    print(f"[phase] memory growth over {seconds}s")
    blocks = []
    step = max(1, seconds)
    for _ in range(step):
        # ~50 MB per second, held until the phase ends
        blocks.append(bytearray(50 * 1024 * 1024))
        time.sleep(1)
    print(f"[phase] holding ~{len(blocks) * 50} MB, releasing")
    del blocks


def phase_mixed(seconds, workers):
    print(f"[phase] mixed CPU + memory for {seconds}s")
    half = max(1, workers // 2) or 1
    procs = [Process(target=_cpu_burn, args=(seconds,)) for _ in range(half)]
    for p in procs:
        p.start()
    blocks = [bytearray(30 * 1024 * 1024) for _ in range(seconds)]
    for p in procs:
        p.join()
    del blocks


def main():
    parser = argparse.ArgumentParser(description="Dummy profiler workload")
    parser.add_argument("--seconds", type=int, default=5,
                        help="duration of each phase in seconds (default 5)")
    parser.add_argument("--workers", type=int, default=4,
                        help="parallel CPU workers during burn phases (default 4)")
    args = parser.parse_args()

    start = time.time()
    print(f"Dummy workload starting: {args.seconds}s/phase, {args.workers} workers")

    phase_idle(args.seconds)
    phase_cpu(args.seconds, args.workers)
    phase_memory(args.seconds)
    phase_mixed(args.seconds, args.workers)

    print(f"Dummy workload complete in {time.time() - start:.1f}s")


if __name__ == "__main__":
    main()
