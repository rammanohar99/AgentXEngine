/**
 * ReasoningBlock — collapsible agent thought display.
 *
 * Renders the agent's "Thought:" reasoning steps in a subtle,
 * collapsible block so users can inspect the reasoning without
 * it dominating the conversation.
 */

import { useState } from "react";
import { ChevronDown, ChevronRight, Brain } from "lucide-react";

interface ReasoningBlockProps {
  content: string;
}

export function ReasoningBlock({ content }: ReasoningBlockProps) {
  const [isExpanded, setIsExpanded] = useState(false);

  return (
    <div className="my-1 rounded-lg border border-border bg-muted/40 text-xs">
      <button
        onClick={() => setIsExpanded((prev) => !prev)}
        className="flex w-full items-center gap-2 px-3 py-2 text-left text-muted-foreground transition-colors hover:text-foreground"
        aria-expanded={isExpanded}
      >
        <Brain size={12} className="shrink-0" />
        <span className="flex-1 font-medium">Reasoning</span>
        {isExpanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
      </button>
      {isExpanded && (
        <div className="border-t border-border px-3 py-2 text-muted-foreground">
          <p className="whitespace-pre-wrap leading-relaxed">{content}</p>
        </div>
      )}
    </div>
  );
}
