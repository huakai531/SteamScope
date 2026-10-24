import { cn } from "@/lib/utils";

/*
 * Beautiful UI / Notchset field classes · MIT, adapted for SteamScope.
 * Server-safe structural utilities. Colors, typography and focus are owned by
 * beautiful-ui.css; the original instrument gradient and monospace were removed.
 */

/** Preserve a system focus outline in Windows forced-colors mode. */
const TRACE =
  "forced-colors:focus:outline forced-colors:focus:outline-2 forced-colors:focus:outline-offset-2 forced-colors:focus:outline-[Highlight]";

export const inputClass = cn(
  "flex h-10 w-full min-w-0 border border-solid border-[var(--notchset-control-edge,var(--input))] bg-background px-3 py-0 font-sans text-sm text-foreground outline-none",
  "caret-[var(--notchset-signal,var(--destructive))] selection:bg-[var(--notchset-tint,color-mix(in_oklab,var(--destructive)_18%,transparent))] placeholder:text-muted-foreground",
  "hover:border-foreground focus:border-foreground aria-invalid:border-[var(--notchset-signal-text,var(--destructive))]",
  "disabled:cursor-not-allowed disabled:border-[var(--notchset-rule,var(--border))] disabled:opacity-40",
  "file:inline-flex file:h-full file:border-0 file:bg-transparent file:font-sans file:text-sm file:font-medium file:text-foreground",
  "pointer-coarse:h-11",
  TRACE,
);

export const textareaClass = cn(
  "flex field-sizing-content min-h-24 w-full border border-solid border-[var(--notchset-control-edge,var(--input))] bg-background px-3 pt-[11px] pb-1.5 font-sans text-sm leading-[1.5] text-foreground outline-none",
  "caret-[var(--notchset-signal,var(--destructive))] selection:bg-[var(--notchset-tint,color-mix(in_oklab,var(--destructive)_18%,transparent))] placeholder:text-muted-foreground",
  "hover:border-foreground focus:border-foreground aria-invalid:border-[var(--notchset-signal-text,var(--destructive))]",
  "disabled:cursor-not-allowed disabled:border-[var(--notchset-rule,var(--border))] disabled:opacity-40",
  TRACE,
);
