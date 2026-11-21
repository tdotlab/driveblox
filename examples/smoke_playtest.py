#!/usr/bin/env python
"""Generic smoke test for any place: start a playtest, make sure the player spawns,
fail if the output log has errors, stop. Exit code 0 means clean.

    python examples/smoke_playtest.py [--seconds 3]
"""
import argparse
import re
import sys
import time

from driveblox import Studio, WaitTimeout

ERROR = re.compile(r"\b(error|exception|failed|stack begin)\b", re.I)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=3, help="how long to let the game run")
    args = ap.parse_args()

    with Studio() as s:
        s.play(True)
        try:
            s.wait_for("game.Players.LocalPlayer and game.Players.LocalPlayer.Character", dm="client", timeout=30)
            print("player spawned")
            time.sleep(args.seconds)
        except WaitTimeout as e:
            print(f"FAIL: {e}")
            s.play(False)
            return 1
        log = s.console(last=200)
        s.play(False)

    errors = [ln for ln in log.splitlines() if ERROR.search(ln)]
    for ln in errors:
        print("  " + ln)
    print("FAIL: errors in the output log" if errors else "ok: no errors in the output log")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
