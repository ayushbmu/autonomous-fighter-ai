from brain.live_env import perception_to_env_state


def test_perception_to_env_state_mapping():
    packet = {
        "state": {
            "dx": 0.25,
            "dy": -0.1,
            "distance": 0.2,
            "confidence": 0.92,
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
