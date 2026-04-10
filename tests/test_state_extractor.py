from perception.detector import Detection
from perception.state_extractor import assign_player_enemy


def test_assign_player_enemy_prefers_role_labels():
    detections = [
        Detection(label="fighter_enemy", confidence=0.82, x1=900, y1=120, x2=1040, y2=540),
        Detection(label="fighter_player", confidence=0.78, x1=180, y1=110, x2=340, y2=520),
    ]

    player, enemy = assign_player_enemy(detections)

    assert player is not None
    assert enemy is not None
    assert player.label == "fighter_player"
    assert enemy.label == "fighter_enemy"
