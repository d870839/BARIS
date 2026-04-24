from __future__ import annotations

import json
from typing import Any

# Client -> Server message types
JOIN = "join"
CHOOSE_SIDE = "choose_side"
READY = "ready"
UNREADY = "unready"
END_TURN = "end_turn"
CHOOSE_ARCHITECTURE = "choose_architecture"
SCRUB_SCHEDULED = "scrub_scheduled"
START_TRAINING = "start_training"
CANCEL_TRAINING = "cancel_training"
RECRUIT_GROUP = "recruit_group"
REQUEST_INTEL = "request_intel"

# Server -> Client message types
JOINED = "joined"
STATE = "state"
ERROR = "error"


def encode(msg_type: str, **fields: Any) -> str:
    payload: dict[str, Any] = {"type": msg_type, **fields}
    return json.dumps(payload)


def decode(raw: str) -> dict[str, Any]:
    msg = json.loads(raw)
    if not isinstance(msg, dict) or "type" not in msg:
        raise ValueError(f"malformed message: {raw!r}")
    return msg
