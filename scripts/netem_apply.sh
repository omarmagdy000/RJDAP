#!/usr/bin/env bash
set -euo pipefail

SCENARIO="${1:-baseline}"
IFACE="${2:-lo}"

sudo tc qdisc del dev "$IFACE" root 2>/dev/null || true

case "$SCENARIO" in
  baseline|crash)
    echo "[netem] Scenario '$SCENARIO': no network impairment applied on $IFACE."
    ;;
  loss2)
    echo "[netem] Applying 2% packet loss on $IFACE..."
    sudo tc qdisc add dev "$IFACE" root netem loss 2%
    ;;
  loss5)
    echo "[netem] Applying 5% packet loss on $IFACE..."
    sudo tc qdisc add dev "$IFACE" root netem loss 5%
    ;;
  loss10)
    echo "[netem] Applying 10% packet loss on $IFACE..."
    sudo tc qdisc add dev "$IFACE" root netem loss 10%
    ;;
  loss15)
    echo "[netem] Applying 15% packet loss on $IFACE..."
    sudo tc qdisc add dev "$IFACE" root netem loss 15%
    ;;
  delayed_ack)
    echo "[netem] Applying 150ms delay on server outbound packets (sport 9000) on $IFACE..."
    sudo tc qdisc add dev "$IFACE" root handle 1: prio
    sudo tc qdisc add dev "$IFACE" parent 1:3 handle 30: netem delay 150ms
    sudo tc filter add dev "$IFACE" protocol ip parent 1:0 prio 3 u32 \
         match ip sport 9000 0xffff flowid 1:3
    ;;
  *)
    echo "Unknown scenario: $SCENARIO"
    exit 1
    ;;
esac
