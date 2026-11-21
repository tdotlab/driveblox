"""A small MCP client over stdio (newline-delimited JSON-RPC, protocol 2024-11-05).

Just enough of the protocol to start a server, list tools and call them. No
dependencies. Used by :mod:`driveblox.studio`, but it speaks to any MCP stdio server.
"""
from __future__ import annotations

import base64
import collections
import json
import os
import queue
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

PROTOCOL = "2024-11-05"


class McpError(RuntimeError):
    """The server failed, exited, timed out, or returned a protocol error."""


@dataclass
class Result:
    """A flattened tools/call result."""
    text: str = ""
    is_error: bool = False
    images: List[Dict[str, Any]] = field(default_factory=list)

    def json(self) -> Any:
        return json.loads(self.text)


def parse_result(res: Dict[str, Any]) -> Result:
    parts, images = [], []
    for c in res.get("content", []):
        if c.get("type") == "text":
            parts.append(c.get("text", ""))
        elif c.get("type") == "image":
            images.append(c)
    return Result("\n".join(parts), bool(res.get("isError")), images)


def save_images(images: List[Dict[str, Any]], stem: str) -> List[str]:
    """Write returned images to ``stem.ext`` (``stem_1.ext`` and so on); return the paths."""
    out = []
    for i, im in enumerate(images):
        ext = (im.get("mimeType") or "image/png").split("/")[-1]
        path = f"{stem}{'' if i == 0 else '_' + str(i)}.{ext}"
        with open(path, "wb") as f:
            f.write(base64.b64decode(im["data"]))
        out.append(path)
    return out


class McpClient:
    """One server process. Not thread-safe: use one request at a time."""

    def __init__(self, argv: List[str], env: Optional[Dict[str, str]] = None,
                 verbose: bool = False, init_timeout: float = 30):
        self.argv = list(argv)
        self.verbose = verbose
        full_env = dict(os.environ)
        full_env.update(env or {})
        try:
            self.proc = subprocess.Popen(
                self.argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, encoding="utf-8", errors="replace", bufsize=1, env=full_env)
        except OSError as e:
            raise McpError(f"cannot start {self.argv[0]!r}: {e}") from e
        self._lines: "queue.Queue[str]" = queue.Queue()
        self.stderr_lines: "collections.deque[str]" = collections.deque(maxlen=200)
        self._id = 0
        threading.Thread(target=self._pump_out, daemon=True).start()
        threading.Thread(target=self._pump_err, daemon=True).start()
        try:
            r = self.request("initialize", {"protocolVersion": PROTOCOL, "capabilities": {},
                                            "clientInfo": {"name": "driveblox", "version": "0.1"}},
                             timeout=init_timeout)
            self.server_info = r.get("serverInfo", {})
            self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        except BaseException:
            self.close()
            raise

    # -- plumbing ------------------------------------------------------------
    def _pump_out(self) -> None:
        try:
            for line in self.proc.stdout:
                self._lines.put(line.rstrip("\n"))
        except (OSError, ValueError):  # pipe closed during shutdown
            pass

    def _pump_err(self) -> None:
        try:
            for line in self.proc.stderr:
                line = line.rstrip("\n")
                self.stderr_lines.append(line)
                if self.verbose:
                    print("[server]", line, file=sys.stderr)
        except (OSError, ValueError):
            pass

    def _send(self, obj: Dict[str, Any]) -> None:
        try:
            self.proc.stdin.write(json.dumps(obj) + "\n")
            self.proc.stdin.flush()
        except (OSError, ValueError) as e:
            raise McpError("server closed its input: " + self._stderr_tail()) from e

    def _stderr_tail(self, n: int = 3) -> str:
        return " | ".join(list(self.stderr_lines)[-n:])

    def request(self, method: str, params: Optional[Dict[str, Any]] = None, timeout: float = 60) -> Dict[str, Any]:
        self._id += 1
        rid = self._id
        self._send({"jsonrpc": "2.0", "id": rid, "method": method, "params": params or {}})
        end = time.time() + timeout
        while time.time() < end:
            try:
                line = self._lines.get(timeout=0.25)
            except queue.Empty:
                if self.proc.poll() is not None:
                    raise McpError("server exited: " + self._stderr_tail())
                continue
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            if "method" in msg:  # server-initiated request or notification
                if "id" in msg:
                    self._send({"jsonrpc": "2.0", "id": msg["id"],
                                "error": {"code": -32601, "message": "not supported"}})
                continue
            if msg.get("id") == rid:
                if "error" in msg:
                    raise McpError(json.dumps(msg["error"]))
                return msg.get("result", {})
        raise McpError(f"timeout after {timeout:g}s waiting for {method}")

    # -- API -----------------------------------------------------------------
    def tools(self, wait: float = 0) -> List[Dict[str, Any]]:
        """tools/list, retrying for up to ``wait`` seconds while the server connects to its host app."""
        end = time.time() + wait
        while True:
            tools = self.request("tools/list").get("tools", [])
            if tools or time.time() >= end:
                return tools
            time.sleep(0.5)

    def call(self, name: str, args: Optional[Dict[str, Any]] = None, timeout: float = 120) -> Result:
        res = self.request("tools/call", {"name": name, "arguments": args or {}}, timeout=timeout)
        return parse_result(res)

    def auth_hint(self) -> Optional[str]:
        tail = " ".join(self.stderr_lines)
        if "401" in tail or "no_auth_header" in tail:
            return ("Studio rejected the proxy (401). In Studio open Assistant > ... > Manage MCP Servers "
                    "and turn on 'Enable Studio as MCP server', then keep Studio open.")
        return None

    def close(self) -> None:
        try:
            self.proc.stdin.close()
        except Exception:
            pass
        try:
            self.proc.terminate()
            self.proc.wait(timeout=3)
        except Exception:
            try:
                self.proc.kill()
            except Exception:
                pass
        for stream in (self.proc.stdout, self.proc.stderr):
            try:
                stream.close()
            except Exception:
                pass

    def __enter__(self) -> "McpClient":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()
