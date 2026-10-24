import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, expect, test, vi } from "vitest";
import {
  SocialActions,
  RecommendationCard,
  socialMessage,
} from "@/components/social-app";
import { accountRequest, AccountError } from "@/lib/api/account";

vi.mock("@/lib/api/account", async (original) => ({
  ...(await original<typeof import("@/lib/api/account")>()),
  accountRequest: vi.fn(),
}));
const api = vi.mocked(accountRequest);
function wrap(ui: React.ReactNode) {
  return render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      {ui}
    </QueryClientProvider>,
  );
}
afterEach(() => vi.resetAllMocks());

test("social error copy hides block existence and explains explicit reverse acceptance", () => {
  expect(
    socialMessage(
      new AccountError(404, { code: "SOCIAL_UNAVAILABLE", message: "" }),
    ),
  ).not.toMatch(/blocked/i);
  expect(
    socialMessage(
      new AccountError(409, { code: "INCOMING_REQUEST_EXISTS", message: "" }),
    ),
  ).toContain("accept or reject");
});

test("block needs explicit confirmation and uses the bound handle", async () => {
  api.mockResolvedValue({
    status: "connected",
    request_id: null,
    can_request: false,
  });
  wrap(<SocialActions handle="player_B" />);
  fireEvent.click(await screen.findByLabelText("More player actions"));
  fireEvent.click(
    await screen.findByRole("menuitem", { name: "Block player" }),
  );
  expect(api).toHaveBeenCalledTimes(1);
  expect(
    screen.getByRole("dialog", { name: "Block @player_B?" }),
  ).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Confirm block" }));
  await waitFor(() =>
    expect(api).toHaveBeenCalledWith("/blocks/player_B", "POST", undefined),
  );
});

test("report description stays literal and submission is distinct from block", async () => {
  api.mockResolvedValue({
    status: "none",
    request_id: null,
    can_request: true,
  });
  wrap(<SocialActions handle="player_B" />);
  fireEvent.click(await screen.findByLabelText("More player actions"));
  fireEvent.click(
    await screen.findByRole("menuitem", { name: "Report player" }),
  );
  fireEvent.change(screen.getByRole("combobox", { name: "Reason" }), {
    target: { value: "spam" },
  });
  fireEvent.change(screen.getByLabelText("Description (optional)"), {
    target: { value: "<script>{one,two}</script>" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Submit report" }));
  await waitFor(() =>
    expect(api).toHaveBeenCalledWith("/reports", "POST", {
      handle: "player_B",
      reason: "spam",
      description: "<script>{one,two}</script>",
    }),
  );
  expect(
    await screen.findByText(/Report saved for review/),
  ).toBeInTheDocument();
  expect(api.mock.calls.some(([path]) => path.startsWith("/blocks"))).toBe(
    false,
  );
});

test("recommendation text is escaped and unknown is not invented as zero evidence", async () => {
  api.mockResolvedValue({
    status: "none",
    request_id: null,
    can_request: false,
  });
  const { container } = wrap(
    <RecommendationCard
      item={{
        person: {
          handle: "player_B",
          display_name: "<img src=x onerror=alert(1)>",
        },
        score: 10,
        mutual_games: null,
        recent_overlap: null,
        reasons: ["Your Steam friend is also on SteamScope"],
        steam_friend: true,
      }}
    />,
  );
  expect(screen.getByText("<img src=x onerror=alert(1)>")).toBeInTheDocument();
  expect(container.querySelectorAll("img,script")).toHaveLength(0);
  expect(screen.queryByText(/0 mutual games/)).not.toBeInTheDocument();
  expect(
    screen.queryByText("Shared games", { exact: true }),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByText("Recent overlap", { exact: true }),
  ).not.toBeInTheDocument();
  expect(await screen.findByText("Not accepting requests")).toBeInTheDocument();
});
