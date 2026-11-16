#!/usr/bin/env bash
IFACE="${1:-lo}"
sudo tc qdisc del dev "$IFACE" root 2>/dev/null || true
echo "[netem] Cleared qdisc rules on $IFACE."
