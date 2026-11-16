"""Unit tests for src/tasks.py.

Run from the repo root:  python -m unittest discover tests -v
"""

import hashlib
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import tasks as T  # noqa: E402


class TestMakeTasks(unittest.TestCase):
    def test_count_and_deterministic_seed(self):
        a = T.make_tasks(1000, seed=42)
        b = T.make_tasks(1000, seed=42)
        c = T.make_tasks(1000, seed=43)
        self.assertEqual(len(a), 1000)
        self.assertEqual(a, b)
        self.assertNotEqual(a[0].start_nonce, c[0].start_nonce)
        self.assertEqual(a[0].task_id, 1)
        self.assertEqual(a[-1].task_id, 1000)

    def test_non_overlapping_nonce_ranges(self):
        items = T.make_tasks(50, seed=42, task_size=500)
        for prev, nxt in zip(items, items[1:]):
            self.assertEqual(prev.start_nonce + prev.count, nxt.start_nonce)

    def test_rejects_invalid_args(self):
        with self.assertRaises(ValueError):
            T.make_tasks(10, job_key=b"short")
        with self.assertRaises(ValueError):
            T.make_tasks(-1)
        with self.assertRaises(ValueError):
            T.make_tasks(10, task_size=0)
        with self.assertRaises(ValueError):
            T.make_tasks(10, difficulty_bits=257)


class TestRunTask(unittest.TestCase):
    def test_finds_known_valid_nonce(self):
        found, nonce = T.run_task(T.DEFAULT_JOB_KEY, 0, 20_000, 12)
        self.assertTrue(found)
        digest = hashlib.sha256(T.DEFAULT_JOB_KEY + str(nonce).encode()).digest()
        self.assertEqual(int.from_bytes(digest, "big") >> (256 - 12), 0)

    def test_returns_false_when_not_found_in_range(self):
        # Empty range [0, 0) cannot match
        self.assertEqual(T.run_task(T.DEFAULT_JOB_KEY, 0, 0, 12), (False, 0))

    def test_zero_difficulty_matches_first_nonce(self):
        self.assertEqual(T.run_task(T.DEFAULT_JOB_KEY, 7, 5, 0), (True, 7))


if __name__ == "__main__":
    unittest.main()
