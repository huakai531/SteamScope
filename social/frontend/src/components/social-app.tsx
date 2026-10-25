"use client";

import Link from "next/link";
import { SegmentedControl } from "./ui/notchset/segmented-control";
import { Button, EmptyState } from "./ui";
import { ConfirmDialog } from "./confirm-dialog";
import { Input, Textarea } from "./ui";
import { AppShell } from "./app-shell";
import {
  DiscoverHero,
  DiscoverPlayerCard,
  DiscoverEmptyState,
} from "./discover-ui";
import {
  PlayerAvatar,
  Icon,
  MoreActions,
  StatusBadge,
  HelpDisclosure,
} from "./ui";
import { useEffect, useState, type ReactNode } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  accountRequest,
  accountMessage,
  AccountError,
  type Account,
} from "@/lib/api/account";
import type { components } from "@/lib/api/schema";

type S = components["schemas"];
type Person = S["Person"];
type Section = "discover" | "connections" | "notifications";

export function socialMessage(error: unknown): string {
  if (error instanceof AccountError) {
    const messages: Record<string, string> = {
      SOCIAL_UNAVAILABLE:
        "This player or action is unavailable. Reload to check current visibility.",
      SOCIAL_SELF_ACTION: "Choose another player for this action.",
      INCOMING_REQUEST_EXISTS:
        "You already have an incoming request. Open Connections to accept or reject it.",
      REQUEST_FINALIZED: "This request has already ended. Reload the list.",
      PLAYER_SNAPSHOT_CHANGED:
        "The visible results changed. Start again from the first page.",
      RATE_LIMITED:
        "Too many actions. Please wait before trying again; reports have an hourly limit.",
    };
    if (messages[error.detail.code]) return messages[error.detail.code];
  }
  return accountMessage(error);
}

function useAction() {
  const cache = useQueryClient();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [message, setMessage] = useState("");
  async function act(
    path: string,
    method: string,
    body?: unknown,
    success = "Saved.",
  ) {
    if (busy) return false;
    setBusy(true);
    setError(null);
    setMessage("");
    try {
      await accountRequest(path, method, body);
      // Discard stale authorization projections after every graph transition.
      if (path !== "/reports")
        await cache.invalidateQueries({
          predicate: (query) =>
            query.queryKey[0] !== "account" &&
            !(query.queryKey[0] === "social" && query.queryKey[1] === "/me"),
        });
      setMessage(success);
      return true;
    } catch (failure) {
      setError(failure);
      return false;
    } finally {
      setBusy(false);
    }
  }
  return {
    busy,
    act,
    feedback: (
      <>
        {error != null && <p role="alert">{socialMessage(error)}</p>}
        {message && <p role="status">{message}</p>}
      </>
    ),
  };
}

function useRead<T>(path: string, enabled = true) {
  return useQuery({
    queryKey: ["social", path],
    enabled,
    queryFn: () => accountRequest<T>(path),
    staleTime: 0,
    gcTime: 0,
    refetchOnMount: "always",
    refetchOnWindowFocus: "always",
    retry: false,
  });
}

function PersonLink({ person }: { person: Person | null }) {
  return person ? (
    <Link className="person-link" href={`/users/${person.handle}`}>
      <PlayerAvatar
        uploadedSrc={person.avatar_url}
        name={person.display_name}
      />
      <strong>{person.display_name}</strong> <span>@{person.handle}</span>
    </Link>
  ) : (
    <span>Player unavailable</span>
  );
}

