"""Practice data for aggregate.py and make_plots.py. Owner: R5.

ONLY for testing the analysis before the real server is finished.
It writes per-packet logs in exactly the same format as src/logger.py,
into fake_results/ (not results/, so it never mixes with real data).

Run from the repo root:
    python analysis/fake_data.py
    python analysis/aggregate.py fake_results
    python analysis/make_plots.py fake_results
Then delete fake_results/ and docs/report/figures/ (fake pictures).
"""

import os
import random

COLUMNS = ("ts_us,node,role,event,msg_type,task_id,worker_id,attempt,"
           "bytes,seed,scenario,run")

SCENARIOS = {  # name: (loss, extra delay ms on server packets, crash worker 1?)
    "baseline": (0, 0, False), "crash": (0, 0, True),
    "loss10": (.10, 0, False), "delayed_ack": (0, 150, False),
    "loss2": (.02, 0, False), "loss5": (.05, 0, False), "loss15": (.15, 0, False),
}
TASKS = 1000
RTO_US = 200_000


def fake_run(scenario, seed, run):
    loss, delay_ms, crash = SCENARIOS[scenario]
    delay = delay_ms * 1000
    rnd = random.Random(seed)
    logs = {"server": []}
    logs.update({f"worker{w}": [] for w in range(1, 5)})

    def line(node, ts, event, msg, task=0, wid=0, att=0, nbytes=14):
        role = "server" if node == "server" else "worker"
        logs[node].append((ts, f"{ts},{node},{role},{event},{msg},{task},{wid},"
                               f"{att},{nbytes},{seed},{scenario},{run}"))

    t0 = 1_800_000_000_000_000
    free = {w: t0 for w in range(1, 5)}
    dead = set()
    for w in free:
        line(f"worker{w}", t0, "send", "WORKER_JOIN", wid=w)
        line("server", t0 + 50, "recv", "WORKER_JOIN", wid=w)

    for task in range(1, TASKS + 1):
        attempt = 1
        w = min((x for x in free if x not in dead), key=free.get)
        if crash and task == TASKS // 2:       # worker 1 dies holding this task
            w, dead = 1, {1}
        t = free[w] + rnd.randint(100, 400)
        while True:
            line("server", t, "send", "TASK_DISPATCH", task, w, attempt, 47)
            if w in dead or rnd.random() < loss:          # dispatch lost / worker dead
                t += RTO_US
                line("server", t, "reassign", "TASK_DISPATCH", task, w, attempt)
                attempt += 1
                w = min((x for x in free if x not in dead), key=free.get)
                t = max(t, free[w])
                continue
            break
        t += 80 + delay
        line(f"worker{w}", t, "recv", "TASK_DISPATCH", task, w, attempt, 47)
        t += rnd.randint(1500, 3000)                       # computing
        line(f"worker{w}", t, "send", "TASK_RESULT", task, w, attempt, 27)
        sends = 1
        while rnd.random() < loss and sends < 5:           # result lost, resend
            t += RTO_US
            line(f"worker{w}", t, "send", "TASK_RESULT", task, w, attempt, 27)
            sends += 1
        t += 80
        line("server", t, "recv", "TASK_RESULT", task, w, attempt, 27)
        line("server", t + 20, "send", "ACK_RESULT", task, w, attempt, 18)
        if rnd.random() < loss:                            # ACK lost -> duplicate result
            line(f"worker{w}", t + RTO_US, "send", "TASK_RESULT", task, w, attempt, 27)
            line("server", t + RTO_US + 80, "recv", "TASK_RESULT", task, w, attempt, 27)
            line("server", t + RTO_US + 81, "dup", "TASK_RESULT", task, w, attempt, 27)
        line(f"worker{w}", t + 100 + delay, "recv", "ACK_RESULT", task, w, attempt, 18)
        free[w] = t + 100 + delay

    folder = os.path.join("fake_results", f"{scenario}_fake_{seed}_run{run}")
    os.makedirs(folder, exist_ok=True)
    for node, rows in logs.items():
        with open(os.path.join(folder, f"{node}.csv"), "w") as f:
            f.write(COLUMNS + "\n")
            f.write("\n".join(r for _, r in sorted(rows)) + "\n")


if __name__ == "__main__":
    for scen in SCENARIOS:
        for run, seed in enumerate([42, 43, 44, 45, 46], start=1):
            fake_run(scen, seed, run)
    print("Fake logs written to fake_results/")
