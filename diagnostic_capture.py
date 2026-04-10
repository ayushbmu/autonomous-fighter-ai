#!/usr/bin/env python3
"""
Detailed diagnostic to debug window capture region calculation.
"""

import sys

try:
    import win32gui
except ImportError:
    print("ERROR: pywin32 not installed")
    sys.exit(1)

import argparse
from perception.capture import ScreenCapture, CaptureRegion


def main():
    parser = argparse.ArgumentParser(description="Debug window capture region calculation")
    parser.add_argument("--window-title", default="Shadow Fight Arena", help="Window title to find")
    args = parser.parse_args()

    print("=" * 80)
    print(f"WINDOW CAPTURE DIAGNOSTICS: {args.window_title}")
    print("=" * 80)
    print()

    # Create capture
    capture = ScreenCapture(
        CaptureRegion(0, 0, 1280, 720),
        follow_window_title=args.window_title,
    )

    try:
        # Grab first frame to trigger window detection
        print(f"Searching for window with title: '{args.window_title}'")
        frame = capture.grab_bgr()

        info = capture.get_window_info()
        print()
        print(f"Window Detection Results:")
        print(f"  HWND found: {info['last_hwnd']}")
        print(f"  Capture FPS: {info.get('capture_fps', 0.0):.1f}")
        print(f"  Quality scale: {info.get('quality_scale', 1.0):.2f}")

        if info['last_hwnd'] == 0:
            print(f"  ✗ WINDOW NOT FOUND!")
            print()
            print("  Debug: Listing all visible windows...")

            windows = []
            def callback(hwnd, _):
                if win32gui.IsWindowVisible(hwnd):
                    try:
                        title = win32gui.GetWindowText(hwnd)
                        if title and "shadow" in title.lower():
                            left, top, right, bottom = win32gui.GetWindowRect(hwnd)
                            width = right - left
                            height = bottom - top
                            windows.append({
                                'title': title,
                                'hwnd': hwnd,
                                'left': left,
                                'top': top,
                                'width': width,
                                'height': height,
                            })
                    except:
                        pass
                return True

            try:
                win32gui.EnumWindows(callback, None)
            except:
                pass

            if windows:
                print(f"\n  Windows containing 'shadow':")
                for w in windows:
                    print(f"    - {w['title']}")
                    print(f"      Hwnd: {w['hwnd']}, Pos: ({w['left']},{w['top']}), Size: {w['width']}x{w['height']}")
            else:
                print(f"  No windows with 'shadow' in title found!")
            sys.exit(1)

        print(f"  ✓ Window found!")
        print()

        # Get window details
        try:
            left, top, right, bottom = win32gui.GetWindowRect(info['last_hwnd'])
            window_width = right - left
            window_height = bottom - top
            print(f"Window Rect (including decorations):")
            print(f"  Position: ({left}, {top})")
            print(f"  Size: {window_width}x{window_height}")
            print()
        except Exception as e:
            print(f"  Error getting window rect: {e}")
            print()

        # Get client area
        try:
            client_left, client_top = win32gui.ClientToScreen(info['last_hwnd'], (0, 0))
            client_rect = win32gui.GetClientRect(info['last_hwnd'])
            client_width = int(client_rect[2])
            client_height = int(client_rect[3])
            print(f"Client Area (game content only):")
            print(f"  Position: ({client_left}, {client_top})")
            print(f"  Size: {client_width}x{client_height}")
            print()
        except Exception as e:
            print(f"  Error getting client area: {e}")
            print()

        # Show current capture region
        print(f"Current Capture Region:")
        region = info['current_region']
        print(f"  Position: ({region['left']}, {region['top']})")
        print(f"  Size: {region['width']}x{region['height']}")
        print()

        # Show actual frame captured
        print(f"Actual Frame Captured:")
        print(f"  Size: {frame.shape[1]}x{frame.shape[0]}")
        print()

        # Analysis
        print(f"Analysis:")
        if frame.shape[1] != region['width'] or frame.shape[0] != region['height']:
            print(f"  ⚠️  MISMATCH: Frame size ({frame.shape[1]}x{frame.shape[0]}) != Region size ({region['width']}x{region['height']})")
        else:
            print(f"  ✓ Frame size matches region")

        if region['left'] == 0 and region['top'] == 0 and region['width'] == 1280 and region['height'] == 720:
            print(f"  ⚠️  WARNING: Capture is FULL SCREEN (default region)!")
            print(f"     This means window detection ran but region wasn't updated!")
        elif region['left'] == 0 and region['top'] == 0:
            print(f"  ⚠️  WARNING: Capture starts at (0,0). May include screen edges or other windows!")
        else:
            print(f"  ✓ Capture region looks reasonable")

        print()
    finally:
        capture.stop()


if __name__ == "__main__":
    main()
