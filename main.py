from __future__ import annotations

import argparse
import logging
import signal
import sys
import threading
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict

import numpy as np
import uvicorn

from api.server import app, broadcast_sync
from brain.action_space import FighterAction
from brain.policy_runtime import build_runtime
from brain.strategy_memory import AdaptiveComboLearner
from common.logging_config import configure_logging
from common.settings import RuntimeSettings, load_runtime_settings
from muscles.python_wrapper import InputExecutor
from perception.capture import CaptureRegion, ScreenCapture, FpsCounter
from perception.detector import FighterDetector
from perception.pipeline import HudEstimatorConfig, PerceptionPipeline

LOGGER = logging.getLogger("autonomous_fighter.main")


KEY_BINDINGS = {
    FighterAction.MOVE_FORWARD: 0x44,   # D
    FighterAction.MOVE_BACKWARD: 0x41,  # A
    FighterAction.JUMP: 0x57,           # W
    FighterAction.CROUCH: 0x53,         # S
    FighterAction.LIGHT_ATTACK: 0x4F,   # O
    FighterAction.HEAVY_ATTACK: 0x50,   # P (light kick)
    FighterAction.SPECIAL: 0x4B,        # K (throwing knife)
}

SHADOW_SPECIAL_KEY = 0x4C  # L

COMBO_LIBRARY = {
    "base_forward_o5": [
        FighterAction.MOVE_FORWARD,
        FighterAction.LIGHT_ATTACK,
        FighterAction.LIGHT_ATTACK,
        FighterAction.LIGHT_ATTACK,
        FighterAction.LIGHT_ATTACK,
        FighterAction.LIGHT_ATTACK,
    ],
    "base_backward_o4": [
        FighterAction.MOVE_BACKWARD,
        FighterAction.LIGHT_ATTACK,
        FighterAction.LIGHT_ATTACK,
        FighterAction.LIGHT_ATTACK,
        FighterAction.LIGHT_ATTACK,
    ],
    "base_down_o": [
        FighterAction.CROUCH,
        FighterAction.LIGHT_ATTACK,
    ],
    "base_up_o": [
        FighterAction.JUMP,
        FighterAction.LIGHT_ATTACK,
    ],
    "base_up_p": [
        FighterAction.JUMP,
        FighterAction.HEAVY_ATTACK,
    ],
    "base_down_p": [
        FighterAction.CROUCH,
        FighterAction.HEAVY_ATTACK,
    ],
    "base_forward_p3": [
        FighterAction.MOVE_FORWARD,
        FighterAction.HEAVY_ATTACK,
        FighterAction.HEAVY_ATTACK,
        FighterAction.HEAVY_ATTACK,
    ],
    "base_backward_p3": [
        FighterAction.MOVE_BACKWARD,
        FighterAction.HEAVY_ATTACK,
        FighterAction.HEAVY_ATTACK,
        FighterAction.HEAVY_ATTACK,
    ],
    "rush_o6": [
        FighterAction.MOVE_FORWARD,
        FighterAction.LIGHT_ATTACK,
        FighterAction.LIGHT_ATTACK,
        FighterAction.LIGHT_ATTACK,
        FighterAction.LIGHT_ATTACK,
        FighterAction.LIGHT_ATTACK,
        FighterAction.LIGHT_ATTACK,
    ],
    "rush_mix": [
        FighterAction.MOVE_FORWARD,
        FighterAction.LIGHT_ATTACK,
        FighterAction.HEAVY_ATTACK,
        FighterAction.LIGHT_ATTACK,
        FighterAction.HEAVY_ATTACK,
    ],
    "jump_in": [
        FighterAction.JUMP,
        FighterAction.MOVE_FORWARD,
        FighterAction.LIGHT_ATTACK,
        FighterAction.HEAVY_ATTACK,
    ],
    "low_mix": [
        FighterAction.CROUCH,
        FighterAction.LIGHT_ATTACK,
        FighterAction.LIGHT_ATTACK,
        FighterAction.HEAVY_ATTACK,
    ],
    "combo_2_s_o": [
        FighterAction.CROUCH,
        FighterAction.LIGHT_ATTACK,
    ],
    "combo_3_w_o": [
        FighterAction.JUMP,
        FighterAction.LIGHT_ATTACK,
    ],
    "combo_4_a_o": [
        FighterAction.MOVE_BACKWARD,
        FighterAction.LIGHT_ATTACK,
    ],
    "guard_punish": [
        FighterAction.MOVE_BACKWARD,
        FighterAction.CROUCH,
        FighterAction.LIGHT_ATTACK,
        FighterAction.HEAVY_ATTACK,
    ],
}


