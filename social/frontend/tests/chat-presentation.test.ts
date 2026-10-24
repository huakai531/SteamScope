import { describe, expect, it } from "vitest";
import {
  dayKey,
  dayLabel,
  startsMessageGroup,
  presenceLabel,
} from "@/lib/chat-presentation";
import type { ChatMessage } from "@/lib/chat";

const message = (date: string, mine = true) =>
  ({ created_at: date, mine }) as ChatMessage;
describe("message presentation preserves time and permission meaning", () => {
  it("uses local calendar boundaries, including month/year rollover", () => {
    const now = new Date(2027, 0, 1, 0, 5);
    expect(dayLabel(new Date(2027, 0, 1, 0, 1).toISOString(), now)).toBe(
      "Today",
    );
    expect(dayLabel(new Date(2026, 11, 31, 23, 59).toISOString(), now)).toBe(
      "Yesterday",
    );
    expect(dayKey(now)).not.toBe(dayKey(new Date(2026, 11, 31, 23, 59)));
  });
  it("groups only the same author within five minutes on the same day", () => {
    const first = message(new Date(2026, 9, 23, 23, 58).toISOString());
    expect(startsMessageGroup(first)).toBe(true);
    expect(
      startsMessageGroup(
        message(new Date(2026, 9, 23, 23, 59).toISOString()),
        first,
      ),
    ).toBe(false);
    expect(startsMessageGroup(message(first.created_at, false), first)).toBe(
      true,
    );
    expect(
      startsMessageGroup(
        message(new Date(2026, 9, 24, 0, 0).toISOString()),
        first,
      ),
    ).toBe(true);
    expect(
      startsMessageGroup(
        message(new Date(2026, 9, 23, 12, 6).toISOString()),
        message(new Date(2026, 9, 23, 12, 0).toISOString()),
      ),
    ).toBe(true);
  });
  it("does not turn hidden, unavailable or absent presence into offline", () => {
    expect(presenceLabel("online")).toBe("Online");
    expect(presenceLabel("offline")).toBe("Offline");
    for (const value of [undefined, "hidden", "unavailable", "unexpected"]) {
      expect(presenceLabel(value)).toBe("Status unavailable");
    }
  });
});
