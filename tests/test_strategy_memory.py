import base64

from brain.action_space import FighterAction
from brain.strategy_memory import AdaptiveComboLearner


def _active_packet(confidence: float = 0.9, distance: float = 0.2, enemy_airborne: float = 1.0):
    return {
        "timestamp": 1000.0,
        "confidence_score": confidence,
        "detections": [{"label": "player"}, {"label": "enemy"}],
        "state": {
            "confidence": confidence,
            "distance": distance,
            "enemy": {"airborne": enemy_airborne},
            "player": {"airborne": 0.0},
        },
        "live_frame_jpeg": base64.b64encode(b"fake-jpeg-data").decode("ascii"),
    }


def _inactive_packet():
    return {
        "timestamp": 2000.0,
        "confidence_score": 0.0,
        "detections": [],
        "state": None,
        "live_frame_jpeg": base64.b64encode(b"fake-jpeg-data").decode("ascii"),
    }


def test_episode_tracker_saves_summary_and_snapshots(tmp_path):
    learner = AdaptiveComboLearner(tmp_path)
    learner.exploration_rate = 0.0
    learner.snapshot_stride = 1
    learner.inactive_grace_frames = 2

    first_summary = learner.observe_step(
        _active_packet(),
        FighterAction.LIGHT_ATTACK,
        attack_streak=1,
        combo_name="jump_in",
    )
    assert first_summary is None

    learner.observe_step(
        _active_packet(confidence=0.95, distance=0.18, enemy_airborne=1.0),
        FighterAction.HEAVY_ATTACK,
        attack_streak=2,
        combo_name="jump_in",
    )

    summary = None
    for _ in range(3):
        maybe_summary = learner.observe_step(
            _inactive_packet(),
            FighterAction.IDLE,
            attack_streak=0,
            combo_name=None,
        )
        if maybe_summary is not None:
            summary = maybe_summary
            break

    assert summary is not None
    assert summary["frames"] == 2
    assert summary["strategy_bucket"] == "anti_air"
    assert summary["enemy_style"] == "aerial"
    assert summary["snapshot_count"] >= 1
    assert summary["screenshot_paths"]

    summary_path = tmp_path / "episodes" / summary["episode_id"] / "summary.json"
    assert summary_path.exists()

    history_path = tmp_path / "episode_history.jsonl"
    assert history_path.exists()
    assert learner.combo_scores["jump_in"] != 0.0


def test_choose_combo_uses_learned_scores(tmp_path):
    learner = AdaptiveComboLearner(tmp_path)
    learner.exploration_rate = 0.0
    learner.combo_scores["rush_mix"] = -0.5
    learner.combo_scores["jump_in"] = 0.75
    learner.context_combo_scores["anti_air"]["jump_in"] = 1.0

    assert learner.choose_combo(distance=0.2, enemy_airborne=True) == "jump_in"


def test_recommend_punish_combo_uses_opponent_style_memory(tmp_path):
    learner = AdaptiveComboLearner(tmp_path)
    learner.opponent_combo_scores["zoning"]["rush_o6"] = 1.2
    learner.combo_scores["rush_o6"] = 0.2

    combo = learner.recommend_punish_combo(
        distance=0.55,
        enemy_airborne=False,
        attack_streak=3,
        confidence_score=0.9,
    )

    assert combo == "rush_o6"


def test_live_strategy_profile_switches_modes(tmp_path):
    learner = AdaptiveComboLearner(tmp_path)

    berserk = learner.live_strategy_profile(
        distance=0.2,
        enemy_airborne=True,
        attack_streak=1,
        confidence_score=0.9,
    )
    assert berserk.aggression_mode == "berserk"
    assert berserk.combo_interval <= 4

    chase = learner.live_strategy_profile(
        distance=0.6,
        enemy_airborne=False,
        attack_streak=0,
        confidence_score=0.7,
    )
    assert chase.aggression_mode == "chase"
    assert chase.force_pressure is True


def test_combo_lockout_after_repeated_failures(tmp_path):
    learner = AdaptiveComboLearner(tmp_path)
    learner._tick = 10

    learner.record_attempt("rush_o6", confidence_score=0.8, attack_streak=1)
    learner.update_feedback(confidence_score=0.2, attack_streak=0)
    learner.record_attempt("rush_o6", confidence_score=0.8, attack_streak=1)
    learner.update_feedback(confidence_score=0.1, attack_streak=0)

    assert learner.combo_failure_streak["rush_o6"] >= 2
    assert learner.combo_lockout_until["rush_o6"] > learner._tick


def test_episode_exports_player_enemy_labels(tmp_path):
    learner = AdaptiveComboLearner(tmp_path)
    learner.exploration_rate = 0.0
    learner.snapshot_stride = 100
    learner.label_export_stride = 1
    learner.inactive_grace_frames = 2

    packet = _active_packet()
    packet["frame_shape"] = [720, 1280, 3]
    packet["detections"] = [
        {"label": "fighter_player", "confidence": 0.91, "x1": 100, "y1": 200, "x2": 250, "y2": 520},
        {"label": "fighter_enemy", "confidence": 0.93, "x1": 820, "y1": 180, "x2": 980, "y2": 515},
    ]

    learner.observe_step(packet, FighterAction.LIGHT_ATTACK, attack_streak=1, combo_name="rush_mix")
    learner.observe_step(packet, FighterAction.LIGHT_ATTACK, attack_streak=2, combo_name="rush_mix")

    for _ in range(3):
        summary = learner.observe_step(_inactive_packet(), FighterAction.IDLE, attack_streak=0, combo_name=None)
        if summary is not None:
            break

    label_dir = tmp_path / "labels" / summary["episode_id"]
    assert (label_dir / "images" / "frame_0001.jpg").exists()
    label_text = (label_dir / "labels" / "frame_0001.txt").read_text(encoding="utf-8")
    assert label_text.count("\n") >= 2
    assert label_text.startswith("0 ")


