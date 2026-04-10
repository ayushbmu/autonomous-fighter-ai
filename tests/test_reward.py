from brain.reward import aggressive_reward


def test_aggressive_reward_prefers_forward_pressure():
    forward = aggressive_reward(
        dealt_damage=5,
        received_damage=1,
        combo_hits=2,
        moved_forward=True,
        moved_backward=False,
        idle_frames=0,
        distance_to_enemy=0.2,
    )

    backward = aggressive_reward(
        dealt_damage=5,
        received_damage=1,
        combo_hits=2,
        moved_forward=False,
        moved_backward=True,
        idle_frames=0,
        distance_to_enemy=0.2,
    )

    assert forward > backward


def test_aggressive_reward_rewards_blocking_under_pressure():
    blocked = aggressive_reward(
        dealt_damage=0,
        received_damage=0,
        combo_hits=0,
        moved_forward=False,
        moved_backward=True,
        idle_frames=0,
        distance_to_enemy=0.15,
        blocked=True,
        under_pressure=True,
    )

    unblocked = aggressive_reward(
        dealt_damage=0,
        received_damage=0,
        combo_hits=0,
        moved_forward=False,
        moved_backward=False,
        idle_frames=0,
        distance_to_enemy=0.15,
        blocked=False,
        under_pressure=True,
    )

    assert blocked > unblocked
