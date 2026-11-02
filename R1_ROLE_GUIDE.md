# R1 (Protocol Architect & RFC Lead) — Line-by-Line Code Review, Testing & Optimization Guide

> **Owner:** Omar Magdy (`omarmagdy000`) — Role 1: Protocol Architect & RFC Lead  
> **Scope:** Everything created in Milestone 1 (Phase 1 / Week 7) for R1.  
> **Purpose of this file:** Your personal companion sheet so you can explain every line of your code, why every bit/byte size was chosen, how the tests work, and how the code is optimized during your video demo, TA code review, and pair syncs with R2 & R5.

---

## 1. What Your Role (R1) Is About & Exactly What Your Code Does

### What Your Part Is About (The Big Picture)
In this project, a **Command Hub (server, built by R2)** sends 1,000 tasks over **raw UDP** to **4+ Worker nodes (built by R3)** and collects their answers. Because UDP only sends raw bytes (`bytes`) across the network and gives zero guarantees (packets can get corrupted, truncated, lost, duplicated, or arrive out of order), the server and workers cannot just send Python objects or plain text to each other.

**Your job as R1 (Protocol Architect & RFC Lead)** is to design and build **the language they speak on the wire**:
1. **You define the binary contract (`src/protocol.py`):** You decide the exact byte-by-byte layout of every UDP packet (the 14-byte header and the payloads for all 6 message types) so that R2's server and R3's worker can talk to each other without ever touching raw bytes or `struct` formats themselves.
2. **You guard the door against bad packets:** Whenever a packet arrives from the UDP socket, your code checks its version, message type, length, fragment numbers, and **16-bit CRC checksum**. If even a single bit was flipped on the network, your code catches it and raises `ProtocolError` so the server or worker drops it safely.
3. **You build the wire support for our 2 Original Mechanisms (M1 & M2):**
   - **M1 (Compute-Compensated Adaptive RTO):** Your `TASK_RESULT` payload carries `compute_us` (how many microseconds the worker spent computing) alongside `Attempt_Num` in the header, allowing the server to subtract CPU time from round-trip time and measure pure network delay.
   - **M2 (Cumulative 32-Bit ACK Bitmap):** Your `ACK_RESULT` payload carries a 32-bit integer (`bitmap`) where each bit confirms whether one of the previous 32 tasks (`task_id - 1` down to `task_id - 32`) is also finished. If an earlier ACK was lost on a 10%-loss network, the next surviving ACK automatically confirms it!
4. **You write the official specification (`MINI_RFC.md`, `PROPOSAL.md`, `FSM_DIAGRAMS.md`):** Just like real internet protocols (TCP, QUIC, HTTP), your Mini-RFC documents the exact header bit offsets, state machines (FSMs), and rules that R2 and R3 must follow.

---

### Exactly What `src/protocol.py` Does (Step-by-Step)
Think of `src/protocol.py` as a **translator and security guard** sitting right above the UDP socket on both the server and the workers:

