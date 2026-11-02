"""RJDAP wire format, version 1: header, checksum and payload codecs.

Owner: R1 (Protocol Architect). The server and workers touch the wire only
through pack() / unpack() and the payload helpers below, so a change to the
format happens here and nowhere else. Standard library only.
"""

from __future__ import annotations

import binascii
import struct
from collections.abc import Container
from typing import NamedTuple

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
PROTOCOL_NAME = "RJDAP"
VERSION = 1

HEADER_FORMAT = "!BBHIBBHH"                    # network byte order, 14 bytes
_HEADER = struct.Struct(HEADER_FORMAT)         # pre-compiled for speed
HEADER_SIZE = _HEADER.size                     # 14
CHECKSUM_OFFSET = 12                           # Payload_Checksum lives at bytes 12-13
MAX_PAYLOAD = 512                              # brief: payload <= 512 bytes per packet
MAX_DATAGRAM = HEADER_SIZE + MAX_PAYLOAD       # 526, use as recvfrom() buffer size
MAX_FRAGMENTS = 15                             # frag_count is a 4-bit field

# Message types (4-bit field; 0 is reserved and always rejected)
WORKER_JOIN = 1
JOIN_ACK = 2
HEARTBEAT = 3
TASK_DISPATCH = 4
TASK_RESULT = 5
ACK_RESULT = 6
MSG_NAMES = {
    WORKER_JOIN: "WORKER_JOIN",
    JOIN_ACK: "JOIN_ACK",
    HEARTBEAT: "HEARTBEAT",
    TASK_DISPATCH: "TASK_DISPATCH",
    TASK_RESULT: "TASK_RESULT",
    ACK_RESULT: "ACK_RESULT",
}

# Flag bits (byte 1). Unknown bits must be sent as 0 and are ignored on receipt.
FLAG_FRAG = 0x01   # packet is one fragment of a larger payload
FLAG_RETX = 0x02   # packet is a retransmission (helps reading pcaps)
FLAG_LAST = 0x04   # last fragment of a fragmented payload
FLAG_MASK = FLAG_FRAG | FLAG_RETX | FLAG_LAST

# Worker states carried in HEARTBEAT
STATE_IDLE = 0
STATE_BUSY = 1

ACK_BITMAP_BITS = 32


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


# ---------------------------------------------------------------------------
# Checksum
# ---------------------------------------------------------------------------
def crc16(data: bytes, value: int = 0xFFFF) -> int:
    """CRC-16/CCITT-FALSE (poly 0x1021, init 0xFFFF). Chainable via `value`."""
    return binascii.crc_hqx(data, value)


_ZERO_CRC = b"\x00\x00"


def _packet_crc(head12: bytes, payload: bytes) -> int:
    """CRC over header bytes 0-11, two zero bytes (checksum field), payload."""
    return crc16(payload, crc16(_ZERO_CRC, crc16(head12)))


# ---------------------------------------------------------------------------
# Packet encode / decode
# ---------------------------------------------------------------------------
def pack(msg_type: int, worker_id: int, task_id: int = 0, attempt: int = 0,
         payload: bytes = b"", flags: int = 0,
         frag_idx: int = 0, frag_count: int = 1) -> bytes:
    """Build one datagram: 14-byte header + payload, checksum filled in."""
    if msg_type not in MSG_NAMES:
        raise ProtocolError(f"unknown msg_type {msg_type}")
    if len(payload) > MAX_PAYLOAD:
        raise ProtocolError(f"payload {len(payload)} B > {MAX_PAYLOAD} B")
    if flags & ~FLAG_MASK:
        raise ProtocolError(f"undefined flag bits 0x{flags:02x}")
    if not 0 <= frag_idx < frag_count <= MAX_FRAGMENTS:
        raise ProtocolError(f"bad fragment {frag_idx}/{frag_count}")
    try:
        head = _HEADER.pack((VERSION << 4) | msg_type, flags, worker_id, task_id,
                            attempt, (frag_idx << 4) | frag_count, len(payload), 0)
    except struct.error as exc:                    # field out of range
        raise ProtocolError(str(exc)) from None
    crc = _packet_crc(head[:CHECKSUM_OFFSET], payload)
    return head[:CHECKSUM_OFFSET] + crc.to_bytes(2, "big") + payload


