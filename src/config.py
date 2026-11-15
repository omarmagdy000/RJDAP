"""Shared config: ports, timeout, seed. Shared file (PR with pair approval).

Everyone imports these numbers instead of typing them in their own file,
so the server, the workers and the scripts always agree.
Values match tests/stub_server.py.
"""

# network
SERVER_HOST = "127.0.0.1"
SERVER_PORT = 9000

# experiment
SEEDS = [42, 43, 44, 45, 46]   # 5 runs per scenario, one seed each
DEFAULT_SEED = 42
NUM_TASKS = 1000               # brief: at least 1,000 tasks
NUM_WORKERS = 4                # brief: at least 4 workers

# the task itself (N = nonces per task, D = difficulty in bits)
JOB_KEY = b"rjdap-job-key-01"  # 16 bytes
TASK_SIZE_N = 20000
DIFFICULTY_BITS_D = 12

# timers (milliseconds)
HEARTBEAT_MS = 1000            # worker sends HEARTBEAT every second
DEAD_AFTER_HEARTBEATS = 3      # no heartbeat for 3 intervals -> worker is dead
BASE_RTO_MS = 200              # starting task timeout before the adaptive RTO kicks in
MAX_RESULT_RETRIES = 5         # worker resends a result at most 5 times

# where logs go
RESULTS_DIR = "results"
