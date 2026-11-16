"""Regenerate all figures from CSVs. Owner: R5.

Run AFTER aggregate.py. Reads <folder>/runs.csv and <folder>/workers.csv and
saves 4 figures into docs/report/figures/. Same data in -> same pictures out.

Run from the repo root:
    python analysis/make_plots.py              (reads ./results)
    python analysis/make_plots.py some/folder

Loss scenarios must be named like loss0, loss2, loss5, loss10, loss15
so the script can read the loss % from the name.
"""

import os
import re
import sys

import matplotlib
matplotlib.use("Agg")                  # works without a screen
import matplotlib.pyplot as plt
import pandas as pd

RESULTS = sys.argv[1] if len(sys.argv) > 1 else "results"
OUT = os.path.join("docs", "report", "figures")
os.makedirs(OUT, exist_ok=True)

runs = pd.read_csv(os.path.join(RESULTS, "runs.csv"))
workers = pd.read_csv(os.path.join(RESULTS, "workers.csv"))


def med_range(df, by, col):
    """median plus the distance down to min and up to max (for error bars)."""
    g = df.groupby(by)[col]
    med = g.median()
    return med, [med - g.min(), g.max() - med]


saved = []


def save(name):
    plt.tight_layout()
    plt.savefig(os.path.join(OUT, name), dpi=150)
    plt.close()
    saved.append(name)


# 1) completion time per scenario
main_scen = [s for s in ["baseline", "crash", "loss10", "delayed_ack"]
             if s in set(runs["scenario"])]
if main_scen:
    d = runs[runs["scenario"].isin(main_scen)]
    med, err = med_range(d, "scenario", "total_completion_time_ms")
    med, err = med.reindex(main_scen), [e.reindex(main_scen) for e in err]
    plt.figure(figsize=(6, 4))
    plt.bar(med.index, med.values / 1000, yerr=[e / 1000 for e in err],
            capsize=5, color="#3b6ea5")
    plt.ylabel("Total completion time (s)")
    plt.title("Completion time per scenario\n(bar = median, line = min to max)")
    save("completion_time_per_scenario.png")

# 2) and 3) loss % vs reassigned / duplicates (baseline counts as 0% loss)
def loss_of(s):
    m = re.fullmatch(r"loss(\d+)", s)
    return int(m.group(1)) if m else (0 if s == "baseline" else None)


runs["loss_pct"] = runs["scenario"].map(loss_of)
lossruns = runs.dropna(subset=["loss_pct"])
if lossruns["loss_pct"].nunique() > 1:          # need at least 2 loss levels for a line
    for col, name, label in [
            ("reassigned_task_count", "loss_vs_reassigned.png", "Reassigned tasks"),
            ("duplicate_results_dropped", "loss_vs_duplicates.png", "Duplicate results dropped")]:
        med, err = med_range(lossruns, "loss_pct", col)
        plt.figure(figsize=(6, 4))
        plt.errorbar(med.index, med.values, yerr=err, marker="o", capsize=5, color="#b0452a")
        plt.xlabel("Packet loss (%)")
        plt.ylabel(label)
        plt.title(f"Network loss vs {label.lower()}\n(median of the runs, line = min to max)")
        plt.grid(alpha=.3)
        save(name)

# 4) computing vs idle time per worker (baseline, median over runs)
b = workers[workers["scenario"] == "baseline"]
if len(b):
    b = b.groupby("worker")[["busy_ms", "worker_idle_time_ms"]].median()
    plt.figure(figsize=(6, 4))
    plt.bar(b.index, b["busy_ms"] / 1000, label="computing", color="#3b6ea5")
    plt.bar(b.index, b["worker_idle_time_ms"] / 1000, bottom=b["busy_ms"] / 1000,
            label="idle / waiting", color="#c9d3e0")
    plt.ylabel("Time (s)")
    plt.title("Baseline: how each worker spent its time")
    plt.legend()
    save("idle_time_per_worker.png")

print(f"Saved {len(saved)} plots in {OUT}/: " + ", ".join(saved))
if len(saved) < 4:
    print("(some plots were skipped because those scenarios have no runs yet)")