def test_requested_combo_shortcuts_exist(tmp_path):
    learner = AdaptiveComboLearner(tmp_path)

    combo_2 = learner.combo_sequence("combo_2_s_o")
    combo_3 = learner.combo_sequence("combo_3_w_o")
    combo_4 = learner.combo_sequence("combo_4_a_o")

    assert combo_2 == [FighterAction.CROUCH, FighterAction.LIGHT_ATTACK]
    assert combo_3 == [FighterAction.JUMP, FighterAction.LIGHT_ATTACK]
    assert combo_4 == [FighterAction.MOVE_BACKWARD, FighterAction.LIGHT_ATTACK]


def test_dynamic_combo_pack_generated_per_match_and_saved(tmp_path):
    learner = AdaptiveComboLearner(tmp_path)

    learner.observe_step(
        _active_packet(),
        FighterAction.LIGHT_ATTACK,
        attack_streak=1,
        combo_name="rush_mix",
    )

    status = learner.current_status()
    combo_pack = status["episode_combo_pack"]
    history = status["match_combo_history"]

    assert len(combo_pack) >= 3
    assert len(history) >= 1
    for combo_name in combo_pack:
        assert combo_name.startswith("match_")
        sequence = learner.combo_sequence(combo_name)
        assert len(sequence) >= 4

    reloaded = AdaptiveComboLearner(tmp_path)
    reloaded_history = reloaded.current_status()["match_combo_history"]
    assert len(reloaded_history) >= 1


def test_successful_feedback_creates_learned_combo(tmp_path):
    learner = AdaptiveComboLearner(tmp_path)

    packet = _active_packet(confidence=0.85, distance=0.2, enemy_airborne=0.0)
    learner.observe_step(packet, FighterAction.MOVE_FORWARD, attack_streak=0, combo_name=None)
    learner.observe_step(packet, FighterAction.LIGHT_ATTACK, attack_streak=1, combo_name="rush_mix")
    learner.observe_step(packet, FighterAction.HEAVY_ATTACK, attack_streak=2, combo_name=None)
    learner.observe_step(packet, FighterAction.LIGHT_ATTACK, attack_streak=3, combo_name="rush_mix")

    learned = [name for name in learner.combo_library if name.startswith("learned_")]
    assert learned
    assert learner.current_status()["learned_combo_count"] >= 1


def test_choose_combo_can_use_learned_combo(tmp_path):
    learner = AdaptiveComboLearner(tmp_path)
    learner.exploration_rate = 0.0

    learned_name = "learned_move_forward_light_attack_heavy_attack_light_attack"
    learner._register_combo(
        learned_name,
        [
            FighterAction.MOVE_FORWARD,
            FighterAction.LIGHT_ATTACK,
            FighterAction.HEAVY_ATTACK,
            FighterAction.LIGHT_ATTACK,
        ],
    )
    learner.combo_scores[learned_name] = 1.5

    choice = learner.choose_combo(distance=0.45, enemy_airborne=False)
    assert choice == learned_name


def test_requested_base_combos_exist(tmp_path):
    learner = AdaptiveComboLearner(tmp_path)

    assert learner.combo_sequence("base_forward_o5") == [
        FighterAction.MOVE_FORWARD,
        FighterAction.LIGHT_ATTACK,
        FighterAction.LIGHT_ATTACK,
        FighterAction.LIGHT_ATTACK,
        FighterAction.LIGHT_ATTACK,
        FighterAction.LIGHT_ATTACK,
    ]
    assert learner.combo_sequence("base_backward_o4") == [
        FighterAction.MOVE_BACKWARD,
        FighterAction.LIGHT_ATTACK,
        FighterAction.LIGHT_ATTACK,
        FighterAction.LIGHT_ATTACK,
        FighterAction.LIGHT_ATTACK,
    ]
    assert learner.combo_sequence("base_down_o") == [FighterAction.CROUCH, FighterAction.LIGHT_ATTACK]
    assert learner.combo_sequence("base_up_o") == [FighterAction.JUMP, FighterAction.LIGHT_ATTACK]
    assert learner.combo_sequence("base_up_p") == [FighterAction.JUMP, FighterAction.HEAVY_ATTACK]
    assert learner.combo_sequence("base_down_p") == [FighterAction.CROUCH, FighterAction.HEAVY_ATTACK]
    assert learner.combo_sequence("base_forward_p3") == [
        FighterAction.MOVE_FORWARD,
        FighterAction.HEAVY_ATTACK,
        FighterAction.HEAVY_ATTACK,
        FighterAction.HEAVY_ATTACK,
    ]
    assert learner.combo_sequence("base_backward_p3") == [
        FighterAction.MOVE_BACKWARD,
        FighterAction.HEAVY_ATTACK,
        FighterAction.HEAVY_ATTACK,
        FighterAction.HEAVY_ATTACK,
    ]
