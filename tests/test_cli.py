import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from helpers import run_cli  # noqa: E402


class CliTests(unittest.TestCase):
    def test_help_and_version(self):
        code, out, _ = run_cli("--help")
        self.assertEqual(code, 0)
        self.assertIn("exit codes", out)
        code, out, _ = run_cli("--version")
        self.assertEqual(code, 0)
        self.assertIn("driveblox", out)

    def test_state_and_studios(self):
        code, out, _ = run_cli("state")
        self.assertEqual((code, out.strip()), (0, "Edit"))
        code, out, _ = run_cli("studios")
        self.assertEqual(json.loads(out)[0]["id"], "studio-1")

    def test_tools_listing_marks_required(self):
        code, out, _ = run_cli("tools")
        self.assertEqual(code, 0)
        self.assertIn("execute_luau()", out)  # studio_id is hidden, nothing else required in the fake

    def test_lua_code_file_and_stdin(self):
        self.assertEqual(run_cli("lua", "-d", "server", "-c", "return 1")[1].strip(), "ok:Server")
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "a.luau")
            with open(p, "w") as f:
                f.write("return 1 + 1")
            self.assertEqual(run_cli("lua", p)[1].strip(), "2")
        self.assertEqual(run_cli("lua", "-", stdin="return 1 + 1")[1].strip(), "2")

    def test_lua_error_exits_1_and_prints_to_stderr(self):
        code, out, err = run_cli("lua", "-c", "BOOM")
        self.assertEqual(code, 1)
        self.assertIn("boom", err)
        self.assertEqual(out.strip(), "")

    def test_wait_success_and_timeout(self):
        code, out, _ = run_cli("wait", "TICK", "--interval", "0.01", "--timeout", "5")
        self.assertEqual((code, out.strip()), (0, "true"))
        code, _, err = run_cli("wait", "TICK", "--timeout", "0", "--interval", "0.01")
        self.assertEqual(code, 1)
        self.assertIn("timed out", err)

    def test_input_commands_need_arguments(self):
        self.assertEqual(run_cli("click")[0], 2)
        self.assertEqual(run_cli("nav", "1", "2")[0], 2)
        self.assertEqual(run_cli("key", "hold", "E")[0], 2)
        self.assertEqual(run_cli("key", "seq", "jump:W")[0], 2)

    def test_key_hold_roundtrip(self):
        code, out, _ = run_cli("batch", "-", stdin="key hold e 0.1\nlua -d client -c \"return ACTIONS\"\n")
        self.assertEqual(code, 0)
        actions = json.loads(out.strip().splitlines()[-1])
        self.assertEqual([a["action"] for a in actions], ["keyDown", "wait", "keyUp"])
        self.assertEqual(actions[1]["wait_time_ms"], 100)

    def test_shot_writes_png(self):
        with tempfile.TemporaryDirectory() as d:
            code, out, _ = run_cli("shot", os.path.join(d, "x.png"))
            self.assertEqual(code, 0)
            self.assertTrue(os.path.exists(os.path.join(d, "x.png")))

    def test_call_passthrough_and_bad_json(self):
        code, out, _ = run_cli("call", "execute_luau", '{"code":"return 1 + 1","datamodel_type":"Edit"}')
        self.assertEqual((code, out.strip()), (0, "2"))
        self.assertEqual(run_cli("call", "execute_luau", "{not json")[0], 2)
        self.assertEqual(run_cli("call", "no_such_tool")[0], 1)

    def test_schema_unknown_tool(self):
        self.assertEqual(run_cli("schema", "nope")[0], 2)
        self.assertEqual(run_cli("schema", "execute_luau")[0], 0)

    def test_two_studios_needs_flag(self):
        code, _, err = run_cli("state", mode="two")
        self.assertEqual(code, 3)
        self.assertIn("studio-2", err)
        self.assertEqual(run_cli("--studio", "studio-2", "state", mode="two")[0], 0)
        self.assertEqual(run_cli("--place", "Two", "state", mode="two")[0], 0)

    def test_noauth_exits_3_with_hint(self):
        code, _, err = run_cli("state", mode="noauth")
        self.assertEqual(code, 3)
        self.assertIn("Enable Studio as MCP server", err)


class BatchTests(unittest.TestCase):
    def test_batch_runs_in_order_over_one_connection(self):
        script = "# comment\n\nplay start\nlua -d client -c \"return CALLS\"\nplay stop\n"
        code, out, err = run_cli("batch", "-", stdin=script)
        self.assertEqual(code, 0, err)
        self.assertIn("+ play start", err)
        # one connection means the fake saw one initialize and the whole call sequence
        self.assertIn("list_roblox_studios", out)
        self.assertIn("start_stop_play", out)

    def test_batch_stops_at_first_failure(self):
        code, out, err = run_cli("batch", "-", stdin="lua -c BOOM\nlua -c \"return 1 + 1\"\n")
        self.assertEqual(code, 1)
        self.assertNotIn("2", out)
        self.assertIn("stopped at line 1", err)

    def test_batch_keep_going(self):
        code, out, _ = run_cli("batch", "-", "--keep-going", stdin="lua -c BOOM\nlua -c \"return 1 + 1\"\n")
        self.assertEqual(code, 1)
        self.assertEqual(out.strip(), "2")

    def test_batch_rejects_nested_and_bad_lines(self):
        self.assertEqual(run_cli("batch", "-", stdin="batch other.txt\n")[0], 2)
        self.assertEqual(run_cli("batch", "-", stdin="frobnicate\n")[0], 2)

    def test_pause_in_batch(self):
        self.assertEqual(run_cli("batch", "-", stdin="pause 0.05\nstate\n")[0], 0)


class DoctorTests(unittest.TestCase):
    def test_doctor_passes(self):
        code, out, _ = run_cli("doctor")
        self.assertEqual(code, 0, out)
        self.assertIn("all good", out)
        self.assertNotIn("FAIL", out)

    def test_doctor_input_passes_and_fails(self):
        code, out, _ = run_cli("doctor", "--input")
        self.assertEqual(code, 0, out)
        self.assertIn("[ok] keystroke reaches the game", out)
        code, out, _ = run_cli("doctor", "--input", mode="noinput")
        self.assertEqual(code, 1)
        self.assertIn("[FAIL] keystroke reaches the game", out)
        self.assertIn("Click once inside the Studio game viewport", out)

    def test_focus_unsupported_off_windows(self):
        if sys.platform == "win32":
            self.skipTest("focus is implemented on Windows")
        code, _, err = run_cli("focus")
        self.assertEqual(code, 1)
        self.assertIn("Windows-only", err)

    def test_doctor_reports_toggle_off(self):
        code, out, _ = run_cli("doctor", mode="noauth")
        self.assertEqual(code, 3)
        self.assertIn("[FAIL] list tools", out)
        self.assertIn("Enable Studio as MCP server", out)

    def test_doctor_missing_proxy(self):
        import subprocess
        env = dict(os.environ, DRIVEBLOX_MCP_CMD=json.dumps(["definitely-not-a-real-binary-xyz"]),
                   DRIVEBLOX_CONNECT_TIMEOUT="2")
        env["PYTHONPATH"] = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
        p = subprocess.run([sys.executable, "-m", "driveblox", "doctor"], env=env, capture_output=True, text=True)
        self.assertEqual(p.returncode, 3)
        self.assertIn("[FAIL] start the proxy", p.stdout)


if __name__ == "__main__":
    unittest.main()
