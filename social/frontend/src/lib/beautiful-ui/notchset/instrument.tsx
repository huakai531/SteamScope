"use client";
/** Beautiful UI Notchset MIT helpers, reduced to those SteamScope uses. */
export { NOTCHSET_ROOT, OWN_SOUND } from "./root";
export const GLIDE = "cubic-bezier(.2,.8,.2,1)";
export function motionOff(element?: Element | null) {
  return (
    !!element?.closest('[data-motion="off"]') ||
    (typeof window !== "undefined" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches)
  );
}
