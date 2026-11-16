import argparse
import os
import socket
import sys
import time
from collections import deque

import protocol as P
import tasks
from logger import Logger


class Worker:
    ACK_WAIT = 2.0

    def __init__(self, args):
        host, port = args.server.rsplit(":", 1)
        self.server = (host, int(port))
        self.id = args.id
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.settimeout(0.5)
        self.log = Logger(args.log, f"worker{args.id}", "worker", args.seed,
                          args.scenario, args.run)
        self.backlog = deque()
        self.heartbeat_ms = 1000
        self.base_rto_ms = 200
        self.tasks_done = 0
        self.compute_s = 0.0

    def send(self, msg_type, task_id=0, attempt=0, payload=b"", flags=0):
        data = P.pack(msg_type, self.id, task_id, attempt, payload, flags)
        self.sock.sendto(data, self.server)
        self.log.event("send", msg_type, task_id, self.id, attempt, len(data))

    def receive(self):
        try:
            data, _addr = self.sock.recvfrom(P.MAX_DATAGRAM)
        except socket.timeout:
            return None
        except ConnectionResetError:
            time.sleep(0.2)
            return None
        try:
            header, payload = P.unpack(data)
        except P.ProtocolError:
            self.log.event("drop", 0, 0, self.id, 0, len(data))
            return None
        self.log.event("recv", header.msg_type, header.task_id,
                       header.worker_id, header.attempt, len(data))
        return header, payload

    def join(self, tries):
        for n in range(1, tries + 1):
            self.send(P.WORKER_JOIN)
            got = self.receive()
            if got is None:
                print(f"[worker{self.id}] no answer yet (JOIN try {n}/{tries})")
                continue
            header, payload = got
            if header.msg_type == P.JOIN_ACK:
                try:
                    info = P.decode_join_ack(payload)
                    self.heartbeat_ms = info.heartbeat_ms
                    self.base_rto_ms = info.base_rto_ms
                except P.ProtocolError:
                    pass
                return True
            if header.msg_type == P.TASK_DISPATCH:
                self.backlog.append(got)
                return True
        return False

    def handle_task(self, header, payload):
        try:
            task = P.decode_dispatch(payload)
        except P.ProtocolError:
            self.log.event("drop", header.msg_type, header.task_id, self.id,
                           header.attempt, len(payload))
            return False

        t0 = time.perf_counter()
        found, nonce = tasks.run_task(task.job_key, task.start_nonce, task.count,
                                      task.difficulty_bits)
        compute_s = time.perf_counter() - t0
        self.compute_s += compute_s
        self.tasks_done += 1

        self.send(P.TASK_RESULT, header.task_id, header.attempt,
                  P.encode_result(found, nonce, int(compute_s * 1_000_000)))

        deadline = time.monotonic() + self.ACK_WAIT
        while time.monotonic() < deadline:
            got = self.receive()
            if got is None:
                continue
            reply, reply_payload = got
            if reply.msg_type == P.ACK_RESULT:
                try:
                    confirmed = P.decode_ack(reply.task_id, reply_payload)
                except P.ProtocolError:
                    continue
                if header.task_id in confirmed:
                    return True
            elif reply.msg_type == P.TASK_DISPATCH:
                self.backlog.append(got)
        self.log.event("timeout", P.TASK_RESULT, header.task_id, self.id,
                       header.attempt, 0)
        print(f"[worker{self.id}] no ACK for task {header.task_id}")
        return False

    def run(self, max_idle):
        last_activity = time.monotonic()
        while True:
            got = self.backlog.popleft() if self.backlog else self.receive()
            if got is None:
                if time.monotonic() - last_activity > max_idle:
                    print(f"[worker{self.id}] idle for {max_idle}s, stopping")
                    return
                continue
            last_activity = time.monotonic()
            header, payload = got
            if header.msg_type == P.TASK_DISPATCH:
                self.handle_task(header, payload)
                last_activity = time.monotonic()

    def close(self):
        self.log.close()
        self.sock.close()


def self_check():
    print(f"protocol.py: {P.PROTOCOL_NAME} v{P.VERSION}, "
          f"header {P.HEADER_SIZE} bytes, max payload {P.MAX_PAYLOAD}")
    for code, name in sorted(P.MSG_NAMES.items()):
        print(f"  {name:14s} = {code}")
    key = b"0123456789abcdef"
    payload = P.encode_dispatch(key, 100, 50, 8)
    datagram = P.pack(P.TASK_DISPATCH, 3, 77, 2, payload)
    header, body = P.unpack(datagram)
    task = P.decode_dispatch(body)
    ok = (header.task_id == 77 and header.worker_id == 3 and header.attempt == 2
          and task.job_key == key and task.start_nonce == 100
          and task.count == 50 and task.difficulty_bits == 8)
    print("pack/unpack round trip:", "OK" if ok else "FAILED")
    found, nonce = tasks.run_task(key, 0, 100000, 12)
    print(f"run_task test: found={found}, nonce={nonce}")
    return 0 if ok else 1


def main():
    p = argparse.ArgumentParser(description="RJDAP worker (R3, Phase 1)")
    p.add_argument("--id", type=int, help="worker id, e.g. 1")
    p.add_argument("--server", default="127.0.0.1:9000")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--scenario", default="baseline")
    p.add_argument("--run", type=int, default=1)
    p.add_argument("--log", default=None, help="CSV log path")
    p.add_argument("--max-idle", type=float, default=10.0,
                   help="stop after this many seconds with no packets")
    p.add_argument("--join-tries", type=int, default=20)
    p.add_argument("--check", action="store_true",
                   help="show protocol constants, run a self-test and exit")
    args = p.parse_args()

    if args.check:
        sys.exit(self_check())
    if args.id is None:
        p.error("--id is required")
    if args.log is None:
        args.log = os.path.join("results", f"phase1_worker{args.id}.csv")

    worker = Worker(args)
    print(f"[worker{args.id}] talking to {worker.server}, log: {args.log}")
    try:
        if not worker.join(args.join_tries):
            print(f"[worker{args.id}] server never answered; is it running?")
            sys.exit(1)
        print(f"[worker{args.id}] joined (heartbeat {worker.heartbeat_ms} ms, "
              f"base RTO {worker.base_rto_ms} ms)")
        worker.run(args.max_idle)
    except KeyboardInterrupt:
        print(f"\n[worker{args.id}] stopped with Ctrl+C")
    finally:
        print(f"[worker{args.id}] tasks done: {worker.tasks_done}, "
              f"compute time: {worker.compute_s * 1000:.0f} ms")
        worker.close()


if __name__ == "__main__":
    main()