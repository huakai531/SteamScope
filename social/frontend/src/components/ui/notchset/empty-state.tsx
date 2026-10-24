"use client";
/**
 * Empty State (Notchset) v1.0.0 · Beautiful UI · MIT
 * Source: https://beautiful-ui.dev/components/empty-state
 * Installed with shadcn 4.21.0; adapted to SteamScope's existing visual system.
 * Unused demo, sound and instrument variants removed. Accessible primitives retained.
 */
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";
import { NOTCHSET_ROOT } from "@/lib/beautiful-ui/notchset/root";

export function EmptyState({
  title,
  children,
  actions,
  icon,
  className,
}: {
  title: ReactNode;
  children?: ReactNode;
  actions?: ReactNode;
  icon?: ReactNode;
  className?: string;
}) {
  return (
    <div
      {...NOTCHSET_ROOT}
      data-slot="empty-state"
      className={cn("bui-empty", className)}
    >
      {icon && (
        <span className="bui-empty-icon" aria-hidden="true">
          {icon}
        </span>
      )}
      <h3>{title}</h3>
      {children && <div className="bui-empty-description">{children}</div>}
      {actions && <div className="bui-empty-actions">{actions}</div>}
    </div>
  );
}
