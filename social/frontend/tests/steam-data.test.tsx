import { render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { minutes, ResourceStatus, SteamData } from "@/components/steam-data";
import { Providers } from "@/components/providers";

afterEach(() => {
  vi.unstubAllGlobals();
});

test.each(["queued", "running", "retry", "partial", "succeeded", "failed"])(
  "owner sees saved job outcome %s without claiming full completion",
  async (status) => {
    const state = {
      resource: "library",
      status: "unknown",
      code: "UNKNOWN",
      data_available: false,
      stale: false,
      in_progress: status === "running",
    };
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) =>
        Response.json(
          url.endsWith("sync-status")
            ? {
                capability: "configured",
                resources: [],
                latest_job: { status, attempts: 1 },
              }
            : url.endsWith("profile")
              ? { state, persona_name: null }
              : { state, items: [] },
        ),
      ),
    );
    render(
      <Providers>
        <SteamData ownerId="fixture-status-owner" />
      </Providers>,
    );
    expect(await screen.findByText(status, { exact: true })).toBeVisible();
    expect(screen.getByText(/Partial means only some resources/)).toBeVisible();
    expect(
      screen.queryByText(/Games returned by Steam:/),
    ).not.toBeInTheDocument();
  },
);

test("playtime preserves unknown versus real zero", () => {
  expect(minutes(null)).toBe("Unknown");
  expect(minutes(0)).toBe("0 min (0.0 h)");
  expect(minutes(61)).toBe("61 min (1.0 h)");
});

test.each([
  [
    "unknown",
    "Unknown: Steam did not provide enough visibility or data information",
  ],
  ["restricted", "Restricted by Steam visibility"],
  ["empty", "Confirmed empty snapshot"],
  ["error", "Invalid or rejected upstream response"],
  ["never", "Never synchronized"],
])("resource %s has a distinct honest display", (status, label) => {
  render(
    <ResourceStatus
      state={{
        resource: "library",
        status,
        code: "FIXTURE",
        stale: false,
        in_progress: false,
        data_available: false,
      }}
    />,
  );
  expect(screen.getByText(label)).toBeVisible();
});

test("missing key instructions disable synchronization without hiding account UI", async () => {
  const state = { resource: "library", status: "never", code: "NEVER_SYNCED" };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) =>
      Response.json(
        url.endsWith("sync-status")
          ? {
              capability: "unconfigured",
              operator_instruction:
                "Steam sync not configured. Project owner: configure SOCIAL_STEAM_API_KEY privately.",
              resources: [],
              latest_job: null,
            }
          : url.endsWith("profile")
            ? { state, persona_name: null }
            : { state, items: [] },
      ),
    ),
  );
  render(
    <Providers>
      <SteamData ownerId="fixture-owner" />
    </Providers>,
  );
  expect(await screen.findByText(/Steam sync not configured/)).toBeVisible();
  expect(
    screen.getByRole("button", { name: "Sync my Steam data" }),
  ).toBeDisabled();
  expect(
    screen.getByRole("button", { name: "Clear imported Steam data" }),
  ).toBeDisabled();
  expect(screen.getByRole("heading", { name: "My Steam Data" })).toBeVisible();
});