def run_api(host: str = "127.0.0.1", port: int = 8001) -> None:
    try:
        uvicorn.run(
            app,
            host=host,
            port=port,
            log_level="info",
            access_log=False,
            use_colors=False,
        )
    except Exception as e:
        LOGGER.error("API server error: %s", e)


def execute_action(
    executor: InputExecutor,
    action: FighterAction,
    min_delay_ms: int,
    max_delay_ms: int,
    shadow_meter_full: bool = False,
) -> None:
    if action == FighterAction.IDLE:
        return

    if action == FighterAction.SPECIAL:
        if shadow_meter_full:
            execute_shadow_special(executor, min_delay_ms, max_delay_ms)
        else:
            execute_throwing_knife(executor, min_delay_ms, max_delay_ms)
        return

    key = KEY_BINDINGS.get(action)
    if key is None:
        return

    executor.tap_key(key, min_delay_ms, max_delay_ms)


def execute_throwing_knife(
    executor: InputExecutor,
    min_delay_ms: int,
    max_delay_ms: int,
) -> FighterAction:
    executor.tap_key(KEY_BINDINGS[FighterAction.SPECIAL], min_delay_ms, max_delay_ms)
    return FighterAction.SPECIAL


def execute_shadow_special(
    executor: InputExecutor,
    min_delay_ms: int,
    max_delay_ms: int,
) -> FighterAction:
    # Shadow move input: Forward + L.
    executor.press_key(KEY_BINDINGS[FighterAction.MOVE_FORWARD])
    try:
        executor.tap_key(SHADOW_SPECIAL_KEY, min_delay_ms, max_delay_ms)
    finally:
        executor.release_key(KEY_BINDINGS[FighterAction.MOVE_FORWARD])
    return FighterAction.SPECIAL


def execute_block(
    executor: InputExecutor,
    min_delay_ms: int,
    max_delay_ms: int,
) -> FighterAction:
    hold_ms = max(max_delay_ms * 2, min_delay_ms + 35)
    executor.press_key(KEY_BINDINGS[FighterAction.MOVE_BACKWARD])
    executor.sleep_ms(hold_ms)
    executor.release_key(KEY_BINDINGS[FighterAction.MOVE_BACKWARD])
    return FighterAction.MOVE_BACKWARD


def execute_combo_forward_light(
    executor: InputExecutor,
    min_delay_ms: int,
    max_delay_ms: int,
) -> FighterAction:
    # Execute the requested combo pattern: FORWARD + O + O + O + O + O + O.
    executor.tap_key(KEY_BINDINGS[FighterAction.MOVE_FORWARD], min_delay_ms, max_delay_ms)
    for _ in range(6):
        executor.tap_key(KEY_BINDINGS[FighterAction.LIGHT_ATTACK], min_delay_ms, max_delay_ms)
    return FighterAction.LIGHT_ATTACK


def execute_named_combo(
    executor: InputExecutor,
    combo_name: str,
    min_delay_ms: int,
    max_delay_ms: int,
    combo_library: Dict[str, list[FighterAction]] | None = None,
    shadow_meter_full: bool = False,
) -> FighterAction:
    source = combo_library or COMBO_LIBRARY
    sequence = source.get(combo_name, source.get("rush_o6", COMBO_LIBRARY["rush_o6"]))
    last_action = FighterAction.LIGHT_ATTACK
    for combo_action in sequence:
        execute_action(
            executor,
            combo_action,
            min_delay_ms,
            max_delay_ms,
            shadow_meter_full=shadow_meter_full,
        )
        if combo_action in {FighterAction.LIGHT_ATTACK, FighterAction.HEAVY_ATTACK, FighterAction.SPECIAL}:
            last_action = combo_action
    return last_action


def execute_opening_pressure(
    executor: InputExecutor,
    frame_index: int,
    min_delay_ms: int,
    max_delay_ms: int,
) -> FighterAction:
    if frame_index % 5 == 0:
        return execute_combo_forward_light(executor, min_delay_ms, max_delay_ms)

    executor.tap_key(KEY_BINDINGS[FighterAction.MOVE_FORWARD], min_delay_ms, max_delay_ms)
    attack_action = FighterAction.LIGHT_ATTACK if frame_index % 2 == 0 else FighterAction.HEAVY_ATTACK
    executor.tap_key(KEY_BINDINGS[attack_action], min_delay_ms, max_delay_ms)
    return attack_action


