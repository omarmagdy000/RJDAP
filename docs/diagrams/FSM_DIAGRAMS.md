# RJDAP Architecture & State Machine Diagrams

This folder contains the architecture and Finite State Machine (FSM) diagrams for **RJDAP v1**, maintained by **R1 (Protocol Architect & RFC Lead)**. These diagrams match [`src/protocol.py`](../../src/protocol.py) and [`docs/rfc/MINI_RFC.md`](../rfc/MINI_RFC.md) byte-for-byte.

---

## 1. System Topology & Message Flow

```mermaid
flowchart TB
    subgraph Hub["Command Hub (Server - UDP :9000)"]
        Q["Task Queue (1,000 tasks)<br/>PENDING -> DISPATCHED -> DONE"]
        WR["Worker Registry<br/>ALIVE / DEAD + per-worker SRTT/RTO"]
        DD["Dedup Table (DONE Task_IDs)<br/>+ 32-bit ACK Bitmap Builder"]
    end

    subgraph Pool["Worker Pool (>= 4 UDP Clients)"]
        W1["Worker 1<br/>Result Cache + Retx Timer"]
        W2["Worker 2<br/>Result Cache + Retx Timer"]
        W3["Worker 3<br/>Result Cache + Retx Timer"]
        W4["Worker 4<br/>Result Cache + Retx Timer"]
    end

    W1 & W2 & W3 & W4 <-->|"14B Header + <=512B Payload<br/>WORKER_JOIN, JOIN_ACK, HEARTBEAT,<br/>TASK_DISPATCH, TASK_RESULT, ACK_RESULT"| Hub
```

---

## 2. Command Hub: Per-Task State Machine

Each of the 1,000 tasks in the Command Hub transitions independently through three states:

```mermaid
stateDiagram-v2
    [*] --> PENDING : tasks.make_tasks(1000, seed)
    PENDING --> DISPATCHED : Idle ALIVE worker available<br/>send TASK_DISPATCH (attempt += 1)<br/>start task deadline (RTO + 1.5 * E[compute])
    DISPATCHED --> DONE : First valid TASK_RESULT arrives<br/>record result, send ACK_RESULT (with bitmap)
    DISPATCHED --> PENDING : Task deadline expires OR assigned worker -> DEAD<br/>reassigned_task_count += 1
    PENDING --> DONE : Late valid TASK_RESULT from earlier attempt arrives<br/>record result, send ACK_RESULT (first result wins)
    DONE --> DONE : Any subsequent TASK_RESULT for this Task_ID<br/>duplicate_results_dropped += 1<br/>DO NOT count again, re-send ACK_RESULT
    DONE --> [*] : All 1,000 tasks in DONE state
```

---

## 3. Command Hub: Worker Liveness State Machine

```mermaid
stateDiagram-v2
    [*] --> ALIVE : Receive WORKER_JOIN<br/>register addr, last_seen = now<br/>send JOIN_ACK(heartbeat_ms, base_rto_ms)
    ALIVE --> ALIVE : Receive HEARTBEAT or TASK_RESULT<br/>last_seen = now, update RTT if sample valid
    ALIVE --> ALIVE : Receive duplicate WORKER_JOIN<br/>last_seen = now, re-send JOIN_ACK
    ALIVE --> DEAD : now - last_seen > 3 * heartbeat_ms<br/>move worker's DISPATCHED tasks -> PENDING<br/>reassigned_task_count += k
    DEAD --> ALIVE : Receive WORKER_JOIN or late packet<br/>last_seen = now, send JOIN_ACK
```

---

## 4. Worker Node State Machine

```mermaid
stateDiagram-v2
    [*] --> JOINING : Start worker (--id, --server)
    JOINING --> JOINING : 500 ms timer expires without JOIN_ACK<br/>re-send WORKER_JOIN (FLAG_RETX)
    JOINING --> IDLE : Receive JOIN_ACK<br/>save heartbeat_ms & base_rto_ms, start heartbeat timer

    IDLE --> IDLE : heartbeat_ms timer fires -> send HEARTBEAT(STATE_IDLE)
    IDLE --> WAIT_ACK : Receive TASK_DISPATCH for Task_ID already in cache<br/>re-send cached TASK_RESULT (NO recompute!)
    IDLE --> REASSEMBLING : Receive fragmented TASK_DISPATCH (frag_count > 1)
    REASSEMBLING --> REASSEMBLING : Collect fragments (0 .. frag_count-1)
    REASSEMBLING --> IDLE : Reassembly timeout -> drop partial fragments
    REASSEMBLING --> COMPUTING : All fragments received -> reassemble payload

    IDLE --> COMPUTING : Receive unfragmented TASK_DISPATCH (new Task_ID)
    COMPUTING --> WAIT_ACK : SHA-256 search finishes in compute_us<br/>cache Result under Task_ID<br/>send TASK_RESULT, tries = 1, timer = RTO

    WAIT_ACK --> WAIT_ACK : Retransmit timer expires AND tries < 5<br/>re-send cached TASK_RESULT (FLAG_RETX)<br/>tries += 1, timer = RTO * 2^(tries-1)
    WAIT_ACK --> IDLE : Receive ACK_RESULT where decode_ack() contains Task_ID<br/>stop retransmit timer
    WAIT_ACK --> IDLE : Retransmit timer expires AND tries == 5<br/>stop retrying (keep result in cache in case server re-dispatches)
```
