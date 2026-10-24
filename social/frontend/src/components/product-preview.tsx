"use client";
import { useState } from "react";
import Image from "next/image";
import { Icon } from "./ui";

// Public, illustrative content only. No account data, mutations or network calls.
const games = [
  { name: "Orbit Relay", hours: 21.2, art: "orbit-relay.svg" },
  { name: "Mosslight Vale", hours: 15.8, art: "mosslight-vale.svg" },
  { name: "Ember Circuit", hours: 12, art: "ember-circuit.svg" },
];

export function ProductPreview() {
  const [selected, setSelected] = useState(games[0].name);
  const [motionPaused, setMotionPaused] = useState(false);
  return (
    <figure
      className="product-preview"
      id="product-preview"
      data-motion-paused={motionPaused}
    >
      <figcaption>
        <span>Illustrative preview · fictional games</span>
        <button
          type="button"
          className="preview-motion-toggle"
          onClick={() => setMotionPaused(!motionPaused)}
          aria-label={
            motionPaused ? "Resume preview motion" : "Pause preview motion"
          }
        >
          <svg
            aria-hidden="true"
            viewBox="0 0 20 20"
            width="16"
            height="16"
            fill="currentColor"
          >
            {motionPaused ? (
              <path d="m6 4 10 6-10 6Z" />
            ) : (
              <path d="M5 4h3v12H5zm7 0h3v12h-3z" />
            )}
          </svg>
        </button>
      </figcaption>
      <div className="preview-composition">
        <div className="preview-profile" data-ui>
          <div className="preview-app-name">Player profile</div>
          <div className="preview-person">
            <PreviewAvatar person="Alex" large />
            <div>
              <h2>Alex</h2>
              <span>Steam linked</span>
            </div>
          </div>
          <dl className="preview-stats">
            <div>
              <dt>Games</dt>
              <dd>{games.length}</dd>
            </div>
            <div>
              <dt>Hours played</dt>
              <dd>
                {games.reduce((total, game) => total + game.hours, 0)}
                <span>h</span>
              </dd>
            </div>
          </dl>
          <div className="preview-library-title">
            <strong>Game library</strong>
            <Icon name="games" />
          </div>
          <div className="preview-library">
            {games.map((game) => (
              <div key={game.name}>
                <PreviewGameArt game={game} />
                <strong>{game.name}</strong>
                <span>{game.hours} h</span>
              </div>
            ))}
          </div>
        </div>
        <div className="preview-mutual" data-ui>
          <div className="preview-match-heading">
            <Icon name="discover" />
            <strong>{games.length} games in common</strong>
          </div>
          <div
            className="preview-game-picker"
            role="group"
            aria-label="Try a game in the sample conversation"
          >
            {games.map((game) => (
              <button
                key={game.name}
                aria-label={game.name}
                aria-pressed={selected === game.name}
                onClick={() => setSelected(game.name)}
              >
                <PreviewGameArt game={game} compact />
              </button>
            ))}
          </div>
          <span>Try a game</span>
        </div>
        <div className="preview-conversation" data-ui>
          <div className="preview-connection">
            <PreviewAvatar person="Mira" />
            <strong>Mira</strong>
            <span>
              <CheckMark /> Connected
            </span>
          </div>
          <div className="preview-chat" aria-live="polite">
            <p>You play {selected} too?</p>
          </div>
        </div>
      </div>
    </figure>
  );
}

export function JourneyPreview({
  kind,
}: {
  kind: "profile" | "discover" | "chat";
}) {
  return (
    <div
      className={`journey-preview journey-panel-${kind}`}
      data-ui
      aria-label={`Illustrative ${kind} preview`}
    >
      {kind === "profile" ? (
        <>
          <div className="journey-person">
            <PreviewAvatar person="Alex" />
            <strong>Alex</strong>
          </div>
          <div className="journey-shared">
            {games.map((game) => (
              <PreviewGameArt key={game.name} game={game} compact />
            ))}
          </div>
        </>
      ) : kind === "discover" ? (
        <>
          <div className="journey-person">
            <PreviewAvatar person="Mira" />
            <strong>Mira</strong>
          </div>
          <div className="journey-shared">
            {games.map((game) => (
              <PreviewGameArt key={game.name} game={game} compact />
            ))}
          </div>
        </>
      ) : (
        <>
          <div className="journey-person">
            <PreviewAvatar person="Mira" />
            <strong>Mira</strong>
            <span>Connected</span>
          </div>
          <div className="journey-chat">
            <p>Co-op tonight?</p>
            <p>I’m in.</p>
          </div>
        </>
      )}
    </div>
  );
}

// Bundled original fictional artwork; never fetch an account avatar or a remote CDN at runtime.
function PreviewGameArt({
  game,
  compact = false,
}: {
  game: (typeof games)[number];
  compact?: boolean;
}) {
  return (
    <span
      className={`game-art preview-game-art${compact ? " preview-game-icon" : ""}`}
      data-game={game.name}
      aria-hidden="true"
    >
      <Image
        src={`/preview-games/${game.art}`}
        alt=""
        width={160}
        height={96}
        unoptimized
      />
    </span>
  );
}

function PreviewAvatar({
  person,
  large = false,
}: {
  person: "Alex" | "Mira";
  large?: boolean;
}) {
  return (
    <span
      className={`preview-avatar${large ? " preview-avatar-large" : ""}`}
      data-person={person}
      aria-hidden="true"
    >
      <Image
        src={`/preview-games/${person === "Alex" ? "mosslight-vale.svg" : "ember-circuit.svg"}`}
        alt=""
        width={64}
        height={64}
        unoptimized
      />
    </span>
  );
}

function CheckMark() {
  return (
    <svg
      className="preview-check"
      aria-hidden="true"
      viewBox="0 0 20 20"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="m3 10 4 4 8-9" />
    </svg>
  );
}
