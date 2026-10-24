"use client";
/**
 * Select (Notchset) v1.0.0 · Beautiful UI · MIT
 * Source: https://beautiful-ui.dev/components/select
 * Installed with shadcn 4.21.0; adapted to SteamScope's existing visual system.
 * Unused demo, sound and instrument variants removed. Accessible primitives retained.
 */
import * as React from "react";
import { Select as Primitive } from "@base-ui/react/select";
import { cn } from "@/lib/utils";
import { NOTCHSET_ROOT } from "@/lib/beautiful-ui/notchset/root";

export const Select = Primitive.Root;
export const SelectValue = Primitive.Value;
export function SelectTrigger({
  className,
  children,
  ...props
}: Primitive.Trigger.Props) {
  return (
    <Primitive.Trigger
      {...NOTCHSET_ROOT}
      data-slot="select-trigger"
      className={cn("bui-select-trigger", className)}
      {...props}
    >
      {children}
      <Primitive.Icon>
        <svg
          aria-hidden="true"
          width="16"
          height="16"
          viewBox="0 0 16 16"
          fill="none"
        >
          <path d="m4 6 4 4 4-4" stroke="currentColor" strokeWidth="1.5" />
        </svg>
      </Primitive.Icon>
    </Primitive.Trigger>
  );
}
export function SelectContent({
  children,
  className,
  ...props
}: Primitive.Popup.Props) {
  return (
    <Primitive.Portal>
      <Primitive.Positioner
        sideOffset={7}
        alignItemWithTrigger={false}
        collisionPadding={12}
        className="bui-overlay-positioner"
      >
        <Primitive.Popup
          {...NOTCHSET_ROOT}
          data-slot="select-content"
          className={cn("bui-select-content", className)}
          {...props}
        >
          <Primitive.ScrollUpArrow className="bui-select-scroll">
            ↑
          </Primitive.ScrollUpArrow>
          <Primitive.List>{children}</Primitive.List>
          <Primitive.ScrollDownArrow className="bui-select-scroll">
            ↓
          </Primitive.ScrollDownArrow>
        </Primitive.Popup>
      </Primitive.Positioner>
    </Primitive.Portal>
  );
}
export function SelectItem({
  children,
  className,
  ...props
}: Primitive.Item.Props) {
  return (
    <Primitive.Item
      data-slot="select-item"
      className={cn("bui-select-item", className)}
      {...props}
    >
      <Primitive.ItemText>{children}</Primitive.ItemText>
      <Primitive.ItemIndicator aria-hidden="true">
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
          <path d="m3 8 3 3 7-7" stroke="currentColor" strokeWidth="1.5" />
        </svg>
      </Primitive.ItemIndicator>
    </Primitive.Item>
  );
}
