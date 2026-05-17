/**
 * API service layer — all HTTP calls to the backend go through here.
 *
 * Design:
 * - Single base URL from env variable
 * - Typed request/response functions
 * - Streaming handled via fetch + ReadableStream (SSE)
 * - Errors thrown as typed ApiError instances
 */

import type { ChatRequest, ChatResponse, StreamChunk } from "@/types/chat";

export interface IngestRequest {
  content: string;
  metadata: {
    source: string;
    source_type: string;
    title?: string;
    language?: string;
    extra?: Record<string, unknown>;
  };
}

export interface IngestResponse {
  document_id: string;
  chunk_count: number;
  source: string;
}

export interface KnowledgeDocument {
  document_id: string;
  source: string;
  source_type: string;
  title: string;
  created_at: string;
  chunk_count: number;
}

const BASE_URL: string = (import.meta.env.VITE_API_URL as string | undefined) ?? "/api/v1";

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const body = await response.text();
    throw new ApiError(response.status, body.length > 0 ? body : response.statusText);
  }
  return response.json() as Promise<T>;
}

/**
 * List all documents in the knowledge base.
 */
export async function listDocuments(): Promise<KnowledgeDocument[]> {
  const response = await fetch(`${BASE_URL}/documents/`, {
    method: "GET",
    headers: { "Content-Type": "application/json" },
  });
  const envelope = await handleResponse<{ success: boolean; data: KnowledgeDocument[] }>(response);
  return envelope.data;
}

/**
 * Delete a document and all its chunks from the knowledge base.
 */
export async function deleteDocument(documentId: string): Promise<void> {
  const response = await fetch(`${BASE_URL}/documents/${documentId}`, {
    method: "DELETE",
  });
  await handleResponse<{ success: boolean; data: unknown }>(response);
}

/**
 * Upload a file (PDF or text) to the RAG ingestion pipeline.
 *
 * Sends the raw file bytes as multipart/form-data. The backend extracts
 * text server-side (pypdf for PDFs) before chunking and embedding.
 * This avoids the browser's inability to parse PDF binary content.
 */
export async function uploadDocument(file: File): Promise<IngestResponse> {
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch(`${BASE_URL}/documents/upload`, {
    method: "POST",
    body: formData,
    // Do NOT set Content-Type — browser sets it automatically with the boundary
  });
  const envelope = await handleResponse<{ success: boolean; data: IngestResponse }>(response);
  return envelope.data;
}

/**
 * Ingest a document into the RAG pipeline.
 *
 * Sends plain text content to /documents/ingest where it is chunked,
 * embedded, and stored in pgvector for later retrieval.
 */
export async function ingestDocument(request: IngestRequest): Promise<IngestResponse> {
  const response = await fetch(`${BASE_URL}/documents/ingest`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  const envelope = await handleResponse<{ success: boolean; data: IngestResponse }>(response);
  return envelope.data;
}

/** Non-streaming chat completion */
export async function sendChatMessage(
  request: ChatRequest,
): Promise<ChatResponse> {
  const response = await fetch(`${BASE_URL}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  const envelope = await handleResponse<{ success: boolean; data: ChatResponse }>(response);
  return envelope.data;
}

/**
 * Streaming chat via Server-Sent Events.
 *
 * Calls onChunk for each text chunk, onDone when the stream ends,
 * and onError if something goes wrong.
 */
export async function streamChatMessage(
  request: ChatRequest,
  onChunk: (chunk: StreamChunk) => void,
  onDone: (sessionId: string) => void,
  onError: (error: Error) => void,
): Promise<void> {
  let response: Response;

  try {
    response = await fetch(`${BASE_URL}/chat/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...request, stream: true }),
    });
  } catch (err) {
    onError(err instanceof Error ? err : new Error(String(err)));
    return;
  }

  if (!response.ok || response.body === null) {
    onError(new ApiError(response.status, "Stream request failed"));
    return;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() ?? ""; // Keep incomplete line in buffer

      for (const line of lines) {
        const prefix = "data: ";
        if (!line.startsWith(prefix)) continue;
        const jsonStr = line.slice(prefix.length).trim();
        if (jsonStr.length === 0) continue;

        try {
          const chunk = JSON.parse(jsonStr) as StreamChunk;
          onChunk(chunk);

          if (chunk.type === "done") {
            const sessionId = (chunk.metadata?.session_id as string | undefined) ?? "";
            onDone(sessionId);
            return;
          }

          if (chunk.type === "error") {
            onError(new Error(chunk.content ?? "Stream error"));
            return;
          }
        } catch {
          // Malformed JSON chunk — skip and continue
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
}
