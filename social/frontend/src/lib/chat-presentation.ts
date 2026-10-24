import type { ChatMessage } from "./chat";

// Display-only helpers. Message ordering, read state and authorization stay in
// the existing chat flow; calendar grouping uses the viewer's local timezone.
export function dayKey(value: string | Date) {
  const date = new Date(value);
  return `${date.getFullYear()}-${date.getMonth()}-${date.getDate()}`;
}
export function clockTime(value: string) {
  return new Date(value).toLocaleTimeString(undefined, {
    hour: "numeric",
    minute: "2-digit",
  });
}
export function dayLabel(value: string, now = new Date()) {
  if (dayKey(value) === dayKey(now)) return "Today";
  const yesterday = new Date(
    now.getFullYear(),
    now.getMonth(),
    now.getDate() - 1,
  );
  if (dayKey(value) === dayKey(yesterday)) return "Yesterday";
  return new Date(value).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}
export function conversationTime(value: string, now = new Date()) {
  return dayKey(value) === dayKey(now)
    ? clockTime(value)
    : new Date(value).toLocaleDateString(undefined, {
        month: "short",
        day: "numeric",
      });
}
export function startsMessageGroup(
  current: ChatMessage,
  previous?: ChatMessage,
) {
  return (
    !previous ||
    current.mine !== previous.mine ||
    dayKey(current.created_at) !== dayKey(previous.created_at) ||
    new Date(current.created_at).getTime() -
      new Date(previous.created_at).getTime() >
      300_000
  );
}
export function presenceLabel(value?: string) {
  if (value === "online") return "Online";
  if (value === "offline") return "Offline";
  return "Status unavailable";
}
