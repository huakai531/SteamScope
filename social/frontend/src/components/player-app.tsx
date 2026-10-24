"use client";

import Link from "next/link";
import { Input } from "./ui";
import { useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { AccountError, accountRequest } from "@/lib/api/account";
import type { components } from "@/lib/api/schema";
import { AppShell } from "./app-shell";
import {
  PlayerAvatar,
  GameArt,
  GameIcon,
  Icon,
  StatusBadge,
  HelpDisclosure,
} from "./ui";
import { SocialActions } from "@/components/social-app";

type Schema = components["schemas"];
type Profile = Schema["PlayerProfile"];
type Game = Schema["PlayerGame"];
type State = Schema["PlayerState"];
type Progress = Schema["PlayerProgress"];
type View = "overview" | "games" | "game" | "compare";

export function minutes(value: number | null | undefined) {
  return value == null
    ? "Unknown"
    : `${value.toLocaleString()} min · ${(value / 60).toFixed(1)} h`;
}
function date(value: string | null | undefined) {
  return value ? new Date(value).toLocaleString() : "Unknown";
}
export function stateLabel(state: State) {
  if (state.status === "private") return "Private or not shared";
  if (state.stale)
    return state.data_available
      ? "Historical snapshot · stale"
      : "Stale snapshot · unavailable";
  if (state.status === "never") return "Not synchronized";
  if (!state.data_available) return "Source unavailable";
  if (state.status === "empty") return "Confirmed empty";
  if (state.status === "partial") return "Partial snapshot";
  return "Saved snapshot";
}
function Source({ state }: { state: State }) {
  return (
    <div className="player-source">
      <StatusBadge
        detail={stateLabel(state)}
        tone={state.stale ? "warning" : "muted"}
      >
        {state.status === "private"
          ? "Private"
          : state.stale
            ? "Stale"
            : stateLabel(state)}
      </StatusBadge>
      <span className="sr-only">{stateLabel(state)}</span>
      {state.in_progress && <span>Synchronization in progress</span>}
      <HelpDisclosure title="Snapshot details">
        <p>{stateLabel(state)}</p>
        {state.last_success_at && (
          <p>Last successful sync: {date(state.last_success_at)}</p>
        )}
      </HelpDisclosure>
    </div>
  );
}

function useRead<T>(path: string) {
  return useQuery({
    queryKey: ["player", path],
    queryFn: () => accountRequest<T>(path),
    staleTime: 0,
    gcTime: 0,
    refetchOnMount: "always",
    refetchOnWindowFocus: "always",
    retry: false,
  });
}
function Failure({ error }: { error: unknown }) {
  const code = error instanceof AccountError ? error.status : 0;
  return (
    <section className="player-card" role="alert">
      <h2>
        {code === 404
          ? "Player or game unavailable"
          : code === 401
            ? "Sign in to view players"
            : code === 409
              ? "The visible snapshot changed"
              : "Unable to load this view"}
      </h2>
      <p>
        {code === 404
          ? "This profile or game may be private, unavailable, or no longer exist."
          : code === 409
            ? "Privacy or saved data changed. Start again from the first page."
            : "Your previous view is hidden. Retry after checking your connection or session."}
      </p>
      {code === 401 && <Link href="/login">Sign in through Steam</Link>}
      <button onClick={() => window.location.reload()}>Restart view</button>
    </section>
  );
}
function ReadView<T>({
  query,
  children,
}: {
  query: ReturnType<typeof useRead<T>>;
  children: (data: T) => ReactNode;
}) {
  if (query.isFetching || query.isPending)
    return (
      <p role="status" className="player-loading">
        Loading visible saved data…
      </p>
    );
  if (query.isError || !query.data) return <Failure error={query.error} />;
  return <>{children(query.data)}</>;
}

export function PlayerApp({
  handle,
  view,
  appid,
  achievementLibrary = false,
}: {
  handle: string;
  view: View;
  appid?: string;
  achievementLibrary?: boolean;
}) {
  const client = useQueryClient();
  const profile = useRead<Profile>(`/users/${encodeURIComponent(handle)}`);
  useEffect(() => {
    const ended = () => {
      document.documentElement.style.visibility = "hidden";
      void client.cancelQueries();
      client.clear();
      window.location.replace("/login?status=session-changed");
    };
    const channel =
      typeof BroadcastChannel === "undefined"
        ? null
        : new BroadcastChannel("steamscope-session");
    if (channel) channel.onmessage = ended;
    const restored = (e: PageTransitionEvent) => {
      if (e.persisted) {
        document.documentElement.style.visibility = "hidden";
        window.location.reload();
      }
    };
    const visibility = () => {
      document.documentElement.style.visibility = document.hidden
        ? "hidden"
        : "";
    };
    window.addEventListener("pageshow", restored);
    window.addEventListener("steamscope-auth-ended", ended);
    document.addEventListener("visibilitychange", visibility);
    return () => {
      channel?.close();
      window.removeEventListener("pageshow", restored);
      window.removeEventListener("steamscope-auth-ended", ended);
      document.removeEventListener("visibilitychange", visibility);
      document.documentElement.style.visibility = "";
    };
  }, [client]);
  const base = `/users/${encodeURIComponent(handle)}`;
  return (
    <AppShell
      ownHandle={profile.data?.is_owner ? profile.data.handle : undefined}
    >
      <main id="player-main" className="player-layout" data-view={view}>
        <div className="player-topline">
          <Link className="back-link" href="/discover">
            <Icon name="arrow" /> Players
          </Link>
          <button
            onClick={() =>
              void client.invalidateQueries({ queryKey: ["player"] })
            }
          >
            Reload saved data
          </button>
        </div>
        <ReadView query={profile}>
          {(p) => (
            <>
              <header className="player-identity">
                <PlayerAvatar name={p.display_name} large />
                <div className="profile-heading">
                  <h1>{p.display_name}</h1>
                  <p className="player-handle">
                    @{p.handle}
                    {p.is_owner ? " · Your profile" : ""}
                  </p>
                  <p className="player-bio">
                    {p.biography || "No biography shared."}
                  </p>
                  <div className="player-steam">
                    <span>
                      Steam identity ·{" "}
                      {p.persona_name ?? "Steam persona unavailable"}
                    </span>
                    {p.steam_profile_url && (
                      <a
                        href={p.steam_profile_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        referrerPolicy="no-referrer"
                      >
                        View Steam profile ↗
                      </a>
                    )}
                  </div>
                  <Source state={p.profile_state} />
                </div>
                <div className="profile-actions">
                  {p.is_owner ? (
                    <Link className="secondary-action" href="/account/profile">
                      Edit profile
                    </Link>
                  ) : (
                    <SocialActions handle={p.handle} />
                  )}
                </div>
              </header>
              <nav className="player-tabs" aria-label="Player navigation">
                <Link
                  href={base}
                  aria-current={view === "overview" ? "page" : undefined}
                >
                  Overview
                </Link>
                <Link
                  href={base + "/games"}
                  aria-current={
                    view === "games" && !achievementLibrary ? "page" : undefined
                  }
                >
                  Game library
                </Link>
                <Link
                  href={base + "/games?achievements=true"}
                  aria-current={
                    achievementLibrary || view === "game" ? "page" : undefined
                  }
                >
                  Achievements
                </Link>
                {!p.is_owner && (
                  <Link
                    href={base + "/compare"}
                    aria-current={view === "compare" ? "page" : undefined}
                  >
                    Compare with me
                  </Link>
                )}
                {p.is_owner && (
                  <Link href="/account/steam">Manage Steam data</Link>
                )}
              </nav>
              {view === "overview" && <Overview profile={p} base={base} />}
              {view === "games" && (
                <Library
                  handle={handle}
                  profile={p}
                  achievementLibrary={achievementLibrary}
                />
              )}
              {view === "game" && (
                <GameDetail handle={handle} appid={appid ?? ""} />
              )}
              {view === "compare" && <Compare handle={handle} />}
            </>
          )}
        </ReadView>
        <HelpDisclosure title="Saved data & privacy">
          <p>
            These pages read saved snapshots. Viewing, filtering and refreshing
            do not request Steam synchronization. Visibility is checked for
            every request.
          </p>
        </HelpDisclosure>
      </main>
    </AppShell>
  );
}

function Stat({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="player-stat">
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}
function GamingIdentityCard({
  profile: p,
  base,
}: {
  profile: Profile;
  base: string;
}) {
  return (
    <section className="gaming-identity-card" aria-labelledby="summary-title">
      <div className="gaming-card-heading">
        <div>
          <h2 id="summary-title">Gaming identity</h2>
          <Source state={p.library_state} />
        </div>
        <Link className="gaming-card-link" href={base + "/games"}>
          Browse library <span aria-hidden="true">→</span>
        </Link>
      </div>
      {!!p.most_played?.length && (
        <div className="identity-games" aria-label="Saved most-played games">
          {p.most_played.slice(0, 3).map((g) => (
            <Link key={g.app_id} href={`${base}/games/${g.app_id}`}>
              <GameArt
                title={g.name ?? "Game title unavailable"}
                appId={g.app_id}
              />
              <strong>{g.name ?? `Game ${g.app_id}`}</strong>
              <span>
                {g.total_minutes == null
                  ? "Playtime unknown"
                  : `${(g.total_minutes / 60).toFixed(1)} h played`}
              </span>
            </Link>
          ))}
        </div>
      )}
      <dl className="player-stats">
        <Stat label="Visible games" value={p.game_count ?? "Unavailable"} />
        <Stat
          label="Visible total playtime"
          value={
            p.playtime_visible ? (
              p.total_minutes == null ? (
                "Unknown"
              ) : (
                <>
                  <span className="stat-emphasis">
                    {(p.total_minutes / 60).toFixed(1)}
                    <small> h</small>
                  </span>
                  <span className="stat-detail">
                    {p.total_minutes.toLocaleString()} min
                  </span>
                </>
              )
            ) : (
              "Not shared or unavailable"
            )
          }
        />
        <Stat
          label="Saved achievement games"
          value={p.synchronized_achievement_games ?? "Unavailable"}
        />
      </dl>
      <HelpDisclosure title="About achievement coverage">
        <p>
          Achievement coverage is limited to selected synchronized games. It is
          not overall Steam completion.
        </p>
      </HelpDisclosure>
    </section>
  );
}
function Overview({ profile: p, base }: { profile: Profile; base: string }) {
  return (
    <>
      <GamingIdentityCard profile={p} base={base} />
      <div className="player-columns">
        <section className="player-card">
          <h2>Most played</h2>
          <GameList
            items={p.most_played ?? []}
            base={base}
            empty={
              p.playtime_visible
                ? "No known playtime to order."
                : "Playtime is not shared or unavailable."
            }
          />
        </section>
        <section className="player-card">
          <h2>Recent games</h2>
          <Source state={p.recent_state} />
          <GameList
            items={p.recent_games ?? []}
            base={base}
            recent
            empty={
              p.recent_state.data_available
                ? "No recent games in the saved snapshot."
                : "Recent data unavailable. Old activity is not shown as current."
            }
          />
        </section>
      </div>
      <HelpDisclosure title="Compare saved libraries">
        <p>Enter a SteamScope handle to compare mutually visible games.</p>
        <CompareForm />
      </HelpDisclosure>
    </>
  );
}
function CompareForm() {
  const router = useRouter();
  const [target, setTarget] = useState("");
  return (
    <form
      className="player-inline"
      onSubmit={(e) => {
        e.preventDefault();
        if (/^[A-Za-z][A-Za-z0-9_]{2,23}$/.test(target))
          router.push(`/users/${encodeURIComponent(target)}/compare`);
      }}
    >
      <label>
        SteamScope handle
        <Input
          value={target}
          onChange={(e) => setTarget(e.target.value)}
          minLength={3}
          maxLength={24}
          pattern="[A-Za-z][A-Za-z0-9_]{2,23}"
          required
          autoComplete="off"
        />
      </label>
      <button type="submit">Compare with me</button>
    </form>
  );
}
function GameList({
  items,
  base,
  recent = false,
  empty,
}: {
  items: Game[];
  base: string;
  recent?: boolean;
  empty: string;
}) {
  return items.length ? (
    <ul className="player-game-list">
      {items.map((g) => (
        <li key={g.app_id}>
          <GameIcon title={g.name ?? "Game"} appId={g.app_id} />
          <Link href={`${base}/games/${g.app_id}`}>
            {g.name ?? `Game ${g.app_id}`}
          </Link>
          <span>{minutes(recent ? g.recent_minutes : g.total_minutes)}</span>
        </li>
      ))}
    </ul>
  ) : (
    <p>{empty}</p>
  );
}
function Pager({
  next,
  previous,
  onNext,
  onPrevious,
}: {
  next?: string | null;
  previous: boolean;
  onNext: () => void;
  onPrevious: () => void;
}) {
  return (
    <nav className="player-pager" aria-label="Pagination">
      <button onClick={onPrevious} disabled={!previous}>
        Previous page
      </button>
      <button onClick={onNext} disabled={!next}>
        Next page
      </button>
    </nav>
  );
}
function Library({
  handle,
  profile,
  achievementLibrary,
}: {
  handle: string;
  profile: Profile;
  achievementLibrary: boolean;
}) {
  const [q, setQ] = useState("");
  const [sort, setSort] = useState("name");
  const [ach, setAch] = useState(achievementLibrary);
  const [recent, setRecent] = useState(false);
  const params = new URLSearchParams({
    q,
    sort: profile.playtime_visible ? sort : "name",
    achievements: String(profile.achievements_visible && ach),
    recent: String(profile.playtime_visible && recent),
  }).toString();
  return (
    <section>
      <h2>Game library</h2>
      <Source state={profile.library_state} />
      <div className="player-filters">
        <label>
          Search visible game names
          <Input
            type="search"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            maxLength={80}
          />
        </label>
        <label>
          Sort games
          <select
            value={profile.playtime_visible ? sort : "name"}
            onChange={(e) => setSort(e.target.value)}
          >
            <option value="name">Name A–Z</option>
            <option value="total" disabled={!profile.playtime_visible}>
              Total playtime
            </option>
            <option value="recent" disabled={!profile.playtime_visible}>
              Recent playtime
            </option>
            <option value="last_played" disabled={!profile.playtime_visible}>
              Last played
            </option>
          </select>
        </label>
        <label className="player-check">
          <input
            type="checkbox"
            checked={profile.achievements_visible && ach}
            onChange={(e) => setAch(e.target.checked)}
            disabled={!profile.achievements_visible}
          />
          With achievement data
        </label>
        <label className="player-check">
          <input
            type="checkbox"
            checked={profile.playtime_visible && recent}
            onChange={(e) => setRecent(e.target.checked)}
            disabled={!profile.playtime_visible}
          />
          Recently played
        </label>
      </div>
      <LibraryPage key={handle + params} handle={handle} params={params} />
    </section>
  );
}
function LibraryPage({ handle, params }: { handle: string; params: string }) {
  const [cursors, setCursors] = useState<string[]>([]);
  const query = useRead<Schema["PlayerLibrary"]>(
    `/users/${handle}/games?${params}&limit=12${cursors.length ? "&cursor=" + encodeURIComponent(cursors.at(-1)!) : ""}`,
  );
  return (
    <ReadView query={query}>
      {(data) => (
        <>
          <p className="player-muted">
            {data.total_count == null
              ? "Library not shared or unavailable"
              : `${data.total_count} visible matching games`}
          </p>
          <div className="player-library">
            {data.items.map((g) => (
              <article key={g.app_id} className="player-card library-game-card">
                <GameArt title={g.name ?? "Game"} appId={g.app_id} />
                <div className="game-card-content">
                  <h3>
                    <Link href={`/users/${handle}/games/${g.app_id}`}>
                      {g.name ?? `Game ${g.app_id}`}
                    </Link>
                  </h3>
                  <dl className="game-card-stats">
                    <Stat
                      label="Total playtime"
                      value={minutes(g.total_minutes)}
                    />
                    <Stat
                      label="Recent playtime"
                      value={minutes(g.recent_minutes)}
                    />
                  </dl>
                  <HelpDisclosure title="Last played">
                    <p>{date(g.last_played_at)}</p>
                  </HelpDisclosure>
                  <ProgressSummary progress={g.achievements} compact />
                </div>
              </article>
            ))}
          </div>
          {!data.items.length && (
            <p>
              {data.state.data_available
                ? "No games match these filters."
                : "Saved game rows and counts are unavailable."}
            </p>
          )}
          <Pager
            next={data.next_cursor}
            previous={!!cursors.length}
            onPrevious={() => setCursors(cursors.slice(0, -1))}
            onNext={() =>
              data.next_cursor && setCursors([...cursors, data.next_cursor])
            }
          />
        </>
      )}
    </ReadView>
  );
}
export function ProgressSummary({
  progress: p,
  compact = false,
}: {
  progress: Progress;
  compact?: boolean;
}) {
  return (
    <div className={`player-progress${compact ? " progress-compact" : ""}`}>
      <p className="progress-state">
        <StatusBadge
          detail={stateLabel(p.state)}
          tone={p.state.stale ? "warning" : "muted"}
        >
          {p.state.stale
            ? "Stale"
            : p.state.status === "private"
              ? "Private"
              : stateLabel(p.state)}
        </StatusBadge>
        <span className="sr-only">{stateLabel(p.state)}</span>
        <span>Coverage: {p.coverage}</span>
      </p>
      {p.state.data_available && (
        <p className="achievement-counts">
          Known unlocked: {p.known_unlocked ?? "Unknown"} · Known locked:{" "}
          {p.known_locked ?? "Unknown"} · Definitions:{" "}
          {p.definition_count ?? "Unknown"}
        </p>
      )}
      {p.completion_percent != null && (
        <progress
          className="achievement-meter"
          max={100}
          value={p.completion_percent}
          aria-label="Selected game completion"
        />
      )}
      <p className="completion-value">
        Selected game completion:{" "}
        {p.completion_percent == null
          ? "Unavailable"
          : `${p.completion_percent}%`}
      </p>
      {p.coverage === "stale" && (
        <HelpDisclosure title="Why is completion unavailable?">
          <p>
            Historical achievement data. Exact completion needs fresh compatible
            snapshots.
          </p>
        </HelpDisclosure>
      )}
    </div>
  );
}
function GameDetail({ handle, appid }: { handle: string; appid: string }) {
  const query = useRead<Schema["PlayerGameDetail"]>(
    `/users/${handle}/games/${appid}`,
  );
  return (
    <ReadView query={query}>
      {(data) => (
        <>
          <section className="player-card game-detail-summary">
            <div className="game-detail-identity">
              <GameArt
                title={data.game.name ?? "Game"}
                appId={data.game.app_id}
              />
              <div>
                <h2>{data.game.name ?? `Game ${appid}`}</h2>
                <Source state={data.library_state} />
              </div>
            </div>
            <dl className="player-stats">
              <Stat
                label="Total playtime"
                value={minutes(data.game.total_minutes)}
              />
              <Stat
                label="Recent playtime"
                value={minutes(data.game.recent_minutes)}
              />
              <Stat
                label="Last played"
                value={date(data.game.last_played_at)}
              />
            </dl>
          </section>
          <Achievements key={handle + appid} handle={handle} appid={appid} />
        </>
      )}
    </ReadView>
  );
}
function Achievements({ handle, appid }: { handle: string; appid: string }) {
  const [cursors, setCursors] = useState<string[]>([]);
  const [reveal, setReveal] = useState(false);
  const query = useRead<Schema["PlayerAchievements"]>(
    `/users/${handle}/games/${appid}/achievements?limit=50${cursors.length ? "&cursor=" + encodeURIComponent(cursors.at(-1)!) : ""}`,
  );
  return (
    <section className="player-card" id="achievements">
      <h2>Selected-game achievements</h2>
      <ReadView query={query}>
        {(data) => (
          <>
            <Source state={data.progress.state} />
            <ProgressSummary progress={data.progress} />
            {data.items.length > 0 && (
              <label className="player-check">
                <input
                  type="checkbox"
                  checked={reveal}
                  onChange={(e) => setReveal(e.target.checked)}
                />
                Reveal hidden achievement spoilers
              </label>
            )}
            <ul className="player-achievements">
              {data.items.map((a) => (
                <li
                  key={a.api_name}
                  className={
                    a.unlocked === true
                      ? "achievement-unlocked"
                      : a.unlocked === false
                        ? "achievement-locked"
                        : "achievement-unknown"
                  }
                >
                  <span className="achievement-icon" aria-hidden="true">
                    <Icon name="award" />
                  </span>
                  <div>
                    <strong>
                      {a.hidden && !reveal
                        ? "Hidden achievement"
                        : (a.display_name ?? "Unnamed achievement")}
                    </strong>
                    {(!a.hidden || reveal) && a.description && (
                      <p>{a.description}</p>
                    )}
                  </div>
                  <div className="player-achievement-state">
                    <span>
                      {a.unlocked === null
                        ? "State unknown"
                        : a.unlocked
                          ? "Unlocked"
                          : "Locked"}
                    </span>
                    {a.unlocked && a.unlocked_at && (
                      <time dateTime={a.unlocked_at}>
                        {date(a.unlocked_at)}
                      </time>
                    )}
                  </div>
                </li>
              ))}
            </ul>
            {!data.items.length && (
              <p>
                {data.progress.coverage === "no_achievements"
                  ? "No achievements in the compatible saved schema."
                  : "Achievement details are not shared or not available."}
              </p>
            )}
            <Pager
              next={data.next_cursor}
              previous={!!cursors.length}
              onPrevious={() => setCursors(cursors.slice(0, -1))}
              onNext={() =>
                data.next_cursor && setCursors([...cursors, data.next_cursor])
              }
            />
          </>
        )}
      </ReadView>
    </section>
  );
}
function Compare({ handle }: { handle: string }) {
  const [cursors, setCursors] = useState<string[]>([]);
  const query = useRead<Schema["PlayerComparison"]>(
    `/users/${handle}/comparison?limit=12${cursors.length ? "&cursor=" + encodeURIComponent(cursors.at(-1)!) : ""}`,
  );
  return (
    <section>
      <h2>Mutually visible games</h2>
      <ReadView query={query}>
        {(data) => (
          <>
            <p>
              Comparing @{data.left_handle} (you) with @{data.right_handle}
            </p>
            <dl className="player-stats">
              <Stat
                label="Mutual games"
                value={data.mutual_count ?? "Unavailable"}
              />
              <Stat
                label="Your mutual playtime"
                value={minutes(data.left_total_minutes)}
              />
              <Stat
                label="Their mutual playtime"
                value={minutes(data.right_total_minutes)}
              />
              <Stat
                label="Comparable achievement games"
                value={data.comparable_achievement_games ?? "Unavailable"}
              />
            </dl>
            <div className="player-columns">
              <Source state={data.left_library_state} />
              <Source state={data.right_library_state} />
            </div>
            {!data.items.length && (
              <div className="player-card">
                <h3>
                  {data.status === "available"
                    ? "No mutually visible games"
                    : "Comparison unavailable"}
                </h3>
                <p>
                  {data.status === "available"
                    ? "The currently visible libraries have no games in common."
                    : "Both libraries need visible saved data. No hidden counts or shared-game evidence are shown."}
                </p>
              </div>
            )}
            {data.items.map((g) => (
              <article key={g.app_id} className="player-card">
                <h3>
                  <Link
                    className="comparison-game-name"
                    href={`/users/${handle}/games/${g.app_id}`}
                  >
                    <GameIcon
                      title={g.name ?? "Game title unavailable"}
                      appId={g.app_id}
                    />
                    {g.name ?? `Game ${g.app_id}`}
                  </Link>
                </h3>
                <div className="player-columns">
                  <div>
                    <h4>@{data.left_handle} · You</h4>
                    <p>Total: {minutes(g.left_minutes)}</p>
                    <p>Recent: {minutes(g.left_recent_minutes)}</p>
                    <p>
                      Achievement coverage: {g.left_achievements.coverage} ·{" "}
                      {stateLabel(g.left_achievements.state)}
                    </p>
                    <p>
                      Comparable completion:{" "}
                      {g.left_completion == null
                        ? "Unavailable"
                        : `${g.left_completion}%`}
                    </p>
                  </div>
                  <div>
                    <h4>@{data.right_handle}</h4>
                    <p>Total: {minutes(g.right_minutes)}</p>
                    <p>Recent: {minutes(g.right_recent_minutes)}</p>
                    <p>
                      Achievement coverage: {g.right_achievements.coverage} ·{" "}
                      {stateLabel(g.right_achievements.state)}
                    </p>
                    <p>
                      Comparable completion:{" "}
                      {g.right_completion == null
                        ? "Unavailable"
                        : `${g.right_completion}%`}
                    </p>
                  </div>
                </div>
                <p className="player-muted">
                  Playtime difference (you − them):{" "}
                  {g.difference_minutes == null
                    ? "Unknown"
                    : `${g.difference_minutes} min`}
                </p>
              </article>
            ))}
            <Pager
              next={data.next_cursor}
              previous={!!cursors.length}
              onPrevious={() => setCursors(cursors.slice(0, -1))}
              onNext={() =>
                data.next_cursor && setCursors([...cursors, data.next_cursor])
              }
            />
            <p className="player-muted">
              A comparison of saved data, not a skill ranking or compatibility
              score.
            </p>
          </>
        )}
      </ReadView>
    </section>
  );
}
