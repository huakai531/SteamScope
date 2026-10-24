"use client";
import { useRef, type ReactNode } from "react";
import { Button } from "./ui/notchset/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "./ui/notchset/dialog";

export function ConfirmDialog({
  open,
  onClose,
  onConfirm,
  title,
  children,
  confirmLabel,
  cancelLabel = "Cancel",
  busy = false,
  label,
}: {
  open: boolean;
  onClose: () => void;
  onConfirm: () => void | Promise<void>;
  title: string;
  children: ReactNode;
  confirmLabel: string;
  cancelLabel?: string;
  busy?: boolean;
  label?: string;
}) {
  const cancel = useRef<HTMLButtonElement>(null);
  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next && !busy) onClose();
      }}
    >
      <DialogContent initialFocus={cancel} aria-label={label}>
        <DialogTitle>{title}</DialogTitle>
        <DialogDescription>{children}</DialogDescription>
        <div className="bui-dialog-actions">
          <Button
            ref={cancel}
            variant="secondary"
            disabled={busy}
            onClick={onClose}
          >
            {cancelLabel}
          </Button>
          <Button
            variant="destructive"
            loading={busy}
            onClick={() => void onConfirm()}
          >
            {confirmLabel}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
