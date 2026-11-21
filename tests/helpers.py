import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FAKE = os.path.join(HERE, "fake_studio_mcp.py")
SRC = os.path.join(HERE, "..", "src")


def fake_cmd():
    """DRIVEBLOX_MCP_CMD value that runs the fake server (JSON form, safe for any path)."""
    return json.dumps([sys.executable, FAKE])


def fake_argv():
    return [sys.executable, FAKE]


def run_cli(*args, mode="", stdin=None):
    """Run the real CLI in a subprocess against the fake server. Returns (code, stdout, stderr)."""
    env = dict(os.environ)
    env["DRIVEBLOX_MCP_CMD"] = fake_cmd()
    env["PYTHONPATH"] = os.path.abspath(SRC) + os.pathsep + env.get("PYTHONPATH", "")
    env["PYTHONIOENCODING"] = "utf-8"
    env.pop("DRIVEBLOX_STUDIO", None)
    env["DRIVEBLOX_CONNECT_TIMEOUT"] = "2"
    if mode:
        env["FAKE_MODE"] = mode
    p = subprocess.run([sys.executable, "-m", "driveblox", *args], env=env, input=stdin,
                       capture_output=True, text=True, timeout=60)
    return p.returncode, p.stdout, p.stderr
