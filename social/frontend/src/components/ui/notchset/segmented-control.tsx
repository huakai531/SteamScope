"use client";

/**
 * Segmented Control (Notchset) v1.0.0 · Beautiful UI
 * Docs: https://beautiful-ui.dev/components/segmented-control
 * MIT licensed: free to use, change and share.
 */

import * as React from "react";
import { cn } from "@/lib/utils";
import {
  NOTCHSET_ROOT,
  OWN_SOUND,
  motionOff,
  GLIDE,
} from "@/lib/beautiful-ui/notchset/instrument";

/*
 * Notchset Segmented Control (no primitive, one file for both builds). Equal segments on
 * a track; the ink thumb's edges are computed (right on the first frame) and stretch: the leading edge
 * moves first, the trailing edge 80ms later (340ms). Inside the thumb, a strip of on-ink labels moves
 * with the thumb's left edge, so the label colour flips exactly where the edge passes. The muted labels
 * underneath are the real radios: arrow keys move, roving tabindex.
 */

function SegmentedControl({
  options,
  value,
  onValueChange,
  size = "default",
  segment,
  fill = false,
  className,
  "aria-label": ariaLabel,
}: {
  options: readonly { value: string; label: string }[];
  value: string;
  onValueChange: (value: string) => void;
  /** 40px (104px segments) or 28px (60px segments). */
  size?: "default" | "sm";
  /** Segment width in px, if not the size's. */
  segment?: number;
  /** Fill the container's width with equal segments (they shrink with it) instead of fixed ones. */
  fill?: boolean;
  className?: string;
  "aria-label"?: string;
}) {
  const group = React.useRef<HTMLDivElement>(null);
  const n = options.length;
  // Segments are equal and never narrower than the longest label: 1fr columns in a shrink-to-fit grid all
  // take the widest label's width (layout measures it; no per-font guess), and `segment` is the minimum.
  const w = segment ?? (size === "sm" ? 60 : 104);
  // No option matches (a custom value elsewhere): nothing is checked and the thumb hides, so pressing
  // any option, the first included, chooses it.
  const sel = options.findIndex((o) => o.value === value);
  const i = Math.max(0, sel);
  const [dir, setDir] = React.useState(1);
  const set = (k: number) => {
    const o = options[k];
    if (!o || k === sel) return;
    setDir(k > i ? 1 : -1);
    onValueChange(o.value);
  };
  const tl = `340ms ${GLIDE} ${dir > 0 ? 80 : 0}ms`;
  const tr = `340ms ${GLIDE} ${dir > 0 ? 0 : 80}ms`;
  const h = size === "sm" ? "min-h-7" : "min-h-10";
  const fs = "text-[11px]";
  // Fixed segments keep their natural size, every label on one line. When the container is narrower than
  // the control (a phone), the control scrolls sideways inside its own box, like a tab strip, so a label
  // is never squeezed, broken or cut and the page never scrolls sideways. Filling segments share the
  // container instead, and a label longer than its share wraps onto a second line.
  const label = fill
    ? "py-1 text-center leading-[1.2] [text-wrap:balance]"
    : "whitespace-nowrap";
  // Keep the chosen segment in view when the control has scrolled.
  React.useEffect(() => {
    const box = group.current;
    const b = box?.querySelectorAll<HTMLElement>("[role=radio]")[i];
    if (!box || !b || fill || box.scrollWidth <= box.clientWidth) return;
    const left = b.offsetLeft - 8;
    const right = b.offsetLeft + b.offsetWidth + 8 - box.clientWidth;
    if (left < box.scrollLeft)
      box.scrollTo({ left, behavior: motionOff(box) ? "auto" : "smooth" });
    else if (right > box.scrollLeft)
      box.scrollTo({
        left: right,
        behavior: motionOff(box) ? "auto" : "smooth",
      });
  }, [i, fill]);
  return (
    <div
      {...NOTCHSET_ROOT}
      ref={group}
      role="radiogroup"
      aria-label={ariaLabel}
      data-slot="segmented-control"
      data-wraps={fill || undefined}
      onKeyDown={(e) => {
        // Arrows follow what you see: in a right-to-left layout → moves back.
        const rtl = getComputedStyle(e.currentTarget).direction === "rtl";
        const fwd = rtl ? "ArrowLeft" : "ArrowRight";
        const back = rtl ? "ArrowRight" : "ArrowLeft";
        const d =
          e.key === fwd || e.key === "ArrowDown"
            ? 1
            : e.key === back || e.key === "ArrowUp"
              ? -1
              : 0;
        if (!d && e.key !== "Home" && e.key !== "End") return;
        e.preventDefault();
        const k =
          e.key === "Home" ? 0 : e.key === "End" ? n - 1 : (i + d + n) % n;
        set(k);
        group.current
          ?.querySelectorAll<HTMLElement>("[role=radio]")
          [k]?.focus();
      }}
      className={cn(
        fill
          ? "flex w-full min-w-0"
          : "inline-flex max-w-full overflow-x-auto overscroll-x-contain align-middle [scrollbar-width:none] [&::-webkit-scrollbar]:hidden",
        h,
        className,
      )}
    >
      <div
        data-slot="segmented-control-track"
        className={cn(
          "relative box-border border border-solid border-[var(--notchset-control-edge,var(--input))] p-[3px]",
          fill ? "grid w-full min-w-0" : "inline-grid flex-none",
        )}
        style={{
          gridTemplateColumns: fill
            ? `repeat(${n}, minmax(0, 1fr))`
            : `repeat(${n}, minmax(${w}px, 1fr))`,
        }}
      >
        {options.map((o, k) => (
          <button
            key={o.value}
            {...OWN_SOUND}
            type="button"
            role="radio"
            aria-checked={k === sel}
            tabIndex={k === i ? 0 : -1}
            onClick={() => set(k)}
            className={cn(
              `notchset-focus`,
              "relative z-0 flex h-full min-w-0 cursor-pointer items-center justify-center overflow-hidden border-0 bg-transparent px-2.5 font-sans font-medium text-muted-foreground transition-colors duration-(--notchset-fade) ease-(--notchset-ease-fade) hover:text-foreground",
              fs,
              label,
            )}
          >
            {o.label}
          </button>
        ))}
        <span
          aria-hidden
          className="pointer-events-none absolute inset-y-[3px] z-[1] overflow-hidden bg-foreground"
          style={{
            // Segments are equal, so the thumb is placed in shares of the track (less its 3px padding).
            insetInlineStart: `calc(3px + ${i} * (100% - 6px) / ${n})`,
            insetInlineEnd: `calc(3px + ${n - 1 - i} * (100% - 6px) / ${n})`,
            opacity: sel < 0 ? 0 : 1,
            transition: `inset-inline-start ${tl}, inset-inline-end ${tr}, opacity 120ms linear`,
          }}
        >
          <span
            className="absolute inset-y-0 grid"
            style={{
              insetInlineStart: `${-i * 100}%`,
              width: `${n * 100}%`,
              gridTemplateColumns: `repeat(${n}, minmax(0, 1fr))`,
              transition: `inset-inline-start ${tl}`,
            }}
          >
            {options.map((o) => (
              <span
                key={o.value}
                className={cn(
                  "flex min-w-0 items-center justify-center overflow-hidden px-2.5 font-sans font-medium text-background",
                  fs,
                  label,
                )}
              >
                {o.label}
              </span>
            ))}
          </span>
        </span>
      </div>
    </div>
  );
}

export { SegmentedControl };
