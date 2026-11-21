"""Give Studio's game viewport real OS input focus.

Why this exists: Studio's MCP input tools (``user_keyboard_input`` and friends) report
"Success" even when the game never sees the input. During a playtest the game only
receives it once its viewport has genuine window focus, and a fresh playtest, a click
elsewhere in Studio, or switching apps can lose that. The symptom is a script that
runs cleanly and does nothing. One real click inside the viewport fixes it.

Only Windows is implemented. Elsewhere, click inside the Studio game viewport yourself.
"""
from __future__ import annotations

import ctypes
import sys
import time
from typing import Optional, Tuple


class FocusUnsupported(RuntimeError):
    """Not available on this platform."""


class FocusFailed(RuntimeError):
    """Studio's window could not be found or focused."""


def supported() -> bool:
    return sys.platform == "win32"


def focus_viewport(x: Optional[int] = None, y: Optional[int] = None) -> Tuple[int, int]:
    """Bring Studio to the front and click inside it; returns the screen point clicked.

    ``x``/``y`` are pixels inside Studio's client area. The default is the middle of the
    window, which is the 3D viewport in Studio's standard layout. This moves the real mouse
    cursor and sends a real click, so don't run it while you're using the mouse.
    """
    if not supported():
        raise FocusUnsupported("driveblox focus is Windows-only; click inside the Studio game viewport instead")
    from ctypes import wintypes as wt

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    user32.SetProcessDPIAware()

    def image_name(pid: int) -> str:
        handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return ""
        try:
            buf = ctypes.create_unicode_buffer(1024)
            size = wt.DWORD(1024)
            if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
                return buf.value.rsplit("\\", 1)[-1].lower()
            return ""
        finally:
            kernel32.CloseHandle(handle)

    found = []

    @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    def visit(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        pid = wt.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if image_name(pid.value) == "robloxstudiobeta.exe":
            rect = wt.RECT()
            user32.GetClientRect(hwnd, ctypes.byref(rect))
            if rect.right > 200 and rect.bottom > 150:
                found.append((rect.right * rect.bottom, hwnd, rect.right, rect.bottom))
        return True

    user32.EnumWindows(visit, 0)
    if not found:
        raise FocusFailed("no visible Roblox Studio window found")
    _, hwnd, width, height = max(found)

    if user32.GetForegroundWindow() != hwnd:
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        # Borrow the foreground thread's input queue so SetForegroundWindow is allowed.
        foreground = user32.GetForegroundWindow()
        their_thread = user32.GetWindowThreadProcessId(foreground, None)
        my_thread = kernel32.GetCurrentThreadId()
        user32.AttachThreadInput(my_thread, their_thread, True)
        user32.SetForegroundWindow(hwnd)
        user32.AttachThreadInput(my_thread, their_thread, False)
        time.sleep(0.25)

    origin = wt.POINT(0, 0)
    user32.ClientToScreen(hwnd, ctypes.byref(origin))
    sx = origin.x + (x if x is not None else width // 2)
    sy = origin.y + (y if y is not None else height // 2)
    user32.SetCursorPos(sx, sy)
    time.sleep(0.05)
    user32.mouse_event(0x0002, 0, 0, 0, 0)  # left down
    user32.mouse_event(0x0004, 0, 0, 0, 0)  # left up
    time.sleep(0.2)
    return sx, sy
