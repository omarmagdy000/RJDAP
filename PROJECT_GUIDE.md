# RJDAP Project Guide and Milestone Checklist

> **CSE361 Computer Networks, Fall 2026, Major Task (25% of course), Project 2**
> **RJDAP = Reliable Job Dispatch & Aggregation Protocol** (working name; the team must pick a unique final name).
> 5 members, 5 roles (R1-R5). One LMS submission per group per phase.
>
> Keep this file in the repo root. Tick boxes as work is finished (`[ ]` to `[x]`) and commit the change.
> Exact deadline dates are not in the brief, only **weeks 7 / 12 / 14**. Confirm on the LMS and write them in section 3.

## Table of contents

1. [The project in plain English](#1-the-project-in-plain-english)
2. [Hard requirements and rules (cost marks if missed)](#2-hard-requirements-and-rules-cost-marks-if-missed)
3. [Deadlines and deliverables at a glance](#3-deadlines-and-deliverables-at-a-glance)
4. [Milestone checklists](#4-milestone-checklists)
   - [M0: Day 0 kickoff](#m0-day-0-kickoff-all-five-12-days)
   - [M1: Phase 1, Prototype (Week 7)](#m1-phase-1-prototype-week-7)
   - [M2: Phase 2, Features and tests (Week 12)](#m2-phase-2-features-and-tests-week-12)
   - [M3: Phase 3, Final (Week 14)](#m3-phase-3-final-week-14)
5. [How the protocol works](#5-how-the-protocol-works)
6. [The compute task](#6-the-compute-task-what-workers-do)
7. [Timeouts and retransmission](#7-timeouts-and-retransmission)
8. [Test scenarios and netem commands](#8-test-scenarios-and-netem-commands)
9. [Metrics, runs and plots](#9-metrics-runs-and-plots)
10. [Roles: who owns what](#10-roles-who-owns-what)
11. [Repo structure and ownership](#11-repo-structure-and-ownership)
12. [How we work (Git, communication, definition of done)](#12-how-we-work)
13. [Mini-RFC requirements](#13-mini-rfc-requirements)
14. [Originality (graded)](#14-originality-graded)
15. [Common mistakes](#15-common-mistakes-to-avoid)
16. [Glossary](#16-glossary)
17. [Brief for AI assistants](#17-brief-for-ai-assistants)

---

## 1. The project in plain English

A teacher (the **server / Command Hub**) has 1,000 small exercises and at least 4 students (the **workers**). The teacher hands out exercises and the students send back answers. The mail (**UDP**) loses letters, delays them, duplicates them, and sometimes a student vanishes (crashes).

Our job is to design the rules of the conversation, a **protocol**, on top of raw UDP. All 1,000 answers must still arrive, **each must be counted exactly once**, and we must prove it with measurements.

- UDP gives no delivery guarantee, no ordering and no retries. **Our protocol adds all of that**, using only sockets.
- The compute task is deliberately trivial. The grade is about **networking**: timers, retransmission, duplicate handling, reassignment and measurement.
- **Exactly-once is not magic.** It is two things combined:
  1. **At-least-once delivery**: keep retransmitting until acknowledged.
  2. **Idempotent receiving**: the server remembers which `Task_ID`s are already DONE, ignores repeats, but **still re-ACKs them** so the sender stops.

| We build | We hand in | What earns marks |
|---|---|---|
| A server and 4+ workers talking over UDP | Working code (Phases 1, 2, 3) | Works under loss, delay and crash |
| A packet format and rules (the protocol) | Mini-RFC (written protocol spec) | Reproducible experiments |
| Scripts that break the network on purpose and measure it | CSVs, plots, pcaps, report, slides, demo videos | Original design and honest limitations |
| | | Clear explanation (RFC, report, video) |

---

## 2. Hard requirements and rules (cost marks if missed)

**Must have**
- [ ] **UDP only**, custom binary header with `Task_ID`, `Worker_ID`, `Attempt_Num`, `Payload_Checksum` (plus version, type, flags, length, fragment index/count).
- [ ] Messages: `WORKER_JOIN`, `HEARTBEAT`, `TASK_DISPATCH`, `TASK_RESULT`, `ACK_RESULT`.
- [ ] **Exactly-once**: a retransmitted result is never counted twice.
- [ ] **Timeout-based task reassignment** and **payload fragmentation**.
- [ ] **Payload per packet is at most 512 bytes.**
- [ ] At least **4 worker clients**; a queue of **1,000 tasks**; a server-defined timeout (for example 200 ms).
- [ ] **Python 3.10+**, standard library only for networking. No ENet, RakNet or similar. Allowed: `socket, struct, hashlib, zlib, threading/selectors, time, random, csv, logging, argparse, json`. `pandas` and `matplotlib` are allowed for analysis only.
- [ ] Runs **unchanged on Linux and Windows**. **Graded on Linux with `tc netem`.**
- [ ] **Seeded randomness**, fixed seeds, results folder named by timestamp and seed.
- [ ] **Every packet logged to CSV** with a timestamp.
- [ ] **At least 2 pcaps per scenario.**
- [ ] **5 runs per measurement**, reported as min / median / max, with variance explained.
- [ ] Scripts must **apply and remove** the qdisc; document the commands in the README.
- [ ] A plot script/notebook that regenerates **every figure from the CSVs**.
- [ ] **Original design** (at least 2 own mechanisms) and a **Mini-RFC**.
- [ ] **Commit history matters.** Everyone commits their own work.
- [ ] Videos are **links only**, inside `README.txt`, set to "anyone with the link can view" (test while logged out).
- [ ] Submissions are checked for similarity. Write your own code and explain the design in the RFC.

---

## 3. Deadlines and deliverables at a glance

The brief gives three phases: **week 7, week 12, week 14**. One LMS submission per group each time.

| Phase | Week | Exact date (fill in from LMS) | Deliverables |
|---|---|---|---|
| **1: Prototype** | 7 | `____-__-__` | Proposal (3 pages max), Mini-RFC sections 1-3, working JOIN + DISPATCH prototype, README + 5-minute demo video link, baseline local script, logs |
| **2: Features & tests** | 12 | `____-__-__` | All mandatory features + error handling; logs, pcaps, netem command list and raw CSVs for all 4 scenarios; Mini-RFC sections 4-7 |
| **3: Final** | 14 | `____-__-__` | Final Mini-RFC (5-8 pages, all 9 sections), repo with commit history + reproducible scripts, technical report (6-8 pages), slides (8-10), final demo video (10 minutes max) |

**Final video must cover:** header fields and sizes (and why those lengths), loss/reorder handling, a pcap excerpt showing a retransmission, and one experiment explained.

**Rhythm**
- 3 days before each deadline: pairs hold an integration session (30 min).
- 3 days before: R5 reminds everyone and starts the pre-submission checklist.
- 2 days before: R5 runs the submission checklist from a **fresh clone on Linux**.
- One person uploads to the LMS; R5 verifies.

---

## 4. Milestone checklists

Legend: **R1** Protocol and RFC, **R2** Server, **R3** Worker, **R4** Testbed and scripts, **R5** Data and docs. "All" means the whole team.

### M0: Day 0 kickoff (all five, 1-2 days)

This freezes the contract so all five people can work in parallel. After this, everyone codes against the contract, not against each other.

- [ ] **All**: pick a **unique protocol name** and a version field.
- [ ] **All**: freeze **Header v1** (see below) and the message type numbers.
- [ ] **All**: freeze the **log CSV schema** (see below).
- [ ] **All**: agree ports (server on UDP **9000**), folder layout, and the `config.py` values (ports, seed, timeouts, N, D).
- [ ] **All**: pick **2 original mechanisms** (see [section 14](#14-originality-graded)).
- [x] **R1**: create/finish the repo (done: `omarmagdy000/RJDAP`, local structure committed and pushed to `origin/main`).
- [ ] **R1**: add all 5 members as collaborators; replace `@R2`..`@R5` in `.github/CODEOWNERS` with real GitHub usernames (`@omarmagdy000` set for R1).
- [ ] **R1**: protect `main` (PR + 1 review required) if the plan is to enforce that on GitHub.
- [x] **R1**: write `src/protocol.py` (`pack` / `unpack` / `crc16`) plus unit tests; **push by day 2**; tag `protocol-v1`.
- [ ] **R5**: write `src/logger.py` and `src/config.py`; push.
- [ ] **All**: install the tools ([section 8.1](#81-setup-everyone-day-1)); confirm Python is 3.10 or newer.
- [ ] **R4**: get Linux (Ubuntu VM or WSL2); prove `tc netem` works on `lo` (add a delay, ping, delete it; capture with tcpdump).
- [ ] **All**: schedule the 2 short syncs per week (15 min: done / next / blocked).

**Header v1 (14 bytes, struct `'!BBHIBBHH'`, network byte order)**

| Offset | Size | Field |
|---|---|---|
| 0 | 1 B | `version` (4 bits) \| `msg_type` (4 bits) |
| 1 | 1 B | `flags` (FRAG, RETX, LAST) |
| 2 | 2 B | `Worker_ID` |
| 4 | 4 B | `Task_ID` |
| 8 | 1 B | `Attempt_Num` |
| 9 | 1 B | `frag_idx` (4 bits) \| `frag_count` (4 bits) |
| 10 | 2 B | `Payload_Len` |
| 12 | 2 B | `Payload_Checksum` (CRC-CCITT) |

R1 owns the final version. Others only use it through `protocol.py` (`pack()` / `unpack()`).

**Log schema (CSV, one line per packet event)**

```
ts_us,node,role,event(send|recv|drop|timeout|reassign|dup),
msg_type,task_id,worker_id,attempt,bytes,seed,scenario,run
```

---

### M1: Phase 1, Prototype (Week 7)

**Goal:** a working JOIN + DISPATCH (+ RESULT + ACK) exchange over UDP between one server and clients on localhost, with docs and a demo.

**Submission contents**
- [x] Proposal (3 pages max): scenario, motivation, approach (`docs/proposal/PROPOSAL.md`).
- [x] Mini-RFC draft, sections 1-3 (introduction, architecture, message formats + sample) (`docs/rfc/MINI_RFC.md`).
- [ ] Working prototype (server + client).
- [ ] README + 5-minute demo video link.
- [ ] Script for the Baseline local scenario.
- [ ] Logs present.

**Per-role tasks**

*R1: Protocol Architect & RFC Lead*
- [x] Final protocol name + version; header table with byte offsets and struct format.
- [x] `protocol.py` (pack/unpack/CRC) published to the team by day 2; `tests/test_protocol.py` green (19/19 tests pass).
- [x] Draw FSMs: server task states (PENDING, DISPATCHED, DONE) and the worker states (`docs/diagrams/FSM_DIAGRAMS.md` & `docs/rfc/MINI_RFC.md`).
- [x] Write the proposal (3 pages max) (`docs/proposal/PROPOSAL.md`).
- [x] Write RFC sections 1-3, including one **sample packet in hex** (`docs/rfc/MINI_RFC.md`).
- [x] Define the 2 original mechanisms (with R2/R3) and how they differ from known protocols.

*R2: Command Hub (Server) Engineer*
- [ ] UDP socket on port 9000 with a short timeout (`settimeout(0.05)`) so the loop can check timers.
- [ ] Handle `WORKER_JOIN`: store worker id, address, `last_seen`; send a join confirmation (ACK type or a flag).
- [ ] Build the 1,000-task table from `tasks.make_tasks(1000, seed)`; states PENDING / DISPATCHED / DONE.
- [ ] Send `TASK_DISPATCH` to an idle worker; on `TASK_RESULT` mark DONE and send `ACK_RESULT`.
- [ ] Stop when all 1,000 are DONE and print a summary.
- [ ] Log everything with `logger.py`.
- [ ] Test early against a 10-line **stub worker**.

*R3: Worker Node Engineer*
- [ ] Parse `--id` and `--server`; open a UDP socket with a short timeout.
- [ ] Send `WORKER_JOIN` (retry every 500 ms) until the server confirms.
- [ ] Receive `TASK_DISPATCH`, run `tasks.run_task`, send `TASK_RESULT`.
- [ ] Wait for `ACK_RESULT`, then be ready for the next task.
- [ ] Test early against a **stub server**; then run 4 workers locally via the launcher script.

*R4: Network Testbed & Automation Engineer*
- [ ] Linux VM or WSL2 testbed ready; `tc netem` confirmed working on `lo`.
- [ ] `scripts/run_experiment.sh <scenario> <seed> <run>`: starts capture, server and 4 workers; sets the seed; stores output in `results/<scenario>_<timestamp>_<seed>_run<N>/`.
- [ ] Baseline local scenario script works.
- [ ] Help R5 write the Linux and Windows run instructions in the README.

*R5: Data, Metrics & Presentation Lead*
- [ ] `logger.py` and the CSV schema handed to everyone; server and workers use it.
- [ ] Log parser that computes the 4 metrics from raw logs (start of `analysis/aggregate.py`).
- [ ] Fill in `README.txt` (requirements, run commands for Linux and Windows, environment).
- [ ] Record the **5-minute demo video**; set sharing to "anyone with the link"; **test while logged out**; put the link in `README.txt`.
- [ ] Assemble the LMS submission checklist.

**Integration gate (pairs, 3 days before the deadline)**
- [ ] R1+R2: header, FSM and server logic match the RFC exactly.
- [ ] R2+R3: JOIN, one DISPATCH, one RESULT, one ACK on localhost; then 4 workers, 1,000 tasks, no loss.
- [ ] Verified: zero duplicates and a correct final count (1,000 DONE).
- [ ] `python3 -m unittest discover tests` passes.
- [ ] Fresh clone on Linux runs the baseline script (R5 verifies).
- [ ] Tag `phase1`; one person uploads to the LMS; R5 verifies the upload.

---

### M2: Phase 2, Features and tests (Week 12)

**Goal:** every mandatory feature, error handling, and evidence from all 4 scenarios.

**Submission contents**
- [ ] All mandatory features + error handling.
- [ ] Evidence for all 4 scenarios: logs, pcaps, netem command list, raw CSVs.
- [ ] Mini-RFC sections 4-7 (procedures, reliability, experiment plan, walkthrough).

**Per-role tasks**

*R1*
- [ ] Write the timeout formula and the duplicate-suppression state machine.
- [ ] Fragmentation rules for payloads over 512 bytes.
- [ ] RFC sections 4-7: procedures, reliability, experiment plan, walkthrough (get a **real pcap excerpt** from R4).
- [ ] Handle protocol change requests (GitHub Issues labelled `protocol`): update code and RFC together; tag a new version.

*R2*
- [ ] Per-task deadline; on expiry set the task back to PENDING with `Attempt_Num + 1` and count `reassigned_task_count`; reassign to another **live** worker.
- [ ] Heartbeat tracking: no heartbeat for 3 intervals means the worker is dead; its tasks go back to PENDING.
- [ ] **Dedup table keyed by `Task_ID`**: a repeated result is not counted, **is re-ACKed**, and increments `duplicate_results_dropped`.
- [ ] Adaptive per-worker RTO and a retry cap.
- [ ] Checksum validation (drop bad packets silently).
- [ ] Fragment sending.
- [ ] Server-side metrics written to CSV at the end (completion time, reassigned, duplicates).

*R3*
- [ ] Periodic `HEARTBEAT` (every ~1 s; separate thread or timer).
- [ ] Result cache (`task_id` to packed result); if the same task comes again, **resend the cached result, never recompute**.
- [ ] Retransmit unacknowledged results with RTO doubling each try, **max 5 tries**; accept a late ACK; never retry forever.
- [ ] Handle delayed ACKs without infinite retransmit.
- [ ] Reassemble fragmented payloads; drop packets with a bad checksum.
- [ ] Measure idle time vs compute time to produce `worker_idle_time_ms`.

*R4*
- [ ] Scripts for all 4 scenarios: `baseline`, `crash` (kill Client 1 around 50% progress), `loss10`, `delayed_ack` (150 ms on server outbound only).
- [ ] **Always add and remove the qdisc** (`trap ... EXIT`); verify with `tc qdisc show dev lo`.
- [ ] `tcpdump` captures; **at least 2 pcaps per scenario**.
- [ ] `scripts/run_experiments.sh` runs every scenario x 5 runs with seeds 42-46.
- [ ] Extra runs at loss 0, 2, 5, 10, 15% for the plots (with R5).
- [ ] Provide the netem command list for the RFC.

*R5*
- [ ] `analysis/aggregate.py`: read `results/*/server.csv` and worker CSVs, compute the 4 metrics per run, write `results/summary.csv` with min/median/max per scenario.
- [ ] `analysis/make_plots.py` regenerates all figures from CSVs: completion time per scenario, loss vs reassigned tasks, loss vs duplicates dropped, idle time per worker.
- [ ] Draft the analysis: why the numbers look this way, why median differs from max (timer alignment, random loss bursts, OS scheduling).

**Scenario acceptance (must all pass, see [section 8](#8-test-scenarios-and-netem-commands))**
- [ ] Baseline: 1,000 tasks done, zero duplicate executions.
- [ ] Crash: timeout detected, tasks reassigned to workers 2/3/4, 100% complete.
- [ ] Loss 10%: duplicate suppression triggers, no result counted twice.
- [ ] Delayed ACKs (150 ms): no crash, no infinite retransmit.
- [ ] 5 runs per scenario; no leftover qdisc after any run.

**Integration gate**
- [ ] R3+R4: crash and delayed-ACK scenarios run under netem with correct worker behaviour.
- [ ] R4+R5: runs, then logs/pcaps, then CSVs, then plots, reproducible end to end.
- [ ] R5+R1: RFC, report and slides tell the same story as the data.
- [ ] Fresh clone on Linux runs everything; tests pass.
- [ ] Tag `phase2`; upload to the LMS; R5 verifies.

---

### M3: Phase 3, Final (Week 14)

**Goal:** polish, final fixed-seed runs, and the written and recorded deliverables.

**Submission contents**
- [ ] Final Mini-RFC (5-8 pages, all 9 sections).
- [ ] Repo with commit history and reproducible scripts.
- [ ] Technical report (6-8 pages): method, plots, interpretation, limitations.
- [ ] Slides (8-10).
- [ ] Final demo video (10 minutes max) covering the 4 required points.

**Per-role tasks**

*R1*
- [ ] Final RFC: add limitations, references and the "differences from known protocols" justification (sections 8-9); reach 5-8 pages.
- [ ] Check RFC against the code **line by line**; fix any mismatch.
- [ ] Record the video part: **header fields and why those lengths**.

*R2*
- [ ] Stress runs with R4 (loss 10%, delayed ACKs, crash); fix edge cases (e.g. **late result after reassignment: first result wins**).
- [ ] Clean code, comments, commit history.
- [ ] Explain dedup logic in the video.

*R3*
- [ ] Workers killable cleanly **and** abruptly (`kill -9`); nothing blocks the others.
- [ ] Tune retransmit/backoff using R5's plots.
- [ ] Explain loss/reordering handling in the video.

*R4*
- [ ] **Final full run** with fixed seeds; archive results.
- [ ] Pick the best pcap excerpt (retransmission/recovery) for the video and RFC; save to `docs/pcap_excerpts/`.
- [ ] Record environment info: OS, kernel, Python versions.
- [ ] Confirm a **fresh clone** runs end to end.

*R5*
- [ ] Technical report (6-8 pages): methodology, plots, interpretation, limitations, baseline comparison. Numbers must match the CSVs.
- [ ] Slides (8-10).
- [ ] Final video (10 minutes max) with all required points; **test the link while logged out**.
- [ ] Final submission check.

**Final checks**
- [ ] Every member has commits in their own area (history is graded).
- [ ] Everyone can explain everything they committed (video and review ask this).
- [ ] README has: requirements, exact run commands (Linux + Windows), netem commands, seeds, environment used, public demo video link.
- [ ] `python3 -m unittest discover tests` passes; baseline script still runs.
- [ ] Tag `phase3`; upload to the LMS; R5 verifies.

---

## 5. How the protocol works

### 5.1 One task from start to finish (normal case)

1. **Join:** Worker sends `WORKER_JOIN`. Server stores `worker_id`, address, `last_seen` and replies with a join confirmation.
2. **Alive:** Worker sends `HEARTBEAT` every ~1 s (can piggyback an RTT sample). No heartbeat for 3 intervals means the server marks the worker dead.
3. **Dispatch:** Server sends `TASK_DISPATCH` (`Task_ID`, `Attempt_Num`, job params). Server starts a per-task timer.
4. **Compute:** Worker runs the loop and stores the result in a local cache keyed by `Task_ID`.
5. **Result:** Worker sends `TASK_RESULT` (`Task_ID`, outcome, checksum) and starts a retransmit timer.
6. **Ack:** Server marks the task DONE and sends `ACK_RESULT`. Worker receives it, deletes the cache entry and gets the next task.

### 5.2 What goes wrong, and what the protocol does

| What gets lost / goes wrong | What the protocol does |
|---|---|
| `TASK_DISPATCH` lost | Server timer expires, resends the same task (`Attempt_Num + 1`) to the same or another worker |
| `TASK_RESULT` lost | Worker retransmit timer expires, resends the **cached** result (no recompute) |
| `ACK_RESULT` lost | Worker resends the result; server sees `Task_ID` already DONE, `duplicate_results_dropped++`, re-sends ACK, does **not** count again. **This is the core exactly-once case** |
| ACK delayed 150 ms | Worker's retransmit timer must be longer than the delay (adaptive RTO), cap the retries, back off; a late ACK is accepted normally |
| Worker crashes | Heartbeats stop and the task timer expires; server reassigns its pending tasks to live workers (`reassigned_task_count++`) |
| Old worker's result arrives after reassignment | **First result wins**; any later one for the same `Task_ID` is a duplicate: drop and ACK |
| Corrupted payload | Checksum mismatch: silently drop, let timers recover |
| Packet duplicated / reordered | `Task_ID` + `Attempt_Num` make every handler safe to run twice |

### 5.3 Message reference

| Type | From, To | Carries | Reply / timer |
|---|---|---|---|
| `WORKER_JOIN` | W to S | `Worker_ID` (or 0 = request one), version | Retry every 500 ms until confirmed |
| `HEARTBEAT` | W to S | `Worker_ID`, timestamp echo, idle/busy flag | Server updates `last_seen` and RTT |
| `TASK_DISPATCH` | S to W | `Task_ID`, `Attempt_Num`, job params, fragment info | Server task timer (RTO) |
| `TASK_RESULT` | W to S | `Task_ID`, `Attempt_Num`, found flag + nonce, checksum | Worker retransmit timer |
| `ACK_RESULT` | S to W | `Task_ID` (optionally a bitmap of recent Task_IDs) | Stops retransmission |

### 5.4 Server task state machine (for the RFC figure)

```
PENDING --dispatch--> DISPATCHED(worker, attempt)
DISPATCHED --result (first)--> DONE            -> send ACK
DISPATCHED --timer expires / worker dead--> PENDING (attempt+1, reassigned++)
DONE --result again--> DONE                    -> duplicate_dropped++, re-send ACK
Finished when all 1000 tasks are DONE -> print summary, stop
```

---

## 6. The compute task (what workers do)

Simple and **stateless** (a task must not depend on any previous task, so it can be re-run anywhere).

```
Task i  = search nonce range [start_i, start_i + N)
find n such that  sha256(job_key + n)  starts with D zero bits
result  = (found: bool, nonce: int)

Task generation: random.Random(SEED), so every run is identical.
Choose N so one task takes ~5-50 ms. Too fast = network dominates (fine),
too slow = tests take forever. Tune it once, put it in config.py.
```

**Fragmentation** is required by the brief. A cheap way to exercise it: let a task carry extra input data (for example a 1-2 KB "vector block") split into fragments of at most 512 bytes using `frag_idx` / `frag_count`. The worker starts only after all fragments have arrived; missing fragments are re-requested or the whole task is resent.

---

## 7. Timeouts and retransmission

Per worker, updated on every heartbeat / ACK round trip (Jacobson/Karels):

```
SRTT   = 0.875*SRTT + 0.125*sample
RTTVAR = 0.75*RTTVAR + 0.25*|SRTT - sample|
RTO    = SRTT + 4*RTTVAR          (min 50 ms, max 2 s)

Server task timeout   = RTO + expected_compute_time * 1.5
Worker result timeout = RTO ; on each retry RTO *= 2 (backoff), max 5 tries
Dead worker           = no heartbeat for 3 x heartbeat_interval
```

> **Tip:** use the server's fixed 200 ms timeout first (simple, enough for Phase 1), then upgrade to adaptive RTO in Phase 2. That upgrade can be one of the "original mechanisms".

---

## 8. Test scenarios and netem commands

| Scenario | netem / action | Must show |
|---|---|---|
| **Baseline LAN** | none | 1,000 tasks done, zero duplicate executions |
| **Worker crash** | hard-kill Client 1 mid-execution | Timeout detected, tasks reassigned to 2/3/4, 100% complete |
| **Severe loss** | `loss 10%` | Duplicate suppression triggers, no result counted twice |
| **Delayed ACKs** | `delay 150ms` on server outbound | No crash, no infinite retransmit |

### 8.1 Setup (everyone, day 1)

```bash
# Linux / WSL2 setup
sudo apt update && sudo apt install -y python3 python3-pip tcpdump tshark iproute2 git
pip install pandas matplotlib psutil
python3 --version     # 3.10 or newer
tc -V                 # confirms iproute2 is installed
```

| Need | Tool | Notes |
|---|---|---|
| Language | Python 3.10+ | Allowed libs only (see section 2) |
| Test OS | Linux (Ubuntu VM or WSL2) | Graded on Linux with `tc netem`. Windows users can develop anywhere but must test on Linux before every deadline |
| Impairment | `tc qdisc ... netem` | Needs sudo. Clumsy is a GUI substitute on Windows, **for development only** |
| Capture | `tcpdump`, Wireshark / `tshark` | Save a `.pcap` per run (at least 2 per scenario). Filter: `udp.port==9000` |
| Analysis | `pandas`, `matplotlib` | Analysis only, not networking |
| Optional | `psutil` | CPU / memory per node |
| Docs | Markdown / Word, draw.io | FSM and sequence diagrams as png/svg |

### 8.2 Exact netem commands (loopback `lo`, server on UDP port 9000)

```bash
# Baseline: nothing to add

# Severe loss 10%
sudo tc qdisc add dev lo root netem loss 10%

# Delayed ACKs: delay only packets the SERVER sends (source port 9000)
sudo tc qdisc add dev lo root handle 1: prio
sudo tc qdisc add dev lo parent 1:3 handle 30: netem delay 150ms
sudo tc filter add dev lo protocol ip parent 1:0 prio 3 u32 \
     match ip sport 9000 0xffff flowid 1:3

# Worker crash: no netem, kill the process abruptly
kill -9 $(pgrep -f "worker.py --id 1")

# Cleanup after EVERY run
sudo tc qdisc del dev lo root

# Capture (separate terminal, before starting the run)
sudo tcpdump -i lo -w results/baseline_run1.pcap udp port 9000
```

> **Note:** on `lo`, loss is applied to each packet once, in both directions, which is what you want. **Always run the cleanup**, or the next scenario will be polluted. Put add + remove in the same script with `trap ... EXIT`.

---

## 9. Metrics, runs and plots

| Metric | How it is computed |
|---|---|
| `total_completion_time` | Server clock: first dispatch to the moment the 1000th task becomes DONE |
| `reassigned_task_count` | Server increments each time a task is re-dispatched because of timeout or dead worker |
| `duplicate_results_dropped` | Server increments each time a result arrives for an already-DONE `Task_ID` |
| `worker_idle_time_ms` | Worker: sum of (time next task received minus time previous result ACKed) vs sum of compute time |

**Runs:** every measurement x **5 runs** with fixed seeds **42-46**; report **min / median / max**. Results go in `results/<scenario>_<timestamp>_<seed>_run<N>/` (CSV, logs, pcap).

**Plots to prepare** (all regenerated by `analysis/make_plots.py` from CSVs):
- [ ] Completion time per scenario (min / median / max bars).
- [ ] Loss rate vs reassigned count (extra loss values: 0, 2, 5, 10, 15%).
- [ ] Loss rate vs duplicates dropped.
- [ ] Idle time per worker.
- [ ] Written explanation of variance: why median differs from max (timer alignment, random loss bursts, OS scheduling).

---

## 10. Roles: who owns what

Edit **only files you own**. Need a change elsewhere? Ask the owner or open a GitHub Issue (protocol changes: Issue labelled `protocol` to R1).

| Role | Name (fill in) | Goal | Owns |
|---|---|---|---|
| **R1** Protocol Architect & RFC Lead | `omarmagdy000` | Decide exactly what every packet looks like and what rules both sides follow, then document it | `src/protocol.py`, `tests/test_protocol.py`, `docs/rfc/MINI_RFC.md`, `docs/proposal/`, `docs/diagrams/`, `R1_ROLE_GUIDE.md` |
| **R2** Command Hub (Server) Engineer | `________` | Dispatcher that hands out tasks and guarantees each result is counted once | `src/server.py` |
| **R3** Worker Node Engineer | `________` | Compute tasks and return each result reliably, never computing the same task twice | `src/worker.py` |
| **R4** Network Testbed & Automation Engineer | `________` | Linux, netem, captures and scripts that run every scenario identically every time | `scripts/`, `results/` |
| **R5** Data, Metrics & Presentation Lead | `________` | Logs, then metrics, then plots, then report, slides, videos, submissions | `src/logger.py`, `analysis/`, `docs/report/`, `docs/slides/`, `README.txt` |

Shared files (`src/config.py`, `README.txt`) change only via PR with a pair partner's approval.

### Pairing map

Each person has two partners, so everyone is paired but nobody is stuck waiting on just one person. The pairs form a ring: R1-R2-R3-R4-R5-R1.

| Pair | They co-own |
|---|---|
| R1 + R2 | Header, FSM and server logic must match the RFC exactly |
| R2 + R3 | Server and worker integration: join, dispatch, result, ACK, reassignment |
| R3 + R4 | Crash and delayed-ACK scenarios: worker behaviour under netem |
| R4 + R5 | Runs, logs/pcaps, CSVs, plots, reproducible end to end |
| R5 + R1 | RFC, report and slides tell the same story as the data |

**Hand-offs**
- R1 gives `protocol.py` to R2/R3 and RFC text to R5; needs a pcap from R4, results from R5, feedback from R2/R3.
- R2 gives a running server to R3/R4 and metrics to R5; needs `protocol.py` (R1), worker (R3), logger (R5).
- R3 gives results to R2 and idle-time data to R5; needs `protocol.py` (R1), server (R2), crash/delay scenarios (R4).
- R4 gives runs, logs and pcaps to R5/R1; needs server + worker from R2/R3 and the CSV schema from R5.
- R5 gives plots and analysis to R1 and the team; needs logs and pcaps from R4, metrics from R2/R3, RFC from R1.

**Tools per role:** R1 Python `struct`, draw.io, Markdown, Wireshark. R2 `socket`, `time`/`selectors`, `unittest`, Wireshark, netem. R3 `socket`, `threading`, `hashlib`, Wireshark. R4 `tc`/netem, tcpdump, Wireshark/tshark, bash, WSL2/VM. R5 `csv`/`pandas`/`matplotlib`, Markdown/Word/Slides, screen recorder, Git.

---

## 11. Repo structure and ownership

```
RJDAP/
  README.txt  CONTRIBUTING.md  PROJECT_GUIDE.md  requirements.txt  .gitignore
  .github/    CODEOWNERS  pull_request_template.md
  src/        protocol.py(R1) server.py(R2) worker.py(R3) logger.py(R5) config.py tasks.py
  scripts/    run_experiment.sh run_experiments.sh netem_apply.sh netem_clear.sh   (R4)
  analysis/   aggregate.py make_plots.py                                          (R5)
  tests/      test_protocol.py test_tasks.py
  results/    <scenario>_<timestamp>_<seed>_run<N>/  (csv, logs, pcap)
  docs/       rfc/ proposal/ report/ slides/ diagrams/ pcap_excerpts/
```

`README.txt` must contain: requirements, exact run commands (Linux + Windows), netem commands, seeds, environment used, and the public demo video link (tested logged out).

> **Note:** the source files in `src/`, `scripts/`, `analysis/` and `tests/` are currently one-line placeholders naming the owner. The Explained file refers to "provided" versions of `protocol.py`, `logger.py` and the scripts; those were not part of the upload, so the owners write them.

---

## 12. How we work

**Git**
- `main` always runs; **never push to it directly**.
- Branch per task: `r2/reassignment-timer`.
- Small commits: `r2: add dedup table`.
- Pull Request needs **1 review (pair partner)**, within 24 h.
- `git pull --rebase origin main` daily.
- Tag submissions `phase1`, `phase2`, `phase3` (and `protocol-v1` etc. for protocol versions).
- **Everyone commits their own work** (graded).

**Never wait for anyone**
- Code against `protocol.py` and a **stub** of your partner's side.
- Need a protocol change? GitHub Issue labelled `protocol` to R1.
- Blocked more than a few hours? Post in the group chat, then work on the next checklist item.

**Rhythm**
- Day 0 kickoff (all 5): freeze header, log schema, folders.
- 2 short syncs per week (15 min): done / next / blocked.
- Integration session (pairs) 3 days before every deadline.
- 2 days before: R5 runs the submission checklist from a fresh clone on Linux.
- One person uploads to the LMS; R5 verifies.

**Definition of done (for every PR)**
- [ ] Tests pass: `python3 -m unittest discover tests`
- [ ] Baseline script still runs
- [ ] Logs written for what you built
- [ ] RFC updated if the wire format or timers changed

**Working with AI agents**
- Give every session this file (and the two HTML files if you have them).
- The agent edits only files you own.
- No external networking libraries; no changing `protocol.py` without R1.
- You must understand and be able to explain everything you commit (the video and review ask this).

### Recommended build order

1. **Day 0, all five:** agree header v1, message types, ports, log schema, folder layout, protocol name. Create the repo.
2. **R1:** `protocol.py` (`pack_header` / `unpack_header` / `crc16`) plus unit tests; push. Everyone imports it.
3. **R5:** `logger.py` and `config.py` (ports, seed, timeouts, N, D); push.
4. **R2 and R3 in parallel:** server and worker, each tested against a tiny stub of the other. First goal: JOIN, one DISPATCH, one RESULT, one ACK on localhost.
5. **Integrate (R2+R3):** 4 workers, 1,000 tasks, no loss. Verify zero duplicates and a correct final count.
6. **R4:** launcher + `run_experiment.sh` + baseline script; first video + README, then **Phase 1 submission**.
7. Add heartbeats, per-task timers, reassignment (R2) and result retransmit + cache (R3).
8. Add dedup table and re-ACK on duplicates (R2). Add checksum validation (both).
9. Run loss 10%, look at duplicate counters and logs, fix bugs. Then delayed ACKs, then the crash test.
10. Add fragmentation and adaptive RTO (the original mechanisms).
11. R4 runs every scenario x5 with fixed seeds; R5 aggregates and plots; R1 completes RFC 4-7, then **Phase 2 submission**.
12. Polish code, final runs, report, slides, final video, README, then **Phase 3 submission**.

---

## 13. Mini-RFC requirements

- **Draft (Phase 1):** at most 4 pages, sections 1-3 (intro, architecture with FSM diagrams, message formats).
- **Phase 2:** add sections 4-7 (procedures, reliability, experiment plan, walkthrough with a real pcap excerpt).
- **Final (Phase 3):** 5-8 pages, **all 9 required headings**, adding limitations, references and the differences-from-known-protocols justification (sections 8-9).
- Message formats need: a table with **bit sizes and byte offsets**, the **struct string**, and **one sample packet in hex**.
- The RFC must match the code **exactly**; R1 checks line by line before Phase 3.
- Location: `docs/rfc/MINI_RFC.md`.

> The brief's 9 headings are not listed in the project files we have. Take the exact list from the assignment PDF and paste it here: `________`.

---

## 14. Originality (graded)

Pick a **unique protocol name and version field**, and include **at least 2 original mechanisms** with a "how we differ from known protocols" section.

Ideas:
- Per-worker **adaptive timeout** (`RTO = SRTT + 4*RTTVAR`).
- **Result-ID sliding window with a cumulative ACK bitmap.**
- **Piggybacked ACKs** on heartbeats.
- **Compact task-range encoding** instead of sending full task lists.

Chosen mechanisms (decide at Day 0):
1. **M1 — Compute-Compensated, Attempt-Matched Adaptive RTO** (`compute_us` in `TASK_RESULT` + echoed `Attempt_Num` to feed pure network RTT into per-worker `SRTT`/`RTTVAR` without Karn's ambiguity).
2. **M2 — Cumulative 32-Bit ACK Bitmap across Independent Tasks** (`ACK_RESULT` carries a 32-bit bitmap confirming completion of `task_id - 1` through `task_id - 32`).

---

## 15. Common mistakes to avoid

- **Recomputing** on a repeated dispatch: the worker must return the cached result.
- **Not re-ACKing duplicates:** the worker will retransmit forever.
- **Retransmit timer shorter than the injected delay:** retransmit storm. Use adaptive RTO + backoff + retry cap.
- **Blocking `recvfrom` with no timeout:** the process cannot notice timers; use `settimeout` or `selectors`.
- Forgetting `tc qdisc del` between runs; forgetting to seed the RNG.
- **Counting a duplicate result in the totals** (the one thing that fails the severe-loss scenario).
- **Logging too little:** if it is not in the CSV, it cannot go in a plot.
- **Copying public code:** submissions are checked for similarity. Write your own and explain your design in the RFC.

---

## 16. Glossary

| Term | Plain meaning |
|---|---|
| **UDP** | User Datagram Protocol. No guarantee: packets can be lost, duplicated, late or out of order. We add reliability ourselves |
| **TCP** | The reliable internet protocol. **Not allowed** for the data path |
| **IP / IP address** | Address of a machine (`127.0.0.1` = your own computer) |
| **Port** | Number (e.g. 9000) saying which program receives the packet |
| **Socket** | Programming object used to send/receive packets (Python `socket`) |
| **Packet / datagram** | One message sent over UDP |
| **Header / Payload** | First bytes of our packet (control info) / the data after it |
| **MTU** | Largest packet the network carries without splitting. Our limit: payload at most 512 bytes |
| **Fragmentation** | Splitting big data into several small packets and reassembling |
| **Big-endian / network byte order** | Standard order for multi-byte numbers; use `!` in `struct` formats |
| **struct** | Python module that turns numbers into exact bytes and back |
| **RFC / Mini-RFC** | Document that formally specifies a protocol |
| **FSM** | Finite State Machine: states and the events that move between them |
| **ACK** | Acknowledgement: "I received it". Ours is `ACK_RESULT` |
| **Retransmission** | Sending again because no ACK arrived |
| **Timeout** | How long to wait before retrying or reassigning |
| **RTT / SRTT / RTTVAR** | Round-trip time / smoothed average of it / how much it jumps around |
| **RTO** | Retransmission timeout = `SRTT + 4*RTTVAR`; the adaptive wait time |
| **Backoff** | Doubling the wait after each failed retry |
| **Heartbeat** | Small "I am alive" packet workers send regularly |
| **Exactly-once** | Each result counted once; built from at-least-once delivery + ignoring repeats |
| **At-least-once** | Keep resending until acknowledged |
| **Idempotent** | Doing it twice has the same effect as once |
| **Dedup** | Server remembers finished `Task_ID`s and ignores repeats (but still re-ACKs) |
| **Reassignment** | Giving a task to another worker when the first timed out or died |
| **Stateless task** | A task needing no earlier task's data, so any worker can run it any time |
| **Task_ID / Worker_ID / Attempt_Num** | Which task / which worker / how many times this task was sent (1, 2, 3...) |
| **Checksum / CRC** | Small number computed from the payload to detect corruption |
| **SHA-256 / nonce** | Fingerprint function / the number we try until the hash looks right (busy-work compute) |
| **Command Hub / Dispatcher** | The server |
| **Worker / compute node / client** | A program that runs tasks |
| **Queue** | The list of tasks waiting to be sent (1,000) |
| **Loss / delay / jitter** | Packets dropped / packets late / delay that varies |
| **netem / tc / qdisc** | Linux tools that fake bad network conditions |
| **Loopback (`lo`)** | Virtual network inside your machine; where we run tests |
| **LAN** | Local network; "baseline" means no added loss or delay |
| **pcap** | Packet capture file; opened in Wireshark |
| **tcpdump / tshark / Wireshark** | Tools to record and inspect packets (CLI / CLI / GUI) |
| **WSL2** | Linux inside Windows; use it to run netem |
| **Seed / deterministic** | Fixed number that makes "random" choices repeat exactly |
| **CSV** | Plain comma-separated table file; our logs and results |
| **Min / median / max** | Smallest / middle / largest of the 5 runs |
| **LMS** | University portal where we submit (one submission per group) |
| **Git / branch / PR** | Version control / your own line of work / request to merge into `main` after review |
| **CODEOWNERS** | GitHub file saying who owns which files |
| **Stub** | Tiny fake version of the other side so you can test before your partner finishes |
| **TA** | Teaching assistant who grades on Linux |

---

## 17. Brief for AI assistants

Paste or point your agent here first.

```
PROJECT: RJDAP = Reliable Job Dispatch & Aggregation Protocol (working name; team picks a unique one). CSE361 Computer Networks, Fall 2026, Project 2, 5 students, 25% of course.
GOAL: custom UDP protocol. 1 server (Command Hub) dispatches 1,000 stateless tasks (hash search) to >=4 workers. Results must be counted EXACTLY ONCE despite loss, delay, crashes.
MESSAGES: WORKER_JOIN, HEARTBEAT, TASK_DISPATCH, TASK_RESULT, ACK_RESULT. Header fields: Task_ID, Worker_ID, Attempt_Num, Payload_Checksum (+ version/type/flags/frag/len). Payload <= 512 bytes.
RULES: UDP only; Python 3.10+; standard library only for networking (no ENet/RakNet etc); runs on Linux+Windows; graded on Linux with tc netem; seeded randomness; log every packet to CSV; >=2 pcaps per scenario; 5 runs per measurement (min/median/max); original design (>=2 own mechanisms) + Mini-RFC.
SCENARIOS: baseline (0 duplicate executions), worker crash (kill client 1, reassign, 100% done), loss 10% (no result counted twice), delayed ACKs delay 150ms server outbound (no crash, no infinite retransmit).
METRICS: total_completion_time, reassigned_task_count, duplicate_results_dropped, worker_idle_time_ms.
ROLES: R1 protocol+RFC (protocol.py), R2 server (server.py), R3 worker (worker.py), R4 testbed+scripts (scripts/, results/), R5 data+docs (logger.py, analysis/, docs/report, slides, README). Edit only files you own; protocol changes via GitHub Issue to R1.
DEADLINES: Phase 1 week 7, Phase 2 week 12, Phase 3 week 14 (confirm dates on LMS).
FILES: PROJECT_GUIDE.md (this file: everything, with milestone checklists).
```

