/**
 * Chat domain types — mirrors the backend Pydantic schemas.
 * Keep these in sync with apps/backend/app/schemas/chat.py
 * and packages/agents/schemas.py
 */

export type MessageRole = "user" | "assistant" | "system" | "tool";

/** A single SSE chunk from the streaming endpoint. */
export interface StreamChunk {
  type: "text" | "reasoning" | "tool_call" | "tool_result" | "done" | "error";
  content?: string;
  metadata?: Record<string, unknown>;
}

/**
 * AgentMessage — the frontend's representation of a single turn.
 *
 * For user messages: role="user", content=text, events=[].
 * For assistant messages: role="assistant", content=accumulated text,
 *   events=all StreamChunks received (reasoning, tool_call, tool_result, etc.)
 */
export interface AgentMessage {
  role: MessageRole;
  content: string;
  events: StreamChunk[];
}

export interface ChatSession {
  sessionId: string;
  messages: AgentMessage[];
  createdAt: string;
}

export interface ChatRequest {
  sessionId?: string;
  message: string;
  stream?: boolean;
}

export interface ChatResponse {
  sessionId: string;
  message: {
    role: MessageRole;
    content: string;
  };
  usage?: {
    input_tokens: number;
    output_tokens: number;
  };
  createdAt: string;
}
