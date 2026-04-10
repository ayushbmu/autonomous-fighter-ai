#!/usr/bin/env python3
"""
Debug script to visualize the capture region for the game window.
Useful for verifying that the correct game screen is being captured.

Usage: python debug_capture_region.py --window-title "Shadow Fight Arena"
"""

import argparse
import sys
import time

try:
    import win32gui
except ImportError:
    print("ERROR: win32gui not found. Install with: pip install pywin32")
    sys.exit(1)

try:
    import cv2
except ImportError:
    print("ERROR: opencv-python not found. Install with: pip install opencv-python")
    sys.exit(1)

try:
    import mss
except ImportError:
    print("ERROR: mss not found. Install with: pip install mss")
    sys.exit(1)

import numpy as np
from perception.capture import CaptureRegion, ScreenCapture


def main():
    parser = argparse.ArgumentParser(
        description="Visualize the game screen capture region"
    )
    parser.add_argument(
        "--window-title",
        default="Shadow Fight Arena",
        help="Game window title to track"
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=10,
        help="Duration in seconds to display the capture"
    )
    args = parser.parse_args()

    print(f"Looking for window with title containing: '{args.window_title}'")
    print(f"Display duration: {args.duration} seconds")
    print()
    
    # Initialize capture
    capture = ScreenCapture(
        CaptureRegion(0, 0, 1280, 720),
        follow_window_title=args.window_title,
    )
    
    print("Starting capture preview...")
    print("Press 'q' to quit or wait for duration to expire.")
    print()
    
    start_time = time.perf_counter()
    frame_count = 0
    
    try:
        # Grab first frame to trigger window search
        first_frame = capture.grab_bgr()
        window_info = capture.get_window_info()
        
        print(f"Initial window detection:")
        print(f"  Title searched: {window_info['follow_title']}")
        print(f"  Window found (hwnd): {window_info['last_hwnd']}")
        if window_info['last_hwnd'] == 0:
            print(f"  ⚠️  WARNING: Window NOT found!")
            print(f"      Make sure the game window is open and visible.")
            print(f"      Try matching more of the window title.")
        else:
            print(f"  ✓ Window detected successfully")
        print(f"  Capture region: ({window_info['current_region']['left']}, {window_info['current_region']['top']}) "
              f"{window_info['current_region']['width']}x{window_info['current_region']['height']}")
        print()
        
        while True:
            elapsed = time.perf_counter() - start_time
            if elapsed > args.duration:
                print(f"\nDuration expired after {frame_count} frames")
                break
            
            frame = capture.grab_bgr()
            frame_count += 1
            
            # Add region info to frame
            height = capture.region.height
            window_info = capture.get_window_info()
            
            # Color indicator based on window state
            status_color = (0, 255, 0) if window_info['last_hwnd'] != 0 else (0, 0, 255)
            status_text = "✓ Window Found" if window_info['last_hwnd'] != 0 else "✗ Window NOT Found"
            
            cv2.putText(
                frame,
                f"Window: {args.window_title}",
                (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 255, 0),
                2
            )
            cv2.putText(
                frame,
                status_text,
                (10, 70),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                status_color,
                2
            )
            cv2.putText(
                frame,
                f"Region: ({capture.region.left}, {capture.region.top}) "
                f"Size: {capture.region.width}x{capture.region.height}",
                (10, 110),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 255, 0),
                2
            )
            cv2.putText(
                frame,
                f"Frame: {frame_count} | Time: {elapsed:.1f}s",
                (10, height - 20),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (0, 255, 0),
                1
            )
            
            cv2.imshow("Capture Region Preview", frame)
            
            # Check for 'q' key press (waitKey with 1ms timeout)
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                print("\nUser quit")
                break
    
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
    
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        capture.stop()
        cv2.destroyAllWindows()
        print(f"Captured {frame_count} frames total")
        window_info = capture.get_window_info()
        print(f"Final status:")
        print(f"  Window hwnd: {window_info['last_hwnd']}")
        print(f"  Capture region: left={capture.region.left}, "
              f"top={capture.region.top}, "
              f"width={capture.region.width}, "
              f"height={capture.region.height}")


if __name__ == "__main__":
    main()
