from __future__ import annotations

from dataclasses import asdict
from typing import Any, Dict

from perception.capture import FpsCounter, ScreenCapture
from perception.detector import FighterDetector
from perception.state_extractor import extract_relative_state
from perception.visualize import draw_detections, encode_jpeg_base64


class PerceptionPipeline:
    def __init__(self, capture: ScreenCapture, detector: FighterDetector) -> None:
        self.capture = capture
        self.detector = detector
        self.fps_counter = FpsCounter()

    def step(self) -> Dict[str, Any]:
        frame = self.capture.grab_latest_bgr()
        fps = self.fps_counter.tick()
        detections = self.detector.detect(frame)
        annotated = draw_detections(frame, detections)
        encoded = encode_jpeg_base64(annotated)

        relative_state = extract_relative_state(
            detections=detections,
            frame_width=frame.shape[1],
            frame_height=frame.shape[0],
        )

        return {
            "fps": fps,
            "detections": [asdict(d) for d in detections],
            "state": asdict(relative_state) if relative_state else None,
            "frame_shape": list(frame.shape),
            "live_frame_jpeg": encoded,
        }
