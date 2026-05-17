/**
 * AlertDialog — accessible confirmation modal built on Radix UI.
 *
 * Usage:
 *   <AlertDialog
 *     open={open}
 *     onOpenChange={setOpen}
 *     title="Delete document?"
 *     description="This will permanently remove..."
 *     confirmLabel="Delete"
 *     confirmVariant="danger"
 *     onConfirm={handleDelete}
 *     isLoading={isDeleting}
 *   />
 */

import * as RadixAlertDialog from "@radix-ui/react-alert-dialog";
import { Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

interface AlertDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description: React.ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  confirmVariant?: "danger" | "primary";
  onConfirm: () => void;
  isLoading?: boolean;
}

export function AlertDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  confirmVariant = "primary",
  onConfirm,
  isLoading = false,
}: AlertDialogProps) {
  return (
    <RadixAlertDialog.Root open={open} onOpenChange={onOpenChange}>
      <RadixAlertDialog.Portal>
        {/* Overlay */}
        <RadixAlertDialog.Overlay
          className={cn(
            "fixed inset-0 z-50 bg-black/50 backdrop-blur-sm",
            "data-[state=open]:animate-in data-[state=closed]:animate-out",
            "data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0",
          )}
        />

        {/* Content */}
        <RadixAlertDialog.Content
          className={cn(
            "fixed left-1/2 top-1/2 z-50 w-full max-w-md -translate-x-1/2 -translate-y-1/2",
            "rounded-xl border border-border bg-background p-6 shadow-xl",
            "data-[state=open]:animate-in data-[state=closed]:animate-out",
            "data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0",
            "data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95",
            "data-[state=closed]:slide-out-to-left-1/2 data-[state=closed]:slide-out-to-top-[48%]",
            "data-[state=open]:slide-in-from-left-1/2 data-[state=open]:slide-in-from-top-[48%]",
          )}
        >
          {/* Icon + Title */}
          <div className="flex items-start gap-4">
            {confirmVariant === "danger" && (
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-red-100 dark:bg-red-950">
                <svg
                  className="h-5 w-5 text-red-600 dark:text-red-400"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                  strokeWidth={2}
                  aria-hidden="true"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z"
                  />
                </svg>
              </div>
            )}

            <div className="flex-1">
              <RadixAlertDialog.Title className="text-base font-semibold text-foreground">
                {title}
              </RadixAlertDialog.Title>
              <RadixAlertDialog.Description className="mt-2 text-sm text-muted-foreground">
                {description}
              </RadixAlertDialog.Description>
            </div>
          </div>

          {/* Actions */}
          <div className="mt-6 flex justify-end gap-3">
            <RadixAlertDialog.Cancel asChild>
              <button
                disabled={isLoading}
                className={cn(
                  "rounded-lg border border-border px-4 py-2 text-sm font-medium",
                  "text-foreground transition-colors hover:bg-muted",
                  "disabled:opacity-50 disabled:cursor-not-allowed",
                )}
              >
                {cancelLabel}
              </button>
            </RadixAlertDialog.Cancel>

            <RadixAlertDialog.Action asChild>
              <button
                onClick={onConfirm}
                disabled={isLoading}
                className={cn(
                  "flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition-colors",
                  "disabled:opacity-50 disabled:cursor-not-allowed",
                  confirmVariant === "danger"
                    ? "bg-red-600 text-white hover:bg-red-700 dark:bg-red-700 dark:hover:bg-red-600"
                    : "bg-primary text-primary-foreground hover:opacity-90",
                )}
              >
                {isLoading && <Loader2 size={14} className="animate-spin" />}
                {confirmLabel}
              </button>
            </RadixAlertDialog.Action>
          </div>
        </RadixAlertDialog.Content>
      </RadixAlertDialog.Portal>
    </RadixAlertDialog.Root>
  );
}
