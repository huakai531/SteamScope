import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { DiscoverPlayerCard, MutualGamesStrip } from "@/components/discover-ui";
import type { components } from "@/lib/api/schema";

type Comparison = components["schemas"]["PlayerComparison"];
const source = {
  status: "populated",
  data_available: true,
  stale: false,
  last_success_at: null,
  in_progress: false,
};
const comparison = {
  status: "available",
  left_handle: "owner",
  right_handle: "friend",
  left_library_state: source,
  right_library_state: source,
  mutual_count: 5,
  items: [1, 2, 3, 4, 5].map((n) => ({ app_id: n, name: `Shared game ${n}` })),
} as Comparison;

test("common-game strip limits visuals but retains the authorized remainder", () => {
  render(
    <MutualGamesStrip
      games={comparison.items}
      total={comparison.mutual_count ?? null}
    />,
  );
  expect(screen.getAllByRole("listitem")).toHaveLength(3);
  expect(screen.getByText("+2 more in common")).toBeInTheDocument();
  expect(screen.queryByText("Shared game 4")).not.toBeInTheDocument();
});

test.each(["private", "stale", "unavailable"])(
  "%s comparison cannot supply named games",
  (mode) => {
    const hidden = {
      ...comparison,
      status: mode === "unavailable" ? "unavailable" : "available",
      left_library_state: {
        ...source,
        data_available: mode !== "private",
        stale: mode === "stale",
      },
    } as Comparison;
    render(
      <DiscoverPlayerCard
        person={{ handle: "friend", display_name: "A friend" }}
        comparison={hidden}
        actions={<button>Connect</button>}
      />,
    );
    expect(screen.queryByText("Games in common")).not.toBeInTheDocument();
    expect(screen.queryByText("Shared game 1")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Connect" })).toBeInTheDocument();
  },
);
