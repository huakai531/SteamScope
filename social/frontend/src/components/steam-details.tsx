"use client";

import { useState, type ComponentType } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  AccountError,
  accountMessage,
  accountRequest,
} from "@/lib/api/account";
import type { components } from "@/lib/api/schema";

type Achievements = components["schemas"]["AchievementsView"];
type Friends = components["schemas"]["FriendsView"];
type Resource = components["schemas"]["ResourceView"];
type Game = components["schemas"]["GameView"];

export function AchievementSnapshot({ data }: { data: Achievements }) {
  const [reveal, setReveal] = useState(false);
  return (
    <>
      <p>
        Coverage: {data.coverage.replaceAll("_", " ")}. Schema language:
        English.
      </p>
      <p>
        Known unlocked: {data.known_unlocked ?? "Unknown"}; known locked:{" "}
        {data.known_locked ?? "Unknown"}; applicable definitions:{" "}
        {data.definition_count ?? "Unknown"}.
      </p>
      <p>
        Selected game completion:{" "}
        {data.completion_percent == null
          ? "Unavailable"
          : `${data.completion_percent}%`}
        . This is not completion across your whole library.
      </p>
      {data.schema_state.status === "empty" && !data.schema_state.stale && (
        <p>The validated schema contains no supported achievements.</p>
      )}
      {data.schema_state.stale && (
        <p>Shared definitions are stale. Exact completion is unavailable.</p>
      )}
      {data.coverage === "partial" && (
        <p>
          Schema and player coverage are incomplete or inconsistent. Unknown
          states are not treated as locked.
        </p>
      )}
      <label>
        <input
          type="checkbox"
          checked={reveal}
          onChange={(e) => setReveal(e.target.checked)}
        />{" "}
        Reveal hidden achievement spoilers
      </label>
      <ul className="steam-games">
        {data.items.map((item) => (
          <li key={item.api_name}>
            <strong>
              {item.hidden && !reveal
                ? "Hidden achievement"
                : (item.display_name ?? item.api_name)}
            </strong>
            {(!item.hidden || reveal) && item.description && (
              <span>{item.description}</span>
            )}
            {!item.definition_available && (
              <span>
                Definition unavailable for this saved player identifier.
              </span>
            )}
            <span>
              {item.unlocked == null
                ? "State unknown"
                : item.unlocked
                  ? "Unlocked"
                  : "Locked"}
            </span>
            {item.unlocked && (
              <span>
                Unlock time:{" "}
                {item.unlocked_at ? (
                  <time dateTime={item.unlocked_at}>
                    {new Date(item.unlocked_at).toLocaleString()}
                  </time>
                ) : (
                  "Unknown"
                )}
              </span>
            )}
          </li>
        ))}
      </ul>
    </>
  );
}

export function FriendSnapshot({ data }: { data: Friends }) {
  return (
    <>
      <p>
        Imported Steam friends: {data.total_count ?? "Unknown"}. These are not
        SteamScope connections.
      </p>
      {data.state.code === "FRIENDS_PRIVATE_OR_UNAUTHORIZED" && (
        <p>
          Steam returns 401 for private friend lists. Privacy or another
          authorization issue may apply; no old list or count is exposed as
          current.
        </p>
      )}
      <ul className="steam-games">
        {data.items.map((friend) => (
          <li key={friend.steam_id64}>
            <span>{friend.steam_id64}</span>
            <a
              href={`https://steamcommunity.com/profiles/${encodeURIComponent(friend.steam_id64)}/`}
              target="_blank"
              rel="noopener noreferrer"
            >
              Open Steam profile {friend.steam_id64}
            </a>
            <span>
              Friends since:{" "}
              {friend.friend_since ? (
                <time dateTime={friend.friend_since}>
                  {new Date(friend.friend_since).toLocaleDateString()}
                </time>
              ) : (
                "Unknown"
              )}
            </span>
          </li>
        ))}
      </ul>
    </>
  );
}

