/**
 * useChat — manages agent chat session state and streaming.
 *
 * Handles the richer agent event stream:
 * - "text" chunks → accumulated into message.content
 * - "reasoning" / "tool_call" / "tool_result" → appended to message.events
 * - "done" → marks streaming complete, persists sessionId
 * - "error" → surfaces error state
 */

import { useCallback, useRef, useState } from "react";
import { streamChatMessage } from "@/services/api";
import type { AgentMessage, StreamChunk } from "@/types/chat";

interface UseChatReturn {
  messages: AgentMessage[];
  sessionId: string | null;
  isStreaming: boolean;
  error: string | null;
  sendMessage: (content: string) => Promise<void>;
  clearSession: () => void;
}

export function useChat(): UseChatReturn {
  const [messages, setMessages] = useState<AgentMessage[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Refs to accumulate without triggering re-renders on every chunk
  const textBufferRef = useRef("");
  const eventsBufferRef = useRef<StreamChunk[]>([]);

  const sendMessage = useCallback(
    async (content: string) => {
      if (isStreaming || !content.trim()) return;

      setError(null);
      setIsStreaming(true);
      textBufferRef.current = "";
      eventsBufferRef.current = [];

      // Optimistic user message
      const userMessage: AgentMessage = { role: "user", content, events: [] };
      setMessages((prev) => [...prev, userMessage]);

      // Empty assistant placeholder
      const assistantPlaceholder: AgentMessage = {
        role: "assistant",
        content: "",
        events: [],
      };
      setMessages((prev) => [...prev, assistantPlaceholder]);

      const handleChunk = (chunk: StreamChunk) => {
        if (chunk.type === "text" && chunk.content) {
          textBufferRef.current += chunk.content;
        }

        // All event types (including text) are stored for rendering
        if (chunk.type !== "done" && chunk.type !== "error") {
          eventsBufferRef.current = [...eventsBufferRef.current, chunk];
        }

        // Update the last message with current accumulated state
        setMessages((prev) => {
          const updated = [...prev];
          updated[updated.length - 1] = {
            role: "assistant",
            content: textBufferRef.current,
            events: eventsBufferRef.current,
          };
          return updated;
        });
      };

      const handleDone = (resolvedSessionId: string) => {
        if (resolvedSessionId) setSessionId(resolvedSessionId);
        setIsStreaming(false);
      };

      const handleError = (err: Error) => {
        setError(err.message);
        setIsStreaming(false);
        // Remove empty placeholder on error
        setMessages((prev) => {
          const updated = [...prev];
          const last = updated[updated.length - 1];
          if (last?.content === "" && last.events.length === 0) {
            updated.pop();
          }
          return updated;
        });
      };

      await streamChatMessage(
        { sessionId: sessionId ?? undefined, message: content },
        handleChunk,
        handleDone,
        handleError,
      );
    },
    [isStreaming, sessionId],
  );

  const clearSession = useCallback(() => {
    setMessages([]);
    setSessionId(null);
    setError(null);
    textBufferRef.current = "";
    eventsBufferRef.current = [];
  }, []);

  return { messages, sessionId, isStreaming, error, sendMessage, clearSession };
}
