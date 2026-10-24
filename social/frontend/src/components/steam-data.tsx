"use client";

import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AccountError,
  accountMessage,
  accountRequest,
} from "@/lib/api/account";
import type { components } from "@/lib/api/schema";
import { SteamDetails } from "@/components/steam-details";

type Status = components["schemas"]["SyncStatusView"];
type Profile = components["schemas"]["SteamProfileView"];
type Games = components["schemas"]["GamesView"];
type Resource = components["schemas"]["ResourceView"];

export function minutes(value: number | null | undefined) {
  return value == null
    ? "Unknown"
    : `${value} min (${(value / 60).toFixed(1)} h)`;
}

const labels: Record<string, string> = {
  never: "Never synchronized",
  populated: "Saved snapshot",
  empty: "Confirmed empty snapshot",
  restricted: "Restricted by Steam visibility",
  unavailable:
    "Unavailable: Steam did not provide this resource; the cause is unconfirmed",
  unknown:
    "Unknown: Steam did not provide enough visibility or data information",
  error: "Invalid or rejected upstream response",
  retry: "Temporary failure or request limit; retry pending or exhausted",
  configuration: "Steam sync not configured",
  partial: "Saved player data with incomplete or mismatched schema coverage",
};

export function ResourceStatus({ state }: { state: Resource }) {
  const denied =
    state.code.startsWith("ACCESS_DENIED_") ||
    state.code === "FRIENDS_PRIVATE_OR_UNAUTHORIZED";
  return (
    <div className="information-note">
      <p>
        {denied
          ? "Unavailable: Steam denied this request; the reason is unconfirmed"
          : (labels[state.status] ?? "Unavailable")}
        {state.in_progress ? " · Synchronization in progress" : ""}
      </p>
      <p>
        Last successful synchronization:{" "}
        {state.last_success_at ? (
          <time dateTime={state.last_success_at}>
            {new Date(state.last_success_at).toLocaleString()}
          </time>
        ) : (
          "Never"
        )}
      </p>
      {state.stale && (
        <p>Stale snapshot. A failed attempt does not refresh its age.</p>
      )}
      {!state.data_available && state.last_success_at && (
        <p>
          Previous data is hidden under the current visibility or freshness
          policy.
        </p>
      )}
    </div>
  );
}

function safeProfileLink(value: string | null | undefined): string | undefined {
  if (!value) return undefined;
  try {
    const url = new URL(value);
    return url.origin === "https://steamcommunity.com" &&
      /^\/profiles\/\d{17}\/$/.test(url.pathname) &&
      !url.search &&
      !url.hash &&
      !url.username &&
      !url.password
      ? url.href
      : undefined;
  } catch {
    return undefined;
  }
}

