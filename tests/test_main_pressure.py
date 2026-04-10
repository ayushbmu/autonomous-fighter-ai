from brain.action_space import FighterAction
from main import KEY_BINDINGS, execute_berserk_pressure


class DummyExecutor:
    def __init__(self) -> None:
        self.calls: list[int] = []

    def tap_key(self, key: int, _min_delay_ms: int, _max_delay_ms: int) -> None:
        self.calls.append(key)


def test_berserk_pressure_pushes_forward_then_attacks():
    executor = DummyExecutor()

    action = execute_berserk_pressure(
        executor,
        frame_index=2,
        distance=0.5,
        enemy_airborne=False,
        attack_streak=0,
        min_delay_ms=10,
        max_delay_ms=20,
    )

    assert action in {FighterAction.LIGHT_ATTACK, FighterAction.HEAVY_ATTACK}
    assert executor.calls[0] == KEY_BINDINGS[FighterAction.MOVE_FORWARD]
    assert executor.calls[1] == KEY_BINDINGS[action]
