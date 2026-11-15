"""CSV packet logger. Owner: R5.

One line per packet event, using the schema the team froze in PROJECT_GUIDE.md:

    ts_us,node,role,event,msg_type,task_id,worker_id,attempt,bytes,seed,scenario,run

event is one of:
    send      we sent a packet
    recv      we received a packet
    drop      we threw a packet away (bad checksum, bad payload)
    timeout   we waited for something and it never came
    reassign  (server) a task timed out and is given out again
    dup       (server) a TASK_RESULT arrived for a task that is already DONE

msg_type can be the number from protocol.py (it gets turned into its name,
e.g. 4 -> TASK_DISPATCH) or already a string.

How to use it (server example):

    from logger import Logger
    log = Logger("results/baseline_run1/server.csv", node="server", role="server",
                 seed=42, scenario="baseline", run=1)
    log.event("send", P.TASK_DISPATCH, task_id=7, worker_id=2, attempt=1, nbytes=len(data))
    log.close()

Every line is written to disk straight away (buffering=1), so even if a
worker is killed with kill -9 in the crash test, its log is not lost.
"""

import os
import time

import protocol as P

COLUMNS = ("ts_us,node,role,event,msg_type,task_id,worker_id,attempt,"
           "bytes,seed,scenario,run")
EVENTS = ("send", "recv", "drop", "timeout", "reassign", "dup")


class Logger:
    def __init__(self, path, node, role, seed, scenario, run):
        folder = os.path.dirname(path)
        if folder:
            os.makedirs(folder, exist_ok=True)
        is_new = not os.path.exists(path) or os.path.getsize(path) == 0
        self.file = open(path, "a", buffering=1, encoding="utf-8")
        self.node, self.role = node, role
        self.seed, self.scenario, self.run = seed, scenario, run
        if is_new:
            self.file.write(COLUMNS + "\n")

    def event(self, event, msg_type, task_id=0, worker_id=0, attempt=0, nbytes=0):
        if event not in EVENTS:
            raise ValueError(f"unknown log event {event!r}, use one of {EVENTS}")
        ts_us = time.time_ns() // 1000  # microseconds
        name = P.MSG_NAMES.get(msg_type, str(msg_type))
        self.file.write(
            f"{ts_us},{self.node},{self.role},{event},{name},{task_id},"
            f"{worker_id},{attempt},{nbytes},{self.seed},{self.scenario},{self.run}\n")

    def close(self):
        self.file.close()
