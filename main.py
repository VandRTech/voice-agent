import json
import logging
import os
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

import requests
from fastapi import FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse
from openai import OpenAI
from twilio.request_validator import RequestValidator
from twilio.twiml.voice_response import VoiceResponse

from services.audio.transcription import transcribe_audio
from services.conversation.slots import SlotManager, SlotState, slots_complete
from services.conversation.slot_extractor import extract_slot_values
from services.db import CallLogRepository
from services.rag.prompts import (
    FALLBACK_SYSTEM_PROMPT,
    PROMPT_TEMPLATE,
    RETRIEVAL_SYSTEM_PROMPT,
)
from services.rag.retriever import ClinicRetriever, RetrievedDocument, format_docs_for_prompt
from services.speech.elevenlabs_service import ElevenLabsService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

FACILITY_NAME = os.getenv("FACILITY_NAME", "Precision Pain and Spine Institute")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "http://localhost:8000")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_SLOT_MODEL = os.getenv("OPENAI_SLOT_MODEL", OPENAI_MODEL)

if not OPENAI_API_KEY:
    raise EnvironmentError("Please set OPENAI_API_KEY in your environment.")
if not TWILIO_AUTH_TOKEN:
    raise EnvironmentError("Please set TWILIO_AUTH_TOKEN in your environment.")

openai_client = OpenAI(api_key=OPENAI_API_KEY)
twilio_validator = RequestValidator(TWILIO_AUTH_TOKEN)
retriever = ClinicRetriever()
elevenlabs_service = ElevenLabsService()
call_logs = CallLogRepository()
call_sequences = defaultdict(int)
slot_manager = SlotManager()

SLOT_KEYS = [
    "patient_name",
    "appointment_reason",
    "preferred_date",
    "preferred_time",
    "doctor_preference",
]
SLOT_LABELS = {
    "patient_name": "your full name",
    "appointment_reason": "the reason for your visit",
    "preferred_date": "the date you prefer",
    "preferred_time": "the time you prefer",
    "doctor_preference": "any doctor preference",
}
RAG_THRESHOLD = 0.78


@app.post("/voice")
async def voice_entry():
    logger.info("Incoming call hit /voice")
    response = VoiceResponse()
    response.say(
        f"Thanks for calling {FACILITY_NAME}. After the beep, let me know how I can help.",
        voice="alice",
        language="en-IN",
    )
    callback_url = f"{PUBLIC_BASE_URL}/recording_callback"
    response.record(
        action=callback_url,
        method="POST",
        play_beep=True,
        max_length=20,
        recording_status_callback=callback_url,
        recording_status_callback_method="POST",
        trim="do-not-trim",
    )
    return Response(str(response), media_type="application/xml")


@app.post("/recording_callback")
async def recording_callback(
    request: Request,
    RecordingUrl: str = Form(...),
    CallSid: str = Form(...),
    From: str = Form(""),
    RecordingSid: str = Form(""),
):
    await validate_twilio_request(request)
    logger.info("Processing recording for call %s", CallSid)

    local_path = download_recording(RecordingUrl, CallSid)
    transcript = transcribe_audio(local_path)
    if not transcript.strip():
        return build_fallback_twiml("I did not catch that. Could you repeat after the beep?")

    result = await process_interaction(
        call_sid=CallSid,
        from_number=From,
        transcript=transcript,
        recording_sid=RecordingSid,
    )

    response = VoiceResponse()
    response.play(result["audio_url"])
    if result.get("continue_recording", True):
        callback_url = f"{PUBLIC_BASE_URL}/recording_callback"
        response.record(
            action=callback_url,
            method="POST",
            play_beep=True,
            max_length=20,
            recording_status_callback=callback_url,
            recording_status_callback_method="POST",
        )
    else:
        response.hangup()

    return Response(str(response), media_type="application/xml")


@app.get("/tts/{filename}")
async def serve_tts_audio(filename: str):
    file_path = Path("static/tts") / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Audio not found")
    return FileResponse(file_path, media_type="audio/mpeg")


