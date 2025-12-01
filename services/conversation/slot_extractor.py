import json
from typing import Dict, Tuple

from services.conversation.slots import SlotState

SLOT_EXTRACTION_SYSTEM_PROMPT = (
    "You are a structured appointment assistant for Precision Pain and Spine "
    "Institute. Extract patient details and respond conversationally. When "
    "values are missing, ask concise follow-up questions. If the user asks a "
    "general clinic question, answer briefly but still remind them you can "
    "schedule appointments."
)


def build_slot_messages(transcript: str, current_state: SlotState):
    known = {k: v for k, v in current_state.items() if v}
    return [
        {
            "role": "system",
            "content": SLOT_EXTRACTION_SYSTEM_PROMPT,
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "known_slots": known,
                    "utterance": transcript,
                }
            ),
        },
    ]


def parse_slot_response(payload: str) -> Tuple[Dict[str, str], str]:
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return {}, ""

    slots: Dict[str, str] = {}
    for key in SlotState().__dict__.keys():
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            slots[key] = value.strip()
    reply = data.get("reply") or ""
    return slots, reply


def extract_slot_values(
    openai_client,
    model: str,
    transcript: str,
    current_state: Dict[str, str],
):
    messages = build_slot_messages(transcript, current_state)
    completion = openai_client.chat.completions.create(
        model=model,
        messages=messages,
        response_format={"type": "json_object"},
    )
    slots, reply = parse_slot_response(completion.choices[0].message.content or "{}")
    updates = {key: value for key, value in slots.items() if value and value != current_state.get(key)}
    return updates, reply

