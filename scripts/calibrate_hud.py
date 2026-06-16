from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import median
from typing import Iterable

import cv2
import numpy as np


def _parse_roi(text: str) -> tuple[float, float, float, float]:
    parts = [p.strip() for p in text.split(",") if p.strip()]
    if len(parts) != 4:
        raise ValueError(f"Invalid ROI '{text}'. Expected x0,y0,x1,y1")
    x0, y0, x1, y1 = (float(p) for p in parts)
    if not (0.0 <= x0 < x1 <= 1.0 and 0.0 <= y0 < y1 <= 1.0):
        raise ValueError(f"ROI out of range: '{text}'")
    return (x0, y0, x1, y1)


def _slice_roi(frame: np.ndarray, roi: tuple[float, float, float, float]) -> np.ndarray:
    h, w = frame.shape[:2]
    x0 = int(w * roi[0])
    y0 = int(h * roi[1])
    x1 = int(w * roi[2])
    y1 = int(h * roi[3])
    x0 = max(0, min(x0, w - 1))
    x1 = max(x0 + 1, min(x1, w))
    y0 = max(0, min(y0, h - 1))
    y1 = max(y0 + 1, min(y1, h))
    return frame[y0:y1, x0:x1]


def _iter_images(root: Path) -> Iterable[Path]:
    patterns = ("*.jpg", "*.jpeg", "*.png", "*.webp")
    for pattern in patterns:
        yield from root.rglob(pattern)


def _collect_hsv_pixels(
    image_paths: list[Path],
    roi: tuple[float, float, float, float],
    sat_min: int,
    val_min: int,
) -> np.ndarray:
    pixels: list[np.ndarray] = []
    for path in image_paths:
        frame = cv2.imread(str(path), cv2.IMREAD_COLOR)
        if frame is None:
            continue
        roi_img = _slice_roi(frame, roi)
        hsv = cv2.cvtColor(roi_img, cv2.COLOR_BGR2HSV)
        mask = (hsv[:, :, 1] >= sat_min) & (hsv[:, :, 2] >= val_min)
        selected = hsv[mask]
        if selected.size:
            pixels.append(selected)
    if not pixels:
        return np.empty((0, 3), dtype=np.uint8)
    return np.vstack(pixels)


def _safe_percentile(values: np.ndarray, q: float, default: float) -> float:
    if values.size == 0:
        return default
    return float(np.percentile(values, q))


def calibrate(
    images_dir: Path,
    left_roi: tuple[float, float, float, float],
    right_roi: tuple[float, float, float, float],
    shadow_roi: tuple[float, float, float, float],
    max_images: int,
) -> dict:
    image_paths = sorted(_iter_images(images_dir))[: max(1, max_images)]

    if not image_paths:
        raise RuntimeError(f"No image files found under: {images_dir}")

    shadow_pixels = _collect_hsv_pixels(image_paths, shadow_roi, sat_min=40, val_min=40)
    health_left_pixels = _collect_hsv_pixels(image_paths, left_roi, sat_min=40, val_min=40)
    health_right_pixels = _collect_hsv_pixels(image_paths, right_roi, sat_min=40, val_min=40)

    health_pixels = np.vstack([p for p in (health_left_pixels, health_right_pixels) if p.size]) if (
        health_left_pixels.size or health_right_pixels.size
    ) else np.empty((0, 3), dtype=np.uint8)

    if shadow_pixels.size:
        shadow_candidate_mask = (shadow_pixels[:, 0] >= 70) & (shadow_pixels[:, 0] <= 145)
        shadow_candidates = shadow_pixels[shadow_candidate_mask]
        if shadow_candidates.size:
            shadow_pixels = shadow_candidates

    shadow_h = shadow_pixels[:, 0] if shadow_pixels.size else np.array([], dtype=np.float32)
    shadow_s = shadow_pixels[:, 1] if shadow_pixels.size else np.array([], dtype=np.float32)
    shadow_v = shadow_pixels[:, 2] if shadow_pixels.size else np.array([], dtype=np.float32)

    rec_shadow_h_min = int(round(_safe_percentile(shadow_h, 8, 88.0)))
    rec_shadow_h_max = int(round(_safe_percentile(shadow_h, 92, 135.0)))
    rec_shadow_s_min = int(round(_safe_percentile(shadow_s, 25, 90.0)))
    rec_shadow_v_min = int(round(_safe_percentile(shadow_v, 20, 70.0)))

    health_s = health_pixels[:, 1] if health_pixels.size else np.array([], dtype=np.float32)
    health_v = health_pixels[:, 2] if health_pixels.size else np.array([], dtype=np.float32)

    report = {
        "images_processed": len(image_paths),
        "rois": {
            "left_health": left_roi,
            "right_health": right_roi,
            "shadow": shadow_roi,
        },
        "recommended": {
            "AF_HUD_SHADOW_H_MIN": max(0, min(179, rec_shadow_h_min)),
            "AF_HUD_SHADOW_H_MAX": max(0, min(179, rec_shadow_h_max)),
            "AF_HUD_SHADOW_S_MIN": max(0, min(255, rec_shadow_s_min)),
            "AF_HUD_SHADOW_V_MIN": max(0, min(255, rec_shadow_v_min)),
            "AF_HUD_HEALTH_LEFT_ROI": ",".join(f"{v:.3f}" for v in left_roi),
            "AF_HUD_HEALTH_RIGHT_ROI": ",".join(f"{v:.3f}" for v in right_roi),
            "AF_HUD_SHADOW_ROI": ",".join(f"{v:.3f}" for v in shadow_roi),
        },
        "stats": {
            "shadow_hue_median": float(median(shadow_h.tolist())) if shadow_h.size else None,
            "shadow_saturation_median": float(median(shadow_s.tolist())) if shadow_s.size else None,
            "shadow_value_median": float(median(shadow_v.tolist())) if shadow_v.size else None,
            "health_saturation_median": float(median(health_s.tolist())) if health_s.size else None,
            "health_value_median": float(median(health_v.tolist())) if health_v.size else None,
        },
    }

    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Calibrate HUD health/shadow thresholds from recorded frames")
    parser.add_argument("--images-dir", default="brain/learning/labels", help="Directory containing captured frames")
    parser.add_argument("--left-health-roi", default="0.05,0.03,0.46,0.09")
    parser.add_argument("--right-health-roi", default="0.54,0.03,0.95,0.09")
    parser.add_argument("--shadow-roi", default="0.07,0.09,0.45,0.14")
    parser.add_argument("--max-images", type=int, default=800)
    parser.add_argument("--out", default=None, help="Optional JSON output path")
    args = parser.parse_args()

    report = calibrate(
        images_dir=Path(args.images_dir),
        left_roi=_parse_roi(args.left_health_roi),
        right_roi=_parse_roi(args.right_health_roi),
        shadow_roi=_parse_roi(args.shadow_roi),
        max_images=args.max_images,
    )

    content = json.dumps(report, indent=2)
    print(content)

    print("\nSuggested environment variables:")
    for key, value in report["recommended"].items():
        print(f"  {key}={value}")

    if args.out:
        Path(args.out).write_text(content + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