@app.post("/api/test/simulate")
async def simulate_interaction(
    text: str = Form(""),
    from_number: str = Form("tester"),
    audio: Optional[UploadFile] = File(None),
):
    transcript = text.strip()
    temp_file: Path | None = None

    if audio is not None:
        suffix = Path(audio.filename or "audio.wav").suffix or ".wav"
        temp_file = Path("/tmp") / f"simulate-{uuid4().hex}{suffix}"
        temp_file.write_bytes(await audio.read())
        transcript = transcribe_audio(temp_file)
    if not transcript:
        raise HTTPException(status_code=400, detail="Provide either text or an audio file.")

    call_sid = f"SIM-{uuid4().hex}"
    result = await process_interaction(
        call_sid=call_sid,
        from_number=from_number,
        transcript=transcript,
        recording_sid="SIMULATED",
    )
    if temp_file and temp_file.exists():
        temp_file.unlink(missing_ok=True)

    return {
        "call_sid": call_sid,
        "transcript": transcript,
        **result,
    }


@app.get("/api/call-logs")
async def get_call_logs(limit: int = 20):
    records = call_logs.fetch_recent(limit)
    return {"items": records}


async def validate_twilio_request(request: Request):
    signature = request.headers.get("X-Twilio-Signature")
    if not signature:
        raise HTTPException(status_code=403, detail="Missing Twilio signature")
    url = str(request.url)
    params = dict(await request.form())
    if not twilio_validator.validate(url, params, signature):
        raise HTTPException(status_code=403, detail="Invalid Twilio signature")


def download_recording(recording_url: str, call_sid: str) -> Path:
    extension = "" if recording_url.endswith(".wav") else ".wav"
    url = f"{recording_url}{extension}"
    auth = (TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN) if TWILIO_ACCOUNT_SID else None
    response = requests.get(url, auth=auth, timeout=30)
    response.raise_for_status()
    local_path = Path("/tmp") / f"{call_sid}.wav"
    local_path.write_bytes(response.content)
    return local_path


def run_llm(system_prompt: str, payload: str) -> Tuple[str, Dict]:
    completion = openai_client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": payload},
        ],
        response_format={"type": "json_object"},
    )
    message = completion.choices[0].message.content
    data = json.loads(message)
    return data.get("response", ""), data.get("developer_note", {})


async def generate_tts(call_sid: str, reply_text: str) -> Tuple[Path, str]:
    call_sequences[call_sid] += 1
    seq = call_sequences[call_sid]
    filename = f"{call_sid}_{seq}.mp3"
    output_path = Path("static/tts") / filename
    output_path.parent.mkdir(parents=True, exist_ok=True)
    audio_data = await elevenlabs_service.generate_speech(reply_text)
    output_path.write_bytes(audio_data)
    audio_url = f"{PUBLIC_BASE_URL}/tts/{filename}"
    return output_path, audio_url


def build_fallback_twiml(message: str):
    response = VoiceResponse()
    response.say(message)
    callback_url = f"{PUBLIC_BASE_URL}/recording_callback"
    response.record(
        action=callback_url,
        method="POST",
        play_beep=True,
        max_length=20,
        recording_status_callback=callback_url,
        recording_status_callback_method="POST",
    )
    return Response(str(response), media_type="application/xml")


