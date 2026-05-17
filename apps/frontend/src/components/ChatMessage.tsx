/**
 * ChatMessage — renders a single message bubble with agent event support.
 *
 * User messages: right-aligned, plain text.
 * Assistant messages: left-aligned, with:
 *   - Markdown-rendered final answer text
 *   - Collapsible reasoning blocks
 *   - Tool call + result cards (paired by call_id)
 *   - Streaming cursor while content is arriving
 */

import ReactMarkdown from "react-markdown";
import { ReasoningBlock } from "@/components/ReasoningBlock";
import { ToolCallBlock } from "@/components/ToolCallBlock";
import { CitationList } from "@/components/CitationList";
import type { AgentMessage } from "@/types/chat";

interface ChatMessageProps {
  message: AgentMessage;
  isStreaming?: boolean;
}

export function ChatMessage({ message, isStreaming = false }: ChatMessageProps) {
  const isUser = message.role === "user";

  if (isUser) {
    return (
      <div className="flex w-full justify-end">
        <div className="max-w-[80%] rounded-2xl rounded-br-sm bg-primary px-4 py-3 text-sm leading-relaxed text-primary-foreground">
          <p className="whitespace-pre-wrap">{message.content}</p>
        </div>
      </div>
    );
  }

  // Assistant message — render events in order
  return (
    <div className="flex w-full justify-start">
      <div className="max-w-[85%] space-y-1">
        {message.events.map((event, index) => {
          if (event.type === "reasoning" && event.content) {
            return <ReasoningBlock key={index} content={event.content} />;
          }

          if (event.type === "tool_call") {
            // Find the matching tool_result by call_id
            const callId = event.metadata?.call_id as string | undefined;
            const resultEvent = callId
              ? message.events.find(
                  (e) => e.type === "tool_result" && e.metadata?.call_id === callId,
                )
              : undefined;
            return (
              <ToolCallBlock key={index} callChunk={event} resultChunk={resultEvent} />
            );
          }

          // Skip tool_result — rendered inside ToolCallBlock
          if (event.type === "tool_result") return null;

          // Skip done/error — handled at the page level
          if (event.type === "done" || event.type === "error") return null;

          return null;
        })}

        {/* Final answer text */}
        {(message.content || isStreaming) && (
          <div className="rounded-2xl rounded-bl-sm bg-muted px-4 py-3 text-sm leading-relaxed text-foreground">
            <div className="prose prose-sm dark:prose-invert max-w-none">
              <ReactMarkdown>{message.content}</ReactMarkdown>
              {isStreaming && (
                <span className="ml-0.5 inline-block h-4 w-0.5 animate-pulse bg-current" />
              )}
            </div>
            {/* Citations from RAG retrieval */}
            <CitationList events={message.events} />
          </div>
        )}
      </div>
    </div>
  );
}
