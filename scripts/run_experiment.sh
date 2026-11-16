#!/usr/bin/env bash
set -euo pipefail

SCENARIO="${1:-baseline}"
SEED="${2:-42}"
RUN_NUM="${3:-1}"
IFACE="${4:-lo}"
PORT=9000

TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
OUT_DIR="results/${SCENARIO}_${TIMESTAMP}_${SEED}_run${RUN_NUM}"
mkdir -p "$OUT_DIR"

TCPDUMP_PID=""
SERVER_PID=""
WORKER_PIDS=()

cleanup() {
  echo "[cleanup] Stopping processes and clearing netem..."
  for pid in "${WORKER_PIDS[@]}"; do
    kill -9 "$pid" 2>/dev/null || true
  done
  if [[ -n "$SERVER_PID" ]]; then
    kill -9 "$SERVER_PID" 2>/dev/null || true
  fi
  if [[ -n "$TCPDUMP_PID" ]]; then
    sudo kill -2 "$TCPDUMP_PID" 2>/dev/null || true
  fi
  bash scripts/netem_clear.sh "$IFACE"
}
trap cleanup EXIT

echo "=== Starting Run: scenario=$SCENARIO seed=$SEED run=$RUN_NUM ==="

# 1. Apply network impairment
bash scripts/netem_apply.sh "$SCENARIO" "$IFACE"

# 2. Start packet capture (saved for >=2 runs per scenario)
if [[ "$RUN_NUM" -le 2 ]]; then
  sudo tcpdump -i "$IFACE" -w "${OUT_DIR}/capture.pcap" udp port "$PORT" >/dev/null 2>&1 &
  TCPDUMP_PID=$!
  sleep 0.5
fi

# 3. Auto-build CLI args matching whatever flags src/server.py currently accepts
SERVER_HELP=$(python3 src/server.py --help 2>&1 || true)
SERVER_ARGS=()
[[ "$SERVER_HELP" == *"--port"* ]]     && SERVER_ARGS+=(--port "$PORT")
[[ "$SERVER_HELP" == *"--seed"* ]]     && SERVER_ARGS+=(--seed "$SEED")
[[ "$SERVER_HELP" == *"--scenario"* ]] && SERVER_ARGS+=(--scenario "$SCENARIO")
[[ "$SERVER_HELP" == *"--run"* ]]      && SERVER_ARGS+=(--run "$RUN_NUM")
[[ "$SERVER_HELP" == *"--out"* ]]      && SERVER_ARGS+=(--out "$OUT_DIR")
[[ "$SERVER_HELP" == *"--log-dir"* ]]  && SERVER_ARGS+=(--log-dir "$OUT_DIR")

python3 src/server.py "${SERVER_ARGS[@]}" > "${OUT_DIR}/server_stdout.log" 2>&1 &
SERVER_PID=$!
sleep 0.5

# 4. Auto-build CLI args matching whatever flags src/worker.py currently accepts
WORKER_HELP=$(python3 src/worker.py --help 2>&1 || true)
for WID in 1 2 3 4; do
  WORKER_ARGS=(--id "$WID")
  if [[ "$WORKER_HELP" == *"--server"* ]]; then
    WORKER_ARGS+=(--server "127.0.0.1:${PORT}")
  else
    [[ "$WORKER_HELP" == *"--host"* ]] && WORKER_ARGS+=(--host "127.0.0.1")
    [[ "$WORKER_HELP" == *"--port"* ]] && WORKER_ARGS+=(--port "$PORT")
  fi
  [[ "$WORKER_HELP" == *"--seed"* ]]     && WORKER_ARGS+=(--seed "$SEED")
  [[ "$WORKER_HELP" == *"--scenario"* ]] && WORKER_ARGS+=(--scenario "$SCENARIO")
  [[ "$WORKER_HELP" == *"--run"* ]]      && WORKER_ARGS+=(--run "$RUN_NUM")
  [[ "$WORKER_HELP" == *"--out"* ]]      && WORKER_ARGS+=(--out "$OUT_DIR")
  [[ "$WORKER_HELP" == *"--log-dir"* ]]  && WORKER_ARGS+=(--log-dir "$OUT_DIR")

  python3 src/worker.py "${WORKER_ARGS[@]}" > "${OUT_DIR}/worker_${WID}_stdout.log" 2>&1 &
  WORKER_PIDS+=($!)
done

# 5. If crash scenario, hard-kill Worker 1 mid-execution
if [[ "$SCENARIO" == "crash" ]]; then
  sleep 1.5
  echo "[crash] Hard-killing Worker 1 (PID ${WORKER_PIDS[0]})..."
  kill -9 "${WORKER_PIDS[0]}" 2>/dev/null || true
fi

# 6. Wait for server to finish all 1,000 tasks (120s safety timeout)
WAIT_SEC=0
while kill -0 "$SERVER_PID" 2>/dev/null; do
  sleep 0.5
  WAIT_SEC=$((WAIT_SEC + 1))
  if [[ "$WAIT_SEC" -ge 240 ]]; then
    echo "[error] Experiment timed out after 120s!"
    exit 1
  fi
done

# Move any CSVs written to default results/ root into this run's folder if needed
shopt -s nullglob
for f in results/*.csv; do
  mv "$f" "$OUT_DIR/"
done

echo "=== Completed Run: results saved in $OUT_DIR ==="
