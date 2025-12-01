# AI-Powered Medical Appointment Voice Agent

[![License: Proprietary](https://img.shields.io/badge/License-Proprietary-blue.svg)](https://opensource.org/licenses/proprietary)

An intelligent voice-based system for managing medical appointments through natural phone conversations. Integrates with EHR systems and provides human-like patient interactions.

## Features

- **Natural Voice Conversations**  
  - Real-time speech-to-text (Deepgram) and text-to-speech (ElevenLabs)
  - Context-aware dialogue management
  - Multi-turn conversation handling

- **Appointment Management**  
  - Scheduling, modification, and cancellation
  - Provider availability checks
  - EHR system integration (eClinicalWorks)

- **Patient Services**  
  - Phone number recognition for existing patients
  - Transportation coordination (Uber)
  - Automated reminders and follow-ups

- **Clinical Integration**  
  - Real-time access to patient records
  - Provider schedule synchronization
  - Medical history context in conversations

- **Administration**  
  - Retool-based staff dashboard
  - Call monitoring and analytics
  - Appointment tracking and reporting

## Getting Started

### Prerequisites

- Python 3.9+
- PostgreSQL 14+
- Twilio account
- ngrok account
- API keys for:
  - Deepgram
  - ElevenLabs
  - OpenAI
  - Twilio

### Installation

1. **Clone Repository**
```bash
git clone https://github.com/your-username/medical-voice-agent.git
cd medical-voice-agent
```

2. **Set Up Virtual Environment**
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate  # Windows
```

3. **Install Dependencies**
```bash
pip install -r requirements.txt
```

4. **Configuration**
Create `.env` file with:
```env
OPENAI_API_KEY=your-openai-key
DEEPGRAM_API_KEY=your-deepgram-key
ELEVENLABS_API_KEY=your-elevenlabs-key
TWILIO_ACCOUNT_SID=your-twilio-sid
TWILIO_AUTH_TOKEN=your-twilio-token
TWILIO_PHONE_NUMBER=+1234567890
FACILITY_NAME="Your Medical Facility"
DATABASE_URL=postgresql://user:password@localhost:5432/medical_voice
PUBLIC_BASE_URL=https://<your-ngrok-id>.ngrok.io
WHISPER_MODE=openai  # or "local"
OPENAI_MODEL=gpt-4o-mini
OPENAI_SLOT_MODEL=gpt-4o-mini  # optional override for slot extraction
ELEVENLABS_VOICE_ID=your-voice-id
REDIS_URL=redis://localhost:6379/0  # optional, falls back to in-memory
API_BASE_URL=http://localhost:8000          # Used by the Next.js proxy (server)
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000  # Used by the browser for audio playback, optional
```

### Database Setup
1. Create PostgreSQL database
2. Run schema from `context.md` (Section 2.1)
3. Initialize with sample data using Retool admin interface

### Seed the Clinic Knowledge Base
1. Edit or add FAQ files under `data/kb/` (JSONL or Markdown). A sample set is provided in `clinic_faqs.jsonl`.
2. Generate embeddings and populate the local Chroma DB:
   ```bash
   python data/kb/seed_kb.py --source data/kb --collection clinic_kb_demo
   ```
3. Embeddings are stored in `data/chroma/`. Delete this folder to rebuild from scratch.

### Running the System
1. **Start FastAPI Server**
```bash
uvicorn main:app --reload --port 8000
```

2. **Start ngrok Tunnel** (separate terminal)
```bash
ngrok http 8000
```

3. **Configure Twilio Webhook**
- Voice webhook: `https://<your-ngrok-id>.ngrok.io/voice`
- Recording callback: `https://<your-ngrok-id>.ngrok.io/recording_callback`
- Set in Twilio Console: Phone Number → Voice & Fax → Webhook

> For a complete checklist (env vars, ngrok, Redis, Twilio REST commands, sanity steps) see `docs/SETUP.md`.

4. **Launch the Test UI (Next.js)**
```bash
cd frontend
npm install          # first run only
npm run dev          # defaults to http://localhost:3000
```
The UI proxies API requests to `API_BASE_URL` (default `http://localhost:8000`). Update the `.env.local` file under `frontend/` if your FastAPI server runs elsewhere.

### End-to-End Demo Flow
1. Caller hits `/voice`; Twilio plays the greeting and records a 20s segment.
2. Twilio POSTs the recording URL to `/recording_callback`.
3. Server downloads the audio and transcribes via Whisper (`WHISPER_MODE` env controls local vs OpenAI).
4. Transcript feeds the Chroma retriever, returning top FAQ chunks over cosine > 0.70.
5. LLM builds a short spoken reply with citations, or a fallback when no evidence exists.
6. ElevenLabs produces MP3 audio saved under `static/tts/<call_sid>_<n>.mp3`.
7. Twilio `<Play>` streams the audio, then another `<Record>` keeps the conversation rolling.
8. Postgres `call_logs` captures transcript, retrieval metadata, LLM response, and TTS URL for auditing.

### Booking Slot Workflow
1. Each transcript is fed to a slot-extraction prompt that returns JSON for: `patient_name`, `appointment_reason`, `preferred_date`, `preferred_time`, and `doctor_preference`, plus a natural reply.
2. Slot state is cached per `call_sid` (Redis when `REDIS_URL` is present, otherwise in-memory) and refreshed with every update.
3. Missing slots trigger short follow-up questions. If the user asks for clinic info (e.g., hours), the agent can answer via RAG **and** append a reminder requesting the next slot.
4. Once all slots are filled, the assistant:
   - Writes to `appointments` with call metadata and preferences.
   - Logs the confirmation + slot history to `call_logs`.
   - Plays a final ElevenLabs confirmation ("You will receive an SMS confirmation shortly.") and hangs up without adding another `<Record>`.
5. `/simulate` and `/logs` in the Next.js console surface slot progress, missing fields, and appointment IDs for quick debugging.

### Web Test Console
- `/simulate`: Trigger the FastAPI pipeline without Twilio by uploading short audio or typing a prompt. Shows transcript, retrieved docs, reply, and ElevenLabs audio preview.
- `/logs`: Lists the latest call records from Postgres with transcript snippets, used docs, and timestamps.
- Both features live at `frontend/src/app/*` and proxy via `/api/simulate` and `/api/call-logs`, which forward to the FastAPI endpoints:
  - `POST /api/test/simulate`
  - `GET /api/call-logs?limit=20`

## System Verification
1. Call your Twilio number
2. Expected flow:
   - System greets with natural voice
   - Responds to appointment requests
   - Handles complex scheduling logic
   - Integrates with EHR data
   - Provides confirmation via SMS/voice

## Testing
Run the mocked test suite:
```bash
pytest
```
- `tests/test_seed_kb.py`: seeds sample docs into a temporary Chroma store.
- `tests/test_voice_flow.py`: covers Twilio webhook, the simulation endpoint, and the call-log API.
- `tests/test_recording_callback.py`: simulates a Twilio recording callback end-to-end, asserting TTS creation plus `call_logs`/`appointments` inserts.

## Demo Script (Faisal)
1. `pip install -r requirements.txt`
2. `python data/kb/seed_kb.py --source data/kb --collection clinic_kb_demo`
3. `uvicorn main:app --reload --port 8000`
4. `cd frontend && npm install && npm run dev`
5. `ngrok http 8000` → update Twilio Voice + Recording webhooks to the ngrok URL.
6. Call the Twilio number and provide: name, reason, preferred date/time, and doctor preference. The agent will confirm and say “You will receive an SMS confirmation.”
7. Inspect `/simulate` (without dialing) and `/logs` (slot status, appointment IDs) on `http://localhost:3000`.
8. Verify Postgres tables (`call_logs`, `appointments`) or review `metadata.developer_note` via the APIs for auditing.

## Key Architecture
```mermaid
graph TD
    A[Patient Call] --> B[Twilio]
    B --> C[Voice Processing]
    C --> D[AI Conversation Engine]
    D --> E[Appointment Logic]
    E --> F[EHR Integration]
    F --> G[Database]
    G --> H[Admin Dashboard]
```

## Development Phases
1. Voice Processing (STT/TTS)
2. Database & Admin Interface
3. Conversation Logic
4. Testing & Security
5. Deployment

## Troubleshooting
- **No Audio**: Check ElevenLabs API key
- **Failed Transcriptions**: Verify Deepgram credentials
- **Database Issues**: Ensure PostgreSQL is running
- **Call Drops**: Check ngrok tunnel status at `http://localhost:4040`

## Future Roadmap
- Multi-language support
- Insurance verification
- Prescription management
- Patient portal integration
- Advanced analytics

## License
Proprietary - © 2025 MedDis

## Contact
Some self entitled tech bro - mememe@meddis.com