def execute_berserk_pressure(
    executor: InputExecutor,
    frame_index: int,
    distance: float,
    enemy_airborne: bool,
    attack_streak: int,
    min_delay_ms: int,
    max_delay_ms: int,
    combo_library: Dict[str, list[FighterAction]] | None = None,
    shadow_meter_full: bool = False,
) -> FighterAction:
    if enemy_airborne:
        if frame_index % 3 == 0:
            return execute_named_combo(
                executor,
                "jump_in",
                min_delay_ms,
                max_delay_ms,
                combo_library=combo_library,
                shadow_meter_full=shadow_meter_full,
            )

        executor.tap_key(KEY_BINDINGS[FighterAction.MOVE_FORWARD], min_delay_ms, max_delay_ms)
        attack_action = FighterAction.HEAVY_ATTACK if attack_streak >= 2 or frame_index % 2 == 0 else FighterAction.LIGHT_ATTACK
        executor.tap_key(KEY_BINDINGS[attack_action], min_delay_ms, max_delay_ms)
        return attack_action

    if distance > 0.35:
        if frame_index % 2 == 0:
            return execute_combo_forward_light(executor, min_delay_ms, max_delay_ms)

        executor.tap_key(KEY_BINDINGS[FighterAction.MOVE_FORWARD], min_delay_ms, max_delay_ms)
        attack_action = FighterAction.LIGHT_ATTACK if frame_index % 3 else FighterAction.HEAVY_ATTACK
        executor.tap_key(KEY_BINDINGS[attack_action], min_delay_ms, max_delay_ms)
        return attack_action

    if attack_streak >= 4 or frame_index % 4 == 0:
        return execute_named_combo(
            executor,
            "rush_mix",
            min_delay_ms,
            max_delay_ms,
            combo_library=combo_library,
            shadow_meter_full=shadow_meter_full,
        )

    attack_action = FighterAction.LIGHT_ATTACK if frame_index % 2 == 0 else FighterAction.HEAVY_ATTACK
    executor.tap_key(KEY_BINDINGS[attack_action], min_delay_ms, max_delay_ms)
    if frame_index % 3 == 0:
        executor.tap_key(KEY_BINDINGS[FighterAction.MOVE_FORWARD], min_delay_ms, max_delay_ms)
    return attack_action


def execute_feint(
    executor: InputExecutor,
    min_delay_ms: int,
    max_delay_ms: int,
) -> None:
    execute_action(executor, FighterAction.MOVE_FORWARD, min_delay_ms, max_delay_ms)
    execute_action(executor, FighterAction.CROUCH, min_delay_ms, max_delay_ms)
    execute_action(executor, FighterAction.MOVE_FORWARD, min_delay_ms, max_delay_ms)


def should_block(
    distance: float,
    enemy_airborne: bool,
    confidence_score: float,
    attack_streak: int,
    frame_index: int,
) -> bool:
    if enemy_airborne:
        return False

    very_close_threat = distance < 0.16
    close_range_threat = distance < 0.24
    unsure_state = confidence_score < 0.72
    anti_mash_guard = attack_streak <= 2 and frame_index % 2 == 0
    emergency_guard = very_close_threat and attack_streak <= 4
    return emergency_guard or (close_range_threat and (anti_mash_guard or unsure_state))


def to_observation(state: Dict[str, Any]) -> np.ndarray:
    if state is None:
        return np.zeros((10,), dtype=np.float32)

    return np.array(
        [
            float(state.get("dx", 0.0)),
            float(state.get("dy", 0.0)),
            float(state.get("distance", 0.5)),
            float(state.get("player", {}).get("airborne", 0.0)),
            float(state.get("enemy", {}).get("airborne", 0.0)),
            0.0,
            0.0,
            0.0,
            0.0,
            float(state.get("confidence", 0.0)),
        ],
        dtype=np.float32,
    )


def _project_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent.parent
    return Path(__file__).resolve().parent


def _default_paths(settings: RuntimeSettings) -> tuple[str, str]:
    root = _project_root()
    dll_default = root / "muscles" / "build" / "Release" / "autonomous_fighter_muscles.dll"
    yolo_default = Path(settings.yolo_model)
    if not yolo_default.is_absolute():
        yolo_default = root / yolo_default
    return str(dll_default), str(yolo_default)


