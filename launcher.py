#!/usr/bin/env python3
"""
AutonomousFighter Launcher
Pure Python/C++ Desktop Application (no web browser required)
"""

import subprocess
import sys
import time
import argparse
import win32gui
from pathlib import Path

def find_window_by_partial_name(partial_name: str):
    """Find game window by partial name match, prioritizing by size."""
    found = []
    
    def callback(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd)
            if partial_name.lower() in title.lower():
                try:
                    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
                    width = right - left
                    height = bottom - top
                    # Game windows are typically substantial in size
                    if width > 300 and height > 300:
                        area = width * height
                        found.append((area, title, hwnd, (left, top, right, bottom)))
                except:
                    pass
        return True
    
    try:
        win32gui.EnumWindows(callback, None)
    except:
        pass
    
    # Sort by size (largest first) - likely the game window
    found.sort(reverse=True)
    return [(title, hwnd) for area, title, hwnd, rect in found]

def main():
    parser = argparse.ArgumentParser(description="AutonomousFighter Launcher")
    parser.add_argument("--window-title", help="Game window title to capture")
    parser.add_argument("--dll", default="muscles/build/Release/autonomous_fighter_muscles.dll")
    parser.add_argument("--yolo", default="yolov8n.pt")
    parser.add_argument("--model", default=None, help="Path to trained PPO model")
    args = parser.parse_args()
    
    project_root = Path(__file__).parent
    
    print("=" * 60)
    print("  AUTONOMOUS FIGHTER - Native Desktop Application")
    print("  Pure Python/C++ | No Web Browser Required")
    print("=" * 60)
    
    # Find game window if not specified
    game_title = args.window_title
    if not game_title:
        print("\nSearching for game windows...")
        time.sleep(1)
        windows = find_window_by_partial_name("Shadow Fight")
        if not windows:
            print("ERROR: Shadow Fight Arena window not found!")
            print("Please launch the game first and make sure it's visible on screen.")
            sys.exit(1)
        game_title = windows[0][0]  # Use the largest matching window
        print(f"  ✓ Found: {game_title}")
    
    print(f"\nLaunching bot targeting game window: '{game_title}'")
    print("  (The perception system will automatically track this window)")
    
    print(f"\nLaunching bot targeting: {game_title}")
    
    # Launch backend
    backend_cmd = [
        sys.executable,
        "main.py",
        "--dll", args.dll,
        "--yolo", args.yolo,
        "--window-title", game_title,
    ]
    if args.model:
        backend_cmd.extend(["--model", args.model])
    
    backend_process = subprocess.Popen(backend_cmd, cwd=project_root)
    print("  ✓ Backend started")
    
    # Wait for backend to initialize
    time.sleep(2)
    
    # Launch UI
    ui_cmd = [sys.executable, "ui_app.py"]
    ui_process = subprocess.Popen(ui_cmd, cwd=project_root)
    print("  ✓ Native UI started")
    
    print("\n" + "=" * 60)
    print("  System Ready!")
    print("  - Backend API: http://127.0.0.1:8001")
    print("  - Desktop UI: PyQt6 Application")
    print("  - Game: Capturing from '" + game_title + "'")
    print("=" * 60)
    
    try:
        backend_process.wait()
    except KeyboardInterrupt:
        print("\nShutting down...")
        backend_process.terminate()
        ui_process.terminate()
        backend_process.wait(timeout=5)
        ui_process.wait(timeout=5)

if __name__ == "__main__":
    main()
