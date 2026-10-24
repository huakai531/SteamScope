import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { minutes, stateLabel, ProgressSummary } from "@/components/player-app";

test("unknown, confirmed zero and historical state remain distinct", () => {
  expect(minutes(null)).toBe("Unknown");
  expect(minutes(0)).toBe("0 min · 0.0 h");
  expect(minutes(456)).toBe("456 min · 7.6 h");
  expect(
    stateLabel({
      stale: false,
      in_progress: false,
      data_available: true,
      status: "empty",
    }),
  ).toBe("Confirmed empty");
  expect(
    stateLabel({
      stale: true,
      in_progress: false,
      data_available: false,
      status: "populated",
    }),
  ).toContain("unavailable");
  expect(
    stateLabel({
      stale: false,
      in_progress: false,
      data_available: false,
      status: "private",
    }),
  ).toBe("Private or not shared");
});
test("stale known counts do not become an exact completion", () => {
  render(
    <ProgressSummary
      progress={{
        state: {
          stale: true,
          in_progress: false,
          data_available: true,
          status: "populated",
        },
        coverage: "stale",
        known_unlocked: 17,
        known_locked: 30,
        definition_count: 47,
        completion_percent: null,
      }}
    />,
  );
  expect(screen.getByText(/Known unlocked: 17/)).toBeInTheDocument();
  expect(
    screen.getByText("Selected game completion: Unavailable"),
  ).toBeInTheDocument();
  expect(screen.queryByText(/36.17%/)).not.toBeInTheDocument();
});
test("private achievement summaries hide counts", () => {
  render(
    <ProgressSummary
      progress={{
        state: {
          stale: false,
          in_progress: false,
          data_available: false,
          status: "private",
        },
        coverage: "unknown",
      }}
    />,
  );
  expect(screen.getByText(/Private or not shared/)).toBeInTheDocument();
  expect(screen.queryByText(/Known unlocked/)).not.toBeInTheDocument();
});