async def process_interaction(
    call_sid: str,
    from_number: str,
    transcript: str,
    recording_sid: str = "",
) -> Dict[str, Any]:
    transcript = transcript.strip()
    slot_state = slot_manager.get(call_sid)
    slot_updates, slot_reply = extract_slot_values(
        openai_client=openai_client,
        model=OPENAI_SLOT_MODEL,
        transcript=transcript,
        current_state=slot_state.to_dict(),
    )
    if slot_updates:
        slot_state = slot_manager.update(call_sid, slot_updates)
    else:
        slot_state = slot_manager.update(call_sid, {})

    documents = retriever.retrieve(transcript)
    missing_slots = get_missing_slots(slot_state)
    used_docs: List[str] = [doc.id for doc in documents]
    rag_note: Dict[str, Any] = {}
    reply_text = (slot_reply or "").strip()
    appointment_id = None
    continue_recording = True
    mode = "slot_filling"

    if should_answer_with_rag(missing_slots, documents, slot_updates):
        rag_reply, rag_note = build_rag_reply(transcript, documents)
        if rag_reply:
            reply_text = rag_reply
        used_docs = rag_note.get("used_docs", used_docs)
        if missing_slots:
            reply_text = f"{reply_text} {build_followup_prompt(missing_slots[0])}".strip()
        mode = "rag_answer"

    if not reply_text:
        if missing_slots:
            reply_text = build_followup_prompt(missing_slots[0])
        else:
            reply_text = "Could you share how I can help with your appointment?"

    if slots_complete(slot_state):
        appointment_id = call_logs.insert_appointment(
            call_sid=call_sid,
            state=slot_state.to_dict(),
            metadata={"recording_sid": recording_sid},
        )
        slot_manager.clear(call_sid)
        continue_recording = False
        reply_text = build_confirmation_message(slot_state)
        mode = "confirmation"

    _, audio_url = await generate_tts(call_sid, reply_text)

    developer_note = {
        "slots": slot_state.to_dict(),
        "slot_updates": slot_updates,
        "missing_slots": missing_slots,
        "appointment_id": appointment_id,
        "used_docs": used_docs,
        "rag_note": rag_note,
        "mode": mode,
    }

    call_logs.insert(
        call_sid=call_sid,
        from_number=from_number,
        transcript=transcript,
        used_docs=used_docs,
        llm_response=reply_text,
        tts_url=audio_url,
        metadata={
            "recording_sid": recording_sid,
            "developer_note": developer_note,
        },
    )

    return {
        "audio_url": audio_url,
        "reply_text": reply_text,
        "developer_note": developer_note,
        "documents": serialize_documents(documents),
        "slots": slot_state.to_dict(),
        "missing_slots": missing_slots,
        "appointment_id": appointment_id,
        "continue_recording": continue_recording,
    }


def serialize_documents(documents: List[RetrievedDocument]) -> List[Dict[str, Any]]:
    serialized: List[Dict[str, Any]] = []
    for doc in documents:
        serialized.append(
            {
                "id": doc.id,
                "score": doc.score,
                "text": doc.text,
                "metadata": doc.metadata,
            }
        )
    return serialized


def get_missing_slots(state: SlotState) -> List[str]:
    return [slot for slot in SLOT_KEYS if not getattr(state, slot)]


def build_followup_prompt(slot_key: str) -> str:
    label = SLOT_LABELS.get(slot_key, slot_key.replace("_", " "))
    return f"Could you please share {label}?"


def should_answer_with_rag(
    missing_slots: List[str],
    documents: List[RetrievedDocument],
    slot_updates: Dict[str, str],
) -> bool:
    if slot_updates:
        return False
    if not documents:
        return False
    top_score = documents[0].score
    if top_score < RAG_THRESHOLD:
        return False
    critical_missing = [slot for slot in missing_slots if slot != "doctor_preference"]
    return len(critical_missing) == 0


def build_rag_reply(transcript: str, documents: List[RetrievedDocument]) -> Tuple[str, Dict[str, Any]]:
    context = format_docs_for_prompt(documents) if documents else "No supporting documents."
    system_prompt = RETRIEVAL_SYSTEM_PROMPT if documents else FALLBACK_SYSTEM_PROMPT
    payload = PROMPT_TEMPLATE.format(context=context, transcript=transcript)
    reply, note = run_llm(system_prompt, payload)
    if not note.get("used_docs"):
        note["used_docs"] = [doc.id for doc in documents]
    return reply, note


def build_confirmation_message(state: SlotState) -> str:
    doctor = (
        f"with {state.doctor_preference}"
        if state.doctor_preference
        else "with the next available specialist"
    )
    return (
        f"Thanks {state.patient_name}. I've noted a {state.appointment_reason} visit on "
        f"{state.preferred_date} at {state.preferred_time} {doctor}. "
        "You will receive an SMS confirmation shortly."
    )