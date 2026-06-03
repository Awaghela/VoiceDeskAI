import type { AgentTurnResponse, ChatMessage } from '../types/agent';

const API_BASE_URL = '';

export type VoiceSettingsPayload = {
  stability: number;
  similarity_boost: number;
  style: number;
  use_speaker_boost: boolean;
};

async function parseError(response: Response): Promise<string> {
  try {
    const payload = await response.json();
    return payload.detail || payload.message || response.statusText;
  } catch {
    return response.statusText;
  }
}

export async function fetchHealth() {
  const response = await fetch(`${API_BASE_URL}/health`);
  if (!response.ok) throw new Error(await parseError(response));
  return response.json();
}

export async function fetchVoices() {
  const response = await fetch(`${API_BASE_URL}/api/voices`);
  if (!response.ok) throw new Error(await parseError(response));
  return response.json();
}

export async function sendVoiceTurn(params: {
  audioBlob: Blob;
  voiceId?: string;
  languageCode: string;
  voiceSettings: VoiceSettingsPayload;
  conversationHistory?: ChatMessage[];
}): Promise<AgentTurnResponse> {
  const form = new FormData();
  form.append('audio_file', params.audioBlob, 'resident-message.webm');
  if (params.voiceId) form.append('voice_id', params.voiceId);
  form.append('language_code', params.languageCode || 'en');
  form.append('stability', String(params.voiceSettings.stability));
  form.append('similarity_boost', String(params.voiceSettings.similarity_boost));
  form.append('style', String(params.voiceSettings.style));
  form.append('use_speaker_boost', String(params.voiceSettings.use_speaker_boost));
  if (params.conversationHistory) {
    form.append('conversation_history_json', JSON.stringify(params.conversationHistory.map((m) => ({ role: m.role, content: m.content }))));
  }

  const response = await fetch(`${API_BASE_URL}/api/agent/full-turn`, {
    method: 'POST',
    body: form
  });
  if (!response.ok) throw new Error(await parseError(response));
  return response.json();
}

export async function sendTextTurn(params: {
  transcript: string;
  voiceId?: string;
  languageCode: string;
  voiceSettings: VoiceSettingsPayload;
  conversationHistory?: ChatMessage[];
}): Promise<AgentTurnResponse> {
  const response = await fetch(`${API_BASE_URL}/api/agent/respond`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      transcript: params.transcript,
      voice_id: params.voiceId,
      language_code: params.languageCode,
      voice_settings: params.voiceSettings,
      conversation_history: params.conversationHistory?.map((m) => ({ role: m.role, content: m.content })) || []
    })
  });
  if (!response.ok) throw new Error(await parseError(response));
  return response.json();
}

export function base64ToAudioUrl(base64: string, mimeType = 'audio/mpeg'): string {
  const byteCharacters = atob(base64);
  const byteArrays: BlobPart[] = [];
  for (let offset = 0; offset < byteCharacters.length; offset += 512) {
    const slice = byteCharacters.slice(offset, offset + 512);
    const byteNumbers = new Array(slice.length);
    for (let i = 0; i < slice.length; i += 1) byteNumbers[i] = slice.charCodeAt(i);
    byteArrays.push(new Uint8Array(byteNumbers).buffer);
  }
  return URL.createObjectURL(new Blob(byteArrays, { type: mimeType }));
}
