#!/usr/bin/env bash
set -euo pipefail

SEEDS=(42 43 44 45 46)
CORE_SCARIOS=("baseline" "loss10" "delayed_ack" "crash")
SWEEP_SCARIOS=("loss2" "loss5" "loss15")

mkdir -p results

{
  echo "=== Environment Info ==="
  date
  uname -a
  python3 --version
  tc -V
} > results/environment_info.txt

echo "Running core scenarios (5 runs each, seeds 42-46)..."
for SCENARIO in "${CORE_SCARIOS[@]}"; do
  for i in "${!SEEDS[@]}"; do
    RUN_NUM=$((i + 1))
    SEED="${SEEDS[$i]}"
    bash scripts/run_experiment.sh "$SCENARIO" "$SEED" "$RUN_NUM"
    sleep 1
  done
done

echo "Running loss-sweep scenarios for R5 plots (5 runs each)..."
for SCENARIO in "${SWEEP_SCARIOS[@]}"; do
  for i in "${!SEEDS[@]}"; do
    RUN_NUM=$((i + 1))
    SEED="${SEEDS[$i]}"
    bash scripts/run_experiment.sh "$SCENARIO" "$SEED" "$RUN_NUM"
    sleep 1
  done
done

echo "All experiments complete!"
