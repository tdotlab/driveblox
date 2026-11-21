import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from helpers import fake_argv, run_cli  # noqa: E402

from driveblox import Studio  # noqa: E402
from driveblox import focus  # noqa: E402
from driveblox.studio import DriveError  # noqa: E402


@unittest.skipIf(sys.platform == "win32", "the unsupported path only exists off Windows")
class FocusOffWindowsTests(unittest.TestCase):
    def test_module_reports_unsupported(self):
        self.assertFalse(focus.supported())
        with self.assertRaises(focus.FocusUnsupported):
            focus.focus_viewport()

    def test_studio_focus_becomes_drive_error(self):
        with Studio(argv=fake_argv()) as s:
            with self.assertRaises(DriveError) as cm:
                s.focus()
            self.assertIn("Windows-only", str(cm.exception))

    def test_play_focus_flag_fails_cleanly(self):
        code, _, err = run_cli("play", "start", "--focus")
        self.assertEqual(code, 1)
        self.assertIn("Windows-only", err)


class FocusEverywhereTests(unittest.TestCase):
    def test_supported_matches_platform(self):
        self.assertEqual(focus.supported(), sys.platform == "win32")

    def test_play_without_focus_never_touches_it(self):
        with Studio(argv=fake_argv()) as s:
            self.assertIn("Server", s.play(True))
            s.play(False)


class FromClientTests(unittest.TestCase):
    def test_from_client_reuses_a_connection(self):
        with Studio(argv=fake_argv()) as s:
            again = Studio.from_client(s.client, s.id, s.argv)
            self.assertEqual(again.state(), "Edit")
            self.assertTrue(again.check_input(timeout=1))


if __name__ == "__main__":
    unittest.main()
