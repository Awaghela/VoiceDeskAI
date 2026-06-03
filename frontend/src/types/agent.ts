export type Priority = 'Emergency' | 'High' | 'Medium' | 'Low';

export type TicketDraft = {
  ticket_id: string;
  title: string;
  category: string;
  issue_type: string;
  priority: Priority;
  location: string;
  summary: string;
  recommended_action: string;
  resident_guidance: string;
  safety_note: string;
  confidence: number;
  status: string;
};

export type AgentDecision = {
  spoken_response: string;
  category: string;
  priority: Priority;
  issue_type: string;
  location: string;
  requires_follow_up: boolean;
  follow_up_question?: string | null;
  next_action: string;
  safety_note: string;
  confidence: number;
  ticket: TicketDraft;
};

export type AgentTurnResponse = {
  transcript: string;
  agent: AgentDecision;
  audio_base64?: string | null;
  audio_mime_type: string;
  metrics: Record<string, number | string | null>;
};

export type Voice = {
  voice_id: string;
  name: string;
  category?: string;
  labels?: Record<string, string>;
  description?: string;
  preview_url?: string;
};

export type ChatMessage = {
  id: string;
  role: 'resident' | 'agent';
  content: string;
  timestamp: string;
};
