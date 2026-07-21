from enum import IntEnum


class TaskType(IntEnum):
    POLYSPACE_CONFIRMATION = 1


class State(IntEnum):
    PENDING = 0
    RUNNING = 1
    COMPLETED = 2
    FAILED = 3


STATE_LABELS = {
    State.PENDING: "pending",
    State.RUNNING: "running",
    State.COMPLETED: "completed",
    State.FAILED: "failed",
}


def state_label(value: int) -> str:
    try:
        return STATE_LABELS[State(value)]
    except (ValueError, KeyError):
        return "unknown"

