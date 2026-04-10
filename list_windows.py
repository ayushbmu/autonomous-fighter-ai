#!/usr/bin/env python3
"""
Diagnostic tool to list all visible windows and their properties.
Useful for identifying the correct window title to use for game capture.
"""

import sys

try:
    import win32gui
except ImportError:
    print("ERROR: pywin32 not installed. Install with: pip install pywin32")
    sys.exit(1)


def list_windows():
    """List all visible windows with their properties."""
    windows = []
    
    def callback(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            try:
                title = win32gui.GetWindowText(hwnd)
                if title:  # Only show windows with titles
                    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
                    width = right - left
                    height = bottom - top
                    if width > 0 and height > 0:
                        windows.append({
                            'hwnd': hwnd,
                            'title': title,
                            'left': left,
                            'top': top,
                            'width': width,
                            'height': height,
                            'area': width * height,
                        })
            except Exception:
                pass
        return True
    
    try:
        win32gui.EnumWindows(callback, None)
    except Exception as e:
        print(f"Error enumerating windows: {e}")
        return []
    
    return windows


def main():
    print("=" * 80)
    print("WINDOWS DIAGNOSTIC - Visible Windows on Screen")
    print("=" * 80)
    print()
    
    windows = list_windows()
    
    if not windows:
        print("No visible windows found!")
        return
    
    # Sort by area (largest first)
    windows.sort(key=lambda w: w['area'], reverse=True)
    
    print(f"Found {len(windows)} visible windows:\n")
    
    for i, win in enumerate(windows, 1):
        print(f"{i}. {win['title']}")
        print(f"   HWND: {win['hwnd']}")
        print(f"   Position: ({win['left']}, {win['top']})")
        print(f"   Size: {win['width']}x{win['height']} (area: {win['area']} px²)")
        
        # Highlight if this looks like a game window
        if win['width'] >= 600 and win['height'] >= 400:
            print(f"   ✓ Game-sized window (good for game capture)")
        print()
    
    print("=" * 80)
    print("GAME WINDOW SEARCH")
    print("=" * 80)
    print()
    
    game_windows = [w for w in windows if w['width'] >= 600 and w['height'] >= 400]
    largest_game = game_windows[0] if game_windows else None
    
    if largest_game:
        print(f"Largest game-sized window: {largest_game['title']}")
        print(f"Size: {largest_game['width']}x{largest_game['height']}")
        print()
        print("For Shadow Fight Arena capture, use:")
        print(f"  python main.py --window-title \"{largest_game['title']}\"")
        print(f"  or")
        print(f"  python debug_capture_region.py --window-title \"{largest_game['title']}\"")
    else:
        print("No game-sized windows (>=600x400) found!")
        print("Make sure your game is running and maximized/large enough.")
    
    print()


if __name__ == "__main__":
    main()