export function SteamDetails({
  ownerId,
  games,
  configured,
  Status,
}: {
  ownerId: string;
  games: Game[];
  configured: boolean;
  Status: ComponentType<{ state: Resource }>;
}) {
  const [app, setApp] = useState("");
  const [achCursor, setAchCursor] = useState({
    after: "",
    snapshot: "",
    revision: "",
  });
  const [friendCursor, setFriendCursor] = useState({ after: "", snapshot: "" });
  const [busy, setBusy] = useState(false);
  const [achievementMessage, setAchievementMessage] = useState({
    app: "",
    text: "",
  });
  const [friendMessage, setFriendMessage] = useState("");
  const selected = games.some((g) => String(g.app_id) === app);
  const achievements = useQuery({
    queryKey: ["steam", ownerId, "achievements", app, achCursor],
    queryFn: () =>
      accountRequest<Achievements>(
        `/me/steam/games/${app}/achievements` +
          (achCursor.after ? `?${new URLSearchParams(achCursor)}` : ""),
      ),
    enabled: selected,
    gcTime: 0,
    staleTime: 0,
    refetchInterval: 3000,
    refetchOnWindowFocus: true,
    retry: false,
  });
  const friends = useQuery({
    queryKey: ["steam", ownerId, "friends", friendCursor],
    queryFn: () =>
      accountRequest<Friends>(
        "/me/steam/friends" +
          (friendCursor.after ? `?${new URLSearchParams(friendCursor)}` : ""),
      ),
    gcTime: 0,
    staleTime: 0,
    refetchInterval: 3000,
    refetchOnWindowFocus: true,
    retry: false,
  });
  async function sync(kind: "achievements" | "friends") {
    const requestedApp = app;
    const feedback = (text: string) => {
      if (kind === "friends") setFriendMessage(text);
      else setAchievementMessage({ app: requestedApp, text });
    };
    setBusy(true);
    feedback("");
    try {
      await accountRequest(
        kind === "friends"
          ? "/me/steam/friends/sync"
          : `/me/steam/games/${app}/achievements/sync`,
        "POST",
      );
      feedback(
        kind === "friends"
          ? "Steam friend-list synchronization requested."
          : "Selected-game achievement synchronization requested.",
      );
      setAchCursor({ after: "", snapshot: "", revision: "" });
      setFriendCursor({ after: "", snapshot: "" });
      await Promise.all([
        friends.refetch(),
        ...(selected ? [achievements.refetch()] : []),
      ]);
    } catch (error) {
      feedback(
        error instanceof AccountError &&
          ["STEAM_SYNC_COOLDOWN", "STEAM_QUEUE_LIMIT"].includes(
            error.detail.code,
          )
          ? "Please wait for the cooldown or active request limit before trying again."
          : accountMessage(error),
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <section aria-label="Selected-game achievements and imported Steam friends">
      <h2>Selected-game achievements</h2>
      <p>
        Choose a game from this library page. This action reads one game only;
        it cannot unlock or reset achievements on Steam.
      </p>
      <label>
        Game for achievements
        <select
          value={selected ? app : ""}
          onChange={(e) => {
            setApp(e.target.value);
            setAchievementMessage({ app: "", text: "" });
            setAchCursor({ after: "", snapshot: "", revision: "" });
          }}
        >
          <option value="">Select an eligible game</option>
          {games.map((g) => (
            <option key={g.app_id} value={g.app_id}>
              {g.name ?? `App ${g.app_id}`}
            </option>
          ))}
        </select>
      </label>
      <button
        disabled={!selected || !configured || busy}
        onClick={() => void sync("achievements")}
      >
        Sync selected game achievements
      </button>
      {achievementMessage.app === app && achievementMessage.text && (
        <p role="status" aria-label="Achievement request feedback">
          {achievementMessage.text}
        </p>
      )}
      {selected && achievements.isPending && <p>Loading saved achievements…</p>}
      {selected && achievements.isError && (
        <div role="alert">
          <p>
            Saved achievements could not be read. The library or snapshot may
            have changed.
          </p>
          <button
            onClick={() => {
              setAchCursor({ after: "", snapshot: "", revision: "" });
              void achievements.refetch();
            }}
          >
            Reload achievement first page
          </button>
        </div>
      )}
      {selected && achievements.data && !achievements.isError && (
        <>
          <p>
            Achievement job:{" "}
            {achievements.data.latest_job?.status ?? "No job requested"}
          </p>
          {achievements.data.latest_job && (
            <p>Achievement task ID: {achievements.data.latest_job.id}</p>
          )}
          <Status state={achievements.data.state} />
          <AchievementSnapshot
            key={`${app}:${achievements.data.state.snapshot_id}`}
            data={achievements.data}
          />
          <div className="steam-pagination">
            <button
              disabled={!achCursor.after}
              onClick={() =>
                setAchCursor({ after: "", snapshot: "", revision: "" })
              }
            >
              First achievement page
            </button>
            <button
              disabled={
                !achievements.data.next_after ||
                !achievements.data.state.snapshot_id ||
                !achievements.data.schema_state.revision
              }
              onClick={() =>
                setAchCursor({
                  after: achievements.data!.next_after!,
                  snapshot: achievements.data!.state.snapshot_id!,
                  revision: achievements.data!.schema_state.revision!,
                })
              }
            >
              Next achievement page
            </button>
          </div>
        </>
      )}
      <h2>Imported Steam friends</h2>
      <p>
        Read your accessible Steam friend list only when you request it. No
        friend profiles, other libraries, SteamScope account matches or friends
        of friends are fetched. You can keep your Steam list private.
      </p>
      <button
        disabled={!configured || busy}
        onClick={() => void sync("friends")}
      >
        Sync my Steam friends
      </button>
      {friendMessage && (
        <p role="status" aria-label="Friend-list request feedback">
          {friendMessage}
        </p>
      )}
      {friends.isPending && <p>Loading saved Steam friends…</p>}
      {friends.isError && (
        <div role="alert">
          <p>
            Saved Steam friends could not be read. Reload the first page if the
            snapshot changed.
          </p>
          <button
            onClick={() => {
              setFriendCursor({ after: "", snapshot: "" });
              void friends.refetch();
            }}
          >
            Reload friend first page
          </button>
        </div>
      )}
      {friends.data && !friends.isError && (
        <>
          <p>
            Friend-list job:{" "}
            {friends.data.latest_job?.status ?? "No job requested"}
          </p>
          {friends.data.latest_job && (
            <p>Friend-list task ID: {friends.data.latest_job.id}</p>
          )}
          <Status state={friends.data.state} />
          <FriendSnapshot data={friends.data} />
          <div className="steam-pagination">
            <button
              disabled={!friendCursor.after}
              onClick={() => setFriendCursor({ after: "", snapshot: "" })}
            >
              First friend page
            </button>
            <button
              disabled={!friends.data.next_after}
              onClick={() =>
                setFriendCursor({
                  after: friends.data!.next_after!,
                  snapshot: friends.data!.state.snapshot_id!,
                })
              }
            >
              Next friend page
            </button>
          </div>
        </>
      )}
    </section>
  );
}
