/**
 * CitationList — renders source references from RAG retrieval results.
 *
 * When the agent uses retrieve_documents, the tool result contains
 * source metadata. This component extracts and displays those sources
 * as a compact citation list below the final answer.
 */

import { BookOpen } from "lucide-react";
import type { StreamChunk } from "@/types/chat";

interface CitationListProps {
  events: StreamChunk[];
}

interface Citation {
  source: string;
  score: number;
}

function extractCitations(events: StreamChunk[]): Citation[] {
  const citations: Citation[] = [];
  const seen = new Set<string>();

  for (const event of events) {
    if (event.type !== "tool_result") continue;

    const toolName = event.metadata?.tool_name as string | undefined;
    if (toolName !== "retrieve_documents") continue;

    // Parse sources from the tool result content
    const content = event.content ?? "";
    const sourceMatches = content.matchAll(/\[Source: ([^|]+)\s*\|\s*Score: ([\d.]+)\]/g);

    for (const match of sourceMatches) {
      const source = match[1].trim();
      const score = parseFloat(match[2]);
      if (!seen.has(source)) {
        seen.add(source);
        citations.push({ source, score });
      }
    }
  }

  return citations.sort((a, b) => b.score - a.score);
}

export function CitationList({ events }: CitationListProps) {
  const citations = extractCitations(events);

  if (citations.length === 0) return null;

  return (
    <div className="mt-2 rounded-lg border border-border bg-muted/30 px-3 py-2">
      <div className="mb-1.5 flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
        <BookOpen size={11} />
        <span>Sources</span>
      </div>
      <ul className="space-y-0.5">
        {citations.map((citation, index) => (
          <li key={index} className="flex items-center justify-between text-xs">
            <span className="truncate text-foreground/80">{citation.source}</span>
            <span className="ml-2 shrink-0 text-muted-foreground">
              {(citation.score * 100).toFixed(0)}%
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