export function SteamData({ ownerId }: { ownerId: string }) {
  const cache = useQueryClient();
  const [cursor, setCursor] = useState<{ after: number; snapshot?: string }>({
    after: 0,
  });
  const [confirmation, setConfirmation] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const channel = useRef<BroadcastChannel | null>(null);
  const query = useQuery({
    queryKey: ["steam", ownerId, cursor],
    queryFn: async () => {
      const suffix = cursor.after
        ? `?after=${cursor.after}&snapshot=${encodeURIComponent(cursor.snapshot ?? "")}`
        : "";
      const [status, profile, games, recent] = await Promise.all([
        accountRequest<Status>("/me/steam/sync-status"),
        accountRequest<Profile>("/me/steam/profile"),
        accountRequest<Games>("/me/steam/games" + suffix),
        accountRequest<Games>("/me/steam/recent-games"),
      ]);
      return { status, profile, games, recent };
    },
    gcTime: 0,
    staleTime: 0,
    refetchInterval: 3000,
    refetchOnWindowFocus: true,
    retry: false,
  });

  useEffect(() => {
    if (typeof BroadcastChannel === "undefined") return;
    const current = new BroadcastChannel("steamscope-steam-data");
    channel.current = current;
    current.onmessage = () => {
      window.location.reload();
    };
    return () => {
      channel.current = null;
      current.close();
    };
  }, []);

  async function action(clear: boolean) {
    setBusy(true);
    setMessage("");
    try {
      if (clear) {
        await cache.cancelQueries({ queryKey: ["steam", ownerId] });
        await accountRequest("/me/steam/data", "DELETE", { confirmation });
        channel.current?.postMessage("cleared");
        setConfirmation("");
        setCursor({ after: 0 });
        await cache.resetQueries({ queryKey: ["steam", ownerId] });
        setMessage(
          "Imported Steam data cleared. Your account and privacy settings are preserved.",
        );
      } else {
        await accountRequest("/me/steam/sync", "POST");
        setMessage(
          "Synchronization requested. Completed resources are saved independently.",
        );
        await query.refetch();
      }
    } catch (error) {
      const code = error instanceof AccountError ? error.detail.code : "";
      setMessage(
        code === "STEAM_SYNC_COOLDOWN"
          ? "Please wait until the synchronization cooldown ends."
          : code === "REAUTH_REQUIRED"
            ? "Verify your Steam identity again before clearing imported data."
            : accountMessage(error),
      );
    } finally {
      setBusy(false);
    }
  }

  async function reverify() {
    try {
      const result = await accountRequest<components["schemas"]["LoginView"]>(
        "/auth/steam/reauth?next=/account/steam",
        "POST",
      );
      const url = new URL(result.url);
      if (
        url.origin !== "https://steamcommunity.com" ||
        url.pathname !== "/openid/login"
      )
        throw new Error("invalid-provider");
      window.location.assign(url.href);
    } catch (error) {
      setMessage(accountMessage(error));
    }
  }

  const data = query.data;
  const link = safeProfileLink(data?.profile.profile_url);
  return (
    <section className="account-panel steam-data">
      <p className="eyebrow">OWNER-ONLY IMPORT</p>
      <h1>My Steam Data</h1>
      <p>
        Import your Steam persona, visible game library, playtime and recent
        two-week activity. OpenID verifies identity; it does not grant access to
        private Steam data. This page is visible only to you.
      </p>
      <p>
        Steam data is provided as is. Steam names are separate from your
        SteamScope profile. Images use placeholders; no external images are
        fetched.
      </p>
      {message && <p role="status">{message}</p>}
      {query.isPending && <p role="status">Loading saved Steam data…</p>}
      {query.isError && (
        <div role="alert">
          <p>
            {query.error instanceof AccountError &&
            query.error.detail.code === "STEAM_SNAPSHOT_CHANGED"
              ? "The library changed. Restart from the first page."
              : accountMessage(query.error)}
          </p>
          <button
            onClick={() => {
              setCursor({ after: 0 });
              void query.refetch();
            }}
          >
            Reload first page
          </button>
        </div>
      )}
      {data && !busy && !query.isError && (
        <>
          {data.status.capability !== "configured" && (
            <p role="status">{data.status.operator_instruction}</p>
          )}
          <button
            className="primary-action"
            disabled={data.status.capability !== "configured"}
            onClick={() => void action(false)}
          >
            Sync my Steam data
          </button>
          <p>
            Job:{" "}
            <strong>
              {data.status.latest_job?.status ?? "No job requested"}
            </strong>
          </p>
          {data.status.latest_job && (
            <p>
              Attempt {data.status.latest_job.attempts}. Partial means only some
              resources completed successfully.
            </p>
          )}
          {data.status.cooldown_until && (
            <p>
              Next new request after{" "}
              {new Date(data.status.cooldown_until).toLocaleString()}. Repeated
              clicks reuse an active job.
            </p>
          )}
          <h2>Steam persona</h2>
          <ResourceStatus state={data.profile.state} />
          {data.profile.state.data_available && (
            <>
              <p>
                {data.profile.persona_name ?? "Steam persona name unavailable"}
              </p>
              {link && (
                <a href={link} target="_blank" rel="noopener noreferrer">
                  Open linked Steam profile
                </a>
              )}
            </>
          )}
          <h2>Game library</h2>
          <ResourceStatus state={data.games.state} />
          {data.games.state.data_available && (
            <>
              <p>
                Games returned by Steam: {data.games.returned_game_count}. This
                is not an authoritative count of purchases, DLC or entitlements.
              </p>
              <p>
                Total library playtime: {minutes(data.games.total_minutes)}.
                Recent endpoint playtime is not added to this total.
              </p>
              <ul className="steam-games">
                {data.games.items.map((game) => (
                  <li key={game.app_id}>
                    <strong>{game.name ?? `App ${game.app_id}`}</strong>
                    <span>Total: {minutes(game.total_minutes)}</span>
                    <span>Recent: {minutes(game.recent_minutes)}</span>
                  </li>
                ))}
              </ul>
              <div className="steam-pagination">
                <button
                  disabled={!cursor.after}
                  onClick={() => setCursor({ after: 0 })}
                >
                  First page
                </button>
                <button
                  disabled={data.games.next_after == null}
                  onClick={() =>
                    setCursor({
                      after: data.games.next_after!,
                      snapshot: data.games.state.snapshot_id ?? undefined,
                    })
                  }
                >
                  Next page
                </button>
              </div>
            </>
          )}
          <h2>Recent games</h2>
          <ResourceStatus state={data.recent.state} />
          {data.recent.window_end && (
            <p>
              Two-week snapshot ending{" "}
              {new Date(data.recent.window_end).toLocaleString()}; hidden after
              15 minutes until refreshed.
            </p>
          )}
          <ul className="steam-games">
            {data.recent.items.map((game) => (
              <li key={game.app_id}>
                <strong>{game.name ?? `App ${game.app_id}`}</strong>
                <span>Recent: {minutes(game.recent_minutes)}</span>
              </li>
            ))}
          </ul>
          <SteamDetails
            key={`${ownerId}:${data.games.state.snapshot_id}:${cursor.after}`}
            ownerId={ownerId}
            games={data.games.state.data_available ? data.games.items : []}
            configured={data.status.capability === "configured"}
            Status={ResourceStatus}
          />
          <h2>Clear imported Steam data</h2>
          <p>
            This removes imported data and cancels queued or running work. Your
            login, Steam association and platform settings remain. Data stays
            cleared until you request another synchronization.
          </p>
          <label>
            Type CLEAR STEAM DATA to confirm
            <input
              value={confirmation}
              onChange={(event) => setConfirmation(event.target.value)}
              autoComplete="off"
            />
          </label>
          <button
            disabled={confirmation !== "CLEAR STEAM DATA"}
            onClick={() => void action(true)}
          >
            Clear imported Steam data
          </button>
          <button onClick={() => void reverify()}>
            Verify Steam identity for clearing
          </button>
        </>
      )}
      {busy && <p role="status">Applying your request…</p>}
    </section>
  );
}
