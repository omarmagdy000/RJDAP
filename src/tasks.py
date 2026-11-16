"""Stateless task generation and execution (SHA-256 nonce search).

Shared module (R2 generates tasks, R3 executes them). Standard library only.
"""

from __future__ import annotations

import hashlib
import random
from typing import NamedTuple

DEFAULT_JOB_KEY = b"rjdap-job-key-01"
DEFAULT_TASK_SIZE = 20_000
DEFAULT_DIFFICULTY_BITS = 12


class Task(NamedTuple):
    task_id: int
    job_key: bytes
    start_nonce: int
    count: int
    difficulty_bits: int


def make_tasks(
    num_tasks: int = 1000,
    seed: int = 42,
    job_key: bytes = DEFAULT_JOB_KEY,
    task_size: int = DEFAULT_TASK_SIZE,
    difficulty_bits: int = DEFAULT_DIFFICULTY_BITS,
) -> list[Task]:
    """Generate a deterministic list of stateless nonce-search tasks."""
    if num_tasks < 0:
        raise ValueError("num_tasks must be non-negative")
    if len(job_key) != 16:
        raise ValueError("job_key must be exactly 16 bytes")
    if task_size <= 0:
        raise ValueError("task_size must be positive")
    if not 0 <= difficulty_bits <= 256:
        raise ValueError("difficulty_bits must be in [0, 256]")

    rng = random.Random(seed)
    base_offset = rng.randrange(0, 1_000_000) * task_size
    return [
        Task(
            task_id=task_id,
            job_key=job_key,
            start_nonce=base_offset + task_id * task_size,
            count=task_size,
            difficulty_bits=difficulty_bits,
        )
        for task_id in range(1, num_tasks + 1)
    ]


def run_task(
    job_key: bytes,
    start_nonce: int,
    count: int,
    difficulty_bits: int,
) -> tuple[bool, int]:
    """Search [start_nonce, start_nonce + count) for a SHA-256 leading-zero match."""
    shift = 256 - difficulty_bits
    for n in range(start_nonce, start_nonce + count):
        digest = hashlib.sha256(job_key + str(n).encode()).digest()
        if difficulty_bits == 0 or (int.from_bytes(digest, "big") >> shift) == 0:
            return True, n
    return False, 0
