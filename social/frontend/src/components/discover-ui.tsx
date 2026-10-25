"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import type { components } from "@/lib/api/schema";
import { PlayerAvatar, GameChip, HelpDisclosure, Icon } from "./ui";

type S = components["schemas"];
type Person = S["Person"];

function reasonLabel(reason: string) {
  const recent = /^You both recently played (\d+) visible games?$/.exec(reason);
  if (recent)
    return `${recent[1]} recent ${recent[1] === "1" ? "game" : "games"} in common`;
  const similar = /^Similar known playtime in (\d+) mutual games$/.exec(reason);
  if (similar) return `Similar playtime · ${similar[1]} games`;
  return reason;
}

export function MutualGamesStrip({
  games,
  total,
}: {
  games: S["MutualGame"][];
  total: number | null;
}) {
  if (!games.length) return null;
  const visible = games.slice(0, 3);
  return (
    <div className="mutual-games">
      <span className="mutual-games-label">Games in common</span>
      <ul>
        {visible.map((game) => (
          <li key={game.app_id}>
            <GameChip
              title={game.name ?? "Game title unavailable"}
              appId={game.app_id}
              visual={game.visual}
            />
          </li>
        ))}
      </ul>
      {total != null && total > visible.length && (
        <span className="mutual-more">
          +{total - visible.length} more in common
        </span>
      )}
    </div>
  );
}

export function DiscoverHero({ person }: { person: Person }) {
  return (
    <header className="discover-hero">
      <div>
        <h1>Discover players</h1>
        <p>Find people who actually play what you play.</p>
      </div>
      <Link className="discover-own-profile" href={`/users/${person.handle}`}>
        <PlayerAvatar
          uploadedSrc={person.avatar_url}
          name={person.display_name}
        />
        <span>
          <small>Your gaming identity</small>
          <strong>{person.display_name}</strong>
        </span>
        <Icon name="arrow" />
      </Link>
    </header>
  );
}

export function DiscoverPlayerCard({
  person,
  recommendation,
  biography,
  comparison,
  featured = false,
  actions,
}: {
  person: Person;
  recommendation?: S["Recommendation"];
  biography?: string;
  comparison?: S["PlayerComparison"];
  featured?: boolean;
  actions: ReactNode;
}) {
  // A second, current authorized read supplies names; no client-side ranking or
  // reconstruction from a hidden library. Missing or stale evidence stays absent.
  const games =
    comparison?.status === "available" &&
    comparison.left_library_state.data_available &&
    comparison.right_library_state.data_available &&
    !comparison.left_library_state.stale &&
    !comparison.right_library_state.stale
      ? comparison.items
      : [];
  return (
    <article
      className={`discovery-player discover-player-card${featured ? " featured-player" : ""}`}
    >
      <header className="discover-player-header">
        <Link className="discover-identity" href={`/users/${person.handle}`}>
          <PlayerAvatar
            uploadedSrc={person.avatar_url}
            name={person.display_name}
          />
          <div>
            <h3>{person.display_name}</h3>
            <span className="discover-handle">@{person.handle}</span>
          </div>
        </Link>
        <div className="discover-connection-action">{actions}</div>
      </header>
      <p className="discover-bio">
        {biography || "A player to get to know. Start with their gaming story."}
      </p>
      {games.length > 0 && (
        <MutualGamesStrip
          games={games}
          total={comparison?.mutual_count ?? null}
        />
      )}
      {recommendation && (
        <ul className="discover-reasons" aria-label="Recommendation reasons">
          {recommendation.mutual_games != null && (
            <li>
              <Icon name="games" />
              {recommendation.mutual_games} games in common
            </li>
          )}
          {recommendation.steam_friend && (
            <li>
              <Icon name="people" />
              Steam friend
            </li>
          )}
          {recommendation.reasons
            .filter(
              (reason) =>
                reason !==
                `You both have ${recommendation.mutual_games} visible games`,
            )
            .slice(0, 3)
            .map((reason) => (
              <li key={reason}>{reasonLabel(reason)}</li>
            ))}
        </ul>
      )}
      <div className="discover-card-footer">
        <Link
          className="discover-profile-link"
          href={`/users/${person.handle}`}
        >
          View profile <span aria-hidden="true">→</span>
        </Link>
        {recommendation && (
          <HelpDisclosure title="Why this player?">
            <p>Based on saved visible evidence, not a skill rating.</p>
            <p>Visible-evidence score: {recommendation.score} / 100</p>
            {recommendation.reasons.length > 0 && (
              <ul>
                {recommendation.reasons.map((reason) => (
                  <li key={reason}>{reason}</li>
                ))}
              </ul>
            )}
          </HelpDisclosure>
        )}
      </div>
    </article>
  );
}

export function DiscoverEmptyState({ search = false }: { search?: boolean }) {
  return (
    <div className={`discover-empty${search ? " discover-empty-search" : ""}`}>
      <Icon name={search ? "search" : "people"} />
      <div>
        <h3>
          {search ? "No players found" : "Your next connection is still ahead."}
        </h3>
        <p>
          {search
            ? "No visible players match this search."
            : "No recommendations yet. More players, more games in common."}
        </p>
      </div>
      {!search && (
        <Link href="/account/steam">
          Manage your Steam library <span aria-hidden="true">↗</span>
        </Link>
      )}
    </div>
  );
}