function Paged<T>({
  title,
  path,
  empty,
  render,
  variant = "rows",
  description,
}: {
  variant?: "rows" | "players";
  description?: string;
  title: string;
  path: string;
  empty: string;
  render: (item: T) => ReactNode;
}) {
  const [cursors, setCursors] = useState<(string | null)[]>([null]);
  const cursor = cursors[cursors.length - 1];
  const data = useRead<{ items: T[]; next_cursor?: string | null }>(
    path +
      (cursor
        ? `${path.includes("?") ? "&" : "?"}cursor=${encodeURIComponent(cursor)}`
        : ""),
  );
  return (
    <section className={`social-panel social-panel-${variant}`}>
      <div className="section-heading">
        <h2>{title}</h2>
        {description && <p>{description}</p>}
      </div>
      {data.isFetching || data.isPending ? (
        <p role="status">Loading saved results…</p>
      ) : data.isError ? (
        <p role="alert">{socialMessage(data.error)}</p>
      ) : (
        <>
          {data.data.items.length === 0 ? (
            <EmptyState
              title={variant === "players" ? "No matches yet." : empty}
              icon={path === "/notifications" ? "bell" : "people"}
            >
              {variant === "players" ? (
                <>
                  {empty}{" "}
                  <Link href="/account/steam">Review your Steam data →</Link>
                </>
              ) : path === "/notifications" ? (
                "Connection requests and accepted invitations will appear here."
              ) : (
                "Your social circle starts with a shared game."
              )}
            </EmptyState>
          ) : (
            <ul className="social-list">
              {data.data.items.map((item, index) => (
                <li key={index}>{render(item)}</li>
              ))}
            </ul>
          )}
          {data.data.next_cursor && (
            <button
              onClick={() =>
                setCursors([...cursors, data.data.next_cursor ?? null])
              }
            >
              Next page
            </button>
          )}
        </>
      )}
      {cursors.length > 1 && (
        <button onClick={() => setCursors([null])}>
          Start from first page
        </button>
      )}
    </section>
  );
}

export function SocialActions({
  handle,
  compact = false,
  discover = false,
}: {
  handle: string;
  compact?: boolean;
  discover?: boolean;
}) {
  const relation = useRead<S["SocialRelationship"]>(
    `/users/${handle}/relationship`,
  );
  const action = useAction();
  const [dialog, setDialog] = useState<"block" | "report" | null>(null);
  if (relation.isFetching || relation.isPending)
    return <p role="status">Checking available actions…</p>;
  if (relation.isError || !relation.data)
    return <p>Social actions unavailable.</p>;
  const state = relation.data;
  if (state.status === "self") return null;
  return (
    <div className="social-actions">
      <div className="social-buttons">
        {state.status === "none" &&
          (state.can_request ? (
            <button
              disabled={action.busy}
              onClick={() =>
                void action.act(
                  "/connection-requests",
                  "POST",
                  { handle },
                  "Connection request sent.",
                )
              }
            >
              {discover ? "Connect" : "Send connection request"}
            </button>
          ) : (
            <span>Not accepting requests</span>
          ))}
        {state.status === "outgoing" && (
          <>
            <StatusBadge>
              {discover ? "Requested" : "Request pending"}
            </StatusBadge>
            {!discover && (
              <button
                disabled={action.busy}
                onClick={() =>
                  void action.act(
                    `/connection-requests/${state.request_id}`,
                    "DELETE",
                    undefined,
                    "Request cancelled.",
                  )
                }
              >
                Cancel request
              </button>
            )}
          </>
        )}
        {state.status === "incoming" && (
          <Link href="/connections">
            {discover ? "Respond" : "Review incoming request"}
          </Link>
        )}
        {state.status === "connected" && (
          <>
            <StatusBadge tone="good">Connected</StatusBadge>
            <Link
              className="primary-action"
              href={`/messages?with=${encodeURIComponent(handle)}`}
            >
              Message
            </Link>
          </>
        )}
        {!compact && (
          <MoreActions label="More player actions">
            {state.status === "connected" && (
              <button
                className="danger-text"
                disabled={action.busy}
                onClick={() =>
                  void action.act(
                    `/connections/${handle}`,
                    "DELETE",
                    undefined,
                    "Connection removed.",
                  )
                }
              >
                Remove connection
              </button>
            )}
            <button className="danger-text" onClick={() => setDialog("block")}>
              Block player
            </button>
            <button onClick={() => setDialog("report")}>Report player</button>
          </MoreActions>
        )}
      </div>
      {action.feedback}
      <ConfirmDialog
        open={dialog === "block"}
        label="Confirm block"
        title={`Block @${handle}?`}
        busy={action.busy}
        onClose={() => setDialog(null)}
        confirmLabel="Confirm block"
        cancelLabel="Keep current relationship"
        onConfirm={async () => {
          if (
            await action.act(
              `/blocks/${handle}`,
              "POST",
              undefined,
              "Player blocked.",
            )
          )
            setDialog(null);
        }}
      >
        This removes your SteamScope connection, cancels pending requests and
        hides both players from each other. Unblocking will not reconnect you.
      </ConfirmDialog>
      {dialog === "report" && (
        <form
          className="social-confirm"
          aria-label="Report player"
          onSubmit={async (event) => {
            event.preventDefault();
            const form = new FormData(event.currentTarget);
            if (
              await action.act(
                "/reports",
                "POST",
                {
                  handle,
                  reason: form.get("reason"),
                  description: form.get("description"),
                },
                "Report saved for review. No notification was sent to this player.",
              )
            )
              setDialog(null);
          }}
        >
          <h3>Report @{handle}</h3>
          <p>
            Reports do not block automatically. Do not include passwords,
            contact details or other unnecessary personal information.
          </p>
          <label>
            Reason
            <select name="reason">
              <option value="harassment">Harassment</option>
              <option value="spam">Spam</option>
              <option value="impersonation">Impersonation</option>
              <option value="inappropriate_content">
                Inappropriate content
              </option>
              <option value="suspicious_behavior">Suspicious behavior</option>
              <option value="other">Other</option>
            </select>
          </label>
          <label>
            Description (optional)
            <Textarea name="description" maxLength={1000} rows={3} />
          </label>
          <button disabled={action.busy}>Submit report</button>
          <button
            type="button"
            disabled={action.busy}
            onClick={() => setDialog(null)}
          >
            Cancel report
          </button>
        </form>
      )}
    </div>
  );
}

