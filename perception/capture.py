from __future__ import annotations

import ctypes
import os
import threading
import time
from dataclasses import dataclass
from typing import Dict, Optional

import cv2
import mss
import numpy as np

try:
    import win32gui  # type: ignore[import]
except ImportError:  # pragma: no cover
    win32gui = None


try:
    # Avoid DPI-virtualized coordinates that can shift capture away from the real game client area.
    ctypes.windll.user32.SetProcessDPIAware()
except Exception:
    pass


@dataclass
class CaptureRegion:
    left: int
    top: int
    width: int
    height: int


class ScreenCapture:
    def __init__(
        self,
        region: CaptureRegion,
        follow_window_title: str | None = None,
        async_capture: bool = True,
        target_fps: float = 60.0,
        quality_scale: float = 1.0,
        adaptive_quality: bool = True,
    ):
        self.region = region
        self.follow_window_title = follow_window_title
        self._mss: mss.mss | None = None
        self._mss_thread_id: int | None = None
        self._last_hwnd = 0  # Track the last found window handle
        self._window_lost_count = 0  # Count consecutive frames where window wasn't found

        self._async_capture = bool(async_capture)
        self._target_fps = max(1.0, float(target_fps))
        self._base_quality_scale = min(1.0, max(0.5, float(quality_scale)))
        self._effective_quality_scale = self._base_quality_scale
        self._adaptive_quality = bool(adaptive_quality)

        self._latest_frame: Optional[np.ndarray] = None
        self._latest_frame_id = 0
        self._capture_fps = 0.0
        self._capture_error_count = 0
        self._capture_thread_alive = False

        self._state_lock = threading.Lock()
        self._grab_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._capture_thread: threading.Thread | None = None
        self._capture_fps_counter = FpsCounter()

        if self._async_capture:
            self.start()

    def _find_window_by_title_substring(self, title_substring: str) -> int:
        if win32gui is None:
            return 0

        needle = title_substring.strip().lower()
        if not needle:
            return 0

        matches = []

        def callback(hwnd: int, _lparam: object) -> bool:
            if not win32gui.IsWindowVisible(hwnd):
                return True

            title = win32gui.GetWindowText(hwnd)
            if needle in title.lower():
                try:
                    # Get window dimensions for validation
                    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
                    width = right - left
                    height = bottom - top
                    # Prioritize reasonably-sized game windows (typically 600+ x 400+)
                    if width >= 600 and height >= 400:
                        matches.append((hwnd, width * height, title))
                except Exception:
                    pass
            return True

        try:
            win32gui.EnumWindows(callback, None)
        except Exception:
            return 0
        
        # Return the largest visible window matching the criteria (likely the game)
        if matches:
            matches.sort(key=lambda x: x[1], reverse=True)
            return matches[0][0]
        return 0

    def _maybe_update_region_from_window(self) -> None:
        if not self.follow_window_title or win32gui is None:
            return

        hwnd = self._find_window_by_title_substring(self.follow_window_title)
        if hwnd == 0:
            # Window not found, keep current region but track it
            self._window_lost_count += 1
            return

        # Window found, reset counter
        self._window_lost_count = 0
        self._last_hwnd = hwnd

        try:
            # Get the client area coordinates (excludes window decorations)
            client_left, client_top = win32gui.ClientToScreen(hwnd, (0, 0))
            client_rect = win32gui.GetClientRect(hwnd)
            client_right = client_left + int(client_rect[2])
            client_bottom = client_top + int(client_rect[3])
            
            width = max(1, int(client_right - client_left))
            height = max(1, int(client_bottom - client_top))
            
            # Only use client area - it's more accurate for game capture
            # If client area is tiny (< 200x120), something is wrong, skip update
            if width >= 200 and height >= 120:
                self.region = CaptureRegion(left=client_left, top=client_top, width=width, height=height)
        except Exception:
            # If we can't get client area, fallback to window rect as last resort
            try:
                left, top, right, bottom = win32gui.GetWindowRect(hwnd)
                width = max(1, int(right - left))
                height = max(1, int(bottom - top))
                if width >= 200 and height >= 120:
                    self.region = CaptureRegion(left=left, top=top, width=width, height=height)
            except Exception:
                # Keep current region if all fails
                pass
    
    def get_window_info(self) -> dict:
        """Get diagnostic info about the tracked window."""
        stats = self.get_capture_stats()
        return {
            "follow_title": self.follow_window_title,
            "last_hwnd": self._last_hwnd,
            "window_lost_count": self._window_lost_count,
            "capture_fps": stats["capture_fps"],
            "latest_frame_id": stats["latest_frame_id"],
            "quality_scale": stats["quality_scale"],
            "current_region": {
                "left": self.region.left,
                "top": self.region.top,
                "width": self.region.width,
                "height": self.region.height,
            }
        }

    def get_capture_stats(self) -> dict:
        with self._state_lock:
            return {
                "capture_fps": float(self._capture_fps),
                "latest_frame_id": int(self._latest_frame_id),
                "quality_scale": float(self._effective_quality_scale),
                "target_fps": float(self._target_fps),
                "async_capture": bool(self._async_capture),
                "capture_error_count": int(self._capture_error_count),
                "capture_thread_alive": bool(self._capture_thread_alive),
            }

    def start(self) -> None:
        if self._capture_thread is not None and self._capture_thread.is_alive():
            return

        self._stop_event.clear()
        self._capture_thread = threading.Thread(target=self._capture_worker, name="screen-capture", daemon=True)
        self._capture_thread.start()

    def stop(self, timeout: float = 1.0) -> None:
        self._stop_event.set()
        if self._capture_thread is not None:
            self._capture_thread.join(timeout=timeout)
            self._capture_thread = None

    def _ensure_mss(self) -> mss.mss:
        current_thread_id = threading.get_ident()
        if self._mss is None or self._mss_thread_id != current_thread_id:
            self._mss = mss.mss()
            self._mss_thread_id = current_thread_id
        return self._mss

    def _grab_once_bgr(self) -> np.ndarray:
        self._maybe_update_region_from_window()
        monitor: Dict[str, int] = {
            "left": self.region.left,
            "top": self.region.top,
            "width": self.region.width,
            "height": self.region.height,
        }
        mss_instance = self._ensure_mss()
        with self._grab_lock:
            frame = np.array(mss_instance.grab(monitor), dtype=np.uint8)
        bgr = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
        return self._scale_frame_if_needed(bgr)

    def _scale_frame_if_needed(self, frame: np.ndarray) -> np.ndarray:
        scale = self._effective_quality_scale
        if scale >= 0.999:
            return frame

        width = max(1, int(frame.shape[1] * scale))
        height = max(1, int(frame.shape[0] * scale))
        if width == frame.shape[1] and height == frame.shape[0]:
            return frame
        return cv2.resize(frame, (width, height), interpolation=cv2.INTER_AREA)

    def _capture_worker(self) -> None:
        period = 1.0 / self._target_fps
        next_tick = time.perf_counter()
        with self._state_lock:
            self._capture_thread_alive = True

        try:
            while not self._stop_event.is_set():
                loop_started = time.perf_counter()
                try:
                    frame = self._grab_once_bgr()
                except Exception:
                    with self._state_lock:
                        self._capture_error_count += 1
                    # Recreate mss handle after transient capture failures and continue.
                    self._mss = None
                    self._mss_thread_id = None
                    time.sleep(min(0.05, period))
                    next_tick = time.perf_counter()
                    continue

                with self._state_lock:
                    self._latest_frame = frame
                    self._latest_frame_id += 1
                    self._capture_fps = self._capture_fps_counter.tick()

                loop_elapsed = time.perf_counter() - loop_started
                if self._adaptive_quality:
                    if loop_elapsed > (period * 0.95) and self._effective_quality_scale > 0.5:
                        self._effective_quality_scale = max(0.5, self._effective_quality_scale - 0.05)
                    elif loop_elapsed < (period * 0.60) and self._effective_quality_scale < self._base_quality_scale:
                        self._effective_quality_scale = min(self._base_quality_scale, self._effective_quality_scale + 0.02)

                next_tick += period
                sleep_for = next_tick - time.perf_counter()
                if sleep_for > 0:
                    time.sleep(sleep_for)
                else:
                    # If processing overruns, skip waiting so capture resumes at current time.
                    next_tick = time.perf_counter()
        finally:
            with self._state_lock:
                self._capture_thread_alive = False

    def grab_latest_bgr(self) -> np.ndarray:
        if not self._async_capture:
            return self._grab_once_bgr()

        with self._state_lock:
            if self._latest_frame is not None:
                return self._latest_frame.copy()

        # No frame yet (startup race), perform a direct capture once.
        frame = self._grab_once_bgr()
        with self._state_lock:
            self._latest_frame = frame
            self._latest_frame_id += 1
            self._capture_fps = self._capture_fps_counter.tick()
        return frame.copy()

    def grab_bgr(self) -> np.ndarray:
        return self.grab_latest_bgr()


class FpsCounter:
    def __init__(self) -> None:
        self._last_time = time.perf_counter()

    def tick(self) -> float:
        now = time.perf_counter()
        dt = max(1e-6, now - self._last_time)
        self._last_time = now
        return 1.0 / dt
