from __future__ import annotations

import atexit
import ctypes
import random
import signal
import time
from pathlib import Path
from typing import Any, Optional


class InputExecutor:
    """ctypes wrapper around the C++ SendInput DLL."""

    def __init__(self, dll_path: str | Path):
        dll_resolved = Path(dll_path).resolve()
        if not dll_resolved.exists():
            raise FileNotFoundError(f"DLL not found: {dll_resolved}")

        self._dll = ctypes.WinDLL(str(dll_resolved))
        self._configure_signatures()
        
        # Register cleanup handlers
        atexit.register(self.reset_all_keys)
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum: int, frame: Any) -> None:
        """Handle shutdown signals by resetting all keys."""
        self.reset_all_keys()

    def _configure_signatures(self) -> None:
        self._dll.af_press_key.argtypes = [ctypes.c_uint16]
        self._dll.af_release_key.argtypes = [ctypes.c_uint16]
        self._dll.af_reset_all_keys.argtypes = []
        self._dll.af_tap_key.argtypes = [ctypes.c_uint16, ctypes.c_uint32, ctypes.c_uint32]
        self._dll.af_move_mouse_relative.argtypes = [ctypes.c_int32, ctypes.c_int32]
        self._dll.af_click_left.argtypes = [ctypes.c_uint32, ctypes.c_uint32]
        self._dll.af_sleep_ms.argtypes = [ctypes.c_uint32]

        self._dll.af_press_key.restype = None
        self._dll.af_release_key.restype = None
        self._dll.af_reset_all_keys.restype = None
        self._dll.af_tap_key.restype = None
        self._dll.af_move_mouse_relative.restype = None
        self._dll.af_click_left.restype = None
        self._dll.af_sleep_ms.restype = None

    def press_key(self, virtual_key: int) -> None:
        self._dll.af_press_key(virtual_key)

    def release_key(self, virtual_key: int) -> None:
        self._dll.af_release_key(virtual_key)

    def reset_all_keys(self) -> None:
        """Force release all currently pressed keys."""
        try:
            self._dll.af_reset_all_keys()
        except Exception:
            # Suppress errors during cleanup
            pass

    def tap_key(self, virtual_key: int, min_delay_ms: int = 10, max_delay_ms: int = 30) -> None:
        self._dll.af_tap_key(virtual_key, min_delay_ms, max_delay_ms)

    def move_mouse_relative(self, dx: int, dy: int) -> None:
        self._dll.af_move_mouse_relative(dx, dy)

    def click_left(self, min_delay_ms: int = 10, max_delay_ms: int = 30) -> None:
        self._dll.af_click_left(min_delay_ms, max_delay_ms)

    def sleep_ms(self, ms: int) -> None:
        self._dll.af_sleep_ms(ms)

    def tap_with_human_jitter(
        self,
        virtual_key: int,
        min_press_ms: int = 10,
        max_press_ms: int = 30,
        min_gap_ms: int = 5,
        max_gap_ms: int = 20,
        repetitions: int = 1,
    ) -> None:
        for _ in range(max(1, repetitions)):
            self.tap_key(virtual_key, min_press_ms, max_press_ms)
            time.sleep(random.uniform(min_gap_ms, max_gap_ms) / 1000.0)


def smoke_test(dll_path: str | Path) -> None:
    executor = InputExecutor(dll_path)
    # Virtual-Key code 0x20 is SPACE.
    executor.tap_key(0x20, 10, 30)
    executor.click_left(10, 30)


if __name__ == "__main__":
    default_dll = Path(__file__).resolve().parent / "build" / "Release" / "autonomous_fighter_muscles.dll"
    smoke_test(default_dll)
