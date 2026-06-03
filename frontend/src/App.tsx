import { useEffect, useMemo, useRef, useState } from 'react';
import type { AgentTurnResponse, ChatMessage, Priority, Voice } from './types/agent';
import { base64ToAudioUrl, fetchHealth, fetchVoices, sendTextTurn, sendVoiceTurn } from './api/client';

type Status = 'ready' | 'getting-ready' | 'listening' | 'finishing' | 'processing' | 'speaking' | 'error';

type VoiceSettings = {
  stability: number;
  similarity_boost: number;
  style: number;
  use_speaker_boost: boolean;
};

const demoPrompts = [
  'My dishwasher is not turning on when I press start.',
  'There is water leaking from under my bathroom sink.',
  'I smell gas in my apartment.',
  'My AC is blowing warm air and making a loud noise.'
];

const START_BUFFER_MS = 3000;
const END_BUFFER_MS = 500;

const languageOptions = [
  { label: 'English', value: 'en' },
  { label: 'Spanish', value: 'es' },
  { label: 'Hindi', value: 'hi' },
  { label: 'French', value: 'fr' },
  { label: 'German', value: 'de' }
];

function nowLabel() {
  return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function priorityClass(priority?: Priority) {
  if (priority === 'Emergency') return 'pill danger';
  if (priority === 'High') return 'pill warning';
  if (priority === 'Medium') return 'pill info';
  if (priority === 'Low') return 'pill success';
  return 'pill';
}

export default function App() {
  const [status, setStatus] = useState<Status>('ready');
  const [error, setError] = useState('');
  const [health, setHealth] = useState<Record<string, unknown> | null>(null);
  const [voices, setVoices] = useState<Voice[]>([]);
  const [selectedVoiceId, setSelectedVoiceId] = useState('');
  const [languageCode, setLanguageCode] = useState('en');
  const [typedInput, setTypedInput] = useState('');
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: crypto.randomUUID(),
      role: 'agent',
      content: 'Hi, I’m VoiceDesk AI. Tell me what is wrong in your apartment and I’ll help triage it into a maintenance request.',
      timestamp: nowLabel()
    }
  ]);
  const [lastTurn, setLastTurn] = useState<AgentTurnResponse | null>(null);
  const [audioUrl, setAudioUrl] = useState('');
  const [tickets, setTickets] = useState<AgentTurnResponse[]>([]);
  const [voiceSettings, setVoiceSettings] = useState<VoiceSettings>({
    stability: 0.48,
    similarity_boost: 0.78,
    style: 0.12,
    use_speaker_boost: true
  });

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<BlobPart[]>([]);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const chatBottomRef = useRef<HTMLDivElement | null>(null);

  const selectedVoiceName = useMemo(() => {
    return voices.find((voice) => voice.voice_id === selectedVoiceId)?.name || 'Default voice';
  }, [voices, selectedVoiceId]);

  useEffect(() => {
    async function bootstrap() {
      try {
        const [healthPayload, voicesPayload] = await Promise.allSettled([fetchHealth(), fetchVoices()]);
        if (healthPayload.status === 'fulfilled') setHealth(healthPayload.value);
        if (voicesPayload.status === 'fulfilled') {
          const voiceList: Voice[] = voicesPayload.value.voices || [];
          setVoices(voiceList);
          if (voiceList[0]?.voice_id) setSelectedVoiceId(voiceList[0].voice_id);
        }
      } catch {
        // The app still works enough to show an actionable error when the user runs a turn.
      }
    }
    bootstrap();
  }, []);

  useEffect(() => {
    chatBottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  function addMessage(role: 'resident' | 'agent', content: string) {
    setMessages((prev) => [
      ...prev,
      { id: crypto.randomUUID(), role, content, timestamp: nowLabel() }
    ]);
  }

  function handleTurnResponse(result: AgentTurnResponse) {
    setLastTurn(result);
    setTickets((prev) => [result, ...prev].slice(0, 5));
    addMessage('resident', result.transcript);
    addMessage('agent', result.agent.spoken_response);

    if (result.audio_base64) {
      const url = base64ToAudioUrl(result.audio_base64, result.audio_mime_type);
      setAudioUrl(url);
      setStatus('speaking');
      setTimeout(() => {
        audioRef.current?.play().catch(() => setStatus('ready'));
      }, 80);
    } else {
      setStatus('ready');
    }
  }

  async function startRecording() {
    setError('');
    if (!navigator.mediaDevices?.getUserMedia) {
      setError('Your browser does not support microphone recording. Use the text fallback box instead.');
      setStatus('error');
      return;
    }

    try {
      setStatus('getting-ready');
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      chunksRef.current = [];
      const recorder = new MediaRecorder(stream, { mimeType: MediaRecorder.isTypeSupported('audio/webm') ? 'audio/webm' : undefined });
      mediaRecorderRef.current = recorder;
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) chunksRef.current.push(event.data);
      };
      recorder.onstop = async () => {
        stream.getTracks().forEach((track) => track.stop());
        const audioBlob = new Blob(chunksRef.current, { type: 'audio/webm' });
        if (audioBlob.size < 1000) {
          setError('Recording was too short. Please try again and speak for a little longer.');
          setStatus('error');
          return;
        }
        await submitVoiceBlob(audioBlob);
      };
      window.setTimeout(() => {
        recorder.start();
        setStatus('listening');
      }, START_BUFFER_MS);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not access microphone.');
      setStatus('error');
    }
  }

  function stopRecording() {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'recording') {
      setStatus('finishing');
      window.setTimeout(() => {
        if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'recording') {
          mediaRecorderRef.current.stop();
          setStatus('processing');
        }
      }, END_BUFFER_MS);
    }
  }

  async function submitVoiceBlob(audioBlob: Blob) {
    setStatus('processing');
    setError('');
    try {
      const result = await sendVoiceTurn({
        audioBlob,
        voiceId: selectedVoiceId,
        languageCode,
        voiceSettings,
        conversationHistory: messages
      });
      handleTurnResponse(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Voice turn failed.');
      setStatus('error');
    }
  }

  async function submitText(text = typedInput) {
    const trimmed = text.trim();
    if (!trimmed) return;
    setStatus('processing');
    setError('');
    setTypedInput('');
    try {
      const result = await sendTextTurn({
        transcript: trimmed,
        voiceId: selectedVoiceId,
        languageCode,
        voiceSettings,
        conversationHistory: messages
      });
      handleTurnResponse(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Text turn failed.');
      setStatus('error');
    }
  }

  function fakeSubmitTicket() {
    if (!lastTurn) return;
    setLastTurn({
      ...lastTurn,
      agent: {
        ...lastTurn.agent,
        ticket: { ...lastTurn.agent.ticket, status: 'Ready for property team review' }
      }
    });
  }

  const statusCopy = {
    ready: 'Ready for resident issue',
    'getting-ready': 'Getting microphone ready',
    listening: 'Listening to resident',
    finishing: 'Finishing recording',
    processing: 'Transcribing and reasoning',
    speaking: 'Speaking response',
    error: 'Needs attention'
  }[status];

  return (
    <main className="app-shell">
      <section className="hero-card">
        <div className="hero-copy">
          <div className="eyebrow"><span className="logo-dot">●</span> VoiceDesk AI</div>
          <h1>Apartment voice agent that listens, understands issues, and speaks back.
          </h1>
          <p>
            Voice-first flow using raw STT, maintenance-specific agent logic, and ElevenLabs TTS to convert messy resident issues into clean ticket drafts.
          </p>
          <div className="hero-actions">
            <button className="primary" onClick={status === 'listening' ? stopRecording : startRecording} disabled={status === 'getting-ready' || status === 'finishing' || status === 'processing' || status === 'speaking'}>
              {status === 'getting-ready' ? 'Getting ready...' : status === 'listening' ? 'Stop and triage issue' : status === 'finishing' ? 'Finishing...' : 'Start voice report'}
            </button>
            <button className="secondary" onClick={() => submitText(demoPrompts[1])} disabled={status === 'processing'}>
              Try leak demo
            </button>
          </div>
        </div>
        <div className="hero-panel">
          <div className="status-orb-wrap">
            <div className={`status-orb ${status}`}>{status === 'getting-ready' ? 'Get ready' : status === 'listening' ? 'Listening' : status === 'finishing' ? 'Finishing' : status === 'speaking' ? 'Voice reply' : 'Voice agent'}</div>
          </div>
          <div className="mini-grid">
            <div><strong>STT</strong><span>ElevenLabs</span></div>
            <div><strong>Agent</strong><span>Groq reasoning</span></div>
            <div><strong>TTS</strong><span>{selectedVoiceName}</span></div>
          </div>
        </div>
      </section>

      <section className="topbar">
        <div className="status-chip"><span className={`pulse ${status}`}></span>{statusCopy}</div>
      </section>

      {error && <section className="error-card"><strong>Issue:</strong> {error}</section>}

      <section className="workspace">
        <div className="left-column">
          <section className="card conversation-card">
            <div className="card-header">
              <div>
                <h2>Resident conversation</h2>
                <p>Voice-to-voice, with transcript visible for debugging.</p>
              </div>
              <span className="pill neutral">{messages.length} messages</span>
            </div>
            <div className="chat-window">
              {messages.map((message) => (
                <article className={`message ${message.role}`} key={message.id}>
                  <div className="message-meta">{message.role === 'resident' ? 'Resident' : 'VoiceDesk'} · {message.timestamp}</div>
                  <p>{message.content}</p>
                </article>
              ))}
              <div ref={chatBottomRef} />
            </div>
            <div className="input-row">
              <input
                value={typedInput}
                placeholder="Backup text input: describe a maintenance issue..."
                onChange={(e) => setTypedInput(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && submitText()}
              />
              <button className="secondary compact" onClick={() => submitText()} disabled={status === 'processing'}>Send</button>
            </div>
          </section>

          <section className="card demos-card">
            <div className="card-header compact-header">
              <div>
                <h2>Demo scenarios</h2>
                <p>Use these to test classification and escalation.</p>
              </div>
            </div>
            <div className="demo-grid">
              {demoPrompts.map((prompt) => (
                <button key={prompt} onClick={() => submitText(prompt)}>{prompt}</button>
              ))}
            </div>
          </section>
        </div>

        <aside className="right-column">
          <section className="card control-card">
            <div className="card-header">
              <div>
                <h2>Voice controls</h2>
                <p>ElevenLabs voice, language, and style controls.</p>
              </div>
            </div>
            <label>Agent voice</label>
            <select value={selectedVoiceId} onChange={(e) => setSelectedVoiceId(e.target.value)}>
              {voices.length === 0 ? <option value="">Default server voice</option> : voices.map((voice) => <option value={voice.voice_id} key={voice.voice_id}>{voice.name}</option>)}
            </select>
            <label>Language</label>
            <select value={languageCode} onChange={(e) => setLanguageCode(e.target.value)}>
              {languageOptions.map((language) => <option value={language.value} key={language.value}>{language.label}</option>)}
            </select>
            <Slider label="Stability" value={voiceSettings.stability} onChange={(value) => setVoiceSettings({ ...voiceSettings, stability: value })} />
            <Slider label="Similarity" value={voiceSettings.similarity_boost} onChange={(value) => setVoiceSettings({ ...voiceSettings, similarity_boost: value })} />
            <Slider label="Style" value={voiceSettings.style} onChange={(value) => setVoiceSettings({ ...voiceSettings, style: value })} />
            <label className="check-row"><input type="checkbox" checked={voiceSettings.use_speaker_boost} onChange={(e) => setVoiceSettings({ ...voiceSettings, use_speaker_boost: e.target.checked })} /> Speaker boost</label>
          </section>

          <section className="card audio-card">
            <div className="card-header compact-header">
              <div>
                <h2>Agent voice reply</h2>
                <p>Spoken response generated through TTS.</p>
              </div>
            </div>
            {audioUrl ? (
              <>
                <audio ref={audioRef} controls src={audioUrl} onEnded={() => setStatus('ready')} />
                <a className="download" href={audioUrl} download="voicedesk-agent-response.mp3">Download voice reply</a>
              </>
            ) : (
              <div className="empty-state">The spoken agent reply will appear here after a turn.</div>
            )}
          </section>
        </aside>
      </section>

      <section className="lower-grid">
        <section className="card ticket-card">
          <div className="card-header">
            <div>
              <h2>Maintenance ticket draft</h2>
              <p>Structured output for property teams.</p>
            </div>
            {lastTurn && <span className={priorityClass(lastTurn.agent.priority)}>{lastTurn.agent.priority}</span>}
          </div>
          {lastTurn ? (
            <div className="ticket-body">
              <div className="ticket-title-row">
                <div>
                  <h3>{lastTurn.agent.ticket.title}</h3>
                  <p>{lastTurn.agent.ticket.ticket_id} · {lastTurn.agent.ticket.status}</p>
                </div>
                <button className="primary small" onClick={fakeSubmitTicket}>Mark ready</button>
              </div>
              <div className="facts-grid">
                <Fact label="Category" value={lastTurn.agent.category} />
                <Fact label="Issue type" value={lastTurn.agent.issue_type} />
                <Fact label="Location" value={lastTurn.agent.location} />
                <Fact label="Confidence" value={`${lastTurn.agent.confidence}%`} />
              </div>
              <InfoBlock title="Resident summary" text={lastTurn.agent.ticket.summary} />
              <InfoBlock title="Recommended maintenance action" text={lastTurn.agent.ticket.recommended_action} />
              <InfoBlock title="Resident guidance" text={lastTurn.agent.ticket.resident_guidance} />
              <InfoBlock title="Safety note" text={lastTurn.agent.ticket.safety_note} />
              {lastTurn.agent.requires_follow_up && lastTurn.agent.follow_up_question && <InfoBlock title="Follow-up needed" text={lastTurn.agent.follow_up_question} />}
            </div>
          ) : (
            <div className="empty-state large">No ticket yet. Start a voice report or use a demo scenario.</div>
          )}
        </section>

        <section className="card metrics-card">
          <div className="card-header compact-header">
            <div>
              <h2>Pipeline metrics</h2>
              <p>Useful for engineering demo and observability.</p>
            </div>
          </div>
          {lastTurn ? (
            <div className="metric-list">
              <Metric label="STT latency" value={`${lastTurn.metrics.stt_ms ?? 0} ms`} />
              <Metric label="Agent latency" value={`${lastTurn.metrics.agent_ms ?? 0} ms`} />
              <Metric label="TTS latency" value={`${lastTurn.metrics.tts_ms ?? 0} ms`} />
              <Metric label="Total time" value={`${lastTurn.metrics.total_ms ?? 0} ms`} />
              <Metric label="Audio size" value={`${lastTurn.metrics.audio_bytes ?? 0} bytes`} />
              <Metric label="Mode" value={String(lastTurn.metrics.mode || 'voice-full-turn')} />
            </div>
          ) : <div className="empty-state">Metrics appear after the first agent turn.</div>}
        </section>

        <section className="card history-card">
          <div className="card-header compact-header">
            <div>
              <h2>Recent tickets</h2>
              <p>Session-only ticket history.</p>
            </div>
          </div>
          <div className="history-list">
            {tickets.length === 0 ? <div className="empty-state">No history yet.</div> : tickets.map((turn) => (
              <div className="history-item" key={turn.agent.ticket.ticket_id}>
                <div><strong>{turn.agent.ticket.title}</strong><span>{turn.agent.ticket.ticket_id}</span></div>
                <span className={priorityClass(turn.agent.priority)}>{turn.agent.priority}</span>
              </div>
            ))}
          </div>
        </section>
      </section>
    </main>
  );
}

function Slider({ label, value, onChange }: { label: string; value: number; onChange: (value: number) => void }) {
  return (
    <div className="slider-row">
      <div><span>{label}</span><strong>{value.toFixed(2)}</strong></div>
      <input type="range" min="0" max="1" step="0.01" value={value} onChange={(e) => onChange(Number(e.target.value))} />
    </div>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return <div className="fact"><span>{label}</span><strong>{value}</strong></div>;
}

function InfoBlock({ title, text }: { title: string; text: string }) {
  return <div className="info-block"><span>{title}</span><p>{text}</p></div>;
}

function Metric({ label, value }: { label: string; value: string }) {
  return <div className="metric"><span>{label}</span><strong>{value}</strong></div>;
}