function PlayerCard({
  person,
  recommendation,
  featured = false,
}: {
  person: Person;
  recommendation?: S["Recommendation"];
  featured?: boolean;
}) {
  const relation = useRead<S["SocialRelationship"]>(
    `/users/${person.handle}/relationship`,
  );
  const available = !!relation.data && !relation.isError;
  const profile = useRead<S["PlayerProfile"]>(
    `/users/${person.handle}`,
    available,
  );
  const comparison = useRead<S["PlayerComparison"]>(
    `/users/${person.handle}/comparison?limit=3`,
    available && (recommendation?.mutual_games ?? 0) > 0,
  );
  // A candidate may become hidden between the list and detail reads. Fail closed
  // for authorization denial; do not advertise their previously rendered card.
  if (
    [relation.error, profile.error, comparison.error].some(
      (error) =>
        error instanceof AccountError &&
        (error.status === 403 || error.status === 404),
    )
  )
    return null;
  return (
    <DiscoverPlayerCard
      person={person}
      recommendation={recommendation}
      featured={featured}
      biography={
        !profile.isFetching && !profile.isError
          ? profile.data?.biography
          : undefined
      }
      comparison={
        available && !comparison.isFetching && !comparison.isError
          ? comparison.data
          : undefined
      }
      actions={<SocialActions handle={person.handle} compact discover />}
    />
  );
}

export function RecommendationCard({
  item,
  featured = false,
}: {
  item: S["Recommendation"];
  featured?: boolean;
}) {
  return (
    <PlayerCard
      person={item.person}
      recommendation={item}
      featured={featured}
    />
  );
}

function DiscoverySearchResults({ query }: { query: string }) {
  const [cursor, setCursor] = useState<string | null>(null);
  const result = useRead<S["PersonList"]>(
    `/users/search?q=${encodeURIComponent(query)}${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ""}`,
  );
  return (
    <section
      className="discover-section"
      aria-labelledby="search-results-heading"
    >
      <h2 id="search-results-heading">Search results</h2>
      {result.isFetching || result.isPending ? (
        <p role="status">Finding players…</p>
      ) : result.isError ? (
        <p role="alert">{socialMessage(result.error)}</p>
      ) : result.data.items.length ? (
        <div className="discover-grid">
          {result.data.items.map((person) => (
            <PlayerCard key={person.handle} person={person} />
          ))}
        </div>
      ) : (
        <DiscoverEmptyState search />
      )}
      {!result.isFetching && result.data?.next_cursor && (
        <button onClick={() => setCursor(result.data.next_cursor ?? null)}>
          Next page
        </button>
      )}
      {cursor && (
        <button onClick={() => setCursor(null)}>Start from first page</button>
      )}
    </section>
  );
}

