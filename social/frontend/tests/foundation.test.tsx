import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { SystemStatus } from "@/components/system-status";
import { ProductPreview } from "@/components/product-preview";
import Home from "@/app/page";
import { Providers } from "@/components/providers";
import { GET } from "@/app/api/status/route";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});
const report = (ready = true) => ({
  status: ready ? "ready" : "unavailable",
  scope: "foundation",
  dependencies: { postgres: "up", redis: ready ? "up" : "down" },
});

test("landing page presents the completed product honestly and shows actual status", async () => {
  vi.stubGlobal(
    "fetch",
    vi
      .fn()
      .mockImplementation((url) =>
        Promise.resolve(
          String(url).endsWith("/me")
            ? Response.json(
                { error: { code: "AUTH_REQUIRED" } },
                { status: 401 },
              )
            : Response.json(report()),
        ),
      ),
  );
  render(
    <Providers>
      <Home />
    </Providers>,
  );
  expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
    "Find your people.Through play.",
  );
  expect(
    screen.getByRole("link", { name: /Continue with Steam/ }),
  ).toHaveAttribute("href", "/api/v1/auth/steam/login");
  expect(
    screen.getByText(/Not affiliated with or endorsed by Valve Corporation/),
  ).toBeVisible();
  fireEvent.click(screen.getByText("Service status"));
  expect(screen.getByText("Checking foundation services…")).toBeVisible();
  expect(
    await screen.findByText("Foundation services connected"),
  ).toBeVisible();
});

test("failed request has an honest state and retry can recover", async () => {
  const request = vi
    .fn()
    .mockRejectedValueOnce(new Error("network"))
    .mockResolvedValueOnce(Response.json(report(false), { status: 503 }));
  vi.stubGlobal("fetch", request);
  render(
    <Providers>
      <SystemStatus />
    </Providers>,
  );
  expect(await screen.findByText("Status check unavailable")).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: /Check again/ }));
  expect(
    await screen.findByText("Foundation services unavailable"),
  ).toBeVisible();
  expect(screen.getByText("Unavailable", { selector: "strong" })).toBeVisible();
  await waitFor(() => expect(request).toHaveBeenCalledTimes(2));
});

test("status proxy uses the server origin, preserves outages and strips internal errors", async () => {
  vi.stubEnv("INTERNAL_API_URL", "http://api:8000");
  const request = vi
    .fn()
    .mockResolvedValueOnce(Response.json(report(false), { status: 503 }))
    .mockRejectedValueOnce(new Error("secret-host-password"));
  vi.stubGlobal("fetch", request);
  expect((await GET()).status).toBe(503);
  expect(String(request.mock.calls[0][0])).toBe("http://api:8000/health/ready");
  const failed = await GET();
  expect(failed.status).toBe(502);
  expect(await failed.text()).not.toContain("secret-host-password");
});

test("status proxy rejects malformed success instead of showing green", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(Response.json({ status: "ready" })),
  );
  expect((await GET()).status).toBe(502);
});

test("public sample game selection never fetches account data or sends messages", () => {
  const request = vi.fn();
  vi.stubGlobal("fetch", request);
  render(<ProductPreview />);
  expect(
    screen.getByText("Illustrative preview · fictional games"),
  ).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "Ember Circuit" }));
  expect(screen.getByText("You play Ember Circuit too?")).toBeVisible();
  expect(request).not.toHaveBeenCalled();
});

test("authenticated landing offers account entry without exposing account identity", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockImplementation((url) =>
      Promise.resolve(
        String(url).endsWith("/me")
          ? Response.json({
              id: "synthetic-test-account",
              display_name: "Private test identity",
            })
          : Response.json(report()),
      ),
    ),
  );
  render(
    <Providers>
      <Home />
    </Providers>,
  );
  const entries = await screen.findAllByRole("link", {
    name: /Open SteamScope/,
  });
  expect(entries).toHaveLength(2);
  for (const entry of entries)
    expect(entry).toHaveAttribute("href", "/account");
  expect(screen.queryByText("Private test identity")).not.toBeInTheDocument();
  expect(
    screen.queryByRole("link", { name: /Continue with Steam/ }),
  ).not.toBeInTheDocument();
});