def parse_args(settings: RuntimeSettings) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AutonomousFighter orchestrator")
    default_dll, default_yolo = _default_paths(settings)
    parser.add_argument("--dll", default=default_dll, help="Path to autonomous_fighter_muscles.dll")
    parser.add_argument("--yolo", default=default_yolo, help="Path to YOLOv8 model")
    parser.add_argument("--left", type=int, default=settings.capture_left)
    parser.add_argument("--top", type=int, default=settings.capture_top)
    parser.add_argument("--width", type=int, default=settings.capture_width)
    parser.add_argument("--height", type=int, default=settings.capture_height)
    parser.add_argument("--window-title", default="Shadow Fight Arena", help="Track this active window title for capture region")
    parser.add_argument("--target-fps", type=float, default=60.0)
    parser.add_argument("--capture-thread-fps", type=float, default=60.0, help="Target FPS for dedicated screen capture thread")
    parser.add_argument(
        "--capture-quality-scale",
        type=float,
        default=1.0,
        help="Capture downscale factor in range [0.5, 1.0]; lower is faster/lower quality",
    )
    parser.add_argument("--api-host", default=settings.api_host)
    parser.add_argument("--api-port", type=int, default=settings.api_port)
    parser.add_argument("--min-key-delay", type=int, default=settings.key_tap_min_delay_ms)
    parser.add_argument("--max-key-delay", type=int, default=settings.key_tap_max_delay_ms)
    parser.add_argument(
        "--min-action-confidence",
        type=float,
        default=settings.min_action_confidence,
        help="Only emit keyboard input when perception confidence is at least this value",
    )
    parser.add_argument("--fight-memory-dir", default="brain/learning", help="Directory used to persist fight screenshots and strategy memory")
    parser.add_argument("--model", default=None, help="Path to trained PPO model (.zip)")
    parser.add_argument("--deterministic", action="store_true", help="Use deterministic model inference")
    return parser.parse_args()


class SharedTelemetry:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.detections: list[Any] = []
        self.hud_debug: Dict[str, Any] = {}
        self.metadata: Dict[str, Any] = {
            "current_action": "STANDBY",
            "selected_combo": None,
            "confidence_score": 0.0,
            "attack_streak": 0,
            "combo_scores": {},
            "fight_memory": {},
            "state": None,
        }

    def update_bot_data(self, detections: list[Any], hud_debug: Dict[str, Any], metadata: Dict[str, Any]) -> None:
        with self.lock:
            self.detections = list(detections)
            self.hud_debug = dict(hud_debug) if hud_debug else {}
            self.metadata = dict(metadata)

    def get_snapshot(self) -> tuple[list[Any], Dict[str, Any], Dict[str, Any]]:
        with self.lock:
            return list(self.detections), dict(self.hud_debug), dict(self.metadata)


def run_streaming_thread(
    capture: ScreenCapture,
    shared_telemetry: SharedTelemetry,
    stop_event: threading.Event,
    debug_overlay: bool = True,
    target_fps: float = 60.0,
) -> None:
    from perception.visualize import draw_detections, encode_jpeg_base64
    from dataclasses import asdict

    frame_budget = 1.0 / target_fps
    fps_counter = FpsCounter()

    LOGGER.info("Streaming thread waiting for initial game frame...")
    while not stop_event.is_set():
        frame = capture.grab_latest_bgr()
        if frame is not None and frame.size > 0:
            break
        time.sleep(0.02)

    LOGGER.info("Streaming thread active. Target FPS: %.1f", target_fps)

    while not stop_event.is_set():
        started = time.perf_counter()

        frame = capture.grab_latest_bgr()
        if frame is None or frame.size == 0:
            time.sleep(0.002)
            continue

        detections, hud_debug, metadata = shared_telemetry.get_snapshot()

        annotated = draw_detections(
            frame,
            detections,
            hud_debug=hud_debug if debug_overlay else None,
        )

        encoded = encode_jpeg_base64(annotated)
        cap_stats = capture.get_capture_stats()

        packet = {
            "timestamp": time.time(),
            "fps": float(fps_counter.tick()),
            "capture_fps": float(cap_stats.get("capture_fps", 0.0)),
            "current_action": metadata.get("current_action", "STANDBY"),
            "selected_combo": metadata.get("selected_combo"),
            "confidence_score": metadata.get("confidence_score", 0.0),
            "attack_streak": metadata.get("attack_streak", 0),
            "combo_scores": metadata.get("combo_scores", {}),
            "fight_memory": metadata.get("fight_memory", {}),
            "frame_shape": list(frame.shape),
            "capture_region": {
                "left": capture.region.left,
                "top": capture.region.top,
                "width": capture.region.width,
                "height": capture.region.height,
            },
            "detections": [asdict(d) for d in detections],
            "state": metadata.get("state"),
            "live_frame_jpeg": encoded,
        }

        broadcast_sync(packet)

        elapsed = time.perf_counter() - started
        if elapsed < frame_budget:
            time.sleep(frame_budget - elapsed)


