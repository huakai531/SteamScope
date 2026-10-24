import { fireEvent, render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import {
  AchievementSnapshot,
  FriendSnapshot,
} from "@/components/steam-details";
import type { components } from "@/lib/api/schema";
import { ResourceStatus } from "@/components/steam-data";

const data: components["schemas"]["AchievementsView"] = {
  app_id: 77730001,
  state: {
    resource: "achievements",
    status: "populated",
    code: "OK",
    data_available: true,
    stale: false,
    in_progress: false,
  },
  schema_state: {
    language: "english",
    status: "populated",
    code: "OK",
    revision: "a".repeat(64),
    last_success_at: null,
    stale: false,
  },
  latest_job: null,
  coverage: "complete",
  known_unlocked: 1,
  known_locked: 1,
  definition_count: 2,
  completion_percent: 50,
  items: [
    {
      api_name: "SECRET",
      display_name: "Hidden ending",
      description: "Synthetic spoiler",
      hidden: true,
      definition_available: true,
      unlocked: true,
      unlocked_at: null,
    },
  ],
};

test("application-level unavailable is not falsely labelled HTTP access denied", () => {
  render(
    <ResourceStatus
      state={{
        ...data.state,
        status: "unavailable",
        code: "PLAYER_PROGRESS_UNAVAILABLE",
        data_available: false,
      }}
    />,
  );
  expect(
    screen.getByText(
      "Unavailable: Steam did not provide this resource; the cause is unconfirmed",
    ),
  ).toBeVisible();
  expect(
    screen.queryByText(/denied this request|Restricted by Steam visibility/),
  ).not.toBeInTheDocument();
});

test("hidden spoilers require owner reveal and unknown unlock time never becomes 1970", () => {
  render(<AchievementSnapshot data={data} />);
  expect(screen.queryByText("Synthetic spoiler")).not.toBeInTheDocument();
  expect(screen.getByText(/Unlock time: Unknown/)).toBeVisible();
  expect(screen.queryByText(/1970/)).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("checkbox"));
  expect(screen.getByText("Synthetic spoiler")).toBeVisible();
  expect(screen.getByText(/Selected game completion: 50%/)).toBeVisible();
});

test.each(["unknown", "partial", "stale", "no_achievements"] as const)(
  "%s does not invent a completion percentage",
  (coverage) => {
    render(
      <AchievementSnapshot
        data={{
          ...data,
          coverage,
          completion_percent: null,
          known_unlocked: null,
          known_locked: null,
          items: [],
          definition_count: coverage === "no_achievements" ? 0 : 2,
        }}
      />,
    );
    expect(
      screen.getByText(/Selected game completion: Unavailable/),
    ).toBeVisible();
    expect(screen.getByText(/Known unlocked: Unknown/)).toBeVisible();
    expect(screen.queryByText(/100%/)).not.toBeInTheDocument();
  },
);

test("external achievement strings stay text", () => {
  const { container } = render(
    <AchievementSnapshot
      data={{
        ...data,
        items: [
          {
            ...data.items[0],
            hidden: false,
            display_name: "<img src=x onerror=alert(1)>",
          },
        ],
      }}
    />,
  );
  expect(screen.getByText("<img src=x onerror=alert(1)>")).toBeVisible();
  expect(container.querySelector("img")).toBeNull();
});

test("friend privacy suppresses known counts and is not a claim of invalid key", () => {
  render(
    <FriendSnapshot
      data={{
        state: {
          resource: "friends",
          status: "unavailable",
          code: "FRIENDS_PRIVATE_OR_UNAUTHORIZED",
          data_available: false,
          stale: false,
          in_progress: false,
        },
        latest_job: null,
        total_count: null,
        items: [],
      }}
    />,
  );
  expect(screen.getByText(/Imported Steam friends: Unknown/)).toBeVisible();
  expect(
    screen.getByText(/Privacy or another authorization issue may apply/),
  ).toBeVisible();
  expect(screen.queryByRole("link")).not.toBeInTheDocument();
});

test("imported friend identifiers have fixed Steam links and unknown dates", () => {
  render(
    <FriendSnapshot
      data={{
        state: {
          resource: "friends",
          status: "populated",
          code: "OK",
          data_available: true,
          stale: false,
          in_progress: false,
        },
        latest_job: null,
        total_count: 1,
        items: [
          {
            steam_id64: "76561198000000991",
            profile_url:
              "https://steamcommunity.com/profiles/76561198000000991/",
            friend_since: null,
          },
        ],
      }}
    />,
  );
  expect(screen.getByRole("link")).toHaveAttribute(
    "href",
    "https://steamcommunity.com/profiles/76561198000000991/",
  );
  expect(screen.getByText("Friends since: Unknown")).toBeVisible();
  expect(
    screen.queryByRole("button", { name: /Add friend|Chat/ }),
  ).not.toBeInTheDocument();
});
