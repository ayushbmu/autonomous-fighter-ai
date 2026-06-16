from brain.action_space import FighterAction
from main import KEY_BINDINGS, SHADOW_SPECIAL_KEY, execute_action, execute_berserk_pressure, should_block


class DummyExecutor:
    def __init__(self) -> None:
        self.calls: list[int] = []
        self.pressed: list[int] = []
        self.released: list[int] = []

    def tap_key(self, key: int, _min_delay_ms: int, _max_delay_ms: int) -> None:
        self.calls.append(key)

    def press_key(self, key: int) -> None:
        self.pressed.append(key)

    def release_key(self, key: int) -> None:
        self.released.append(key)


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


def test_should_block_when_close_and_low_confidence():
    assert should_block(
        distance=0.22,
        enemy_airborne=False,
        confidence_score=0.55,
        attack_streak=3,
        frame_index=5,
    )


def test_should_not_block_against_airborne_enemy():
    assert not should_block(
        distance=0.10,
        enemy_airborne=True,
        confidence_score=0.20,
        attack_streak=0,
        frame_index=2,
    )


def test_execute_special_uses_knife_key_when_shadow_not_full():
    executor = DummyExecutor()

    execute_action(
        executor,
        FighterAction.SPECIAL,
        min_delay_ms=10,
        max_delay_ms=20,
        shadow_meter_full=False,
    )

    assert executor.calls == [KEY_BINDINGS[FighterAction.SPECIAL]]
    assert not executor.pressed
    assert not executor.released


def test_execute_special_uses_forward_plus_l_when_shadow_full():
    executor = DummyExecutor()

    execute_action(
        executor,
        FighterAction.SPECIAL,
        min_delay_ms=10,
        max_delay_ms=20,
        shadow_meter_full=True,
    )

    assert executor.calls == [SHADOW_SPECIAL_KEY]
    assert executor.pressed == [KEY_BINDINGS[FighterAction.MOVE_FORWARD]]
    assert executor.released == [KEY_BINDINGS[FighterAction.MOVE_FORWARD]]
