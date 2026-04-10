from __future__ import annotations

import base64
import json
import logging
import random
import time
from collections import Counter, deque
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Deque, Dict, Optional

from brain.action_space import FighterAction
from perception.detector import Detection
from perception.state_extractor import assign_player_enemy

LOGGER = logging.getLogger("autonomous_fighter.strategy_memory")

COMBO_LIBRARY_PATH = Path(__file__).resolve().parent / "learning" / "combo_library.json"


DEFAULT_COMBO_LIBRARY = {
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

OPPONENT_STYLES = ("aerial", "zoning", "rushdown", "scramble")


def _default_combo_library() -> dict[str, list[FighterAction]]:
    return {name: list(sequence) for name, sequence in DEFAULT_COMBO_LIBRARY.items()}


def _load_combo_library(path: Path) -> dict[str, list[FighterAction]]:
    library = _default_combo_library()
    if not path.exists():
        return library

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        LOGGER.warning("Could not load combo library from %s", path)
        return library

    if not isinstance(payload, dict):
        return library

    for combo_name, sequence_names in payload.items():
        if not isinstance(sequence_names, list):
            continue

        sequence: list[FighterAction] = []
        for action_name in sequence_names:
            try:
                sequence.append(FighterAction[str(action_name)])
            except Exception:
                sequence = []
                break

        if sequence:
            library[combo_name] = sequence

    return library


@dataclass
class LiveStrategyProfile:
    aggression_mode: str
    combo_interval: int
    min_delay_scale: float
    max_delay_scale: float
    force_pressure: bool
    feint_chance: float


@dataclass
class FightSnapshot:
    timestamp: float
    frame_index: int
    confidence: float
    distance: float
    attack_streak: int
    action: str
    combo_name: str | None
    enemy_airborne: bool
    screenshot_path: str | None = None


@dataclass
class FightSummary:
    episode_id: str
    started_at: float
    ended_at: float
    duration_seconds: float
    frames: int
    snapshot_count: int
    average_confidence: float
    confidence_trend: float
    average_distance: float
    enemy_airborne_ratio: float
    dominant_action: str | None
    dominant_combo: str | None
    strategy_bucket: str
    screenshot_paths: list[str] = field(default_factory=list)


class FightLabelExporter:
    def __init__(self, export_dir: str | Path, frame_stride: int = 12) -> None:
        self.export_dir = Path(export_dir)
        self.export_dir.mkdir(parents=True, exist_ok=True)
        self.frame_stride = frame_stride

    def export_frame(self, episode_id: str, frame_index: int, packet: Dict[str, Any]) -> str | None:
        frame_shape = packet.get("frame_shape") or []
        if len(frame_shape) < 2:
            return None

        encoded = packet.get("live_frame_jpeg")
        detections = packet.get("detections") or []
        if not encoded or len(detections) < 2:
            return None

        player, enemy = assign_player_enemy([_detection_from_dict(item) for item in detections])
        if player is None or enemy is None:
            return None

        episode_dir = self.export_dir / episode_id
        images_dir = episode_dir / "images"
        labels_dir = episode_dir / "labels"
        images_dir.mkdir(parents=True, exist_ok=True)
        labels_dir.mkdir(parents=True, exist_ok=True)

        image_path = images_dir / f"frame_{frame_index:04d}.jpg"
        label_path = labels_dir / f"frame_{frame_index:04d}.txt"

        image_path.write_bytes(base64.b64decode(encoded))
        width = float(frame_shape[1])
        height = float(frame_shape[0])
        label_path.write_text(
            "\n".join(
                [
                    _yolo_label_line(0, player, width, height),
                    _yolo_label_line(1, enemy, width, height),
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        return str(image_path)


def _detection_from_dict(payload: Dict[str, Any]) -> Detection:
    return Detection(
        label=str(payload.get("label", "unknown")),
        confidence=float(payload.get("confidence", 0.0)),
        x1=float(payload.get("x1", 0.0)),
        y1=float(payload.get("y1", 0.0)),
        x2=float(payload.get("x2", 0.0)),
        y2=float(payload.get("y2", 0.0)),
    )


def _yolo_label_line(class_id: int, detection: Detection, frame_width: float, frame_height: float) -> str:
    x_center = ((detection.x1 + detection.x2) * 0.5) / max(1.0, frame_width)
    y_center = ((detection.y1 + detection.y2) * 0.5) / max(1.0, frame_height)
    width = (detection.x2 - detection.x1) / max(1.0, frame_width)
    height = (detection.y2 - detection.y1) / max(1.0, frame_height)
    return f"{class_id} {x_center:.6f} {y_center:.6f} {width:.6f} {height:.6f}"


class AdaptiveComboLearner:
    """Learns combo preferences from live frames and post-fight summaries."""

    def __init__(self, memory_dir: str | Path = "brain/learning") -> None:
        self.memory_dir = Path(memory_dir)
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        self.episode_dir = self.memory_dir / "episodes"
        self.episode_dir.mkdir(parents=True, exist_ok=True)

        self.state_path = self.memory_dir / "strategy_state.json"
        self.combo_library = _load_combo_library(COMBO_LIBRARY_PATH)
        self.combo_scores = {name: 0.0 for name in self.combo_library}
        self.context_combo_scores = {
            "anti_air": {name: 0.0 for name in self.combo_library},
            "closing_pressure": {name: 0.0 for name in self.combo_library},
            "close_pressure": {name: 0.0 for name in self.combo_library},
        }
        self.opponent_combo_scores = {style: {name: 0.0 for name in self.combo_library} for style in OPPONENT_STYLES}

        self.pending_combo: str | None = None
        self.pending_confidence: float = 0.0
        self.pending_streak: int = 0
        self.pending_combo_tick: int = 0
        self.combo_attempts = {name: 0 for name in self.combo_library}
        self.combo_successes = {name: 0 for name in self.combo_library}
        self.combo_failure_streak = {name: 0 for name in self.combo_library}
        self.combo_lockout_until = {name: 0 for name in self.combo_library}

        self._episode_active = False
        self._episode_id: str | None = None
        self._episode_started_at: float = 0.0
        self._episode_frame_index = 0
        self._episode_inactive_frames = 0
        self._episode_first_confidence: float | None = None
        self._episode_last_confidence: float = 0.0
        self._episode_peak_confidence: float = 0.0
        self._episode_confidence_sum = 0.0
        self._episode_distance_sum = 0.0
        self._episode_airborne_sum = 0.0
        self._episode_action_counts: Counter[str] = Counter()
        self._episode_combo_counts: Counter[str] = Counter()
        self._episode_snapshot_paths: list[str] = []
        self._episode_peak_snapshot: str | None = None
        self._episode_first_snapshot: str | None = None
        self._episode_latest_snapshot: str | None = None
        self._episode_last_packet: Dict[str, Any] | None = None
        self._episode_recent_confidences: Deque[float] = deque(maxlen=5)
        self._episode_ended_recently = False
        self._last_summary: Dict[str, Any] | None = None
        self._label_exporter = FightLabelExporter(self.memory_dir / "labels")
        self._episode_close_in_events = 0
        self._episode_prev_distance: float | None = None
        self._episode_combo_pack: list[str] = []
        self._match_combo_history: list[Dict[str, Any]] = []
        self._recent_actions: Deque[FighterAction] = deque(maxlen=12)
        self._learned_combo_count = 0
        self._tick = 0

        self.snapshot_stride = 15
        self.label_export_stride = 6
        self.active_confidence_threshold = 0.3
        self.inactive_grace_frames = 8
        self.exploration_rate = 0.18
        self._load_state()

    def available_combos(self) -> Dict[str, list[FighterAction]]:
        return {name: list(sequence) for name, sequence in self.combo_library.items()}

    def combo_sequence(self, combo_name: str) -> list[FighterAction]:
        return list(self.combo_library.get(combo_name, self.combo_library["rush_o6"]))

    def _register_combo(self, combo_name: str, sequence: list[FighterAction]) -> None:
        if not sequence:
            return
        self.combo_library[combo_name] = list(sequence)
        self.combo_scores.setdefault(combo_name, 0.0)
        self.combo_attempts.setdefault(combo_name, 0)
        self.combo_successes.setdefault(combo_name, 0)
        self.combo_failure_streak.setdefault(combo_name, 0)
        self.combo_lockout_until.setdefault(combo_name, 0)
        for context_scores in self.context_combo_scores.values():
            context_scores.setdefault(combo_name, 0.0)
        for style_scores in self.opponent_combo_scores.values():
            style_scores.setdefault(combo_name, 0.0)

    def _generated_combo_candidates(self, distance: float, enemy_airborne: bool) -> list[str]:
        if not self._episode_combo_pack:
            return []

        def _matches_context(name: str) -> bool:
            sequence = self.combo_library.get(name, [])
            if not sequence:
                return False
            opener = sequence[0]
            if enemy_airborne:
                return opener in {FighterAction.JUMP, FighterAction.MOVE_FORWARD}
            if distance > 0.35:
                return opener in {FighterAction.MOVE_FORWARD, FighterAction.JUMP, FighterAction.MOVE_BACKWARD}
            return opener in {FighterAction.CROUCH, FighterAction.MOVE_BACKWARD, FighterAction.MOVE_FORWARD}

        return [name for name in self._episode_combo_pack if _matches_context(name)]

    def _learned_combo_candidates(self, distance: float, enemy_airborne: bool) -> list[str]:
        learned_names = [
            name
            for name in self.combo_library
            if name.startswith("learned_") and self.combo_lockout_until.get(name, 0) <= self._tick
        ]
        if not learned_names:
            return []

        def _fits_context(name: str) -> bool:
            sequence = self.combo_library.get(name, [])
            if not sequence:
                return False
            opener = sequence[0]
            if enemy_airborne:
                return opener in {FighterAction.JUMP, FighterAction.MOVE_FORWARD}
            if distance > 0.35:
                return opener in {FighterAction.MOVE_FORWARD, FighterAction.JUMP, FighterAction.MOVE_BACKWARD}
            return opener in {FighterAction.CROUCH, FighterAction.MOVE_BACKWARD, FighterAction.MOVE_FORWARD}

        ranked = sorted(learned_names, key=lambda name: self.combo_scores.get(name, 0.0), reverse=True)
        return [name for name in ranked if _fits_context(name)][:4]

    def _learn_combo_from_recent_actions(self) -> str | None:
        if len(self._recent_actions) < 3:
            return None

        sequence = list(self._recent_actions)[-3:]
        attack_count = sum(1 for action in sequence if action in {FighterAction.LIGHT_ATTACK, FighterAction.HEAVY_ATTACK, FighterAction.SPECIAL})
        if attack_count < 1:
            return None

        signature = "_".join(action.name.lower() for action in sequence)
        combo_name = f"learned_{signature}"
        if combo_name not in self.combo_library:
            self._register_combo(combo_name, sequence)
            self.combo_scores[combo_name] = 0.2
            self._learned_combo_count += 1
            return combo_name

        return combo_name

    def _generate_match_combo_pack(self, episode_id: str) -> list[str]:
        opener_pool = [
            FighterAction.MOVE_FORWARD,
            FighterAction.MOVE_BACKWARD,
            FighterAction.JUMP,
            FighterAction.CROUCH,
        ]
        attack_pool = [FighterAction.LIGHT_ATTACK, FighterAction.HEAVY_ATTACK, FighterAction.SPECIAL]
        support_pool = [FighterAction.MOVE_FORWARD, FighterAction.MOVE_BACKWARD, FighterAction.CROUCH]

        generated_names: list[str] = []
        used_signatures: set[tuple[int, ...]] = set()
        for slot in range(1, 4):
            for _ in range(10):
                opener = random.choice(opener_pool)
                attack_a = random.choice(attack_pool)
                attack_b = random.choice(attack_pool)
                support = random.choice(support_pool)
                sequence = [opener, attack_a, support, attack_b]
                signature = tuple(int(action) for action in sequence)
                if signature in used_signatures:
                    continue
                used_signatures.add(signature)

                combo_name = f"match_{episode_id}_cfg_{slot}"
                self._register_combo(combo_name, sequence)
                generated_names.append(combo_name)
                break

        return generated_names

    def choose_combo(self, distance: float, enemy_airborne: bool) -> str:
        if enemy_airborne:
            context = "anti_air"
            candidates = ["base_up_o", "base_up_p", "combo_3_w_o", "jump_in", "rush_mix", "low_mix"]
        elif distance > 0.35:
            context = "closing_pressure"
            candidates = [
                "base_forward_o5",
                "base_forward_p3",
                "base_backward_p3",
                "rush_o6",
                "combo_4_a_o",
                "jump_in",
                "rush_mix",
                "guard_punish",
            ]
        else:
            context = "close_pressure"
            candidates = [
                "base_down_o",
                "base_down_p",
                "base_backward_o4",
                "combo_2_s_o",
                "rush_mix",
                "low_mix",
                "rush_o6",
                "combo_4_a_o",
                "guard_punish",
            ]

        candidates.extend(self._generated_combo_candidates(distance=distance, enemy_airborne=enemy_airborne))
        candidates.extend(self._learned_combo_candidates(distance=distance, enemy_airborne=enemy_airborne))
        candidates = [name for name in candidates if name in self.combo_library]
        if not candidates:
            candidates = ["rush_o6"]

        available = [name for name in candidates if self.combo_lockout_until.get(name, 0) <= self._tick]
        if not available:
            available = list(candidates)

        if random.random() < self.exploration_rate:
            return random.choice(available)

        enemy_style = self._infer_enemy_style_live(distance, enemy_airborne, attack_streak=0, confidence_score=1.0)

        return max(
            available,
            key=lambda name: (
                self.combo_scores.get(name, 0.0)
                + self.context_combo_scores[context].get(name, 0.0)
                + self.opponent_combo_scores[enemy_style].get(name, 0.0)
                + self._combo_reliability_bonus(name)
            ),
        )

    def live_strategy_profile(
        self,
        distance: float,
        enemy_airborne: bool,
        attack_streak: int,
        confidence_score: float,
    ) -> LiveStrategyProfile:
        if enemy_airborne or attack_streak >= 5:
            return LiveStrategyProfile("berserk", 4, 0.6, 0.65, True, 0.05)
        if distance > 0.45:
            return LiveStrategyProfile("chase", 5, 0.72, 0.78, True, 0.08)
        if confidence_score < 0.5:
            return LiveStrategyProfile("scramble", 6, 0.75, 0.82, False, 0.12)
        return LiveStrategyProfile("pressure", 5, 0.66, 0.72, distance < 0.3 or attack_streak >= 2, 0.18)

    def should_feint(self, frame_index: int, profile: LiveStrategyProfile) -> bool:
        if profile.feint_chance <= 0.0:
            return False
        if frame_index % 11 == 0 and profile.feint_chance >= 0.1:
            return True
        return random.random() < profile.feint_chance

    def recommend_punish_combo(
        self,
        distance: float,
        enemy_airborne: bool,
        attack_streak: int,
        confidence_score: float,
    ) -> str | None:
        enemy_style = self._infer_enemy_style_live(distance, enemy_airborne, attack_streak, confidence_score)
        style_scores = self.opponent_combo_scores[enemy_style]

        if enemy_style == "aerial":
            candidates = ["base_up_o", "base_up_p", "combo_3_w_o", "jump_in", "rush_mix", "rush_o6"]
        elif enemy_style == "zoning":
            candidates = ["base_forward_o5", "base_forward_p3", "rush_o6", "combo_4_a_o", "jump_in", "rush_mix", "guard_punish"]
        elif enemy_style == "rushdown":
            candidates = ["base_down_o", "base_down_p", "base_backward_o4", "combo_2_s_o", "low_mix", "rush_mix", "rush_o6", "guard_punish"]
        else:
            candidates = ["base_forward_o5", "base_forward_p3", "base_backward_p3", "rush_mix", "combo_4_a_o", "rush_o6", "low_mix", "guard_punish"]

        candidates.extend(self._generated_combo_candidates(distance=distance, enemy_airborne=enemy_airborne))
        candidates.extend(self._learned_combo_candidates(distance=distance, enemy_airborne=enemy_airborne))
        candidates = [name for name in candidates if name in self.combo_library]
        if not candidates:
            return None

        best_combo = max(candidates, key=lambda name: self.combo_scores[name] + style_scores[name])
        best_score = self.combo_scores[best_combo] + style_scores[best_combo]
        if self.combo_lockout_until.get(best_combo, 0) > self._tick:
            return None
        if best_score > 0.08 or attack_streak <= 1:
            return best_combo
        return None

    def record_attempt(self, combo_name: str, confidence_score: float, attack_streak: int) -> None:
        if combo_name not in self.combo_library:
            return
        self.pending_combo = combo_name
        self.pending_confidence = confidence_score
        self.pending_streak = attack_streak
        self.pending_combo_tick = self._tick
        self.combo_attempts[combo_name] += 1

    def update_feedback(self, confidence_score: float, attack_streak: int) -> None:
        if not self.pending_combo:
            return

        confidence_delta = confidence_score - self.pending_confidence
        streak_delta = float(attack_streak - self.pending_streak)
        reward = (confidence_delta * 2.5) + (streak_delta * 0.3)
        reward = max(-1.0, min(1.0, reward))

        current = self.combo_scores[self.pending_combo]
        self.combo_scores[self.pending_combo] = (0.9 * current) + (0.1 * reward)
        if reward >= 0.05:
            self.combo_successes[self.pending_combo] += 1
            self.combo_failure_streak[self.pending_combo] = 0
            learned_combo = self._learn_combo_from_recent_actions()
            if learned_combo is not None:
                current_learned = self.combo_scores.get(learned_combo, 0.0)
                self.combo_scores[learned_combo] = (0.8 * current_learned) + (0.2 * max(0.15, reward))
        else:
            self.combo_failure_streak[self.pending_combo] += 1
            if self.combo_failure_streak[self.pending_combo] >= 2:
                self.combo_lockout_until[self.pending_combo] = self._tick + 18
        self.pending_combo = None
        self._persist_state()

    def observe_step(
        self,
        packet: Dict[str, Any],
        action: FighterAction,
        attack_streak: int,
        combo_name: str | None = None,
    ) -> Dict[str, Any] | None:
        state = packet.get("state") or {}
        self._tick += 1
        detections = packet.get("detections") or []
        confidence_score = float(packet.get("confidence_score", state.get("confidence", 0.0)))
        distance = float(state.get("distance", 0.5))
        enemy = state.get("enemy") or {}
        enemy_airborne = bool(float(enemy.get("airborne", 0.0)) > 0.5)
        active = packet.get("state") is not None and len(detections) >= 2 and confidence_score >= self.active_confidence_threshold
        self._recent_actions.append(action)

        if active:
            self._episode_inactive_frames = 0
            if not self._episode_active:
                self._start_episode(packet)

            if combo_name is not None:
                self.record_attempt(combo_name, confidence_score, attack_streak)
            elif self.pending_combo is not None:
                self.update_feedback(confidence_score, attack_streak)

            self._episode_last_packet = packet

            self._episode_frame_index += 1
            self._episode_confidence_sum += confidence_score
            self._episode_distance_sum += distance
            self._episode_airborne_sum += 1.0 if enemy_airborne else 0.0
            if self._episode_prev_distance is not None and (self._episode_prev_distance - distance) > 0.045:
                self._episode_close_in_events += 1
            self._episode_prev_distance = distance
            self._episode_last_confidence = confidence_score
            self._episode_recent_confidences.append(confidence_score)
            self._episode_action_counts[action.name] += 1
            if combo_name:
                self._episode_combo_counts[combo_name] += 1

            if self._episode_first_confidence is None:
                self._episode_first_confidence = confidence_score

            if confidence_score >= self._episode_peak_confidence:
                self._episode_peak_confidence = confidence_score
                peak_path = self._save_snapshot(packet, "peak", self._episode_frame_index)
                if peak_path:
                    self._episode_peak_snapshot = peak_path

            if self._episode_frame_index == 1:
                first_path = self._save_snapshot(packet, "start", self._episode_frame_index)
                if first_path:
                    self._episode_first_snapshot = first_path

            if self._episode_frame_index % self.snapshot_stride == 0:
                snapshot_path = self._save_snapshot(packet, f"frame_{self._episode_frame_index:04d}", self._episode_frame_index)
                if snapshot_path:
                    self._episode_snapshot_paths.append(snapshot_path)
            if self._episode_frame_index % self.label_export_stride == 0:
                episode_id = self._episode_id
                if episode_id is not None:
                    self._label_exporter.export_frame(episode_id, self._episode_frame_index, packet)
            return None

        if self._episode_active:
            self._episode_inactive_frames += 1
            if self._episode_inactive_frames >= self.inactive_grace_frames:
                return self._finalize_episode(reason="inactive")

        return None

    def current_status(self) -> Dict[str, Any]:
        return {
            "episode_active": self._episode_active,
            "episode_id": self._episode_id,
            "frames": self._episode_frame_index,
            "inactive_frames": self._episode_inactive_frames,
            "last_summary": self._last_summary,
            "combo_scores": dict(self.combo_scores),
            "context_combo_scores": {name: dict(scores) for name, scores in self.context_combo_scores.items()},
            "opponent_combo_scores": {name: dict(scores) for name, scores in self.opponent_combo_scores.items()},
            "combo_attempts": dict(self.combo_attempts),
            "combo_successes": dict(self.combo_successes),
            "combo_failure_streak": dict(self.combo_failure_streak),
            "combo_lockout_until": dict(self.combo_lockout_until),
            "combo_library": {
                name: [action.name for action in sequence]
                for name, sequence in self.combo_library.items()
            },
            "match_combo_history": list(self._match_combo_history),
            "episode_combo_pack": list(self._episode_combo_pack),
            "learned_combo_count": self._learned_combo_count,
            "tick": self._tick,
        }

    def _start_episode(self, packet: Dict[str, Any]) -> None:
        self._episode_active = True
        self._episode_ended_recently = False
        self._episode_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
        self._episode_started_at = float(packet.get("timestamp", 0.0))
        self._episode_frame_index = 0
        self._episode_inactive_frames = 0
        self._episode_first_confidence = None
        self._episode_last_confidence = 0.0
        self._episode_peak_confidence = 0.0
        self._episode_confidence_sum = 0.0
        self._episode_distance_sum = 0.0
        self._episode_airborne_sum = 0.0
        self._episode_action_counts = Counter()
        self._episode_combo_counts = Counter()
        self._episode_snapshot_paths = []
        self._episode_peak_snapshot = None
        self._episode_first_snapshot = None
        self._episode_latest_snapshot = None
        self._episode_last_packet = None
        self._episode_recent_confidences = deque(maxlen=5)
        self._episode_close_in_events = 0
        self._episode_prev_distance = None
        self._episode_combo_pack = self._generate_match_combo_pack(self._episode_id)
        self._match_combo_history.append(
            {
                "episode_id": self._episode_id,
                "combos": {
                    name: [action.name for action in self.combo_library[name]]
                    for name in self._episode_combo_pack
                },
            }
        )
        self._match_combo_history = self._match_combo_history[-60:]
        LOGGER.info("Generated %d dynamic combos for match %s", len(self._episode_combo_pack), self._episode_id)
        self._persist_state()

    def _finalize_episode(self, reason: str) -> Dict[str, Any]:
        if not self._episode_active or self._episode_id is None:
            return {}

        self._episode_active = False
        ended_at = float(time.time())
        if self._episode_last_packet is not None:
            end_snapshot = self._save_snapshot(self._episode_last_packet, "end", self._episode_frame_index)
            if end_snapshot:
                self._episode_latest_snapshot = end_snapshot

        snapshot_paths: list[str] = []
        for path in [self._episode_first_snapshot, self._episode_peak_snapshot, self._episode_latest_snapshot]:
            if path and path not in snapshot_paths:
                snapshot_paths.append(path)
        for path in self._episode_snapshot_paths:
            if path not in snapshot_paths:
                snapshot_paths.append(path)

        frames = max(1, self._episode_frame_index)
        average_confidence = self._episode_confidence_sum / frames
        average_distance = self._episode_distance_sum / frames
        enemy_airborne_ratio = self._episode_airborne_sum / frames
        close_in_ratio = self._episode_close_in_events / frames
        first_confidence = self._episode_first_confidence or self._episode_last_confidence
        confidence_trend = self._episode_last_confidence - first_confidence
        dominant_action = self._episode_action_counts.most_common(1)[0][0] if self._episode_action_counts else None
        dominant_combo = self._episode_combo_counts.most_common(1)[0][0] if self._episode_combo_counts else None
        strategy_bucket = self._infer_strategy_bucket(average_distance, enemy_airborne_ratio)
        enemy_style = self._infer_enemy_style_episode(average_distance, enemy_airborne_ratio, close_in_ratio)

        summary = FightSummary(
            episode_id=self._episode_id,
            started_at=self._episode_started_at,
            ended_at=ended_at,
            duration_seconds=max(0.0, ended_at - self._episode_started_at),
            frames=frames,
            snapshot_count=len(snapshot_paths),
            average_confidence=average_confidence,
            confidence_trend=confidence_trend,
            average_distance=average_distance,
            enemy_airborne_ratio=enemy_airborne_ratio,
            dominant_action=dominant_action,
            dominant_combo=dominant_combo,
            strategy_bucket=strategy_bucket,
            screenshot_paths=snapshot_paths,
        )

        summary_dict = asdict(summary)
        summary_dict["reason"] = reason
        summary_dict["confidence_window"] = list(self._episode_recent_confidences)
        summary_dict["enemy_style"] = enemy_style
        summary_dict["close_in_ratio"] = close_in_ratio
        summary_dict["combo_pack"] = {
            name: [action.name for action in self.combo_library.get(name, [])]
            for name in self._episode_combo_pack
        }
        self._last_summary = summary_dict
        self._write_episode_summary(summary_dict)
        self._reinforce_from_summary(summary, enemy_style)
        self._episode_ended_recently = True
        self._persist_state()
        return summary_dict

    def _reinforce_from_summary(self, summary: FightSummary, enemy_style: str) -> None:
        reward = (summary.confidence_trend * 2.5) + max(0.0, 0.35 - summary.average_distance) * 0.9
        reward += summary.enemy_airborne_ratio * 0.5
        reward = max(-1.0, min(1.0, reward))

        if summary.dominant_combo:
            self._update_combo_score(summary.dominant_combo, reward)

        context_scores = self.context_combo_scores[summary.strategy_bucket]
        if summary.dominant_combo:
            context_scores[summary.dominant_combo] = (0.85 * context_scores[summary.dominant_combo]) + (0.15 * reward)

        style_scores = self.opponent_combo_scores[enemy_style]
        if summary.dominant_combo:
            style_scores[summary.dominant_combo] = (0.82 * style_scores[summary.dominant_combo]) + (0.18 * reward)

        if summary.strategy_bucket == "anti_air":
            self._update_combo_score("jump_in", reward * 0.8)
        elif summary.strategy_bucket == "closing_pressure":
            self._update_combo_score("rush_o6", reward * 0.8)
        else:
            self._update_combo_score("rush_mix", reward * 0.8)

        punish_choice = self.recommend_punish_combo(
            distance=summary.average_distance,
            enemy_airborne=summary.enemy_airborne_ratio > 0.25,
            attack_streak=0,
            confidence_score=summary.average_confidence,
        )
        if punish_choice:
            style_scores[punish_choice] = (0.9 * style_scores[punish_choice]) + (0.1 * reward)

    def _update_combo_score(self, combo_name: str, reward: float) -> None:
        current = self.combo_scores[combo_name]
        self.combo_scores[combo_name] = (0.88 * current) + (0.12 * reward)

    def _combo_reliability_bonus(self, combo_name: str) -> float:
        attempts = max(1, self.combo_attempts.get(combo_name, 0))
        successes = self.combo_successes.get(combo_name, 0)
        success_rate = successes / attempts
        penalty = 0.05 * min(4, self.combo_failure_streak.get(combo_name, 0))
        return (success_rate - 0.5) * 0.35 - penalty

    def _infer_strategy_bucket(self, average_distance: float, enemy_airborne_ratio: float) -> str:
        if enemy_airborne_ratio > 0.25:
            return "anti_air"
        if average_distance > 0.35:
            return "closing_pressure"
        return "close_pressure"

    def _infer_enemy_style_episode(self, average_distance: float, enemy_airborne_ratio: float, close_in_ratio: float) -> str:
        if enemy_airborne_ratio > 0.32:
            return "aerial"
        if average_distance > 0.42 and close_in_ratio < 0.22:
            return "zoning"
        if average_distance < 0.26 or close_in_ratio > 0.35:
            return "rushdown"
        return "scramble"

    def _infer_enemy_style_live(
        self,
        distance: float,
        enemy_airborne: bool,
        attack_streak: int,
        confidence_score: float,
    ) -> str:
        if enemy_airborne:
            return "aerial"
        if distance > 0.42 and confidence_score > 0.6:
            return "zoning"
        if distance < 0.27 or attack_streak <= 1:
            return "rushdown"
        return "scramble"

    def _save_snapshot(self, packet: Dict[str, Any], label: str, frame_index: int) -> str | None:
        encoded = packet.get("live_frame_jpeg")
        if not encoded or self._episode_id is None:
            return None

        image_bytes = base64.b64decode(encoded)
        episode_folder = self.episode_dir / self._episode_id
        episode_folder.mkdir(parents=True, exist_ok=True)
        snapshot_path = episode_folder / f"{label}_{frame_index:04d}.jpg"
        snapshot_path.write_bytes(image_bytes)
        self._episode_latest_snapshot = str(snapshot_path)
        return str(snapshot_path)

    def _write_episode_summary(self, summary: Dict[str, Any]) -> None:
        if self._episode_id is None:
            return

        episode_folder = self.episode_dir / self._episode_id
        episode_folder.mkdir(parents=True, exist_ok=True)
        summary_path = episode_folder / "summary.json"
        summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

        history_path = self.memory_dir / "episode_history.jsonl"
        with history_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(summary) + "\n")

    def _persist_state(self) -> None:
        serialized_library = {
            name: [action.name for action in sequence]
            for name, sequence in self.combo_library.items()
        }
        state = {
            "combo_library": serialized_library,
            "combo_scores": self.combo_scores,
            "context_combo_scores": self.context_combo_scores,
            "opponent_combo_scores": self.opponent_combo_scores,
            "combo_attempts": self.combo_attempts,
            "combo_successes": self.combo_successes,
            "combo_failure_streak": self.combo_failure_streak,
            "combo_lockout_until": self.combo_lockout_until,
            "tick": self._tick,
            "last_summary": self._last_summary,
            "match_combo_history": self._match_combo_history,
            "learned_combo_count": self._learned_combo_count,
        }
        self.state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")

    def _load_state(self) -> None:
        if not self.state_path.exists():
            return

        try:
            payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        except Exception:
            LOGGER.warning("Could not load saved fight memory from %s", self.state_path)
            return

        loaded_combo_library = payload.get("combo_library") or {}
        if isinstance(loaded_combo_library, dict):
            for combo_name, sequence_names in loaded_combo_library.items():
                if not isinstance(sequence_names, list):
                    continue
                if combo_name in DEFAULT_COMBO_LIBRARY:
                    continue
                sequence: list[FighterAction] = []
                for action_name in sequence_names:
                    try:
                        sequence.append(FighterAction[str(action_name)])
                    except Exception:
                        sequence = []
                        break
                if sequence:
                    self._register_combo(combo_name, sequence)

        loaded_combo_scores = payload.get("combo_scores") or {}
        for name, score in loaded_combo_scores.items():
            self.combo_scores.setdefault(name, 0.0)
            self.combo_scores[name] = float(score)

        loaded_context_scores = payload.get("context_combo_scores") or {}
        for context_name, scores in loaded_context_scores.items():
            if context_name not in self.context_combo_scores:
                continue
            for name, score in scores.items():
                if name in self.context_combo_scores[context_name]:
                    self.context_combo_scores[context_name][name] = float(score)

        loaded_opponent_scores = payload.get("opponent_combo_scores") or {}
        for style_name, scores in loaded_opponent_scores.items():
            if style_name not in self.opponent_combo_scores:
                continue
            for name, score in scores.items():
                if name in self.opponent_combo_scores[style_name]:
                    self.opponent_combo_scores[style_name][name] = float(score)

        loaded_attempts = payload.get("combo_attempts") or {}
        for name, value in loaded_attempts.items():
            self.combo_attempts.setdefault(name, 0)
            self.combo_attempts[name] = int(value)

        loaded_successes = payload.get("combo_successes") or {}
        for name, value in loaded_successes.items():
            self.combo_successes.setdefault(name, 0)
            self.combo_successes[name] = int(value)

        loaded_failure_streak = payload.get("combo_failure_streak") or {}
        for name, value in loaded_failure_streak.items():
            self.combo_failure_streak.setdefault(name, 0)
            self.combo_failure_streak[name] = int(value)

        loaded_lockouts = payload.get("combo_lockout_until") or {}
        for name, value in loaded_lockouts.items():
            self.combo_lockout_until.setdefault(name, 0)
            self.combo_lockout_until[name] = int(value)

        self._tick = int(payload.get("tick", 0))

        self._last_summary = payload.get("last_summary")
        history = payload.get("match_combo_history")
        if isinstance(history, list):
            self._match_combo_history = history[-60:]

        self._learned_combo_count = int(payload.get("learned_combo_count", 0))
