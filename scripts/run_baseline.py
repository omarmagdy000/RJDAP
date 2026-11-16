
import argparse
import csv
import os
import re
import shutil
import statistics
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORT = 9000
WORKERS = 4


def run_once(seed, run_no, tasks, pcap):
    stamp = time.strftime("%Y%m%d_%H%M%S")
    out = os.path.join(ROOT, "results", f"baseline_{stamp}_{seed}_run{run_no}")
    os.makedirs(out, exist_ok=True)
    py = sys.executable
    procs, files, dump = [], [], None
    try:
        if pcap and shutil.which("tcpdump"):
            dump = subprocess.Popen(
                ["sudo", "tcpdump", "-i", "lo", "-w", os.path.join(out, "capture.pcap"),
                 "udp", "port", str(PORT)], stderr=subprocess.DEVNULL)
            time.sleep(0.8)
        sout = open(os.path.join(out, "server_stdout.log"), "w")
        files.append(sout)
        server = subprocess.Popen(
            [py, os.path.join(ROOT, "src", "server.py"), "--host", "127.0.0.1",
             "--port", str(PORT), "--tasks", str(tasks), "--seed", str(seed),
             "--scenario", "baseline", "--run", str(run_no),
             "--log", os.path.join(out, "server.csv")],
            stdout=sout, stderr=subprocess.STDOUT, cwd=ROOT)
        time.sleep(0.5)
        for wid in range(1, WORKERS + 1):
            wout = open(os.path.join(out, f"worker{wid}_stdout.log"), "w")
            files.append(wout)
            procs.append(subprocess.Popen(
                [py, os.path.join(ROOT, "src", "worker.py"), "--id", str(wid),
                 "--server", f"127.0.0.1:{PORT}", "--seed", str(seed),
                 "--scenario", "baseline", "--run", str(run_no),
                 "--log", os.path.join(out, f"worker{wid}.csv"), "--max-idle", "3"],
                stdout=wout, stderr=subprocess.STDOUT, cwd=ROOT))
        server.wait(timeout=300)
        for p in procs:                       # workers stop by themselves after --max-idle
            try:
                p.wait(timeout=15)
            except subprocess.TimeoutExpired:
                p.kill()
    finally:
        for p in procs:
            if p.poll() is None:
                p.kill()
        if dump is not None:
            subprocess.call(["sudo", "kill", "-2", str(dump.pid)])
        for f in files:
            f.close()
    text = open(os.path.join(out, "server_stdout.log")).read()
    num = lambda pat: float(re.search(pat, text).group(1))
    return {
        "seed": seed, "run": run_no,
        "tasks_completed": int(num(r"Tasks completed: (\d+)/")),
        "total_completion_time_s": num(r"Total completion time: ([\d.]+)"),
        "reassigned_task_count": int(num(r"Reassigned tasks: (\d+)")),
        "duplicate_results_dropped": int(num(r"Duplicate results dropped: (\d+)")),
        "worker_idle_time_ms_total": round(sum(
            float(x) for x in re.findall(r"Worker \d+: ([\d.]+) ms", text)), 2),
        "folder": os.path.relpath(out, ROOT),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--runs", type=int, default=1, help="number of runs (seeds 42, 43, ...)")
    ap.add_argument("--seed", type=int, default=42, help="first seed")
    ap.add_argument("--tasks", type=int, default=1000)
    ap.add_argument("--pcap", action="store_true", help="capture capture.pcap (tcpdump, Linux)")
    a = ap.parse_args()
    rows = []
    for i in range(a.runs):
        row = run_once(a.seed + i, i + 1, a.tasks, a.pcap and i < 2)
        print(row)
        rows.append(row)
        time.sleep(1)
    summary = os.path.join(ROOT, "results", "baseline_summary.csv")
    with open(summary, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    t = [r["total_completion_time_s"] for r in rows]
    print(f"completion time s  min/median/max = {min(t):.3f} / {statistics.median(t):.3f} / {max(t):.3f}")
    print(f"summary written to {os.path.relpath(summary, ROOT)}")
    ok = all(r["tasks_completed"] == a.tasks and r["duplicate_results_dropped"] == 0
             and r["reassigned_task_count"] == 0 for r in rows)
    print("BASELINE", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())