function Discover({ person }: { person: Person }) {
  const cache = useQueryClient();
  const [query, setQuery] = useState("");
  const recommendations = useRead<S["DiscoveryList"]>("/discovery/players");
  const friends = useRead<S["DiscoveryList"]>("/discovery/steam-friends");
  const items =
    !recommendations.isFetching && !recommendations.isError
      ? (recommendations.data?.items ?? [])
      : [];
  const friendItems =
    !friends.isFetching && !friends.isError ? (friends.data?.items ?? []) : [];
  const otherFriends = friendItems.filter(
    (friend) =>
      !items.some((item) => item.person.handle === friend.person.handle),
  );
  return (
    <>
      <DiscoverHero person={person} />
      <div className="discover-search-row">
        <form
          className="social-search"
          onSubmit={(event) => {
            event.preventDefault();
            setQuery(
              String(
                new FormData(event.currentTarget).get("query") ?? "",
              ).trim(),
            );
          }}
        >
          <Icon name="search" />
          <label className="sr-only" htmlFor="social-search">
            Search handle or display name
          </label>
          <Input
            id="social-search"
            name="query"
            minLength={3}
            maxLength={64}
            required
            placeholder="Search players by name or handle"
          />
          <Button type="submit" variant="secondary">
            Search players
          </Button>
          {query && (
            <button type="reset" onClick={() => setQuery("")}>
              Clear search
            </button>
          )}
        </form>
        <div className="discover-utilities">
          <button
            className="discover-reload"
            onClick={() => void cache.invalidateQueries()}
          >
            Reload saved data
          </button>
          <Link className="discover-preferences" href="/account/privacy">
            <Icon name="settings" />
            <span>Preferences</span>
          </Link>
        </div>
      </div>
      {query.length >= 3 && (
        <DiscoverySearchResults key={query} query={query} />
      )}
      <section
        className="discover-section"
        aria-labelledby="recommendations-heading"
      >
        <div className="discover-section-heading">
          <h2 id="recommendations-heading">Recommended for you</h2>
          <span>Shared games. New connections.</span>
        </div>
        {recommendations.isFetching || recommendations.isPending ? (
          <p role="status">Finding your next connection…</p>
        ) : recommendations.isError ? (
          <p role="alert">{socialMessage(recommendations.error)}</p>
        ) : items.length ? (
          <div
            className={`discover-grid discover-grid-${items.length === 1 ? "single" : items.length === 2 ? "pair" : "many"}`}
          >
            {items.map((item, index) => (
              <RecommendationCard
                key={item.person.handle}
                item={item}
                featured={items.length !== 2 && index === 0}
              />
            ))}
          </div>
        ) : (
          <DiscoverEmptyState />
        )}
      </section>
      <section
        className="discover-friends"
        aria-labelledby="steam-friends-heading"
      >
        <div className="discover-friends-title">
          <Icon name="people" />
          <h2 id="steam-friends-heading">Steam friends on SteamScope</h2>
        </div>
        {friends.isFetching || friends.isPending ? (
          <p role="status">Checking your circle…</p>
        ) : friends.isError ? (
          <p role="alert">{socialMessage(friends.error)}</p>
        ) : otherFriends.length ? (
          <div className="discover-grid">
            {otherFriends.map((item) => (
              <RecommendationCard key={item.person.handle} item={item} />
            ))}
          </div>
        ) : (
          <p>
            {friendItems.length
              ? "Your matching Steam friends are included above."
              : "No Steam friends here yet."}{" "}
            <Link href="/account/steam">View your Steam data →</Link>
          </p>
        )}
      </section>
    </>
  );
}