def main() -> None:
    configure_logging()
    settings = load_runtime_settings()
    args = parse_args(settings)

    stop_requested = False
    executor: InputExecutor | None = None
    stream_stop_event = threading.Event()

    def _request_stop(signum: int, _frame: Any) -> None:
        nonlocal stop_requested
        stop_requested = True
        LOGGER.info("Received signal %s, stopping orchestrator loop.", signum)
        stream_stop_event.set()
        # Force release all keys immediately
        if executor is not None:
            executor.reset_all_keys()

    signal.signal(signal.SIGINT, _request_stop)
    signal.signal(signal.SIGTERM, _request_stop)

    api_thread = threading.Thread(target=run_api, args=(args.api_host, args.api_port), daemon=True)
    api_thread.start()
    LOGGER.info("Telemetry API started at %s:%s", args.api_host, args.api_port)

    try:
        executor = InputExecutor(args.dll)
        LOGGER.info("✓ InputExecutor loaded from: %s", args.dll)
    except Exception as e:
        LOGGER.error("✗ Failed to load InputExecutor: %s", e)
        raise
    detector = FighterDetector(args.yolo)
    capture = ScreenCapture(
        CaptureRegion(args.left, args.top, args.width, args.height),
        follow_window_title=args.window_title,
        async_capture=True,
        target_fps=args.capture_thread_fps,
        quality_scale=args.capture_quality_scale,
        adaptive_quality=True,
    )
    
    # Log the initial capture configuration
    LOGGER.info("✓ ScreenCapture configured")
    LOGGER.info("  Window title to follow: '%s'", args.window_title)
    LOGGER.info("  Initial region: left=%d, top=%d, width=%d, height=%d", 
                args.left, args.top, args.width, args.height)
    LOGGER.info("  Capture thread target FPS: %.1f", args.capture_thread_fps)
    LOGGER.info("  Capture quality scale: %.2f", args.capture_quality_scale)
    
    pipeline = PerceptionPipeline(
        capture,
        detector,
        hud_config=HudEstimatorConfig(
            health_left_roi=settings.hud_health_left_roi,
            health_right_roi=settings.hud_health_right_roi,
            shadow_roi=settings.hud_shadow_roi,
            shadow_h_min=settings.hud_shadow_h_min,
            shadow_h_max=settings.hud_shadow_h_max,
            shadow_s_min=settings.hud_shadow_sat_min,
            shadow_v_min=settings.hud_shadow_val_min,
            debug_overlay=settings.hud_debug_overlay,
        ),
    )
    policy = build_runtime(args.model, deterministic=args.deterministic)
    LOGGER.info("✓ Policy runtime: %s", type(policy).__name__)

    # Start the background UI streaming thread
    shared_telemetry = SharedTelemetry()
    stream_thread = threading.Thread(
        target=run_streaming_thread,
        args=(capture, shared_telemetry, stream_stop_event, settings.hud_debug_overlay, 60.0),
        name="telemetry-streamer",
        daemon=True,
    )
    stream_thread.start()

    attack_streak = 0
    frame_budget = 1.0 / max(1.0, args.target_fps)
    LOGGER.info("Main loop started with target FPS %.1f", args.target_fps)
    
    frame_count = 0
    debug_interval = 30  # Log every 30 frames
    opening_pressure_seconds = 10.0
    opening_started = time.perf_counter()
    combo_learner = AdaptiveComboLearner(args.fight_memory_dir)
    
    # Capture and log first frame to verify window detection
    first_frame = capture.grab_latest_bgr()
    first_detections, first_state, first_hud = pipeline.process_frame(first_frame)
    LOGGER.info("First frame captured: shape=%s, detections=%d", 
                list(first_frame.shape), 
                len(first_detections))
    if capture.region:
        LOGGER.info("  Actual capture region: left=%d, top=%d, width=%d, height=%d",
                    capture.region.left, capture.region.top, capture.region.width, capture.region.height)

    bot_fps_counter = FpsCounter()

    try:
        while not stop_requested:
            started = time.perf_counter()
            frame = capture.grab_latest_bgr()
            detections, state, hud_debug = pipeline.process_frame(frame)
            bot_fps = bot_fps_counter.tick()

            confidence_score = float((state or {}).get("confidence", 0.0))
            obs = to_observation(state) if state is not None else np.zeros((10,), dtype=np.float32)
            distance = float(obs[2])
            enemy_airborne = float(obs[4]) > 0.5
            shadow_meter = float((state or {}).get("shadow_meter", 0.0))
            shadow_meter_full = bool((state or {}).get("shadow_full", False) or shadow_meter >= 0.98)
            selected_combo_name: str | None = None
            profile = combo_learner.live_strategy_profile(
                distance=distance,
                enemy_airborne=enemy_airborne,
                attack_streak=attack_streak,
                confidence_score=confidence_score,
            )
            dynamic_combo_interval = max(3, min(10, profile.combo_interval))
            effective_min_delay = max(1, int(args.min_key_delay * profile.min_delay_scale))
            effective_max_delay = max(effective_min_delay, int(args.max_key_delay * profile.max_delay_scale))
            active_combo_library = combo_learner.available_combos()

            frame_count += 1
            if frame_count % debug_interval == 0:
                detections_count = len(detections)
                LOGGER.debug("Frame %d: detections=%d, state=%s, confidence=%.3f",
                            frame_count, detections_count, state is not None, confidence_score)

            in_opening_pressure = (time.perf_counter() - opening_started) < opening_pressure_seconds
            punish_combo_name = combo_learner.recommend_punish_combo(
                distance=distance,
                enemy_airborne=enemy_airborne,
                attack_streak=attack_streak,
                confidence_score=confidence_score,
            )

            if in_opening_pressure:
                action = execute_berserk_pressure(
                    executor,
                    frame_count,
                    distance,
                    enemy_airborne,
                    attack_streak,
                    effective_min_delay,
                    effective_max_delay,
                    combo_library=active_combo_library,
                    shadow_meter_full=shadow_meter_full,
                )
                if frame_count % debug_interval == 0:
                    LOGGER.debug("  → Opening pressure action: berserk %s", action.name)
            elif state is None:
                selected_combo_name = "rush_o6"
                action = execute_named_combo(
                    executor,
                    selected_combo_name,
                    effective_min_delay,
                    effective_max_delay,
                    combo_library=active_combo_library,
                    shadow_meter_full=shadow_meter_full,
                )
                if frame_count % debug_interval == 0:
                    LOGGER.debug("  → No state fallback combo: rush_o6")
            elif confidence_score < args.min_action_confidence:
                selected_combo_name = punish_combo_name or combo_learner.choose_combo(distance=distance, enemy_airborne=enemy_airborne)
                action = execute_named_combo(
                    executor,
                    selected_combo_name,
                    effective_min_delay,
                    effective_max_delay,
                    combo_library=active_combo_library,
                    shadow_meter_full=shadow_meter_full,
                )
                if frame_count % debug_interval == 0:
                    LOGGER.debug("  → Low confidence punish combo: %s", selected_combo_name)
            else:
                if should_block(
                    distance=distance,
                    enemy_airborne=enemy_airborne,
                    confidence_score=confidence_score,
                    attack_streak=attack_streak,
                    frame_index=frame_count,
                ):
                    action = execute_block(executor, effective_min_delay, effective_max_delay)
                    if frame_count % 3 == 0 and confidence_score > 0.70:
                        selected_combo_name = "guard_punish"
                        action = execute_named_combo(
                            executor,
                            selected_combo_name,
                            effective_min_delay,
                            effective_max_delay,
                            combo_library=active_combo_library,
                            shadow_meter_full=shadow_meter_full,
                        )
                else:
                    if combo_learner.should_feint(frame_count, profile):
                        execute_feint(executor, effective_min_delay, effective_max_delay)

                    if punish_combo_name and (attack_streak <= 2 or frame_count % 3 == 0):
                        selected_combo_name = punish_combo_name
                        action = execute_named_combo(
                            executor,
                            selected_combo_name,
                            effective_min_delay,
                            effective_max_delay,
                            combo_library=active_combo_library,
                            shadow_meter_full=shadow_meter_full,
                        )
                    else:
                        if frame_count % dynamic_combo_interval == 0 or attack_streak >= 3:
                            selected_combo_name = combo_learner.choose_combo(distance=distance, enemy_airborne=enemy_airborne)
                            action = execute_named_combo(
                                executor,
                                selected_combo_name,
                                effective_min_delay,
                                effective_max_delay,
                                combo_library=active_combo_library,
                                shadow_meter_full=shadow_meter_full,
                            )
                        else:
                            if profile.force_pressure or distance < 0.28 or attack_streak >= 2 or confidence_score > 0.8:
                                action = execute_berserk_pressure(
                                    executor,
                                    frame_count,
                                    distance,
                                    enemy_airborne,
                                    attack_streak,
                                    effective_min_delay,
                                    effective_max_delay,
                                    combo_library=active_combo_library,
                                    shadow_meter_full=shadow_meter_full,
                                )
                            else:
                                action = policy.choose_action(obs)
                            if action not in {
                                FighterAction.LIGHT_ATTACK,
                                FighterAction.HEAVY_ATTACK,
                                FighterAction.SPECIAL,
                                FighterAction.MOVE_FORWARD,
                                FighterAction.MOVE_BACKWARD,
                                FighterAction.JUMP,
                                FighterAction.CROUCH,
                            }:
                                action = FighterAction.LIGHT_ATTACK
                            execute_action(
                                executor,
                                action,
                                effective_min_delay,
                                effective_max_delay,
                                shadow_meter_full=shadow_meter_full,
                            )

                if frame_count % debug_interval == 0:
                    LOGGER.debug("  → Action executed: %s", action.name)

            if action in {FighterAction.LIGHT_ATTACK, FighterAction.HEAVY_ATTACK, FighterAction.SPECIAL}:
                attack_streak += 1
            else:
                attack_streak = max(0, attack_streak - 1)

            # Update shared telemetry
            shared_telemetry.update_bot_data(
                detections=detections,
                hud_debug=hud_debug,
                metadata={
                    "current_action": action.name,
                    "selected_combo": selected_combo_name,
                    "confidence_score": confidence_score,
                    "attack_streak": attack_streak,
                    "combo_scores": combo_learner.combo_scores,
                    "fight_memory": combo_learner.current_status(),
                    "state": state,
                }
            )

            # Build local packet for combo learner (include raw_frame to save snapshots directly)
            packet = {
                "timestamp": time.time(),
                "fps": float(bot_fps),
                "capture_fps": float(capture.get_capture_stats().get("capture_fps", 0.0)),
                "current_action": action.name,
                "selected_combo": selected_combo_name,
                "confidence_score": confidence_score,
                "attack_streak": attack_streak,
                "combo_scores": combo_learner.combo_scores,
                "fight_memory": combo_learner.current_status(),
                "frame_shape": list(frame.shape),
                "capture_region": {
                    "left": capture.region.left,
                    "top": capture.region.top,
                    "width": capture.region.width,
                    "height": capture.region.height,
                },
                "detections": [asdict(d) for d in detections],
                "state": state,
                "raw_frame": frame,
            }

            episode_summary = combo_learner.observe_step(packet, action, attack_streak, selected_combo_name)
            if episode_summary:
                LOGGER.info(
                    "Fight episode %s ended (%s): frames=%d, trend=%.3f, avg_conf=%.3f, strategy=%s",
                    episode_summary.get("episode_id"),
                    episode_summary.get("reason"),
                    episode_summary.get("frames", 0),
                    episode_summary.get("confidence_trend", 0.0),
                    episode_summary.get("average_confidence", 0.0),
                    episode_summary.get("strategy_bucket"),
                )

            elapsed = time.perf_counter() - started
            if elapsed < frame_budget:
                time.sleep(frame_budget - elapsed)
    finally:
        # Force release all keys before exiting
        if executor is not None:
            executor.reset_all_keys()
        stream_stop_event.set()
        stream_thread.join(timeout=1.0)
        capture.stop()

    LOGGER.info("Orchestrator stopped cleanly.")


if __name__ == "__main__":
    main()
