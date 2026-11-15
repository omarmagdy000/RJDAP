"""Compute metrics, min/median/max. Owner: R5.

Reads every run folder under results/ (one folder per run, as R4's
run_experiment.sh makes them), works out the 4 metrics from the brief,
then min / median / max per scenario.

Run from the repo root:
    python analysis/aggregate.py               # reads ./results
    python analysis/aggregate.py some/folder   # reads another folder

Writes:
    <folder>/runs.csv      one row per run
    <folder>/workers.csv   one row per worker per run
    <folder>/summary.csv   min / median / max per scenario  <- this goes in the report

How each metric is found in the logs (log schema is in src/logger.py):
    total_completion_time_ms   server: first "send TASK_DISPATCH" to the moment
                               the last task got its first "recv TASK_RESULT"
    reassigned_task_count      server: number of "reassign" lines
    duplicate_results_dropped  server: number of "dup" lines
    worker_idle_time_ms        worker: time alive minus time computing, where
                               computing = from "recv TASK_DISPATCH" to the
                               first "send TASK_RESULT" for that same task
"""

import glob
import os
import sys

import pandas as pd

RESULTS = sys.argv[1] if len(sys.argv) > 1 else "results"


def load_folder(folder):
    """Read every CSV log in one run folder into one table."""
    parts = []
    for path in glob.glob(os.path.join(folder, "*.csv")):
        df = pd.read_csv(path)
        if "role" in df.columns:          # skip anything that is not a log
            parts.append(df)
    return pd.concat(parts, ignore_index=True) if parts else None


def worker_times(w):
    """busy and idle time (ms) for one worker's log lines."""
    got = w[(w["event"] == "recv") & (w["msg_type"] == "TASK_DISPATCH")]
    sent = w[(w["event"] == "send") & (w["msg_type"] == "TASK_RESULT")]
    start = got.groupby("task_id")["ts_us"].min()     # first time we got the task
    end = sent.groupby("task_id")["ts_us"].min()      # first time we sent its result
    both = pd.concat([start, end], axis=1, keys=["s", "e"]).dropna()
    busy_us = (both["e"] - both["s"]).clip(lower=0).sum()
    alive_us = w["ts_us"].max() - w["ts_us"].min()
    return len(both), busy_us / 1000, (alive_us - busy_us) / 1000


def one_run(df):
    """Return (run_row, worker_rows) for one run's log table."""
    first = df.iloc[0]
    info = {"scenario": first["scenario"], "seed": int(first["seed"]), "run": int(first["run"])}

    s = df[df["role"] == "server"]
    results_in = s[(s["event"] == "recv") & (s["msg_type"] == "TASK_RESULT")]
    first_dispatch = s[(s["event"] == "send") & (s["msg_type"] == "TASK_DISPATCH")]["ts_us"].min()
    done_at = results_in.groupby("task_id")["ts_us"].min()   # when each task became DONE

    row = dict(info)
    row["tasks_done"] = len(done_at)
    row["total_completion_time_ms"] = (done_at.max() - first_dispatch) / 1000 if len(done_at) else None
    row["reassigned_task_count"] = int((s["event"] == "reassign").sum())
    row["duplicate_results_dropped"] = int((s["event"] == "dup").sum())

    workers = []
    for node, w in df[df["role"] == "worker"].groupby("node"):
        n, busy, idle = worker_times(w)
        workers.append({**info, "worker": node, "tasks_computed": n,
                        "busy_ms": busy, "worker_idle_time_ms": idle})
    row["worker_idle_time_ms"] = (sum(x["worker_idle_time_ms"] for x in workers) / len(workers)
                                  if workers else None)
    return row, workers


def main():
    folders = sorted({os.path.dirname(p) for p in
                      glob.glob(os.path.join(RESULTS, "**", "*.csv"), recursive=True)})
    runs, workers = [], []
    for f in folders:
        df = load_folder(f)
        if df is None or not (df["role"] == "server").any():
            continue                      # not a run folder (e.g. results/ itself)
        r, w = one_run(df)
        runs.append(r)
        workers += w
    if not runs:
        sys.exit(f"No run folders with a server log found under {RESULTS}/")

    runs = pd.DataFrame(runs).sort_values(["scenario", "run"])
    runs.to_csv(os.path.join(RESULTS, "runs.csv"), index=False)
    pd.DataFrame(workers).to_csv(os.path.join(RESULTS, "workers.csv"), index=False)

    metrics = ["total_completion_time_ms", "reassigned_task_count",
               "duplicate_results_dropped", "worker_idle_time_ms"]
    summary = runs.groupby("scenario")[metrics].agg(["min", "median", "max"])
    summary.columns = [f"{m}_{stat}" for m, stat in summary.columns]
    summary.insert(0, "runs", runs.groupby("scenario").size())
    summary.to_csv(os.path.join(RESULTS, "summary.csv"))

    print(f"Read {len(runs)} runs from {RESULTS}/\n")
    for scen, g in runs.groupby("scenario"):
        print(f"{scen}: {len(g)} runs")
        for m in metrics:
            print(f"   {m:28s} min {g[m].min():>10.1f}   median {g[m].median():>10.1f}   max {g[m].max():>10.1f}")
    short = runs[runs["tasks_done"] < runs["tasks_done"].max()]
    if len(short):
        print("\nWARNING: these runs did not finish every task:")
        print(short[["scenario", "run", "tasks_done"]].to_string(index=False))


if __name__ == "__main__":
    main()