def unpack(datagram: bytes) -> tuple[Header, bytes]:
    """Validate and split a datagram. Raises ProtocolError -> caller drops it."""
    if len(datagram) < HEADER_SIZE:
        raise ProtocolError("datagram shorter than header")
    vt, flags, wid, tid, att, frag, plen, csum = _HEADER.unpack_from(datagram)
    version, msg_type = vt >> 4, vt & 0x0F
    if version != VERSION:
        raise ProtocolError(f"unsupported version {version}")
    if msg_type not in MSG_NAMES:
        raise ProtocolError(f"unknown msg_type {msg_type}")
    if plen > MAX_PAYLOAD or len(datagram) != HEADER_SIZE + plen:
        raise ProtocolError("length mismatch")
    frag_idx, frag_count = frag >> 4, frag & 0x0F
    if frag_idx >= frag_count:
        raise ProtocolError("bad fragment fields")
    view = memoryview(datagram)
    if _packet_crc(view[:CHECKSUM_OFFSET], view[HEADER_SIZE:]) != csum:
        raise ProtocolError("checksum mismatch")
    header = Header(version, msg_type, flags, wid, tid, att,
                    frag_idx, frag_count, plen, csum)
    return header, bytes(view[HEADER_SIZE:])


# ---------------------------------------------------------------------------
# Payload codecs (one per message type; WORKER_JOIN has an empty payload)
# ---------------------------------------------------------------------------
_JOIN_ACK = struct.Struct("!HH")        # heartbeat_ms, base_rto_ms
_HEARTBEAT = struct.Struct("!QB")       # sent_ts_us, state
_DISPATCH = struct.Struct("!16sQIB")    # job_key, start_nonce, count, difficulty_bits
_RESULT = struct.Struct("!BQI")         # found, nonce, compute_us
_ACK = struct.Struct("!I")              # cumulative ACK bitmap


class JoinAck(NamedTuple):
    heartbeat_ms: int
    base_rto_ms: int


class Heartbeat(NamedTuple):
    sent_ts_us: int
    state: int


class Dispatch(NamedTuple):
    job_key: bytes
    start_nonce: int
    count: int
    difficulty_bits: int
    data: bytes          # optional extra task data (fragmented in Phase 2)


class Result(NamedTuple):
    found: bool
    nonce: int
    compute_us: int


def _decode(codec: struct.Struct, payload: bytes, name: str) -> tuple:
    if len(payload) != codec.size:
        raise ProtocolError(f"{name} payload must be {codec.size} B, got {len(payload)}")
    return codec.unpack(payload)


def _encode(codec: struct.Struct, *fields) -> bytes:
    try:
        return codec.pack(*fields)
    except struct.error as exc:
        raise ProtocolError(str(exc)) from None


def encode_join_ack(heartbeat_ms: int, base_rto_ms: int) -> bytes:
    return _encode(_JOIN_ACK, heartbeat_ms, base_rto_ms)


def decode_join_ack(payload: bytes) -> JoinAck:
    return JoinAck(*_decode(_JOIN_ACK, payload, "JOIN_ACK"))


def encode_heartbeat(sent_ts_us: int, state: int) -> bytes:
    return _encode(_HEARTBEAT, sent_ts_us, state)


def decode_heartbeat(payload: bytes) -> Heartbeat:
    return Heartbeat(*_decode(_HEARTBEAT, payload, "HEARTBEAT"))


def encode_dispatch(job_key: bytes, start_nonce: int, count: int,
                    difficulty_bits: int, data: bytes = b"") -> bytes:
    if len(job_key) != 16:
        raise ProtocolError("job_key must be exactly 16 bytes")
    return _encode(_DISPATCH, job_key, start_nonce, count, difficulty_bits) + data


def decode_dispatch(payload: bytes) -> Dispatch:
    if len(payload) < _DISPATCH.size:
        raise ProtocolError("TASK_DISPATCH payload too short")
    fields = _DISPATCH.unpack_from(payload)
    return Dispatch(*fields, data=payload[_DISPATCH.size:])


def encode_result(found: bool, nonce: int, compute_us: int) -> bytes:
    return _encode(_RESULT, int(found), nonce, compute_us)


def decode_result(payload: bytes) -> Result:
    found, nonce, compute_us = _decode(_RESULT, payload, "TASK_RESULT")
    return Result(bool(found), nonce, compute_us)


# ---------------------------------------------------------------------------
# Original mechanism 2: cumulative ACK bitmap
#   ACK_RESULT acknowledges header.task_id. Bit i of the bitmap (bit 0 = LSB)
#   set means task_id - (i + 1) is DONE as well, so one surviving ACK repairs
#   up to 32 earlier lost ACKs.
# ---------------------------------------------------------------------------
def encode_ack(task_id: int, done: Container[int]) -> bytes:
    bitmap = 0
    for i in range(min(ACK_BITMAP_BITS, task_id)):
        if task_id - 1 - i in done:
            bitmap |= 1 << i
    return _encode(_ACK, bitmap)


def decode_ack(task_id: int, payload: bytes) -> list[int]:
    """Return every Task_ID this ACK_RESULT confirms (header task first)."""
    (bitmap,) = _decode(_ACK, payload, "ACK_RESULT")
    return [task_id] + [task_id - 1 - i for i in range(min(ACK_BITMAP_BITS, task_id))
                        if bitmap >> i & 1]
