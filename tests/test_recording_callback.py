import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import main

os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ.setdefault("TWILIO_AUTH_TOKEN", "test-token")
os.environ.setdefault("PUBLIC_BASE_URL", "http://testserver")


@pytest.fixture
def client(monkeypatch):
    async def fake_validate(request):
        return None

    monkeypatch.setattr(main, "validate_twilio_request", fake_validate)
    return TestClient(main.app)


def test_recording_callback_creates_log_and_tts(monkeypatch, tmp_path, client):
    call_sid = "CA777"
    main.call_sequences.clear()
    main.slot_manager.clear(call_sid)

    sample = Path("tests/data/sample.wav")

    def fake_download(url, sid):
        target = tmp_path / f"{sid}.wav"
        target.write_bytes(sample.read_bytes())
        return target

    monkeypatch.setattr(main, "download_recording", fake_download)
    monkeypatch.setattr(main, "transcribe_audio", lambda path: "My name is Alex and I need a follow up.")

    def fake_extract(openai_client, model, transcript, current_state):
        return (
            {
                "patient_name": "Alex Patient",
                "appointment_reason": "Follow up",
                "preferred_date": "August 5",
                "preferred_time": "2 PM",
                "doctor_preference": "Dr. Smith",
            },
            "Thanks Alex, let me confirm that for you.",
        )

    monkeypatch.setattr(main, "extract_slot_values", fake_extract)
    monkeypatch.setattr(main.retriever, "retrieve", lambda query: [])

    created = []

    async def fake_generate(call_sid, reply_text):
        filename = f"{call_sid}_reply.mp3"
        path = tmp_path / filename
        path.write_bytes(b"mp3-bytes")
        created.append(path)
        return path, f"http://testserver/tts/{filename}"

    monkeypatch.setattr(main, "generate_tts", fake_generate)

    captured = {}

    def fake_insert(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(main.call_logs, "insert", fake_insert)
    monkeypatch.setattr(main.call_logs, "insert_appointment", lambda call_sid, state, metadata=None: "appt-77")

    response = client.post(
        "/recording_callback",
        data={
            "RecordingUrl": "https://example.com/recording",
            "CallSid": call_sid,
            "From": "+15551230000",
            "RecordingSid": "RS999",
        },
    )

    assert response.status_code == 200
    assert "<Record" not in response.text
    assert created, "TTS audio should be generated"
    assert captured["call_sid"] == call_sid
    assert captured["used_docs"] == []
    assert captured["metadata"]["developer_note"]["appointment_id"] == "appt-77"

