/**
 * ChatPage — the main chat interface.
 *
 * Wires together useChat hook, message list, input, and knowledge panel.
 * Auto-scrolls to the latest message.
 * PDF/Excel/CSV/image uploads are routed through the RAG ingestion pipeline.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { RotateCcw, Database } from "lucide-react";
import { useChat } from "@/hooks/useChat";
import { ChatMessage } from "@/components/ChatMessage";
import { ChatInput } from "@/components/ChatInput";
import { KnowledgePanel } from "@/components/KnowledgePanel";
import { uploadDocument } from "@/services/api";
import { cn } from "@/lib/utils";

export function ChatPage() {
  const { messages, isStreaming, error, sendMessage, clearSession } = useChat();
  const bottomRef = useRef<HTMLDivElement>(null);
  const [panelOpen, setPanelOpen] = useState(false);
  const [knowledgeRefreshKey, setKnowledgeRefreshKey] = useState(0);

  // Auto-scroll to bottom when messages update
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  /**
   * Handle binary file uploads (PDF, Excel, CSV, images).
   * Sends raw bytes to the backend for server-side extraction.
   * After ingestion, sends a confirmation message and refreshes the panel.
   */
  const handleIngestFile = useCallback(
    async (file: File) => {
      const result = await uploadDocument(file);

      const ext = file.name.slice(file.name.lastIndexOf(".")).toLowerCase();
      const formatLabel: Record<string, string> = {
        ".pdf": "PDF",
        ".xlsx": "Excel spreadsheet",
        ".xls": "Excel spreadsheet",
        ".csv": "CSV file",
        ".png": "image",
        ".jpg": "image",
        ".jpeg": "image",
        ".webp": "image",
        ".tiff": "image",
        ".bmp": "image",
      };
      const label = formatLabel[ext] ?? "file";

      // Refresh the knowledge panel list
      setKnowledgeRefreshKey((k) => k + 1);

      await sendMessage(
        `I've uploaded the ${label} "${file.name}" into the knowledge base ` +
          `(${result.chunk_count.toString()} chunks indexed). You can now ask me questions about its contents.`,
      );
    },
    [sendMessage],
  );

  const isEmpty = messages.length === 0;

  return (
    <div className="flex h-screen flex-col bg-background text-foreground">
      {/* Header */}
      <header className="flex items-center justify-between border-b border-border px-6 py-4">
        <div>
          <h1 className="text-base font-semibold">AI Engineering OS</h1>
          <p className="text-xs text-muted-foreground">Powered by Vertex AI Gemini</p>
        </div>

        <div className="flex items-center gap-2">
          {!isEmpty && (
            <button
              onClick={() => { clearSession(); }}
              aria-label="New session"
              className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
            >
              <RotateCcw size={12} />
              New session
            </button>
          )}

          {/* Knowledge base toggle */}
          <button
            onClick={() => { setPanelOpen((o) => !o); }}
            aria-label="Open knowledge base"
            aria-expanded={panelOpen}
            className={cn(
              "flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs transition-colors",
              panelOpen
                ? "bg-muted text-foreground"
                : "text-muted-foreground hover:bg-muted hover:text-foreground",
            )}
          >
            <Database size={12} />
            Knowledge
          </button>
        </div>
      </header>

      {/* Message list */}
      <main className="flex-1 overflow-y-auto px-4 py-6">
        {isEmpty ? (
          <div className="flex h-full flex-col items-center justify-center gap-3 text-center">
            <div className="rounded-2xl bg-muted p-4">
              <span className="text-3xl">⚙️</span>
            </div>
            <h2 className="text-lg font-medium">AI Engineering Assistant</h2>
            <p className="max-w-sm text-sm text-muted-foreground">
              Ask about your codebase, debug issues, plan architecture, or upload documents to
              query with RAG.
            </p>
          </div>
        ) : (
          <div className="mx-auto flex max-w-3xl flex-col gap-4">
            {messages.map((message, index) => {
              const isLastMessage = index === messages.length - 1;
              const isStreamingThisMessage =
                isStreaming && isLastMessage && message.role === "assistant";

              return (
                <ChatMessage
                  key={index}
                  message={message}
                  isStreaming={isStreamingThisMessage}
                />
              );
            })}
            <div ref={bottomRef} />
          </div>
        )}
      </main>

      {/* Error banner */}
      {error && (
        <div className="mx-4 mb-2 rounded-lg bg-red-50 px-4 py-2 text-sm text-red-600 dark:bg-red-950 dark:text-red-400">
          {error}
        </div>
      )}

      {/* Input */}
      <div className="border-t border-border px-4 py-4">
        <div className="mx-auto max-w-3xl">
          <ChatInput
            onSend={(msg) => { void sendMessage(msg); }}
            onIngestFile={handleIngestFile}
            isDisabled={isStreaming}
          />
          <p className="mt-2 text-center text-xs text-muted-foreground">
            Enter to send · Shift+Enter for newline
          </p>
        </div>
      </div>

      {/* Knowledge base panel */}
      <KnowledgePanel
        key={knowledgeRefreshKey}
        isOpen={panelOpen}
        onClose={() => { setPanelOpen(false); }}
      />
    </div>
  );
}
