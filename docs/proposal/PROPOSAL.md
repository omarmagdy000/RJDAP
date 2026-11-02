# RJDAP Project Proposal (Phase 1)

**Course:** CSE361 Computer Networks, Fall 2026  
**Project 2:** Reliable Job Dispatch & Aggregation Protocol (RJDAP)  
**Team Members & Roles:**  
- **R1 (Protocol Architect & RFC Lead):** `omarmagdy000` (Omar Magdy)  
- **R2 (Command Hub Engineer):** `________`  
- **R3 (Worker Node Engineer):** `________`  
- **R4 (Network Testbed & Automation Engineer):** `________`  
- **R5 (Data, Metrics & Presentation Lead):** `________`  

---

## 1. Scenario & Problem Statement

In distributed batch-computing systems—such as render farms, scientific simulation grids, and distributed hash-cracking clusters—a central coordinator (**Command Hub**) distributes thousands of independent, stateless tasks across a pool of **worker nodes** and aggregates their results.

Using **TCP** for coordinator-to-worker communication introduces head-of-line (HoL) blocking across independent tasks, connection-state overhead per worker, and inflexible retransmission timers that cannot distinguish network propagation delay from worker CPU execution time. Conversely, raw **UDP** eliminates connection overhead and HoL blocking, sending each task and result as a self-contained datagram ($\le 512\text{ B}$ payload). However, UDP provides no delivery guarantees: packets may be lost, delayed, reordered, or duplicated, and worker nodes may abruptly crash mid-execution.

**Our Goal:** Design, specify, and evaluate **RJDAP**, a custom application-layer reliability protocol built directly on UDP using only the Python 3.10+ standard library. RJDAP dispatches **1,000 stateless SHA-256 nonce-search tasks** across **$\ge 4$ workers** and guarantees that:
1. **100% of tasks complete** even under packet loss, high latency, or sudden worker crashes.
2. **Every task result is counted exactly once** at the Command Hub (zero duplicate aggregations and zero unnecessary task recomputations).

---

## 2. Motivation & Design Philosophy

Why build a custom UDP protocol rather than layering over existing transport protocols?

1. **Task-Level Independence vs. Byte-Stream Ordering:** TCP enforces strict byte-stream ordering. If packet $k$ is lost, packets $k+1 \dots k+n$ are held in the kernel receive buffer even if they carry results for completely independent tasks. RJDAP operates on discrete `Task_ID`s so every arriving datagram is processed immediately.
2. **Separating Compute Time from Network RTT:** When a Command Hub dispatches a task and waits for a `TASK_RESULT`, the elapsed time is $\text{RTT} + T_{\text{compute}}$. Standard transport timers conflate the two. RJDAP workers report their exact execution time (`compute_us`) in the result payload, enabling the server to isolate pure network RTT.
3. **Lightweight Exactly-Once Semantics:** Full two-phase commit (2PC) is too chatty for small 50 ms tasks over lossy links. RJDAP achieves exactly-once semantics in a single round-trip during normal operation by combining **at-least-once delivery** (bounded retries with exponential backoff), **worker-side result caching** (never recomputing a finished `Task_ID`), and **server-side idempotent deduplication** (recording `DONE` tasks and re-acknowledging duplicates).

---

## 3. Technical Approach & Protocol Overview

### 3.1 Compact 14-Byte Binary Header
Every RJDAP datagram begins with a fixed 14-byte big-endian header (`struct` format `'!BBHIBBHH'`), followed by $0\text{--}512\text{ B}$ of payload:
- `Version` (4b) & `MsgType` (4b): Version `1`; message types `WORKER_JOIN (1)`, `JOIN_ACK (2)`, `HEARTBEAT (3)`, `TASK_DISPATCH (4)`, `TASK_RESULT (5)`, `ACK_RESULT (6)`.
- `Flags` (8b): `FRAG (0x01)`, `RETX (0x02)`, `LAST (0x04)`.
- `Worker_ID` (16b), `Task_ID` (32b), `Attempt_Num` (8b).
- `FragIdx` (4b) & `FragCnt` (4b): Supports splitting payloads $> 512\text{ B}$ into up to 15 fragments.
- `Payload_Len` (16b) & `Payload_Checksum` (16b): CRC-16/CCITT-FALSE computed over the header (with the checksum field zeroed) plus the payload, protecting both routing fields (`Task_ID`, `MsgType`) and task data against bit flips.

### 3.2 Two Original Protocol Mechanisms
To go beyond standard textbook stop-and-wait ARQ, RJDAP introduces two original mechanisms:

1. **M1 — Compute-Compensated, Attempt-Matched Adaptive RTO:**
   - Each `TASK_DISPATCH` carries an `Attempt_Num` ($1, 2, \dots$), which the worker echoes in `TASK_RESULT` along with `compute_us` (microseconds spent in the SHA-256 loop).
   - Because `Attempt_Num` resolves retransmission ambiguity, the server never discards RTT samples from retransmitted tasks (unlike Karn's algorithm in TCP) and subtracts `compute_us` to feed pure network RTT into a per-worker Jacobson/Karels estimator ($\text{RTO} = \text{SRTT} + 4 \cdot \text{RTTVAR}$).
2. **M2 — Cumulative 32-Bit ACK Bitmap across Independent Tasks:**
   - Every `ACK_RESULT` acknowledges `header.task_id` and carries a 32-bit bitmap where bit $i \in [0, 31]$ confirms whether `task_id - (i + 1)` is also `DONE` at the server.
   - Under 10% packet loss, if an earlier `ACK_RESULT` was dropped on the return path, the next surviving `ACK_RESULT` automatically quenches the worker's retransmit timer without an extra packet exchange.

### 3.3 Evaluation & Team Execution Plan
We will evaluate RJDAP on a Linux `tc netem` loopback testbed across four mandatory scenarios (**Baseline LAN**, **Worker Crash via `kill -9`**, **Severe 10% Packet Loss**, and **150 ms Delayed Server ACKs**), repeating every measurement 5 times with deterministic seeds (`42–46`) and logging every packet event to CSV and `.pcap` captures. Work is partitioned cleanly across 5 roles (`protocol.py`, `server.py`, `worker.py`, `scripts/`, `analysis/`) with strict interface contracts frozen on Day 0.
