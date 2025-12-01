import os

os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ.setdefault("TWILIO_AUTH_TOKEN", "test-token")
os.environ.setdefault("PUBLIC_BASE_URL", "http://testserver")

import pytest
from fastapi.testclient import TestClient

import main
from services.rag.retriever import RetrievedDocument


@pytest.fixture
def test_client(monkeypatch):
    async def fake_validate(request):
        return None

    monkeypatch.setattr(main, "validate_twilio_request", fake_validate)
    return TestClient(main.app)


def test_recording_callback_flow(monkeypatch, tmp_path, test_client):
    main.call_sequences.clear()
    main.slot_manager.clear("CA123")

    def fake_download(url, call_sid):
        audio_path = tmp_path / f"{call_sid}.wav"
        audio_path.write_bytes(b"audio-bytes")
        return audio_path

    monkeypatch.setattr(main, "download_recording", fake_download)
    monkeypatch.setattr(main, "transcribe_audio", lambda path: "I need an appointment.")

    doc = RetrievedDocument(id="faq_001", text="We are open Mon-Sat 9 to 6.", score=0.92, metadata={})
    monkeypatch.setattr(main.retriever, "retrieve", lambda query: [doc])

    def fake_extract(openai_client, model, transcript, current_state):
        return (
            {
                "patient_name": "Jane Doe",
                "appointment_reason": "Consultation",
                "preferred_date": "July 10",
                "preferred_time": "10 AM",
                "doctor_preference": None,
            },
            "Thanks Jane, let me confirm that for you.",
        )

    monkeypatch.setattr(main, "extract_slot_values", fake_extract)

    created_files = []

    async def fake_generate(call_sid, reply_text):
        filename = f"{call_sid}.mp3"
        path = tmp_path / filename
        path.write_bytes(b"tts-bytes")
        created_files.append(path)
        return path, f"http://testserver/tts/{filename}"

    monkeypatch.setattr(main, "generate_tts", fake_generate)

    records = {}

    def fake_insert(**kwargs):
        records.update(kwargs)

    monkeypatch.setattr(main.call_logs, "insert", fake_insert)
    monkeypatch.setattr(main.call_logs, "insert_appointment", lambda call_sid, state, metadata=None: "appt-1")

    response = test_client.post(
        "/recording_callback",
        data={
            "RecordingUrl": "https://example.com/recording",
            "CallSid": "CA123",
            "From": "+15551234567",
            "RecordingSid": "RS123",
        },
    )

    assert response.status_code == 200
    assert "<Play>http://testserver/tts/CA123.mp3</Play>" in response.text
    assert "<Record" not in response.text  # confirmation should end loop
    assert records["call_sid"] == "CA123"
    assert records["used_docs"] == ["faq_001"]
    assert created_files, "TTS audio file should be created"


def test_simulate_endpoint(monkeypatch, test_client):
    async def fake_process(call_sid, from_number, transcript, recording_sid=""):
        return {
            "audio_url": "http://audio",
            "reply_text": "Hello world",
            "developer_note": {"mode": "slot_filling", "used_docs": ["faq_001"]},
            "documents": [],
            "slots": {"patient_name": "Sam"},
            "missing_slots": ["preferred_date"],
            "continue_recording": True,
        }

    monkeypatch.setattr(main, "process_interaction", fake_process)

    response = test_client.post(
        "/api/test/simulate",
        data={"text": "Need help", "from_number": "+1"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["reply_text"] == "Hello world"
    assert payload["developer_note"]["mode"] == "slot_filling"
    assert payload["slots"]["patient_name"] == "Sam"
    assert payload["continue_recording"] is True


def test_call_logs_endpoint(monkeypatch, test_client):
    monkeypatch.setattr(
        main.call_logs,
        "fetch_recent",
        lambda limit: [
            {
                "call_sid": "CA999",
                "phone_number": "+1555",
                "transcript": "Hello",
                "llm_response": "Hi",
                "used_docs": ["faq_001"],
                "created_at": "2025-01-01T00:00:00Z",
                "metadata": {"developer_note": {"mode": "slot_filling"}},
            }
        ],
    )

    response = test_client.get("/api/call-logs?limit=1")
    assert response.status_code == 200
    payload = response.json()
    assert payload["items"][0]["call_sid"] == "CA999"

