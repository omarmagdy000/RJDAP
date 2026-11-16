import os
import subprocess

def run_cmd(cmd):
    res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return res.returncode, res.stdout.strip(), res.stderr.strip()

def test_netem_and_cleanup():
    print("1. Applying delayed_ack netem rule...")
    code, out, err = run_cmd("bash scripts/netem_apply.sh delayed_ack lo")
    assert code == 0, f"Failed to apply netem: {err}"

    code, out, _ = run_cmd("tc qdisc show dev lo")
    assert "netem" in out and "150ms" in out, f"netem not active: {out}"
    print("   PASS: 150ms delay active on lo.")

    print("2. Clearing netem rule...")
    code, out, err = run_cmd("bash scripts/netem_clear.sh lo")
    assert code == 0, f"Failed to clear netem: {err}"

    code, out, _ = run_cmd("tc qdisc show dev lo")
    assert "netem" not in out, f"Leftover qdisc found: {out}"
    print("   PASS: lo interface clean.")

    if os.path.exists("src/server.py") and os.path.exists("src/worker.py"):
        print("3. Server and worker detected — running quick baseline smoke test...")
        code, out, err = run_cmd("bash scripts/run_experiment.sh baseline 42 1")
        assert code == 0, f"Baseline run failed: {err}\n{out}"
        print("   PASS: End-to-end baseline run succeeded!")
    else:
        print("3. Server/worker not merged into main yet — skipping end-to-end run.")

if __name__ == "__main__":
    test_netem_and_cleanup()
    print("ALL R4 TESTBED CHECKS PASSED!")
