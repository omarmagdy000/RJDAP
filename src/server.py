import argparse
import socket
import time
from collections import deque

import protocol as P
import tasks
from logger import Logger

HEARTBEAT_MS = 1000
BASE_RTO_MS = 200
SOCKET_TIMEOUT = 0.05
TASK_TIMEOUT = 2.0
MAX_ATTEMPTS = 255


class Server:
    def __init__(self, args):
        self.args = args

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((args.host, args.port))
        self.sock.settimeout(SOCKET_TIMEOUT)

        self.log = Logger(
            args.log, "server", "server", args.seed, args.scenario, args.run
        )

        # Worker ID -> worker information.
        self.workers = {}

        # Task IDs waiting to be dispatched.
        self.pending = deque(range(1, args.tasks + 1))
        self.task_list = {t.task_id: t for t in tasks.make_tasks(args.tasks, args.seed)}

        # Task ID -> task information.
        self.tasks = {}

        for task_id in range(1, args.tasks + 1):
            self.tasks[task_id] = {
                "state": "PENDING",
                "attempt": 0,
                "worker_id": None,
                "sent_at": None,
                "result": None,
                "avoid": None,
            }

        self.done = set()
        self.started_at = None
        self.finished_at = None

        self.reassigned_task_count = 0
        self.duplicate_results_dropped = 0

        self.worker_idle_time = {}

    # ---------------------------------------------------------
    # Packet sending and receiving
    # ---------------------------------------------------------

    def send(self, msg_type, worker_id, addr, task_id=0,
             attempt=0, payload=b"", flags=0):

        packet = P.pack(
            msg_type,
            worker_id,
            task_id,
            attempt,
            payload,
            flags,
        )

        self.sock.sendto(packet, addr)

        self.log.event(
            "send", msg_type, task_id, worker_id,
            attempt, len(packet)
        )

    def receive(self):
        try:
            data, addr = self.sock.recvfrom(P.MAX_DATAGRAM)
        except socket.timeout:
            return None
        except ConnectionResetError:
            return None

        try:
            header, payload = P.unpack(data)
        except P.ProtocolError:
            self.log.event("drop", 0, 0, 0, 0, len(data))
            return None

        self.log.event(
            "recv",
            header.msg_type,
            header.task_id,
            header.worker_id,
            header.attempt,
            len(data),
        )

        return header, payload, addr

    # ---------------------------------------------------------
    # Worker registration
    # ---------------------------------------------------------

    def register_worker(self, header, addr):
        worker_id = header.worker_id

        # Update the address in case the worker reconnected.
        if worker_id not in self.workers:
            self.workers[worker_id] = {
                "addr": addr,
                "busy_task": None,
                "last_seen": time.monotonic(),
                "idle_since": time.monotonic(),
                "idle_total": 0.0,
            }
            self.worker_idle_time[worker_id] = 0.0
            print(f"[server] Worker {worker_id} joined from {addr}")
        else:
            self.workers[worker_id]["addr"] = addr
            self.workers[worker_id]["last_seen"] = time.monotonic()

        worker = self.workers[worker_id]

        # Tell the worker the heartbeat and retransmission settings.
        self.send(
            P.JOIN_ACK,
            worker_id,
            addr,
            payload=P.encode_join_ack(HEARTBEAT_MS, BASE_RTO_MS),
        )

        # A repeated JOIN must not cause a second task assignment.
        if worker["busy_task"] is None:
            self.dispatch_tasks()

    # ---------------------------------------------------------
    # Task dispatch
    # ---------------------------------------------------------

    def dispatch_to_worker(self, worker_id):
        worker = self.workers[worker_id]

        if worker["busy_task"] is not None or not self.pending:
            return False

        task_id = self.pending[0]
        task = self.tasks[task_id]

        # Don't hand a timed-out task straight back to the worker that failed it.
        if task["avoid"] == worker_id and len(self.workers) > 1:
            return False
        self.pending.popleft()

        if task["attempt"] >= MAX_ATTEMPTS:
            raise RuntimeError(
                f"Task {task_id} reached the maximum attempt count"
            )

        task["attempt"] += 1
        attempt = task["attempt"]

        # If this task has already been dispatched before,
        # it is being reassigned.
        if attempt > 1:
            self.reassigned_task_count += 1

        t = self.task_list[task_id]
        payload = P.encode_dispatch(t.job_key, t.start_nonce, t.count, t.difficulty_bits)

        self.send(
            P.TASK_DISPATCH,
            worker_id,
            worker["addr"],
            task_id,
            attempt,
            payload,
            flags=P.FLAG_RETX if attempt > 1 else 0,
        )

        task["state"] = "DISPATCHED"
        task["worker_id"] = worker_id
        task["sent_at"] = time.monotonic()

        worker["busy_task"] = task_id
        worker["last_seen"] = time.monotonic()

        if worker["idle_since"] is not None:
            idle = time.monotonic() - worker["idle_since"]
            worker["idle_total"] += idle
            self.worker_idle_time[worker_id] = worker["idle_total"]
            worker["idle_since"] = None

        print(
            f"[server] Dispatched task {task_id} "
            f"to worker {worker_id}, attempt {attempt}"
        )

        return True

    def dispatch_tasks(self):
        for worker_id in list(self.workers):
            if not self.pending:
                break
            self.dispatch_to_worker(worker_id)

    # ---------------------------------------------------------
    # Result handling
    # ---------------------------------------------------------

    def handle_result(self, header, payload, addr):
        task_id = header.task_id
        worker_id = header.worker_id

        if task_id not in self.tasks:
            print(f"[server] Ignored unknown task {task_id}")
            return

        try:
            result = P.decode_result(payload)
        except P.ProtocolError:
            print(f"[server] Invalid result for task {task_id}")
            return

        # A result is accepted only once.
        if task_id in self.done:
            self.duplicate_results_dropped += 1
            self.log.event("dup", header.msg_type, task_id, worker_id, header.attempt, 0)
            print(f"[server] Duplicate result dropped: task {task_id}")

        else:
            self.done.add(task_id)
            self.tasks[task_id]["state"] = "DONE"
            self.tasks[task_id]["result"] = result

            print(
                f"[server] Task {task_id} completed "
                f"by worker {worker_id}"
            )

        # Release this worker only if it is still assigned this task.
        worker = self.workers.get(worker_id)

        if worker is not None:
            worker["last_seen"] = time.monotonic()

            if worker["busy_task"] == task_id:
                worker["busy_task"] = None
                worker["idle_since"] = time.monotonic()

        # ACK even duplicates. This is important if the original ACK
        # was lost and the worker is still waiting for confirmation.
        self.send(
            P.ACK_RESULT,
            worker_id,
            addr,
            task_id,
            header.attempt,
            P.encode_ack(task_id, self.done),
        )

        self.dispatch_tasks()

        if len(self.done) == self.args.tasks:
            self.finished_at = time.monotonic()

    # ---------------------------------------------------------
    # Timeout and reassignment
    # ---------------------------------------------------------

    def check_timeouts(self):
        now = time.monotonic()

        for task_id, task in self.tasks.items():
            if task["state"] != "DISPATCHED":
                continue

            if now - task["sent_at"] < self.args.task_timeout:
                continue

            worker_id = task["worker_id"]
            worker = self.workers.get(worker_id)

            print(
                f"[server] Timeout: task {task_id} "
                f"from worker {worker_id}"
            )
            self.log.event("reassign", P.TASK_DISPATCH, task_id, worker_id, task["attempt"], 0)

            # Release the old worker's assignment if it still matches.
            if worker is not None and worker["busy_task"] == task_id:
                worker["busy_task"] = None
                worker["idle_since"] = now

            task["avoid"] = worker_id
            task["state"] = "PENDING"
            task["worker_id"] = None
            task["sent_at"] = None

            # Put the task back at the front so it can be reassigned.
            self.pending.appendleft(task_id)

        self.dispatch_tasks()

    # ---------------------------------------------------------
    # Main server loop
    # ---------------------------------------------------------

    def run(self):
        print(
            f"[server] Listening on {self.args.host}:{self.args.port}"
        )
        print(f"[server] Waiting to process {self.args.tasks} tasks")

        try:
            while len(self.done) < self.args.tasks:
                if self.started_at is None and self.workers:
                    self.started_at = time.monotonic()

                if (
                    self.started_at is not None
                    and time.monotonic() - self.started_at
                    > self.args.max_runtime
                ):
                    print("[server] Maximum runtime reached")
                    break

                packet = self.receive()

                if packet is not None:
                    header, payload, addr = packet

                    if header.msg_type == P.WORKER_JOIN:
                        if self.started_at is None:
                            self.started_at = time.monotonic()
                        self.register_worker(header, addr)

                    elif header.msg_type == P.TASK_RESULT:
                        self.handle_result(header, payload, addr)

                self.check_timeouts()

        except KeyboardInterrupt:
            print("\n[server] Stopped with Ctrl+C")

        finally:
            self.print_summary()
            self.close()


    def print_summary(self):
        elapsed = (
            self.finished_at - self.started_at
            if self.finished_at is not None and self.started_at is not None
            else 0.0
        )

        print("\n========== SERVER SUMMARY ==========")
        print(f"Tasks completed: {len(self.done)}/{self.args.tasks}")
        print(f"Tasks remaining: {self.args.tasks - len(self.done)}")
        print(f"Reassigned tasks: {self.reassigned_task_count}")
        print(
            f"Duplicate results dropped: "
            f"{self.duplicate_results_dropped}"
        )
        print(f"Total completion time: {elapsed:.3f} seconds")

        print("\nWorker idle times:")
        for worker_id, worker in sorted(self.workers.items()):
            idle = worker["idle_total"]

            if worker["idle_since"] is not None:
                idle += time.monotonic() - worker["idle_since"]

            print(f"  Worker {worker_id}: {idle * 1000:.2f} ms")

        print("====================================")

    def close(self):
        self.log.close()
        self.sock.close()


def main():
    parser = argparse.ArgumentParser(
        description="RJDAP Command Hub (R2 Server)"
    )

    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=9000)
    parser.add_argument("--tasks", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--scenario", default="baseline")
    parser.add_argument("--run", type=int, default=1)
    parser.add_argument(
        "--log",
        default="results/phase1_server.csv",
    )
    parser.add_argument(
        "--task-timeout",
        type=float,
        default=TASK_TIMEOUT,
    )
    parser.add_argument(
        "--max-runtime",
        type=float,
        default=300.0,
    )

    args = parser.parse_args()

    if args.tasks < 1:
        parser.error("--tasks must be at least 1")

    if args.task_timeout <= 0:
        parser.error("--task-timeout must be positive")

    server = Server(args)
    server.run()


if __name__ == "__main__":
    main()