/**
 * KnowledgePanel — slide-in panel showing all ingested documents.
 *
 * Features:
 * - Lists every document in the knowledge base (name, type, chunks, date)
 * - Delete button opens a confirmation AlertDialog modal
 * - Refresh button
 * - File type icon based on source_type
 * - Empty state when no documents are ingested
 */

import { useState } from "react";
import {
  X,
  RefreshCw,
  Trash2,
  FileText,
  FileSpreadsheet,
  Image,
  File,
  Loader2,
  Database,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { AlertDialog } from "@/components/ui/AlertDialog";
import { useKnowledge } from "@/hooks/useKnowledge";
import type { KnowledgeDocument } from "@/services/api";

interface KnowledgePanelProps {
  isOpen: boolean;
  onClose: () => void;
}

function FileIcon({ sourceType }: { sourceType: string }) {
  switch (sourceType) {
    case "pdf":
      return <FileText size={15} className="shrink-0 text-red-500" />;
    case "excel":
      return <FileSpreadsheet size={15} className="shrink-0 text-green-600" />;
    case "csv":
      return <FileSpreadsheet size={15} className="shrink-0 text-blue-500" />;
    case "image":
      return <Image size={15} className="shrink-0 text-purple-500" />;
    default:
      return <File size={15} className="shrink-0 text-muted-foreground" />;
  }
}

function sourceTypeLabel(t: string): string {
  const map: Record<string, string> = {
    pdf: "PDF",
    excel: "Excel",
    csv: "CSV",
    image: "Image",
    text: "Text",
  };
  return map[t] ?? t;
}

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString(undefined, {
      month: "short",
      day: "numeric",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

function DocumentRow({
  doc,
  isDeleting,
  onDeleteRequest,
}: {
  doc: KnowledgeDocument;
  isDeleting: boolean;
  onDeleteRequest: (doc: KnowledgeDocument) => void;
}) {
  return (
    <div className="flex items-start gap-3 rounded-lg border border-border bg-card p-3 transition-colors hover:bg-muted/40">
      <div className="mt-0.5">
        <FileIcon sourceType={doc.source_type} />
      </div>

      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium text-foreground" title={doc.source}>
          {doc.source}
        </p>
        <div className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs text-muted-foreground">
          <span className="rounded bg-muted px-1.5 py-0.5 font-medium">
            {sourceTypeLabel(doc.source_type)}
          </span>
          <span>{doc.chunk_count} chunk{doc.chunk_count !== 1 ? "s" : ""}</span>
          <span>·</span>
          <span>{formatDate(doc.created_at)}</span>
        </div>
      </div>

      <button
        onClick={() => onDeleteRequest(doc)}
        disabled={isDeleting}
        aria-label={`Delete ${doc.source}`}
        title="Remove from knowledge base"
        className={cn(
          "flex h-7 w-7 shrink-0 items-center justify-center rounded-md",
          "text-muted-foreground transition-colors hover:bg-red-50 hover:text-red-600",
          "dark:hover:bg-red-950 dark:hover:text-red-400",
          isDeleting && "opacity-40 cursor-not-allowed",
        )}
      >
        {isDeleting ? (
          <Loader2 size={13} className="animate-spin" />
        ) : (
          <Trash2 size={13} />
        )}
      </button>
    </div>
  );
}

export function KnowledgePanel({ isOpen, onClose }: KnowledgePanelProps) {
  const { documents, isLoading, isDeleting, error, refresh, remove } = useKnowledge();
  const [pendingDelete, setPendingDelete] = useState<KnowledgeDocument | null>(null);

  const handleDeleteRequest = (doc: KnowledgeDocument) => {
    setPendingDelete(doc);
  };

  const handleDeleteConfirm = async () => {
    if (!pendingDelete) return;
    await remove(pendingDelete.document_id);
    setPendingDelete(null);
  };

  return (
    <>
      {/* Backdrop */}
      {isOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/20 backdrop-blur-sm"
          onClick={onClose}
          aria-hidden="true"
        />
      )}

      {/* Slide-in panel */}
      <aside
        className={cn(
          "fixed right-0 top-0 z-50 flex h-full w-80 flex-col border-l border-border bg-background shadow-xl",
          "transition-transform duration-300 ease-in-out",
          isOpen ? "translate-x-0" : "translate-x-full",
        )}
        aria-label="Knowledge base"
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-border px-4 py-4">
          <div className="flex items-center gap-2">
            <Database size={15} className="text-muted-foreground" />
            <h2 className="text-sm font-semibold">Knowledge Base</h2>
            {documents.length > 0 && (
              <span className="rounded-full bg-muted px-1.5 py-0.5 text-xs text-muted-foreground">
                {documents.length}
              </span>
            )}
          </div>
          <div className="flex items-center gap-1">
            <button
              onClick={refresh}
              disabled={isLoading}
              aria-label="Refresh"
              title="Refresh list"
              className="flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground disabled:opacity-40"
            >
              <RefreshCw size={13} className={cn(isLoading && "animate-spin")} />
            </button>
            <button
              onClick={onClose}
              aria-label="Close panel"
              className="flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
            >
              <X size={14} />
            </button>
          </div>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-4">
          {error && (
            <div className="mb-3 rounded-md bg-red-50 px-3 py-2 text-xs text-red-600 dark:bg-red-950 dark:text-red-400">
              {error}
            </div>
          )}

          {/* Loading skeleton */}
          {isLoading && documents.length === 0 && (
            <div className="space-y-2">
              {[1, 2, 3].map((i) => (
                <div key={i} className="h-16 animate-pulse rounded-lg bg-muted" />
              ))}
            </div>
          )}

          {/* Empty state */}
          {!isLoading && documents.length === 0 && !error && (
            <div className="flex flex-col items-center justify-center gap-3 py-16 text-center">
              <div className="rounded-2xl bg-muted p-4">
                <Database size={24} className="text-muted-foreground" />
              </div>
              <p className="text-sm font-medium">No documents yet</p>
              <p className="max-w-[200px] text-xs text-muted-foreground">
                Upload a PDF, Excel, CSV, or image using the paperclip button in the chat.
              </p>
            </div>
          )}

          {/* Document list */}
          {documents.length > 0 && (
            <div className="space-y-2">
              {documents.map((doc) => (
                <DocumentRow
                  key={doc.document_id}
                  doc={doc}
                  isDeleting={isDeleting === doc.document_id}
                  onDeleteRequest={handleDeleteRequest}
                />
              ))}
            </div>
          )}
        </div>
      </aside>

      {/* Delete confirmation modal — rendered outside the panel so it's always on top */}
      <AlertDialog
        open={pendingDelete !== null}
        onOpenChange={(open) => { if (!open) setPendingDelete(null); }}
        title="Remove from knowledge base?"
        description={
          pendingDelete ? (
            <span>
              <strong className="font-medium text-foreground">{pendingDelete.source}</strong>
              {" "}will be permanently removed along with all{" "}
              <strong className="font-medium text-foreground">
                {pendingDelete.chunk_count} chunk{pendingDelete.chunk_count !== 1 ? "s" : ""}
              </strong>
              . The agent will no longer be able to answer questions about this document.
              <br /><br />
              This action cannot be undone.
            </span>
          ) : null
        }
        confirmLabel="Yes, remove it"
        cancelLabel="Keep it"
        confirmVariant="danger"
        onConfirm={handleDeleteConfirm}
        isLoading={isDeleting === pendingDelete?.document_id}
      />
    </>
  );
}
