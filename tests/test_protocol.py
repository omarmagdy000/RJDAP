"""Unit tests for src/protocol.py. Owner: R1.

Run from the repo root:  python3 -m unittest discover tests -v
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import protocol as P  # noqa: E402


class TestConstants(unittest.TestCase):
    def test_header_is_14_bytes(self):
        self.assertEqual(P.HEADER_SIZE, 14)
        self.assertEqual(P.MAX_DATAGRAM, 526)

    def test_message_types_fit_in_4_bits(self):
        for t in P.MSG_NAMES:
            self.assertTrue(1 <= t <= 15)


class TestCrc(unittest.TestCase):
    def test_standard_check_value(self):
        # Published check value of CRC-16/CCITT-FALSE for "123456789"
        self.assertEqual(P.crc16(b"123456789"), 0x29B1)

    def test_chaining_equals_one_shot(self):
        self.assertEqual(P.crc16(b"6789", P.crc16(b"12345")), P.crc16(b"123456789"))


class TestPackUnpack(unittest.TestCase):
    def test_round_trip_all_fields(self):
        pkt = P.pack(P.TASK_DISPATCH, worker_id=513, task_id=70000, attempt=3,
                     payload=b"hello", flags=P.FLAG_RETX, frag_idx=2, frag_count=5)
        h, payload = P.unpack(pkt)
        self.assertEqual((h.version, h.msg_type, h.flags), (1, P.TASK_DISPATCH, P.FLAG_RETX))
        self.assertEqual((h.worker_id, h.task_id, h.attempt), (513, 70000, 3))
        self.assertEqual((h.frag_idx, h.frag_count, h.payload_len), (2, 5, 5))
        self.assertEqual(payload, b"hello")
        self.assertEqual(len(pkt), P.HEADER_SIZE + 5)

    def test_exact_bytes_of_empty_join(self):
        pkt = P.pack(P.WORKER_JOIN, worker_id=1)
        self.assertEqual(pkt[:12].hex(), "110000010000000000010000")
        self.assertEqual(len(pkt), 14)

    def test_max_payload_ok_and_one_more_rejected(self):
        P.unpack(P.pack(P.TASK_RESULT, 1, 1, 1, b"x" * P.MAX_PAYLOAD))
        with self.assertRaises(P.ProtocolError):
            P.pack(P.TASK_RESULT, 1, 1, 1, b"x" * (P.MAX_PAYLOAD + 1))

    def test_pack_rejects_bad_fields(self):
        bad = [
            dict(msg_type=0, worker_id=1),
            dict(msg_type=9, worker_id=1),
            dict(msg_type=P.HEARTBEAT, worker_id=70000),          # > 16 bits
            dict(msg_type=P.HEARTBEAT, worker_id=1, task_id=-1),
            dict(msg_type=P.HEARTBEAT, worker_id=1, attempt=256),
            dict(msg_type=P.HEARTBEAT, worker_id=1, flags=0x80),
            dict(msg_type=P.HEARTBEAT, worker_id=1, frag_idx=1, frag_count=1),
            dict(msg_type=P.HEARTBEAT, worker_id=1, frag_count=16),
        ]
        for kwargs in bad:
            with self.subTest(**kwargs), self.assertRaises(P.ProtocolError):
                P.pack(**kwargs)


class TestUnpackRejects(unittest.TestCase):
    def setUp(self):
        self.pkt = P.pack(P.TASK_RESULT, 2, 42, 1, P.encode_result(True, 12345, 900))

    def test_every_single_bit_flip_is_detected(self):
        for byte in range(len(self.pkt)):
            for bit in range(8):
                broken = bytearray(self.pkt)
                broken[byte] ^= 1 << bit
                with self.subTest(byte=byte, bit=bit), self.assertRaises(P.ProtocolError):
                    P.unpack(bytes(broken))

    def test_truncated_and_padded(self):
        for data in (b"", self.pkt[:13], self.pkt[:-1], self.pkt + b"\x00"):
            with self.subTest(n=len(data)), self.assertRaises(P.ProtocolError):
                P.unpack(data)

    def test_wrong_version(self):
        broken = bytearray(self.pkt)
        broken[0] = (2 << 4) | P.TASK_RESULT
        with self.assertRaises(P.ProtocolError):
            P.unpack(bytes(broken))

    def test_unknown_flags_are_ignored_on_receipt(self):
        pkt = bytearray(P.pack(P.HEARTBEAT, 1))
        pkt[1] = 0x80
        crc = P._packet_crc(bytes(pkt[:12]), b"")
        pkt[12:14] = crc.to_bytes(2, "big")
        self.assertEqual(P.unpack(bytes(pkt))[0].flags, 0x80)


class TestPayloads(unittest.TestCase):
    def test_join_ack(self):
        self.assertEqual(P.decode_join_ack(P.encode_join_ack(1000, 200)), (1000, 200))

    def test_heartbeat(self):
        hb = P.decode_heartbeat(P.encode_heartbeat(1_700_000_000_000_000, P.STATE_BUSY))
        self.assertEqual(hb, (1_700_000_000_000_000, P.STATE_BUSY))

    def test_dispatch_with_and_without_data(self):
        key = bytes(range(16))
        d = P.decode_dispatch(P.encode_dispatch(key, 2**40, 50_000, 16))
        self.assertEqual(d, P.Dispatch(key, 2**40, 50_000, 16, b""))
        d = P.decode_dispatch(P.encode_dispatch(key, 0, 1, 1, b"extra"))
        self.assertEqual(d.data, b"extra")
        with self.assertRaises(P.ProtocolError):
            P.encode_dispatch(b"short", 0, 1, 1)
        with self.assertRaises(P.ProtocolError):
            P.decode_dispatch(b"\x00" * 10)

    def test_result(self):
        self.assertEqual(P.decode_result(P.encode_result(False, 0, 5)), (False, 0, 5))
        with self.assertRaises(P.ProtocolError):
            P.decode_result(b"\x00" * 12)

    def test_payloads_fit_in_one_packet(self):
        key = b"k" * 16
        for payload in (P.encode_join_ack(1, 1), P.encode_heartbeat(1, 0),
                        P.encode_dispatch(key, 1, 1, 1), P.encode_result(True, 1, 1),
                        P.encode_ack(5, set())):
            self.assertLessEqual(len(payload), P.MAX_PAYLOAD)


class TestAckBitmap(unittest.TestCase):
    def test_bitmap_round_trip(self):
        done = {99, 97, 68, 67, 10}
        ids = P.decode_ack(100, P.encode_ack(100, done))
        self.assertEqual(ids[0], 100)
        self.assertEqual(sorted(ids[1:]), [68, 97, 99])   # 67 is 33 back: outside window

    def test_low_task_ids_never_go_negative(self):
        self.assertEqual(P.decode_ack(0, P.encode_ack(0, {0})), [0])
        self.assertEqual(P.decode_ack(2, b"\xff\xff\xff\xff"), [2, 1, 0])


if __name__ == "__main__":
    unittest.main()
