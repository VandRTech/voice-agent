# Voice Agent Setup & Sanity Checklist

This guide captures the environment requirements, runtime wiring, and sanity checks for the Twilio → FastAPI → Whisper/RAG → ElevenLabs voice agent.

## 1. Environment Variables

Use `.env.example` as your reference. Copy it to `.env` and fill in real credentials:

```bash
cp .env.example .env
```

| Key | Description |
| --- | --- |
| `FACILITY_NAME` | Used in system prompts/greetings |
| `PUBLIC_BASE_URL` | Base URL exposed via ngrok (e.g., `https://<sub>.ngrok-free.dev`) |
| `TWILIO_*` | SID/token/phone number for the Twilio account owning the voice number |
| `OPENAI_API_KEY` | Needed for both slot extraction + RAG responses |
| `WHISPER_*` | Controls whether local or OpenAI Whisper is used |
| `DEEPGRAM_API_KEY` | For `/deepgram-stream` websocket transcription |
| `ELEVENLABS_*` | TTS generation of responses |
| `REDIS_URL` | Slot manager store (Redis or fallback to in-memory) |
| `DATABASE_URL` | Optional Postgres persistence for `call_logs` / `appointments` |

> **Note:** until a valid OpenAI key is configured, `/api/test/simulate` and Twilio calls will fail with `401 AuthenticationError`.

## 2. Runtime Services

1. **Redis** (slot persistence)
   ```bash
   brew install redis
   brew services start redis
   ```

2. **Backend**
   ```bash
   python3 -m uvicorn main:app --reload --port 8000 --env-file .env
   ```
   - Warns if `DATABASE_URL` missing (call logs will be in-memory).

3. **Frontend**
   ```bash
   cd frontend
   npm install
   ./node_modules/.bin/next dev
   ```
   - `/simulate` triggers the exact pipeline without Twilio.
   - `/logs` introspects the most recent calls (slot states, used docs, appointment IDs).

4. **ngrok**
   ```bash
   ngrok config add-authtoken <token>
   ngrok http 8000
   ```
   - Copy the HTTPS URL and set `PUBLIC_BASE_URL` accordingly.

5. **Twilio Webhooks**
   - Voice URL: `<PUBLIC_BASE_URL>/voice`
   - Recording status callback: `<PUBLIC_BASE_URL>/recording_callback`
   - Use the REST API (see `docs/SETUP.md`) or the Twilio console.

## 3. Pipeline Walkthrough

1. **/voice** (Twilio webhook)
   - Greets caller, immediately issues `<Record>` (20s, beep) pointed at `/recording_callback`.
2. **/recording_callback**
   - Verifies Twilio signature ➜ downloads recording ➜ transcribes via Whisper ➜ passes transcript to `process_interaction()`.
3. **Slot Manager**
   - `services/conversation/slots.py` uses Redis to track `patient_name`, `appointment_reason`, `preferred_date`, `preferred_time`, `doctor_preference`.
   - `services/conversation/slot_extractor.py` hits OpenAI with a JSON-only prompt:
     ```json
     {
       "patient_name": null,
       "appointment_reason": "...",
       ...,
       "reply": "spoken response"
     }
     ```
4. **RAG Fallback**
   - `services/rag/retriever.py` queries Chroma (seed via `python data/kb/seed_kb.py`).
   - When confidence ≥ threshold and no critical slots remain, the assistant answers FAQs and appends follow-up prompts.
5. **TTS**
   - `services/speech/elevenlabs_service.py` generates MP3 → saved under `static/tts/<call_sid>_<n>.mp3`.
6. **Response Loop**
   - `/recording_callback` responds with `<Play>` + optional `<Record>` until all slots filled ➜ final confirmation (`You will receive an SMS confirmation shortly.`) ➜ `<Hangup>`.
7. **Persistence**
   - `call_logs.insert()` stores transcript, used docs, developer note, TTS URL.
   - `call_logs.insert_appointment()` runs once `slots_complete()` is true.

## 4. Sanity Checklist

| Check | Command / Action | Status |
| --- | --- | --- |
| Dependencies installed | `python3 -m pip install -r requirements.txt` | ✅ |
| Redis running | `brew services start redis` | ✅ |
| Backend boots | `python3 -m uvicorn ... --env-file .env` | ✅ (warns if DB unset) |
| Frontend boots | `./node_modules/.bin/next dev` | ✅ |
| ngrok tunnel | `ngrok http 8000` ➜ HTTPS URL logged | ✅ |
| Twilio webhook update | REST POST -> `PN...` | ✅ |
| `/api/test/simulate` | `curl -F text="..." http://127.0.0.1:8000/api/test/simulate` | ⚠️ requires valid OpenAI key |
| `pytest` | `python3 -m dotenv run -- python3 -m pytest` | ✅ |

## 5. Testing Workflow

1. **Unit/integration tests**
   ```bash
python3 -m dotenv run -- python3 -m pytest
   ```
   - `tests/test_seed_kb.py`: KB ingestion.
   - `tests/test_voice_flow.py`: webhook logic + slot manager.
   - `tests/test_recording_callback.py`: ensures appointments/logs saved.

2. **Manual flows**
   - `/simulate` (frontend) for text/audio prompts.
   - `curl` Twilio mocks (remember signature validation prevents direct `/recording_callback` posts).
   - Actual phone call via Twilio number once OpenAI key works.

## 6. Known Caveats

- **OpenAI key required:** Without a valid API key, slot extraction and RAG steps throw `401 AuthenticationError`.
- **Database optional:** until `DATABASE_URL` is populated, `call_logs` warning is expected.
- **Signature validation:** manual `curl` to `/recording_callback` returns 403 unless you generate a valid `X-Twilio-Signature`. Use `/api/test/simulate` for local testing instead.

Keep this document updated as you add new integrations or change the call flow.
