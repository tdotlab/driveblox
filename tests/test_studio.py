import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from helpers import fake_argv  # noqa: E402

from driveblox import NoStudio, Studio, ToolError, WaitTimeout, key_code, parse_key_sequence  # noqa: E402
from driveblox.mcp import McpClient, McpError  # noqa: E402


def last_actions(s):
    return json.loads(s.lua("return ACTIONS", "client"))


class KeyTests(unittest.TestCase):
    def test_key_names(self):
        self.assertEqual(key_code("e"), "E")
        self.assertEqual(key_code("1"), "One")
        self.assertEqual(key_code("esc"), "Escape")
        self.assertEqual(key_code("shift"), "LeftShift")
        self.assertEqual(key_code("F5"), "F5")
        self.assertEqual(key_code("LeftShift"), "LeftShift")

    def test_sequence(self):
        self.assertEqual(parse_key_sequence("down:w wait:800 up:w press:space"), [
            {"action": "keyDown", "key_code": "W"},
            {"action": "wait", "wait_time_ms": 800},
            {"action": "keyUp", "key_code": "W"},
            {"action": "keyPress", "key_code": "Space"},
        ])

    def test_sequence_rejects_junk(self):
        for bad in ("jump:W", "wait:abc", "down:"):
            with self.assertRaises(ValueError):
                parse_key_sequence(bad)


class StudioTests(unittest.TestCase):
    def setUp(self):
        self.s = Studio(argv=fake_argv())
        self.addCleanup(self.s.close)

    def test_connects_and_picks_the_only_studio(self):
        self.assertEqual(self.s.id, "studio-1")
        self.assertGreater(len(self.s.tools), 5)

    def test_lua_routes_datamodel(self):
        self.assertEqual(self.s.lua("return 1", "server"), "ok:Server")
        self.assertEqual(self.s.lua("return 1"), "ok:Edit")
        self.assertEqual(self.s.lua("return 1 + 1"), "2")

    def test_lua_error_raises_tool_error(self):
        with self.assertRaises(ToolError) as cm:
            self.s.lua("BOOM")
        self.assertIn("boom", cm.exception.text)

    def test_wait_for_polls_until_truthy(self):
        self.assertEqual(self.s.wait_for("TICK", interval=0.01, timeout=5), "true")

    def test_wait_for_times_out(self):
        self.s.lua("TICK")  # burn one so we know state persists; then demand an impossible wait
        s2 = Studio(argv=fake_argv())
        self.addCleanup(s2.close)
        with self.assertRaises(WaitTimeout):
            s2.wait_for("TICK", interval=0.01, timeout=0.0)

    def test_play_waits_for_both_datamodels(self):
        self.assertIn("Server", self.s.play(True))
        self.assertEqual(self.s.play(False), "Edit")

    def test_hold_sends_down_wait_up(self):
        self.s.hold("e", 0.4)
        self.assertEqual(last_actions(self.s), [
            {"action": "keyDown", "key_code": "E"},
            {"action": "wait", "wait_time_ms": 400},
            {"action": "keyUp", "key_code": "E"},
        ])

    def test_press_and_type(self):
        self.s.press("1", "esc")
        self.assertEqual([a["key_code"] for a in last_actions(self.s)], ["One", "Escape"])
        self.s.type_text("hi there")
        self.assertEqual(last_actions(self.s), [{"action": "textInput", "text_inputs": "hi there"}])

    def test_click_by_position_and_by_path(self):
        self.s.click(10, 20, right=True)
        self.assertEqual(last_actions(self.s), [{"action": "moveTo", "x": 10, "y": 20},
                                                {"action": "mouseButtonClick", "mouse_button": "right"}])
        self.s.click(path="LocalPlayer.PlayerGui.Frame")
        self.assertEqual(last_actions(self.s)[0], {"action": "moveTo", "instance_path": "LocalPlayer.PlayerGui.Frame"})

    def test_nav(self):
        self.s.nav(1, 2, 3, speed=2)
        self.assertEqual(last_actions(self.s), {"datamodel_type": "Client", "speed_multiplier": 2, "x": 1, "y": 2, "z": 3})
        self.s.nav(path="Workspace.Part")
        self.assertEqual(last_actions(self.s)["instance_path"], "Workspace.Part")
        with self.assertRaises(ValueError):
            self.s.nav(1, 2)

    def test_console_grep_and_tail(self):
        self.assertIn("boom", self.s.console(grep="error"))
        self.assertEqual(self.s.console(last=1), "bye")

    def test_screenshot_saves_image(self):
        with tempfile.TemporaryDirectory() as d:
            paths = self.s.screenshot(os.path.join(d, "shot.png"))
            self.assertEqual(len(paths), 1)
            with open(paths[0], "rb") as f:
                self.assertEqual(f.read(4), b"\x89PNG")

    def test_check_input_true_when_keys_arrive(self):
        self.assertTrue(self.s.check_input(timeout=1))
        self.assertEqual(self.s.state(), "Edit")  # it stopped the playtest it started

    def test_check_input_false_when_game_never_sees_keys(self):
        os.environ["FAKE_MODE"] = "noinput"
        try:
            with Studio(argv=fake_argv()) as s2:
                self.assertFalse(s2.check_input(timeout=0.3))
        finally:
            del os.environ["FAKE_MODE"]

    def test_call_raw_unknown_tool_is_error_result(self):
        res = self.s.call_raw("nope")
        self.assertTrue(res.is_error)
        with self.assertRaises(ToolError):
            self.s.call("nope")


class ConnectionTests(unittest.TestCase):
    def test_noauth_gives_actionable_message(self):
        os.environ["FAKE_MODE"] = "noauth"
        try:
            with self.assertRaises(NoStudio) as cm:
                Studio(argv=fake_argv(), wait=1)
        finally:
            del os.environ["FAKE_MODE"]
        self.assertIn("Enable Studio as MCP server", str(cm.exception))

    def test_two_studios_requires_choice(self):
        os.environ["FAKE_MODE"] = "two"
        try:
            with self.assertRaises(NoStudio) as cm:
                Studio(argv=fake_argv())
            self.assertIn("studio-2", str(cm.exception))
            with Studio(argv=fake_argv(), place="two") as s:
                self.assertEqual(s.id, "studio-2")
            with Studio(argv=fake_argv(), studio_id="studio-1") as s:
                self.assertEqual(s.id, "studio-1")
        finally:
            del os.environ["FAKE_MODE"]

    def test_bad_command_is_mcp_error(self):
        with self.assertRaises(McpError):
            McpClient(["definitely-not-a-real-binary-xyz"])

    def test_server_that_exits_is_mcp_error(self):
        with self.assertRaises(McpError):
            McpClient([sys.executable, "-c", "import sys; sys.exit(0)"], init_timeout=5)


if __name__ == "__main__":
    unittest.main()
