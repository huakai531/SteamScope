import { describe, expect, it } from "vitest";
import { mergeMessages, socketURL, type ChatMessage } from "@/lib/chat";

const row = (sequence: number, body = "plain"): ChatMessage => ({
  id: `message-${sequence}`,
  conversation_id: "conversation",
  sequence,
  mine: true,
  client_message_id: `client-${sequence}`,
  body,
  created_at: "2026-10-23T00:00:00Z",
  deleted_at: null,
});

describe("durable chat reconciliation", () => {
  it("deduplicates retried/reordered events while preserving canonical sequence", () => {
    expect(
      mergeMessages([row(2), row(1)], [row(2), row(3)]).map((x) => x.sequence),
    ).toEqual([1, 2, 3]);
  });
  it("replaces historical bodies with deletion tombstones", () => {
    const deleted = {
      ...row(1),
      body: null,
      deleted_at: "2026-10-23T01:00:00Z",
    };
    expect(mergeMessages([row(1, "old content")], [deleted])).toEqual([
      deleted,
    ]);
  });
  it("uses same-origin sockets without credentials or query parameters", () => {
    expect(socketURL("http://127.0.0.1:3100")).toBe(
      "ws://127.0.0.1:3100/api/v1/ws",
    );
    expect(socketURL("https://example.invalid")).toBe(
      "wss://example.invalid/api/v1/ws",
    );
  });
});