function RequestCard({ item }: { item: S["RequestView"] }) {
  const action = useAction();
  return (
    <>
      <PersonLink person={item.person} />
      <p>Pending · expires {new Date(item.expires_at).toLocaleDateString()}</p>
      <div className="social-buttons">
        {item.direction === "incoming" ? (
          <>
            <button
              disabled={action.busy}
              onClick={() =>
                void action.act(
                  `/connection-requests/${item.id}/accept`,
                  "POST",
                  undefined,
                  "Request processed.",
                )
              }
            >
              Accept request
            </button>
            <button
              disabled={action.busy}
              onClick={() =>
                void action.act(
                  `/connection-requests/${item.id}/reject`,
                  "POST",
                  undefined,
                  "Request rejected.",
                )
              }
            >
              Reject request
            </button>
          </>
        ) : (
          <button
            disabled={action.busy}
            onClick={() =>
              void action.act(
                `/connection-requests/${item.id}`,
                "DELETE",
                undefined,
                "Request cancelled.",
              )
            }
          >
            Cancel request
          </button>
        )}
      </div>
      {action.feedback}
    </>
  );
}

function ConnectionCard({ person }: { person: Person }) {
  const action = useAction();
  const [confirm, setConfirm] = useState(false);
  return (
    <>
      <PersonLink person={person} />
      <div className="social-buttons">
        <Link
          className="primary-action"
          href={`/messages?with=${encodeURIComponent(person.handle)}`}
        >
          Message
        </Link>
        <Link className="secondary-action" href={`/users/${person.handle}`}>
          View profile
        </Link>
        <MoreActions label="More connection actions">
          <button
            disabled={action.busy}
            onClick={() =>
              void action.act(
                `/connections/${person.handle}`,
                "DELETE",
                undefined,
                "Connection removed.",
              )
            }
          >
            Remove connection
          </button>
          <button onClick={() => setConfirm(true)}>Block player</button>
        </MoreActions>
      </div>
      <ConfirmDialog
        open={confirm}
        label="Confirm block"
        title={`Block @${person.handle}?`}
        busy={action.busy}
        onClose={() => setConfirm(false)}
        confirmLabel="Confirm block"
        cancelLabel="Cancel block"
        onConfirm={async () => {
          if (await action.act(`/blocks/${person.handle}`, "POST"))
            setConfirm(false);
        }}
      >
        This removes the connection. Unblocking will not restore it.
      </ConfirmDialog>
      {action.feedback}
    </>
  );
}

function BlockCard({ person }: { person: Person }) {
  const action = useAction();
  return (
    <>
      <strong>@{person.handle}</strong>
      <p>Unblocking does not restore a connection or pending request.</p>
      <button
        disabled={action.busy}
        onClick={() =>
          void action.act(
            `/blocks/${person.handle}`,
            "DELETE",
            undefined,
            "Unblocked. Reconnection requires a new request.",
          )
        }
      >
        Unblock player
      </button>
      {action.feedback}
    </>
  );
}

function Connections() {
  const [tab, setTab] = useState("connections");
  return (
    <>
      <section className="player-card">
        <h1>Connections</h1>
        <p>Your people, by mutual invitation.</p>
        <HelpDisclosure title="How connections work">
          <p>
            SteamScope connections require an accepted request. Imported Steam
            friendships do not grant access.
          </p>
        </HelpDisclosure>
      </section>
      <div className="section-tabs">
        <SegmentedControl
          aria-label="Connection sections"
          value={tab}
          onValueChange={setTab}
          options={[
            { value: "connections", label: "Connections" },
            { value: "requests", label: "Requests" },
            { value: "blocked", label: "Blocked" },
          ]}
        />
      </div>
      <div hidden={tab !== "connections"}>
        <Paged<Person>
          title="Your connections"
          path="/connections"
          empty="No SteamScope connections yet."
          render={(p) => <ConnectionCard person={p} />}
        />
      </div>
      <div hidden={tab !== "requests"}>
        <Paged<S["RequestView"]>
          title="Incoming requests"
          path="/connection-requests/incoming"
          empty="No incoming requests."
          render={(item) => <RequestCard item={item} />}
        />
        <Paged<S["RequestView"]>
          title="Outgoing requests"
          path="/connection-requests/outgoing"
          empty="No outgoing requests."
          render={(item) => <RequestCard item={item} />}
        />
      </div>
      <div hidden={tab !== "blocked"}>
        <Paged<Person>
          title="Blocked players"
          path="/blocks"
          empty="You have not blocked anyone."
          render={(p) => <BlockCard person={p} />}
        />
      </div>
    </>
  );
}

