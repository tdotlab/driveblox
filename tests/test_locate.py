import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from driveblox import locate  # noqa: E402


def touch(path, mtime=None):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write("x")
    if mtime:
        os.utime(path, (mtime, mtime))
    return path


class LocateTests(unittest.TestCase):
    def test_override_json_array(self):
        argv, env, src = locate.find_command({"DRIVEBLOX_MCP_CMD": '["wine", "/a b/StudioMCP.exe"]'}, "Linux")
        self.assertEqual(argv, ["wine", "/a b/StudioMCP.exe"])
        self.assertIn("DRIVEBLOX_MCP_CMD", src)

    def test_override_plain_posix(self):
        argv, _, _ = locate.find_command({"DRIVEBLOX_MCP_CMD": 'wine "/a b/StudioMCP.exe"'}, "Linux")
        self.assertEqual(argv, ["wine", "/a b/StudioMCP.exe"])

    def test_override_plain_windows_keeps_backslashes(self):
        argv, _, _ = locate.find_command({"DRIVEBLOX_MCP_CMD": r'"C:\Program Files\x\StudioMCP.exe" --flag'}, "Windows")
        self.assertEqual(argv, [r"C:\Program Files\x\StudioMCP.exe", "--flag"])

    def test_override_bad_json(self):
        with self.assertRaises(locate.NotFound):
            locate.find_command({"DRIVEBLOX_MCP_CMD": "[not json"}, "Linux")

    def test_override_empty_array(self):
        with self.assertRaises(locate.NotFound):
            locate.find_command({"DRIVEBLOX_MCP_CMD": "[]"}, "Linux")

    def test_windows_picks_newest_version_folder(self):
        with tempfile.TemporaryDirectory() as d:
            now = time.time()
            touch(os.path.join(d, "Roblox", "Versions", "version-old", "StudioMCP.exe"), now - 1000)
            new = touch(os.path.join(d, "Roblox", "Versions", "version-new", "StudioMCP.exe"), now)
            argv, _, _ = locate.find_command({"LOCALAPPDATA": d}, "Windows")
            self.assertEqual(argv, [new])

    def test_windows_falls_back_to_mcp_bat(self):
        with tempfile.TemporaryDirectory() as d:
            bat = touch(os.path.join(d, "Roblox", "mcp.bat"))
            argv, _, _ = locate.find_command({"LOCALAPPDATA": d}, "Windows")
            self.assertEqual(argv, ["cmd.exe", "/c", bat])

    def test_windows_not_found(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(locate.NotFound):
                locate.find_command({"LOCALAPPDATA": d}, "Windows")

    def test_mac_not_found_message(self):
        if os.path.exists(locate.MAC_PATHS[0]):
            self.skipTest("a real Studio is installed")
        with self.assertRaises(locate.NotFound) as cm:
            locate.find_command({"HOME": tempfile.gettempdir()}, "Darwin")
        self.assertIn("DRIVEBLOX_MCP_CMD", str(cm.exception))

    def test_linux_finds_exe_in_wineprefix(self):
        with tempfile.TemporaryDirectory() as prefix:
            exe = touch(os.path.join(prefix, "drive_c", "users", "me", "AppData", "Local", "Roblox",
                                     "Versions", "version-abc", "StudioMCP.exe"))
            argv, env, _ = locate.find_command({"WINEPREFIX": prefix}, "Linux")
            self.assertEqual(argv[1], exe)
            self.assertTrue(argv[0].endswith("wine"))
            self.assertEqual(env["WINEPREFIX"], prefix)

    def test_linux_not_found_mentions_wine(self):
        with tempfile.TemporaryDirectory() as prefix:
            with self.assertRaises(locate.NotFound) as cm:
                locate.find_command({"WINEPREFIX": prefix}, "Linux")
            self.assertIn("Wine", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
