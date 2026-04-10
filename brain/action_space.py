from __future__ import annotations

from enum import IntEnum


class FighterAction(IntEnum):
    IDLE = 0
    MOVE_FORWARD = 1
    MOVE_BACKWARD = 2
    JUMP = 3
    CROUCH = 4
    LIGHT_ATTACK = 5
    HEAVY_ATTACK = 6
    SPECIAL = 7
