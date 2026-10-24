"use client";
/**
 * Dropdown Menu (Notchset) v1.0.0 · Beautiful UI · MIT
 * Source: https://beautiful-ui.dev/components/dropdown-menu
 * Installed with shadcn 4.21.0; adapted to SteamScope's existing visual system.
 * Unused demo, sound and instrument variants removed. Accessible primitives retained.
 */
import * as React from "react";
import { Menu as Primitive } from "@base-ui/react/menu";
import { cn } from "@/lib/utils";
import { NOTCHSET_ROOT } from "@/lib/beautiful-ui/notchset/root";

export const DropdownMenu = Primitive.Root;
export function DropdownMenuTrigger(props: Primitive.Trigger.Props) {
  return <Primitive.Trigger data-slot="dropdown-menu-trigger" {...props} />;
}
export function DropdownMenuContent({
  children,
  className,
  align = "end",
  ...props
}: Primitive.Popup.Props & { align?: "start" | "center" | "end" }) {
  return (
    <Primitive.Portal>
      <Primitive.Positioner
        sideOffset={7}
        align={align}
        collisionPadding={12}
        className="bui-overlay-positioner"
      >
        <Primitive.Popup
          {...NOTCHSET_ROOT}
          data-slot="dropdown-menu-content"
          className={cn("bui-menu", className)}
          {...props}
        >
          {children}
        </Primitive.Popup>
      </Primitive.Positioner>
    </Primitive.Portal>
  );
}
export function DropdownMenuItem({
  className,
  ...props
}: Primitive.Item.Props) {
  return (
    <Primitive.Item
      data-slot="dropdown-menu-item"
      className={cn("bui-menu-item", className)}
      {...props}
    />
  );
}