1. **When Sending a Packet (`encode_*` $\rightarrow$ `pack()`):**
   - First, the server or worker calls one of your payload encoders (for example, `encode_dispatch(...)` to pack a task's 16-byte `job_key`, `start_nonce`, `count`, and `difficulty_bits` into 29 raw bytes, or `encode_result(...)` to pack `found`, `nonce`, and `compute_us` into 13 raw bytes).
   - Next, they pass that payload to `pack(msg_type, worker_id, task_id, attempt, payload, ...)`.
   - `pack()` checks that every field is legal (valid message type, payload $\le 512\text{ B}$, valid flags, valid fragment numbers), builds the **14-byte big-endian binary header**, computes a **16-bit CRC-CCITT checksum** over the header + payload, writes the checksum into bytes 12–13, and returns one ready-to-send `bytes` datagram for `socket.sendto()`.

2. **When Receiving a Packet (`unpack()` $\rightarrow$ `decode_*`):**
   - When `socket.recvfrom(526)` receives raw bytes from the network, the server or worker passes them straight into `unpack(datagram)`.
   - `unpack()` inspects the raw bytes:
     - Is it at least 14 bytes long?
     - Is the protocol version `1` and the message type between `1` and `6`?
     - Does the actual UDP packet size match `14 + Payload_Len` (not cut off or padded)?
     - Are the fragment numbers valid (`frag_idx < frag_count`)?
     - **Does the recomputed 16-bit CRC match `Payload_Checksum`?**
   - If **anything** fails, `unpack()` immediately raises `ProtocolError` so the caller logs a `drop` and ignores the bad packet.
   - If everything is valid, `unpack()` returns `(header, payload_bytes)`, where `header` is a clean `Header` object (`header.msg_type`, `header.worker_id`, `header.task_id`, `header.attempt`, etc.), and the caller passes `payload_bytes` to the matching `decode_*` function (`decode_dispatch`, `decode_result`, `decode_ack`, etc.) to get back clean Python fields.

---

## 2. What R1 Owns & What Was Completed for Milestone 1

| File | Purpose | Status |
|---|---|---|
| [`src/protocol.py`](src/protocol.py) | Wire format v1: 14-byte binary header, CRC-16/CCITT-FALSE checksum, `pack()`/`unpack()`, and payload encoders/decoders for all 6 message types + cumulative ACK bitmap | Done |
| [`tests/test_protocol.py`](tests/test_protocol.py) | 19 unit tests (including exhaustive 216-bit single-bit-flip corruption test, boundary checks, round-trips, and standard CRC test vector) | Done (19/19 passing in ~5 ms) |
| [`docs/rfc/MINI_RFC.md`](docs/rfc/MINI_RFC.md) | Mini-RFC Phase 1 draft (Sections 1–3: Introduction, Architecture & FSMs, Message Formats with bit offsets, field-size justifications, and real hex packet dumps) | Done |
| [`docs/proposal/PROPOSAL.md`](docs/proposal/PROPOSAL.md) | 3-page project proposal: scenario, motivation, technical approach, and the 2 original mechanisms (M1 & M2) | Done |
| [`docs/diagrams/FSM_DIAGRAMS.md`](docs/diagrams/FSM_DIAGRAMS.md) | Architecture diagram + Server Task FSM + Server Worker-Liveness FSM + Worker Node FSM | Done |

---

## 3. Line-by-Line Walkthrough of `src/protocol.py`

### Lines 1–14: Module Docstring & Imports
```python
from __future__ import annotations

import binascii
import struct
from collections.abc import Container
from typing import NamedTuple
```
- `from __future__ import annotations`: Postpones evaluation of type hints so functions can use modern type syntax (`tuple[Header, bytes]`, `list[int]`) cleanly with zero import-time overhead.
- `binascii`: Standard-library C extension module. We use `binascii.crc_hqx` which computes CRC-16/CCITT-FALSE directly in compiled C rather than a slow Python loop.
- `struct`: Standard-library binary packing/unpacking module for network byte order (`!`).
- `Container` & `NamedTuple`: Used for clean, self-documenting return types (`Header`, `JoinAck`, `Heartbeat`, `Dispatch`, `Result`) that behave like tuples (fast, immutable, indexable) and also allow attribute access (`header.task_id`, `header.worker_id`).

---

### Lines 16–56: Protocol Constants, Message Types & Flags
```python
PROTOCOL_NAME = "RJDAP"
VERSION = 1

HEADER_FORMAT = "!BBHIBBHH"                    # network byte order, 14 bytes
_HEADER = struct.Struct(HEADER_FORMAT)         # pre-compiled for speed
HEADER_SIZE = _HEADER.size                     # 14
CHECKSUM_OFFSET = 12                           # Payload_Checksum lives at bytes 12-13
MAX_PAYLOAD = 512                              # brief: payload <= 512 bytes per packet
MAX_DATAGRAM = HEADER_SIZE + MAX_PAYLOAD       # 526, use as recvfrom() buffer size
MAX_FRAGMENTS = 15                             # frag_count is a 4-bit field
```
- **Why `"!BBHIBBHH"`?**
  - `!` = Network byte order (**big-endian**), required by all internet protocols so x86 little-endian machines and network tools (Wireshark) agree on multi-byte integers.
  - `B` (byte 0): 1 unsigned byte holding `version` in the top 4 bits (`version << 4`) and `msg_type` in the bottom 4 bits (`msg_type & 0x0F`).
  - `B` (byte 1): 1 unsigned byte for `flags` (`FLAG_FRAG=0x01`, `FLAG_RETX=0x02`, `FLAG_LAST=0x04`).
  - `H` (bytes 2–3): 2-byte unsigned short ($0\text{--}65535$) for `Worker_ID`.
  - `I` (bytes 4–7): 4-byte unsigned int ($0\text{--}4{,}294{,}967{,}295$) for `Task_ID`.
  - `B` (byte 8): 1 unsigned byte ($0\text{--}255$) for `Attempt_Num`.
  - `B` (byte 9): 1 unsigned byte packing `frag_idx` (high 4 bits, $0\text{--}14$) and `frag_count` (low 4 bits, $1\text{--}15$).
  - `H` (bytes 10–11): 2-byte unsigned short for `Payload_Len` ($0\text{--}512$).
  - `H` (bytes 12–13): 2-byte unsigned short for `Payload_Checksum` (CRC-16).
  - Total = $1 + 1 + 2 + 4 + 1 + 1 + 2 + 2 = 14\text{ bytes}$.
- **Why `_HEADER = struct.Struct(HEADER_FORMAT)`?**
  - Calling `struct.pack("!BBHIBBHH", ...)` parses the format string on every call. Pre-compiling a `struct.Struct` object once at import time makes packing/unpacking ~30% faster.
- **Message Types (Lines 28–42):**
  - `WORKER_JOIN = 1`, `JOIN_ACK = 2`, `HEARTBEAT = 3`, `TASK_DISPATCH = 4`, `TASK_RESULT = 5`, `ACK_RESULT = 6`.
  - `0` is deliberately left unused so an all-zero buffer is immediately rejected as invalid.
  - `MSG_NAMES` maps integer codes to human-readable strings for `logger.py`.
- **Flags (Lines 44–48):**
  - `FLAG_FRAG = 0x01` (bit 0), `FLAG_RETX = 0x02` (bit 1), `FLAG_LAST = 0x04` (bit 2).
  - `FLAG_MASK = 0x07` lets `pack()` reject accidental garbage flags when sending, while `unpack()` ignores unknown flags on receipt (forward compatibility, just like RFCs require).

---

### Lines 58–72: `ProtocolError` and `Header` NamedTuple
```python
class ProtocolError(ValueError):
    """Any datagram or field that must not be sent or must be dropped."""

class Header(NamedTuple):
    version: int
    msg_type: int
    flags: int
    worker_id: int
    task_id: int
    attempt: int
    frag_idx: int
    frag_count: int
    payload_len: int
    checksum: int
```
- **Single exception contract for R2 & R3:** R2 (server) and R3 (worker) only need one `try ... except P.ProtocolError:` around `P.unpack(datagram)`. Any malformed, truncated, wrong-version, or corrupted packet raises `ProtocolError`, telling the caller to log a `drop` event and ignore the packet.

---

### Lines 75–87: CRC-16/CCITT-FALSE Checksum
```python
def crc16(data: bytes, value: int = 0xFFFF) -> int:
    """CRC-16/CCITT-FALSE (poly 0x1021, init 0xFFFF). Chainable via `value`."""
    return binascii.crc_hqx(data, value)

_ZERO_CRC = b"\x00\x00"

def _packet_crc(head12: bytes, payload: bytes) -> int:
    """CRC over header bytes 0-11, two zero bytes (checksum field), payload."""
    return crc16(payload, crc16(_ZERO_CRC, crc16(head12)))
```
- **What it does:** Computes a 16-bit cyclic redundancy check over the first 12 bytes of the header, two zero bytes (standing in for the checksum field itself), and the payload.
- **Why cover the header too?** If a bit flip turned `Task_ID=42` into `Task_ID=43`, or turned `HEARTBEAT` into `ACK_RESULT`, checking only the payload wouldn't catch it! Covering the header + payload protects the entire datagram.
- **Why chain three `crc16` calls instead of `crc16(head12 + b"\x00\x00" + payload)`?**
  - Chaining via the `value` parameter avoids allocating and copying a temporary concatenated `bytes` object on every `unpack()`. Combined with `memoryview`, `unpack()` validates the CRC with **zero extra memory copies**.

---

### Lines 90–136: `pack()` and `unpack()`
```python
def pack(msg_type: int, worker_id: int, task_id: int = 0, attempt: int = 0,
         payload: bytes = b"", flags: int = 0,
         frag_idx: int = 0, frag_count: int = 1) -> bytes:
```
1. Validates `msg_type in MSG_NAMES`, `len(payload) <= 512`, no unknown flag bits (`flags & ~FLAG_MASK`), and `0 <= frag_idx < frag_count <= 15`.
2. Packs the 14-byte header with `0` as a placeholder checksum (`_HEADER.pack(...)`). If any integer overflows its byte width (e.g., `worker_id > 65535` or negative), `struct.error` is caught and re-raised as `ProtocolError`.
3. Computes `_packet_crc(head[:12], payload)` and splices the 2-byte big-endian CRC (`crc.to_bytes(2, "big")`) into bytes 12–13, followed by `payload`.

```python
def unpack(datagram: bytes) -> tuple[Header, bytes]:
```
1. Rejects any packet shorter than 14 bytes (`len(datagram) < HEADER_SIZE`).
2. Unpacks the 8 fields from the first 14 bytes using `_HEADER.unpack_from(datagram)` (reads in-place without slicing).
3. Splits byte 0 into `version = vt >> 4` and `msg_type = vt & 0x0F`, verifying `version == 1` and `msg_type in MSG_NAMES`.
4. Verifies `plen <= 512` and that the UDP datagram length equals `14 + plen` (catches both truncated and padded packets).
5. Splits byte 9 into `frag_idx = frag >> 4` and `frag_count = frag & 0x0F`, verifying `frag_idx < frag_count` (note: since `frag_idx >= 0`, this also guarantees `frag_count >= 1`).
6. Wraps `datagram` in a `memoryview` so `view[:12]` and `view[14:]` are zero-copy slices, and checks `_packet_crc(...) == csum`.
7. Returns `(Header(...), bytes(view[14:]))`.

---

### Lines 139–243: Payload Codecs & Original Mechanisms (M1 & M2)

| Helper | Struct Format | Size | Fields & Why |
|---|---|---|---|
| `encode_join_ack` / `decode_join_ack` | `!HH` | 4 B | `heartbeat_ms` (u16), `base_rto_ms` (u16). Lets the server configure worker timers on join. |
| `encode_heartbeat` / `decode_heartbeat` | `!QB` | 9 B | `sent_ts_us` (u64), `state` (`0=IDLE`, `1=BUSY`). Timestamp lets the server/worker track liveness and RTT. |
| `encode_dispatch` / `decode_dispatch` | `!16sQIB` + `data` | $29 + n\text{ B}$ | `job_key` (16 B), `start_nonce` (u64), `count` (u32), `difficulty_bits` (u8), plus optional `data` for Phase 2 fragmentation. |
| `encode_result` / `decode_result` | `!BQI` | 13 B | `found` (bool as u8), `nonce` (u64), `compute_us` (u32). **`compute_us` powers Original Mechanism M1** so the server subtracts worker CPU time from RTT samples. |
| `encode_ack` / `decode_ack` | `!I` | 4 B | `bitmap` (u32). **Powers Original Mechanism M2**: bit $i \in [0, 31]$ is `1` if `task_id - 1 - i` is also `DONE`. `decode_ack` returns the full list of confirmed `Task_ID`s (`[task_id, ...]`). |

---

## 4. How to Test Your Code

Run the full test suite from the repository root (`c:\Users\aa\Desktop\Networking\RJDAP`):

```powershell
python -m unittest discover tests -v
```

### What the 19 Tests in `tests/test_protocol.py` Prove:
1. **`TestConstants`**: Verifies `HEADER_SIZE == 14`, `MAX_DATAGRAM == 526`, and all message type codes fit in 4 bits ($1\text{--}15$).
2. **`TestCrc`**:
   - Checks `crc16(b"123456789") == 0x29B1` (the official IEEE/CCITT standard test vector).
   - Proves that chaining `crc16` across chunks produces the exact same value as one-shot CRC.
3. **`TestPackUnpack`**:
   - Round-trips a packet with non-trivial values in every single field (`worker_id=513`, `task_id=70000`, `attempt=3`, `flags=FLAG_RETX`, `frag_idx=2`, `frag_count=5`).
   - Checks the exact wire hex of an empty `WORKER_JOIN` packet (`110000010000000000010000...`).
   - Boundary test: 512-byte payload succeeds; 513-byte payload raises `ProtocolError`.
   - Out-of-range tests: bad `msg_type`, `worker_id > 65535`, negative `task_id`, `attempt > 255`, unknown flags, `frag_idx >= frag_count`, `frag_count > 15`.
4. **`TestUnpackRejects`**:
   - **Exhaustive single-bit flip test (`test_every_single_bit_flip_is_detected`):** Takes a 27-byte `TASK_RESULT` packet ($27 \times 8 = 216\text{ bits}$), flips every single bit one by one (header bits, checksum bits, and payload bits), and verifies `unpack()` raises `ProtocolError` on all 216 corruptions.
   - Truncated packets (`0` bytes, `13` bytes, missing 1 payload byte) and padded packets (`+1` trailing byte).
   - Wrong protocol version (`version = 2`).
   - Unknown flag bits on receipt are tolerated (forward compatibility) as long as the CRC is valid.
5. **`TestPayloads` & `TestAckBitmap`**:
   - Round-trips every payload type and verifies invalid sizes raise `ProtocolError`.
   - Verifies that `encode_ack(100, {99, 97, 68, 67, 10})` includes `100, 99, 97, 68` and excludes `67` (which is 33 tasks back, outside the 32-bit window), and that `task_id < 32` never produces negative task IDs.

---

## 5. How `src/protocol.py` is Already Optimized (and Why)

We benchmarked `pack()` and `unpack()` on Python 3.13 (200,000 iterations):
- **`pack()`:** **~1.45 microseconds** per packet (~690,000 packets/sec)
- **`unpack()`:** **~1.94 microseconds** per packet (~515,000 packets/sec)

For 1,000 tasks across 4 workers, total serialization time for the entire run is **under 10 milliseconds**. Here are the 4 optimizations built into `src/protocol.py` that you can highlight in your report/video:

1. **Pre-compiled `struct.Struct` objects (`_HEADER`, `_JOIN_ACK`, `_HEARTBEAT`, `_DISPATCH`, `_RESULT`, `_ACK`):** Avoids re-compiling format strings on every packet.
2. **C-accelerated CRC (`binascii.crc_hqx`):** Runs the CRC-16 polynomial in native C instead of bit-shifting in Python (over 50x faster).
3. **Zero-copy `memoryview` + chained CRC in `unpack()`:** `unpack()` uses `_HEADER.unpack_from(datagram)` and slices a `memoryview(datagram)` to verify the CRC without copying slices or concatenating byte strings.
4. **Bit-packed fields (`version|msg_type` and `frag_idx|frag_count`) + 32-bit ACK bitmap:** Saves 2 bytes per header (14 B instead of 16 B) and lets a 4-byte ACK payload replace up to 32 separate ACK packets.

---

## 6. Milestone 1 Outputs & Expected Results

When grading or presenting Milestone 1 (Phase 1 / Week 7), these are the exact outputs produced by your role (R1), where they are located, and what results they show:

### Output 1: Unit Test Suite Results (`tests/test_protocol.py`)
Run command:
```powershell
python -m unittest discover tests -v
```
**Expected Output:**
```text
test_bitmap_round_trip (test_protocol.TestAckBitmap.test_bitmap_round_trip) ... ok
test_low_task_ids_never_go_negative (test_protocol.TestAckBitmap.test_low_task_ids_never_go_negative) ... ok
test_header_is_14_bytes (test_protocol.TestConstants.test_header_is_14_bytes) ... ok
test_message_types_fit_in_4_bits (test_protocol.TestConstants.test_message_types_fit_in_4_bits) ... ok
test_chaining_equals_one_shot (test_protocol.TestCrc.test_chaining_equals_one_shot) ... ok
test_standard_check_value (test_protocol.TestCrc.test_standard_check_value) ... ok
test_exact_bytes_of_empty_join (test_protocol.TestPackUnpack.test_exact_bytes_of_empty_join) ... ok
test_max_payload_ok_and_one_more_rejected (test_protocol.TestPackUnpack.test_max_payload_ok_and_one_more_rejected) ... ok
test_pack_rejects_bad_fields (test_protocol.TestPackUnpack.test_pack_rejects_bad_fields) ... ok
test_round_trip_all_fields (test_protocol.TestPackUnpack.test_round_trip_all_fields) ... ok
test_dispatch_with_and_without_data (test_protocol.TestPayloads.test_dispatch_with_and_without_data) ... ok
test_heartbeat (test_protocol.TestPayloads.test_heartbeat) ... ok
test_join_ack (test_protocol.TestPayloads.test_join_ack) ... ok
test_payloads_fit_in_one_packet (test_protocol.TestPayloads.test_payloads_fit_in_one_packet) ... ok
test_result (test_protocol.TestPayloads.test_result) ... ok
test_every_single_bit_flip_is_detected (test_protocol.TestUnpackRejects.test_every_single_bit_flip_is_detected) ... ok
test_truncated_and_padded (test_protocol.TestUnpackRejects.test_truncated_and_padded) ... ok
test_unknown_flags_are_ignored_on_receipt (test_protocol.TestUnpackRejects.test_unknown_flags_are_ignored_on_receipt) ... ok
test_wrong_version (test_protocol.TestUnpackRejects.test_wrong_version) ... ok
----------------------------------------------------------------------
Ran 19 tests in 0.005s

OK
```
*Meaning:* 100% of header packing, boundary enforcement, CRC computation, bit-corruption detection, and payload encoding tests pass cleanly in under 10 ms.

### Output 2: Wire Serialization & Hex Sample Outputs
Generated from `src/protocol.py` for Worker 3, Task 42 (included directly in the Mini-RFC Section 3.5):

| Message Type | Wire Size | Exact Raw Hex Output on Wire |
|---|---|---|
| `WORKER_JOIN` | 14 B | `11 00 00 03 00 00 00 00 00 01 00 00 c6 57` |
| `JOIN_ACK` | 18 B | `12 00 00 03 00 00 00 00 00 01 00 04 44 df 03 e8 00 c8` |
| `HEARTBEAT` | 23 B | `13 00 00 03 00 00 00 00 00 01 00 09 de 9a 00 00 00 00 00 0f 42 40 01` |
| `TASK_DISPATCH` | 43 B | `14 00 00 03 00 00 00 2a 01 01 00 1d 9b bd 00 11 22 33 44 55 66 77 88 99 aa bb cc dd ee ff 00 00 00 00 00 20 0b 20 00 00 c3 50 10` |
| `TASK_RESULT` | 27 B | `15 00 00 03 00 00 00 2a 01 01 00 0d 88 b9 01 00 00 00 00 00 20 85 89 00 00 30 d4` |
| `ACK_RESULT` | 18 B | `16 00 00 03 00 00 00 2a 01 01 00 04 e9 d7 00 00 00 05` |

*Meaning:* Proves that every packet fits within the maximum datagram size (526 B) and matches the byte-by-byte wire specification in the RFC.

### Output 3: Benchmark & Performance Outputs
Measured across 200,000 calls:
- `pack()` throughput: **~690,000 packets/sec** (1.45 µs per packet)
- `unpack()` throughput: **~515,000 packets/sec** (1.94 µs per packet)
*Meaning:* Packet encoding and decoding consumes less than 1% of total system CPU time during the 1,000-task experiment.

### Output 4: Document Deliverables for Milestone 1
1. **[`docs/rfc/MINI_RFC.md`](docs/rfc/MINI_RFC.md):** Complete formal RFC draft for Sections 1–3 (protocol architecture, FSM diagrams, and bit-level message specifications).
2. **[`docs/proposal/PROPOSAL.md`](docs/proposal/PROPOSAL.md):** 3-page project proposal covering motivation, problem statement, technical approach, and the 2 original mechanisms.
3. **[`docs/diagrams/FSM_DIAGRAMS.md`](docs/diagrams/FSM_DIAGRAMS.md):** Formal Mermaid FSMs for Command Hub task states, worker liveness, and worker node compute loop.
4. **Git Artifacts:** Commit history on `main` and branch `r1/protocol-v1`, tagged `protocol-v1`, and pushed to remote `origin`.

