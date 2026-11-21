#!/usr/bin/env python
"""A worked example: play a whole game loop hands-off and assert on server state.

This one is written for a specific game (a diner where you take an order, grill a patty,
flip it, plate it and serve it), so it will not run on your place as is. Read it for the
pattern, which is what to copy:

  * no screenshots: sync on attributes the server publishes (here ``Stage`` and ``Cash``);
  * ``nav`` to a station, ``hold`` E on its ProximityPrompt (a tap is shorter than the
    prompt's HoldDuration, so hold for longer);
  * ``wait_for`` polls a Luau expression instead of sleeping, so the script is fast and
    doesn't flake;
  * one process, one connection, so thousands of calls cost no model round trips.

Game contract assumed: ``workspace.Diner`` (override with DRIVEBLOX_EXAMPLE_ROOT) carries the attributes
Stage, Cash, OrdersServed, GrillUpgraded; stations sit on z = -5 at the x values below.
"""
import os
import sys
import time

from driveblox import Studio

ROOT = os.environ.get("DRIVEBLOX_EXAMPLE_ROOT", "workspace.Diner")
STATIONS = {"order": -24, "grill": -8, "assembly": 8, "pass": 24}  # worktop x positions


class Fail(AssertionError):
    pass


def attr(s, name):
    return s.lua(f"return tostring({ROOT}:GetAttribute('{name}'))", dm="server").strip()


def stage(s, wanted, timeout=12):
    s.wait_for(f"{ROOT}:GetAttribute('Stage') == '{wanted}'", timeout=timeout)


def step(s, station, then):
    s.nav(STATIONS[station], 3, 0, speed=3)
    s.hold("E", 0.4)
    stage(s, then)
    print(f"  {station:<9} -> {then:<14} cash=${attr(s, 'Cash')}")


def expect(label, got, want):
    ok = str(got) == str(want)
    print(f"  [{'ok' if ok else 'FAIL'}] {label}: {got}" + ("" if ok else f" (wanted {want})"))
    if not ok:
        raise Fail(label)


def serve_one(s, tip):
    """Serve one ticket. With tip=False the flip is taken late; returns seconds the first side took."""
    step(s, "order", "needCook")
    step(s, "grill", "cookingFirst")
    started = time.time()
    stage(s, "flipWindow" if tip else "flipMissed", timeout=15)
    first_side = time.time() - started
    s.hold("E", 0.4)  # flip
    stage(s, "cookingSecond")
    stage(s, "cooked")
    s.hold("E", 0.4)  # pick up
    stage(s, "carryingPatty")
    step(s, "assembly", "assembled")
    step(s, "pass", "needOrder")
    return first_side


def main() -> int:
    started = time.time()
    with Studio() as s:
        try:
            print("starting playtest")
            s.play(True, focus=sys.platform == "win32")  # Windows: click the viewport so keys arrive
            s.wait_for("#game.Players:GetPlayers() == 1", dm="server", timeout=30)
            s.wait_for("game.Players.LocalPlayer.Character ~= nil", dm="client", timeout=30)
            time.sleep(2)  # let the avatar settle

            print("ticket 1: late flip, base pay only")
            expect("start cash", attr(s, "Cash"), 0)
            serve_one(s, tip=False)
            expect("cash after ticket 1", attr(s, "Cash"), 15)

            print("ticket 2: perfect flip, tip")
            slow = serve_one(s, tip=True)
            expect("cash after ticket 2", attr(s, "Cash"), 35)

            print("upgrade the grill")
            s.nav(24, 3, 8, speed=3)
            s.hold("E", 0.5)
            s.wait_for(f"{ROOT}:GetAttribute('GrillUpgraded') == true", timeout=5)
            expect("cash after upgrade", attr(s, "Cash"), 5)

            print("ticket 3: upgraded grill cooks faster")
            fast = serve_one(s, tip=True)
            print(f"  first side: {slow:.1f}s before, {fast:.1f}s after")
            expect("upgraded first side is faster", fast < slow - 0.8, True)
            expect("cash after ticket 3", attr(s, "Cash"), 25)

            print(f"PASS in {time.time() - started:.0f}s")
            return 0
        except (Fail, Exception) as e:  # noqa: BLE001 - report anything, then clean up
            print(f"FAIL: {e}")
            return 1
        finally:
            s.play(False)


if __name__ == "__main__":
    sys.exit(main())
