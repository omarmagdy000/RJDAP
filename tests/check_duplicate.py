#!/usr/bin/env python3
"""Manual duplicate-result check: a fake worker sends the same TASK_RESULT twice.
Expected: hub counts the task once, logs 1 duplicate, and ACKs both copies.
Run from the repo root:  python3 tests/check_duplicate.py
"""
import os, socket, subprocess, sys, time
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
import protocol as P

port = 9055
srv = subprocess.Popen([sys.executable, "src/server.py", "--host", "127.0.0.1", "--port", str(port), "--tasks", "2",
                        "--log", os.path.join(ROOT, "results", "dupcheck_server.csv")], cwd=ROOT,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
time.sleep(0.5)
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.settimeout(2)
s.sendto(P.pack(P.WORKER_JOIN, 7), ("127.0.0.1", port))
got = {}
while P.TASK_DISPATCH not in got:
    h, pl = P.unpack(s.recvfrom(P.MAX_DATAGRAM)[0]); got[h.msg_type] = h
tid = got[P.TASK_DISPATCH].task_id
res = P.pack(P.TASK_RESULT, 7, tid, 1, P.encode_result(True, 123, 1000))
acks, extra = 0, []
def drain():
    global acks
    while True:
        try:
            h, pl = P.unpack(s.recvfrom(P.MAX_DATAGRAM)[0])
        except socket.timeout:
            return
        if h.msg_type == P.ACK_RESULT: acks += 1
        elif h.msg_type == P.TASK_DISPATCH: extra.append(h.task_id)
        s.settimeout(0.3)
for _ in range(2):                       # same result twice (simulates lost ACK + retransmit)
    s.sendto(res, ("127.0.0.1", port)); s.settimeout(2); drain()
for t in extra:                          # finish the 2nd task so the hub can exit
    s.sendto(P.pack(P.TASK_RESULT, 7, t, 1, P.encode_result(True, 9, 1000)), ("127.0.0.1", port))
s.settimeout(1); drain()
out = srv.communicate(timeout=10)[0]
dups = int([l for l in out.splitlines() if "Duplicate results dropped" in l][0].split(":")[1])
done = [l for l in out.splitlines() if "Tasks completed" in l][0]
print(done, "| duplicates dropped:", dups, "| ACKs received:", acks)
print("DUPLICATE CHECK", "PASS" if dups == 1 and acks >= 3 else "FAIL")