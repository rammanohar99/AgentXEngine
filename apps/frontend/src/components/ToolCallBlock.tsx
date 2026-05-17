/**
 * ToolCallBlock — renders a tool invocation and its result.
 *
 * Shows:
 * - Tool name and arguments (collapsible)
 * - Result output (collapsible, shown after result arrives)
 * - Success/failure status
 * - Duration
 */

import { useState } from "react";
import { ChevronDown, ChevronRight, Wrench, CheckCircle, XCircle } from "lucide-react";
import { cn } from "@/lib/utils";
import type { StreamChunk } from "@/types/chat";

interface ToolCallBlockProps {
  callChunk: StreamChunk;
  resultChunk?: StreamChunk;
}

export function ToolCallBlock({ callChunk, resultChunk }: ToolCallBlockProps) {
  const [isExpanded, setIsExpanded] = useState(false);

  const toolName = (callChunk.metadata?.tool_name as string | undefined) ?? "unknown";
  const args = callChunk.metadata?.arguments as Record<string, unknown> | undefined;
  const isSuccess = resultChunk?.metadata?.success as boolean | undefined;
  const durationMs = resultChunk?.metadata?.duration_ms as number | undefined;
  const isPending = resultChunk === undefined;

  return (
    <div
      className={cn(
        "my-1 rounded-lg border text-xs",
        isPending
          ? "border-border bg-muted/30"
          : isSuccess
            ? "border-green-200 bg-green-50 dark:border-green-900 dark:bg-green-950/30"
            : "border-red-200 bg-red-50 dark:border-red-900 dark:bg-red-950/30",
      )}
    >
      {/* Header row */}
      <button
        onClick={() => { setIsExpanded((prev) => !prev); }}
        className="flex w-full items-center gap-2 px-3 py-2 text-left transition-colors hover:opacity-80"
        aria-expanded={isExpanded}
      >
        <Wrench size={12} className="shrink-0 text-muted-foreground" />
        <span className="flex-1 font-mono font-medium text-foreground">{toolName}</span>

        {isPending && (
          <span className="text-muted-foreground animate-pulse">running…</span>
        )}
        {!isPending && isSuccess && (
          <CheckCircle size={12} className="text-green-600 dark:text-green-400" />
        )}
        {!isPending && !isSuccess && (
          <XCircle size={12} className="text-red-600 dark:text-red-400" />
        )}
        {durationMs !== undefined && (
          <span className="text-muted-foreground">{durationMs.toString()}ms</span>
        )}
        {isExpanded ? (
          <ChevronDown size={12} className="text-muted-foreground" />
        ) : (
          <ChevronRight size={12} className="text-muted-foreground" />
        )}
      </button>

      {/* Expanded detail */}
      {isExpanded && (
        <div className="border-t border-border space-y-2 px-3 py-2">
          {args && Object.keys(args).length > 0 && (
            <div>
              <p className="mb-1 font-medium text-muted-foreground">Arguments</p>
              <pre className="overflow-x-auto rounded bg-muted p-2 text-foreground">
                {JSON.stringify(args, null, 2)}
              </pre>
            </div>
          )}
          {resultChunk?.content && (
            <div>
              <p className="mb-1 font-medium text-muted-foreground">
                {isSuccess ? "Output" : "Error"}
              </p>
              <pre className="max-h-48 overflow-y-auto overflow-x-auto rounded bg-muted p-2 text-foreground whitespace-pre-wrap">
                {resultChunk.content}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
