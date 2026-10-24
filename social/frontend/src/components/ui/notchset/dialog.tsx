"use client";
/**
 * Dialog (Notchset) v1.0.0 · Beautiful UI · MIT
 * Source: https://beautiful-ui.dev/components/dialog
 * Installed with shadcn 4.21.0; adapted to SteamScope's existing visual system.
 * Unused demo, sound and instrument variants removed. Accessible primitives retained.
 */
import * as React from "react";
import { Dialog as Primitive } from "@base-ui/react/dialog";
import { cn } from "@/lib/utils";
import { NOTCHSET_ROOT } from "@/lib/beautiful-ui/notchset/root";

export const Dialog = Primitive.Root;
export const DialogTrigger = Primitive.Trigger;
export const DialogClose = Primitive.Close;
export function DialogContent({
  className,
  children,
  ...props
}: Primitive.Popup.Props) {
  return (
    <Primitive.Portal>
      <Primitive.Backdrop
        data-slot="dialog-overlay"
        className="bui-dialog-overlay"
      />
      <Primitive.Popup
        {...NOTCHSET_ROOT}
        data-slot="dialog-content"
        className={cn("bui-dialog", className)}
        {...props}
      >
        {children}
      </Primitive.Popup>
    </Primitive.Portal>
  );
}
export function DialogTitle(props: Primitive.Title.Props) {
  return <Primitive.Title data-slot="dialog-title" {...props} />;
}
export function DialogDescription(props: Primitive.Description.Props) {
  return <Primitive.Description data-slot="dialog-description" {...props} />;
}
