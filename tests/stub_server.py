import argparse
import os
import socket
import sys
import time
from collections import deque

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "src"))
import protocol as P  # noqa: E402

JOB_KEY = b"rjdap-job-key-01"
TASK_SIZE = 20000
DIFFICULTY_BITS = 12
HEARTBEAT_MS = 1000
BASE_RTO_MS = 200


def main():
    p = argparse.ArgumentParser(description="RJDAP stub server")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=9000)
    p.add_argument("--tasks", type=int, default=20)
    p.add_argument("--idle-exit", type=float, default=30.0,
                   help="quit if nothing arrives for this many seconds")
    args = p.parse_args()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((args.host, args.port))
    sock.settimeout(0.5)

    pending = deque(range(1, args.tasks + 1))
    done = {}
    in_flight = {}
    per_worker = {}
    duplicates = 0
    started = None
    last_packet = time.monotonic()

    def send(msg_type, addr, worker_id, task_id=0, attempt=0, payload=b""):
        sock.sendto(P.pack(msg_type, worker_id, task_id, attempt, payload), addr)

    def give_task(worker_id, addr):
        if not pending:
            return
        task_id = pending.popleft()
        payload = P.encode_dispatch(JOB_KEY, task_id * TASK_SIZE, TASK_SIZE,
                                    DIFFICULTY_BITS)
        send(P.TASK_DISPATCH, addr, worker_id, task_id, 1, payload)
        in_flight[worker_id] = task_id

    print(f"stub server on {args.host}:{args.port}, {args.tasks} tasks")
    try:
        while len(done) < args.tasks:
            try:
                data, addr = sock.recvfrom(P.MAX_DATAGRAM)
            except socket.timeout:
                if time.monotonic() - last_packet > args.idle_exit:
                    print("idle too long, quitting")
                    break
                continue
            except ConnectionResetError:
                continue
            last_packet = time.monotonic()
            try:
                header, payload = P.unpack(data)
            except P.ProtocolError:
                continue
            wid = header.worker_id

            if header.msg_type == P.WORKER_JOIN:
                if started is None:
                    started = time.monotonic()
                print(f"JOIN from worker {wid}")
                send(P.JOIN_ACK, addr, wid,
                     payload=P.encode_join_ack(HEARTBEAT_MS, BASE_RTO_MS))
                if wid not in in_flight:
                    give_task(wid, addr)

            elif header.msg_type == P.TASK_RESULT:
                if header.task_id in done:
                    duplicates += 1
                else:
                    try:
                        done[header.task_id] = P.decode_result(payload)
                    except P.ProtocolError:
                        continue
                    per_worker[wid] = per_worker.get(wid, 0) + 1
                in_flight.pop(wid, None)
                send(P.ACK_RESULT, addr, wid, header.task_id, header.attempt,
                     P.encode_ack(header.task_id, done))
                give_task(wid, addr)

    except KeyboardInterrupt:
        print("\nstopped with Ctrl+C")

    elapsed = time.monotonic() - started if started else 0.0
    print("---- summary ----")
    print(f"tasks done: {len(done)}/{args.tasks}")
    print(f"duplicate results dropped: {duplicates}")
    print(f"results per worker: {dict(sorted(per_worker.items()))}")
    print(f"elapsed: {elapsed:.2f} s")
    sock.close()


if __name__ == "__main__":
    main()