function NotificationCard({ item }: { item: S["NotificationView"] }) {
  const action = useAction();
  return (
    <div
      className={`notification-row ${item.read_at ? "is-read" : "is-unread"}`}
    >
      <div className="notification-event">
        <PersonLink person={item.person} />
        <p>
          {item.kind === "connection_request_received"
            ? "Connection request received"
            : "Connection request accepted"}
        </p>
        <time dateTime={item.created_at}>
          {new Date(item.created_at).toLocaleString()} ·{" "}
          {item.read_at ? "Read" : "Unread"}
        </time>
      </div>
      <div className="notification-actions">
        <Link href="/connections">Open Connections</Link>
        {!item.read_at && (
          <button
            disabled={action.busy}
            onClick={() =>
              void action.act(`/notifications/${item.id}/read`, "POST")
            }
          >
            Mark read
          </button>
        )}
      </div>
      {action.feedback}
    </div>
  );
}

function Notifications() {
  const action = useAction();
  return (
    <>
      <section className="player-card">
        <h1>Notifications</h1>
        <p>Saved connection events. Reload to check for updates.</p>
        <button
          disabled={action.busy}
          onClick={() =>
            void action.act(
              "/notifications/read-all",
              "POST",
              undefined,
              "Notifications marked read.",
            )
          }
        >
          Mark all read
        </button>
        {action.feedback}
      </section>
      <Paged<S["NotificationView"]>
        title="Your notifications"
        path="/notifications"
        empty="No notifications yet."
        render={(item) => <NotificationCard item={item} />}
      />
    </>
  );
}

export function SocialApp({ section }: { section: Section }) {
  const cache = useQueryClient();
  const account = useRead<Account>("/me");
  useEffect(() => {
    const ended = () => {
      document.documentElement.style.visibility = "hidden";
      void cache.cancelQueries();
      cache.clear();
      window.location.replace("/login?status=session-changed");
    };
    const channel =
      typeof BroadcastChannel === "undefined"
        ? null
        : new BroadcastChannel("steamscope-session");
    if (channel) channel.onmessage = ended;
    const restore = (event: PageTransitionEvent) => {
      if (event.persisted) {
        document.documentElement.style.visibility = "hidden";
        window.location.reload();
      }
    };
    window.addEventListener("steamscope-auth-ended", ended);
    window.addEventListener("pageshow", restore);
    return () => {
      channel?.close();
      window.removeEventListener("steamscope-auth-ended", ended);
      window.removeEventListener("pageshow", restore);
    };
  }, [cache]);
  return (
    <AppShell ownHandle={account.data?.handle}>
      <main
        id="social-main"
        className={`player-main social-main${section === "discover" ? " discover-v3" : ""}`}
      >
        {section !== "discover" && (
          <div className="page-tools">
            <button onClick={() => void cache.invalidateQueries()}>
              Reload saved data
            </button>
          </div>
        )}
        {account.isPending || account.isFetching ? (
          <p role="status">Checking your session…</p>
        ) : account.isError ? (
          <section className="player-card">
            <h1>Sign in to view your social pages</h1>
            <p role="alert">{socialMessage(account.error)}</p>
            <Link href="/login">Sign in through Steam</Link>
          </section>
        ) : (
          <>
            {section === "discover" && <Discover person={account.data} />}
            {section === "connections" && <Connections />}
            {section === "notifications" && <Notifications />}
          </>
        )}
        <HelpDisclosure title="Saved data & privacy">
          <p>
            These pages read saved data. No Steam synchronization happens when
            you browse or refresh.
          </p>
        </HelpDisclosure>
      </main>
    </AppShell>
  );
}
