/**
 * useKnowledge — manages the knowledge base document list.
 *
 * Provides:
 * - documents: list of ingested documents
 * - isLoading: fetch in progress
 * - error: last error message
 * - refresh(): re-fetch the list
 * - remove(id): delete a document and refresh
 */

import { useCallback, useEffect, useState } from "react";
import { deleteDocument, listDocuments } from "@/services/api";
import type { KnowledgeDocument } from "@/services/api";

interface UseKnowledgeReturn {
  documents: KnowledgeDocument[];
  isLoading: boolean;
  isDeleting: string | null;
  error: string | null;
  refresh: () => Promise<void>;
  remove: (documentId: string) => Promise<void>;
}

export function useKnowledge(): UseKnowledgeReturn {
  const [documents, setDocuments] = useState<KnowledgeDocument[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isDeleting, setIsDeleting] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const docs = await listDocuments();
      setDocuments(docs);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load documents");
    } finally {
      setIsLoading(false);
    }
  }, []);

  const remove = useCallback(
    async (documentId: string) => {
      setIsDeleting(documentId);
      setError(null);
      try {
        await deleteDocument(documentId);
        setDocuments((prev) => prev.filter((d) => d.document_id !== documentId));
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to delete document");
      } finally {
        setIsDeleting(null);
      }
    },
    [],
  );

  // Load on mount
  useEffect(() => {
    refresh();
  }, [refresh]);

  return { documents, isLoading, isDeleting, error, refresh, remove };
}
