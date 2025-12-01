import json
import logging
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import Dict, Optional

try:
    import redis  # type: ignore
except ImportError:  # pragma: no cover
    redis = None

logger = logging.getLogger(__name__)


@dataclass
class SlotState:
    patient_name: Optional[str] = None
    appointment_reason: Optional[str] = None
    preferred_date: Optional[str] = None
    preferred_time: Optional[str] = None
    doctor_preference: Optional[str] = None

    def to_dict(self) -> Dict[str, Optional[str]]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Optional[str]]) -> "SlotState":
        return cls(
            patient_name=data.get("patient_name"),
            appointment_reason=data.get("appointment_reason"),
            preferred_date=data.get("preferred_date"),
            preferred_time=data.get("preferred_time"),
            doctor_preference=data.get("doctor_preference"),
        )


DEFAULT_STATE = SlotState()
SLOT_TTL_SECONDS = 60 * 60  # 1 hour


class SlotManager:
    def __init__(self):
        redis_url = os.getenv("REDIS_URL")
        self._client = None
        if redis_url and redis is not None:
            try:
                self._client = redis.from_url(redis_url, decode_responses=True)
                logger.info("SlotManager using Redis backend")
            except Exception as exc:
                logger.warning("Failed to connect to Redis: %s. Falling back to memory.", exc)
                self._client = None
        elif redis_url and redis is None:
            logger.warning("redis package not installed; falling back to in-memory slot storage.")
        self._memory_store: Dict[str, Dict[str, object]] = {}

    def _memory_cleanup(self):
        now = datetime.utcnow()
        expired_keys = [
            key
            for key, entry in self._memory_store.items()
            if entry["expires_at"] < now
        ]
        for key in expired_keys:
            self._memory_store.pop(key, None)

    def _memory_get(self, call_sid: str) -> SlotState:
        self._memory_cleanup()
        entry = self._memory_store.get(call_sid)
        if not entry:
            return SlotState()
        return SlotState.from_dict(entry["state"])

    def _memory_set(self, call_sid: str, state: SlotState):
        self._memory_store[call_sid] = {
            "state": state.to_dict(),
            "expires_at": datetime.utcnow() + timedelta(seconds=SLOT_TTL_SECONDS),
        }

    def _memory_clear(self, call_sid: str):
        self._memory_store.pop(call_sid, None)

    def get(self, call_sid: str) -> SlotState:
        if self._client:
            raw = self._client.get(self._redis_key(call_sid))
            if raw:
                try:
                    data = json.loads(raw)
                    return SlotState.from_dict(data)
                except json.JSONDecodeError:
                    logger.warning("Corrupted slot state for %s", call_sid)
        return self._memory_get(call_sid)

    def update(self, call_sid: str, updates: Dict[str, Optional[str]]) -> SlotState:
        state = self.get(call_sid)
        for key, value in updates.items():
            if hasattr(state, key) and value:
                setattr(state, key, value.strip())
        self._persist(call_sid, state)
        return state

    def clear(self, call_sid: str):
        if self._client:
            self._client.delete(self._redis_key(call_sid))
        self._memory_clear(call_sid)

    def _persist(self, call_sid: str, state: SlotState):
        if self._client:
            self._client.setex(
                self._redis_key(call_sid),
                SLOT_TTL_SECONDS,
                json.dumps(state.to_dict()),
            )
        self._memory_set(call_sid, state)

    @staticmethod
    def _redis_key(call_sid: str) -> str:
        return f"session:{call_sid}"


def slots_complete(state: SlotState) -> bool:
    return all(
        [
            state.patient_name,
            state.appointment_reason,
            state.preferred_date,
            state.preferred_time,
        ]
    )

