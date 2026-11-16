
import argparse, os, re, subprocess, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ap = argparse.ArgumentParser()
ap.add_argument("--kill-after", type=float, default=1.0)
ap.add_argument("--task-timeout", type=float, default=0.5)
ap.add_argument("--seed", type=int, default=42)
a = ap.parse_args()
out = os.path.join(ROOT, "results", f"crashcheck_{time.strftime('%Y%m%d_%H%M%S')}_{a.seed}")
os.makedirs(out)
py = sys.executable
sf = open(os.path.join(out, "server_stdout.log"), "w")
srv = subprocess.Popen([py, "src/server.py", "--host", "127.0.0.1", "--seed", str(a.seed),
                        "--scenario", "crashcheck", "--task-timeout", str(a.task_timeout),
                        "--log", os.path.join(out, "server.csv")], cwd=ROOT, stdout=sf, stderr=subprocess.STDOUT)
time.sleep(0.5)
ws = [subprocess.Popen([py, "src/worker.py", "--id", str(i), "--seed", str(a.seed), "--scenario", "crashcheck",
                        "--log", os.path.join(out, f"worker{i}.csv"), "--max-idle", "3"], cwd=ROOT,
                       stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT) for i in range(1, 5)]
time.sleep(a.kill_after)
ws[0].kill()
print(f"killed worker 1 after {a.kill_after}s")
srv.wait(timeout=300)
for w in ws[1:]:
    try: w.wait(timeout=15)
    except subprocess.TimeoutExpired: w.kill()
sf.close()
t = open(os.path.join(out, "server_stdout.log")).read()
g = lambda p: re.search(p, t).group(1)
done, re_n, dup = g(r"Tasks completed: (\d+)/"), g(r"Reassigned tasks: (\d+)"), g(r"Duplicate results dropped: (\d+)")
print(f"completed {done}/1000, reassigned {re_n}, duplicates dropped {dup}, time {g(r'Total completion time: ([\d.]+)')} s")
print("CRASH CHECK", "PASS" if done == "1000" and int(re_n) >= 1 else "FAIL", "->", os.path.relpath(out, ROOT))