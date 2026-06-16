from brain.action_space import FighterAction
from brain.live_env import LiveAutonomousFighterEnv, perception_to_env_state


def test_perception_to_env_state_mapping():
    packet = {
        "state": {
            "dx": 0.25,
            "dy": -0.1,
            "distance": 0.2,
            "confidence": 0.92,
            "player_health": 0.84,
            "enemy_health": 0.65,
            "shadow_meter": 1.0,
            "shadow_full": True,
            "player": {"airborne": 1.0},
            "enemy": {"airborne": 0.0},
        }
    }

    state = perception_to_env_state(packet)

    assert state["dx"] == 0.25
    assert state["distance"] == 0.2
    assert state["player_airborne"] == 1.0
    assert state["enemy_airborne"] == 0.0
    assert state["confidence"] == 0.92
    assert state["player_health"] == 0.84
    assert state["enemy_health"] == 0.65
    assert state["shadow_meter"] == 1.0
    assert state["shadow_full"] is True


def test_live_env_estimates_damage_and_combo_from_health_deltas():
    packets = [
        {
            "state": {
                "dx": 0.1,
                "dy": 0.0,
                "distance": 0.2,
                "confidence": 0.9,
                "player_health": 1.0,
                "enemy_health": 1.0,
                "player": {"airborne": 0.0},
                "enemy": {"airborne": 0.0},
            }
        },
        {
            "state": {
                "dx": 0.1,
                "dy": 0.0,
                "distance": 0.2,
                "confidence": 0.9,
                "player_health": 0.97,
                "enemy_health": 0.95,
                "player": {"airborne": 0.0},
                "enemy": {"airborne": 0.0},
            }
        },
        {
            "state": {
                "dx": 0.1,
                "dy": 0.0,
                "distance": 0.2,
                "confidence": 0.9,
                "player_health": 0.97,
                "enemy_health": 0.90,
                "player": {"airborne": 0.0},
                "enemy": {"airborne": 0.0},
            }
        },
    ]

    last_packet = packets[-1]

    def _step():
        nonlocal last_packet
        if packets:
            last_packet = packets.pop(0)
            return last_packet
        return last_packet

    env = LiveAutonomousFighterEnv(perception_step=_step, action_runner=lambda _a: None)

    first = env._state_provider()
    second = env._state_provider()
    third = env._state_provider()

    assert first["dealt_damage"] == 0.0
    assert first["received_damage"] == 0.0
    assert second["dealt_damage"] > 0.0
    assert second["received_damage"] > 0.0
    assert third["dealt_damage"] > 0.0
    assert third["combo_hits"] >= second["combo_hits"]

    env._action_executor(FighterAction.LIGHT_ATTACK)
