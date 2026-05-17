/**
 * ChatInput — message composition area with file upload support.
 *
 * Binary files (PDF, Excel, CSV, images) are routed through the RAG ingestion
 * pipeline via onIngestFile — their bytes are never read in the browser.
 *
 * Plain text files (code, markdown, etc.) are read inline and appended to the message.
 *
 * Supported upload formats:
 *   PDF   .pdf
 *   Excel .xlsx, .xls
 *   CSV   .csv
 *   Image .png, .jpg, .jpeg, .webp, .tiff, .bmp
 *   Text  .txt, .md, .py, .ts, .tsx, .js, .jsx, .json, .yaml, .yml, .toml, .sh, .sql, .html, .css
 */

import { useCallback, useRef, useState, type KeyboardEvent } from "react";
import { Send, Paperclip, X, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

interface AttachedFile {
  name: string;
  content: string;
  size: number;
}

interface ChatInputProps {
  onSend: (message: string, attachments?: AttachedFile[]) => void;
  /** Called for binary files that must be ingested server-side. */
  onIngestFile?: (file: File) => Promise<void>;
  isDisabled?: boolean;
  placeholder?: string;
}

// Plain text types — safe to read inline in the browser
const TEXT_EXTENSIONS = new Set([
  ".txt", ".md", ".py", ".ts", ".tsx", ".js", ".jsx",
  ".json", ".yaml", ".yml", ".toml", ".sh", ".sql", ".html", ".css",
]);

// Binary types — must be sent to the backend for extraction
const BINARY_EXTENSIONS = new Set([
  ".pdf",
  ".xlsx", ".xls",
  ".csv",
  ".png", ".jpg", ".jpeg", ".webp", ".tiff", ".tif", ".bmp",
]);

const TEXT_ACCEPT = Array.from(TEXT_EXTENSIONS).join(",");
const BINARY_ACCEPT = Array.from(BINARY_EXTENSIONS).join(",");
const ACCEPTED_TYPES = `${TEXT_ACCEPT},${BINARY_ACCEPT}`;

// 10 MB — matches backend limit
const MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024;

function getExt(filename: string): string {
  const idx = filename.lastIndexOf(".");
  return idx !== -1 ? filename.slice(idx).toLowerCase() : "";
}

function isBinary(filename: string): boolean {
  return BINARY_EXTENSIONS.has(getExt(filename));
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes}B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)}KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)}MB`;
}

export function ChatInput({
  onSend,
  onIngestFile,
  isDisabled = false,
  placeholder = "Ask anything about your codebase...",
}: ChatInputProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [attachedFiles, setAttachedFiles] = useState<AttachedFile[]>([]);
  const [fileError, setFileError] = useState<string | null>(null);
  const [ingestingFile, setIngestingFile] = useState<string | null>(null);

  const handleSubmit = useCallback(() => {
    const value = textareaRef.current?.value.trim();
    if ((!value && attachedFiles.length === 0) || isDisabled) return;

    let message = value ?? "";
    if (attachedFiles.length > 0) {
      const fileContext = attachedFiles
        .map((f) => `\n\n--- ${f.name} ---\n${f.content}`)
        .join("");
      message = message ? message + fileContext : fileContext.trim();
    }

    onSend(message, attachedFiles);

    if (textareaRef.current) {
      textareaRef.current.value = "";
      textareaRef.current.style.height = "auto";
    }
    setAttachedFiles([]);
    setFileError(null);
  }, [onSend, isDisabled, attachedFiles]);

  const handleKeyDown = useCallback(
    (event: KeyboardEvent<HTMLTextAreaElement>) => {
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        handleSubmit();
      }
    },
    [handleSubmit],
  );

  const handleInput = useCallback(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    textarea.style.height = "auto";
    textarea.style.height = `${Math.min(textarea.scrollHeight, 200)}px`;
  }, []);

  const handleFileChange = useCallback(
    async (event: React.ChangeEvent<HTMLInputElement>) => {
      const files = Array.from(event.target.files ?? []);
      setFileError(null);

      const newAttachments: AttachedFile[] = [];

      for (const file of files) {
        if (file.size > MAX_FILE_SIZE_BYTES) {
          setFileError(`${file.name} is too large (max ${formatBytes(MAX_FILE_SIZE_BYTES)})`);
          continue;
        }

        if (isBinary(file.name)) {
          // Binary files — send raw bytes to backend for extraction
          if (!onIngestFile) {
            setFileError("File ingestion is not available. Please configure the RAG pipeline.");
            continue;
          }
          setIngestingFile(file.name);
          try {
            await onIngestFile(file);
          } catch (err) {
            setFileError(
              `Failed to ingest ${file.name}: ${err instanceof Error ? err.message : String(err)}`,
            );
          } finally {
            setIngestingFile(null);
          }
          continue;
        }

        // Plain text files — safe to read inline
        try {
          const content = await file.text();
          newAttachments.push({ name: file.name, content, size: file.size });
        } catch {
          setFileError(`Failed to read ${file.name}`);
        }
      }

      setAttachedFiles((prev) => [...prev, ...newAttachments]);

      // Reset so the same file can be re-attached
      if (fileInputRef.current) fileInputRef.current.value = "";
    },
    [onIngestFile],
  );

  const removeAttachment = useCallback((index: number) => {
    setAttachedFiles((prev) => prev.filter((_, i) => i !== index));
  }, []);

  const isBusy = isDisabled || ingestingFile !== null;

  return (
    <div className="space-y-2">
      {/* Ingestion progress */}
      {ingestingFile && (
        <div className="flex items-center gap-2 rounded-md bg-blue-50 px-3 py-2 text-xs text-blue-700 dark:bg-blue-950 dark:text-blue-300">
          <Loader2 size={12} className="animate-spin shrink-0" />
          <span>
            Ingesting <strong>{ingestingFile}</strong> into the knowledge base…
          </span>
        </div>
      )}

      {/* Attached text file chips */}
      {attachedFiles.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {attachedFiles.map((file, index) => (
            <div
              key={index}
              className="flex items-center gap-1 rounded-md bg-muted px-2 py-1 text-xs text-muted-foreground"
            >
              <span className="max-w-[120px] truncate">{file.name}</span>
              <span className="text-muted-foreground/60">({formatBytes(file.size)})</span>
              <button
                onClick={() => removeAttachment(index)}
                aria-label={`Remove ${file.name}`}
                className="ml-0.5 rounded hover:text-foreground"
              >
                <X size={10} />
              </button>
            </div>
          ))}
        </div>
      )}

      {/* File error */}
      {fileError && <p className="text-xs text-red-500">{fileError}</p>}

      {/* Input row */}
      <div className="flex items-end gap-2 rounded-2xl border border-border bg-background p-3 shadow-sm">
        {/* File upload button */}
        <button
          onClick={() => fileInputRef.current?.click()}
          disabled={isBusy}
          aria-label="Attach file"
          title="Attach file (PDF, Excel, CSV, image, or text)"
          className={cn(
            "flex h-8 w-8 shrink-0 items-center justify-center rounded-xl text-muted-foreground transition-colors",
            isBusy ? "opacity-40 cursor-not-allowed" : "hover:bg-muted hover:text-foreground",
          )}
        >
          {ingestingFile ? (
            <Loader2 size={14} className="animate-spin" />
          ) : (
            <Paperclip size={14} />
          )}
        </button>

        <input
          ref={fileInputRef}
          type="file"
          accept={ACCEPTED_TYPES}
          multiple
          className="hidden"
          onChange={handleFileChange}
          aria-label="File upload"
        />

        <textarea
          ref={textareaRef}
          rows={1}
          placeholder={placeholder}
          disabled={isBusy}
          onKeyDown={handleKeyDown}
          onInput={handleInput}
          className={cn(
            "flex-1 resize-none bg-transparent text-sm outline-none placeholder:text-muted-foreground",
            "max-h-[200px] leading-relaxed",
            isBusy && "opacity-50 cursor-not-allowed",
          )}
        />

        <button
          onClick={handleSubmit}
          disabled={isBusy}
          aria-label="Send message"
          className={cn(
            "flex h-8 w-8 shrink-0 items-center justify-center rounded-xl",
            "bg-primary text-primary-foreground transition-opacity",
            isBusy ? "opacity-40 cursor-not-allowed" : "hover:opacity-80",
          )}
        >
          <Send size={14} />
        </button>
      </div>
    </div>
  );
}
