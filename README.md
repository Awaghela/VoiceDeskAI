# VoiceDesk AI

Production-style apartment maintenance conversational voice agent.

VoiceDesk AI lets a resident report an apartment issue by voice. The backend transcribes the audio with ElevenLabs STT, uses Groq LLM reasoning to understand intent and generate a structured maintenance decision, applies safety fallback rules, and speaks back using ElevenLabs TTS.

## Core flow

```text
Resident speaks
→ ElevenLabs STT transcribes audio
→ Groq LLM reasons over intent, category, priority, and next action
→ Backend validates structured JSON and applies emergency safety overrides
→ Ticket draft is generated
→ ElevenLabs TTS speaks the response back
```

## Why Groq was added

The first version used deterministic maintenance rules. This version adds a real reasoning layer so the agent understands natural conversation such as:

- "okay thanks"
- "actually it is in the kitchen"
- "no, it stopped leaking"
- "can you repeat that?"
- "never mind"

If `GROQ_API_KEY` is missing or Groq fails, the app falls back to the built-in rule-based triage engine so demos still work.

## Recommended Groq model

Default:

```env
GROQ_MODEL=llama-3.3-70b-versatile
```

Use this for better reasoning and structured JSON quality. For cheaper/faster experiments, you can try:

```env
GROQ_MODEL=llama-3.1-8b-instant
```

## Features

- Light, polished, production-style React UI
- Voice-first push-to-talk recording
- Automatic start/end recording buffer to avoid cut-off audio
- Text fallback for noisy environments
- ElevenLabs Speech-to-Text integration
- Groq LLM intent and reasoning layer
- Rule-based emergency safety overrides
- Rule-based fallback when Groq is not configured
- ElevenLabs Text-to-Speech voice reply
- Dynamic ElevenLabs voice selector
- Language selector
- Voice controls: stability, similarity, style, speaker boost
- Apartment maintenance categories
- Conversation intent handling: greeting, follow-up, closing, cancel, new report
- Priority detection: Emergency, High, Medium, Low
- Follow-up question handling
- Structured ticket preview
- Ticket-ready status simulation
- Session ticket history
- Pipeline metrics: STT latency, Groq/rules reasoning latency, TTS latency, total time, audio bytes
- Railway-ready single Docker deployment

## Tech stack

```text
Frontend: React, TypeScript, Vite, CSS
Backend: FastAPI, Python, httpx, Pydantic
APIs: ElevenLabs STT + Groq LLM + ElevenLabs TTS
Deployment: Railway Docker service
```

## Local development

### 1. Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Create `backend/.env`:

```env
ELEVENLABS_API_KEY=your_elevenlabs_api_key_here
ELEVENLABS_STT_MODEL_ID=scribe_v2
ELEVENLABS_TTS_MODEL_ID=eleven_multilingual_v2

GROQ_API_KEY=your_groq_api_key_here
GROQ_MODEL=llama-3.3-70b-versatile
```

Run backend:

```bash
uvicorn app.main:app --reload --port 8000
```

Open health check:

```text
http://localhost:8000/health
```

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open:

```text
http://localhost:5173
```

The Vite dev server proxies `/api` and `/health` to FastAPI on port 8000.

## Railway deployment

Push this folder to GitHub, then:

1. Railway → New Project
2. Deploy from GitHub Repo
3. Select the repo
4. Add environment variables:

```env
ELEVENLABS_API_KEY=your_elevenlabs_api_key_here
GROQ_API_KEY=your_groq_api_key_here
GROQ_MODEL=llama-3.3-70b-versatile
APP_ENV=production
```

Optional variables:

```env
ELEVENLABS_DEFAULT_VOICE_ID=JBFqnCBsd6RMkjVDRZzb
ELEVENLABS_STT_MODEL_ID=scribe_v2
ELEVENLABS_TTS_MODEL_ID=eleven_multilingual_v2
GROQ_BASE_URL=https://api.groq.com/openai/v1
```

Railway uses the root `Dockerfile` and serves the React build through FastAPI.

## Demo scripts

Use these prompts to test the agent:

1. `My dishwasher is not turning on when I press start.`
2. `There is water leaking from under my bathroom sink.`
3. `I smell gas in my apartment.`
4. `My AC is blowing warm air and making a loud noise.`
5. Follow-up/closing test: after any response, say `okay thanks` and the agent should close naturally instead of creating a new ticket.

## Important notes

- The ElevenLabs and Groq API keys are only used server-side.
- The frontend never calls ElevenLabs or Groq directly.
- Groq produces structured JSON; the backend validates/coerces the result with Pydantic.
- Emergency safety overrides are enforced in backend code even when Groq is used.
- If Groq is unavailable, the app falls back to deterministic triage rules.

## How to explain it

> VoiceDesk AI is a voice-first maintenance service desk agent for apartment residents. It uses raw speech-to-text and text-to-speech APIs to let users report issues naturally. ElevenLabs STT transcribes the resident's issue, Groq reasons over the conversation to classify intent and priority, the backend generates a structured ticket draft with safety overrides, and ElevenLabs TTS speaks the response back.
