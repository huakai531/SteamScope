import type { components } from "@/lib/api/schema";

export type ChatMessage = components["schemas"]["MessageView"];
export function mergeMessages(
  previous: ChatMessage[],
  incoming: ChatMessage[],
) {
  const rows = new Map(previous.map((row) => [row.id, row]));
  for (const row of incoming) rows.set(row.id, row);
  return [...rows.values()].sort((a, b) => a.sequence - b.sequence);
}
export function socketURL(origin: string) {
  const url = new URL("/api/v1/ws", origin);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  return url.toString();
}
