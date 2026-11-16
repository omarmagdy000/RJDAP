RJDAP - Reliable Job Dispatch & Aggregation Protocol
CSE361 Computer Networks, Fall 2026 - Project 2 (RJDAP) - Phase 1 (Prototype)
=============================================================================

DEMO VIDEO (Phase 1, 5 min, "anyone with the link can view"):
    >>> PASTE_VIDEO_LINK_HERE <<<

TEAM
    R1 Protocol Architect & RFC Lead ... Omar Magdy   (omarmagdy000)
    R2 Command Hub Engineer ............ Mariam
    R3 Worker Node Engineer ............ Sama         (Elsamasemo)
    R4 Network Testbed Engineer ........ Jenny Samuel
    R5 Data, Metrics & Presentation .... Toqa Yehia

WHAT THIS IS
    A custom application-layer protocol over UDP. One Command Hub (server)
    dispatches 1,000 stateless SHA-256 nonce-search tasks to 4 workers and
    counts every result exactly once. Wire format v1: 14-byte header +
    0..512 byte payload. Standard library only, no networking libraries.

REQUIREMENTS
    - Python 3.10 or newer (tested with 3.12). Networking uses only the
      standard library (socket, struct, hashlib, binascii).
    - Optional, analysis only: pip install -r requirements.txt  (pandas, matplotlib)
    - Optional, Linux only (Phase 2 scenarios): tc (iproute2), tcpdump, sudo.

QUICK START - BASELINE (LAN) SCENARIO (tested on Linux; Windows/macOS untested)
    From the repository root:

        python3 scripts/run_baseline.py              (Windows: py -3 scripts\run_baseline.py)
        python3 scripts/run_baseline.py --runs 5     (5 runs, seeds 42-46, writes results/baseline_summary.csv)
        python3 scripts/run_baseline.py --pcap       (Linux: also saves capture.pcap, needs sudo + tcpdump)

    Expected result: "BASELINE PASS" - 1000/1000 tasks completed, 0 reassigned,
    0 duplicate results. Output goes to results/baseline_<timestamp>_<seed>_run<N>/
    (server.csv, worker1-4.csv, *_stdout.log, optional capture.pcap).

    Linux alternative using the netem-aware script (applies/clears qdisc):
        bash scripts/run_experiment.sh baseline 42 1

RUN THE PIECES BY HAND (5 terminals)
        python3 src/server.py --host 127.0.0.1 --port 9000 --seed 42
        python3 src/worker.py --id 1 --server 127.0.0.1:9000 --seed 42
        python3 src/worker.py --id 2 --server 127.0.0.1:9000 --seed 42
        python3 src/worker.py --id 3 --server 127.0.0.1:9000 --seed 42
        python3 src/worker.py --id 4 --server 127.0.0.1:9000 --seed 42
    On Windows use "py -3" instead of "python3". Start the server first.

UNIT TESTS
        python3 -m unittest discover tests        (expected: Ran 25 tests ... OK)
        python3 src/worker.py --check             (protocol self-test)
        python3 tests/check_duplicate.py          (expected: DUPLICATE CHECK PASS)
        python3 scripts/run_crash_check.py        (kills worker 1; expected: CRASH CHECK PASS)

NETEM COMMANDS (Linux, used from Phase 2; <IF> = lo for loopback)
    Apply:   sudo tc qdisc add dev <IF> root netem loss 10%
             sudo tc qdisc add dev <IF> root handle 1: prio
             sudo tc qdisc add dev <IF> parent 1:3 handle 30: netem delay 150ms
             sudo tc filter add dev <IF> protocol ip parent 1:0 prio 3 u32 match ip sport 9000 0xffff flowid 1:3
    Remove:  sudo tc qdisc del dev <IF> root     (or: bash scripts/netem_clear.sh lo)
    Scripts: scripts/netem_apply.sh <baseline|crash|loss2|loss5|loss10|loss15|delayed_ack> <IF>

SEEDS
    Task generation is deterministic: random.Random(seed). Runs use seeds
    42, 43, 44, 45, 46 (src/config.py). Results folders are named
    <scenario>_<timestamp>_<seed>_run<N>.

ENVIRONMENT USED FOR THE PHASE 1 BASELINE NUMBERS
    Linux (Ubuntu 24.04.5 LTS container), Python 3.12.3, loopback 127.0.0.1,
    no tc/netem impairment. Timings differ per machine.
    The scripts use portable Python calls but were tested on Linux only;
    Windows and macOS are untested.

LAYOUT
    src/       protocol.py (wire format), server.py, worker.py, tasks.py, logger.py, config.py
    scripts/   run_baseline.py (portable), run_crash_check.py, run_experiment.sh, run_experiments.sh, netem_*.sh   <-- changed
    tests/     test_protocol.py, test_tasks.py, check_duplicate.py, stub_server.py   <-- changed
    analysis/  aggregate.py, make_plots.py
    docs/      proposal/, rfc/ (Mini-RFC), diagrams/ (FSM + sequence PNGs), report/
    results/   run output (logs, CSV, pcap)

LOG FORMAT (CSV, one line per packet event)
    ts_us,node,role,event(send|recv|drop|timeout|reassign|dup),msg_type,task_id,worker_id,attempt,bytes,seed,scenario,run

PHASE 1 STATUS
    Known issue: without heartbeats the hub keeps giving tasks to a dead worker (Phase 2 fix).
    Done: wire format v1 + tests, JOIN/JOIN_ACK + TASK_DISPATCH/TASK_RESULT/ACK_RESULT
    exchange, duplicate suppression and timeout reassignment on the server, CSV packet
    logs, baseline script. Planned for Phase 2: worker HEARTBEAT, result retransmission
    with adaptive RTO (M1), fragmentation, netem scenarios, pcaps, plots.