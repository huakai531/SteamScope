"use client";

import {
  useState,
  Children,
  isValidElement,
  type ReactElement,
  type ReactNode,
  type ComponentProps,
} from "react";
import Image from "next/image";
import {
  gameArtSources,
  artFailedRecently,
  rememberArtFailure,
  type GameVisual,
  type GameArtVariant,
} from "@/lib/game-art";
import { Avatar as AvatarPrimitive } from "./ui/notchset/avatar";
import { EmptyState as EmptyPrimitive } from "./ui/notchset/empty-state";
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
} from "./ui/notchset/dropdown-menu";
export { Button } from "./ui/notchset/button";
export { Input } from "./ui/notchset/input";
export { Textarea } from "./ui/notchset/textarea";

export type IconName =
  | "discover"
  | "games"
  | "people"
  | "chat"
  | "bell"
  | "settings"
  | "arrow"
  | "more"
  | "award"
  | "search";
const paths: Record<IconName, string> = {
  discover:
    "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18Zm4 5-2.5 5.5L8 16l2.5-5.5L16 8Z",
  games:
    "M7 6h10a4 4 0 0 1 4 4v7a2 2 0 0 1-3.4 1.4L15 16H9l-3.6 2.4A2 2 0 0 1 2 17v-7a4 4 0 0 1 4-4Zm0 4v4m-2-2h4m6-1h.01M18 13h.01",
  people:
    "M9 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8Zm-6 8v-2a5 5 0 0 1 5-4h2a5 5 0 0 1 5 4v2m1-16a4 4 0 0 1 0 8m2 2a5 5 0 0 1 3 4v2",
  chat: "M5 4h14a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H9l-6 3V6a2 2 0 0 1 2-2Zm2 5h10M7 13h6",
  bell: "M6 8a6 6 0 0 1 12 0v6l2 3H4l2-3V8m4 12h4",
  settings:
    "m9 3-1 3-3 1 1 3-2 2 2 2-1 3 3 1 1 3h6l1-3 3-1-1-3 2-2-2-2 1-3-3-1-1-3H9Zm3 6a3 3 0 1 0 0 6 3 3 0 0 0 0-6Z",
  arrow: "m14 5-7 7 7 7M7 12h14",
  more: "M5 12h.01M12 12h.01M19 12h.01",
  award:
    "M8 3h8v6a4 4 0 0 1-8 0V3Zm0 2H4v3a4 4 0 0 0 4 4m8-7h4v3a4 4 0 0 1-4 4m-4 1v5m-4 3h8m-8-3h8",
  search: "M10.5 3a7.5 7.5 0 1 0 0 15 7.5 7.5 0 0 0 0-15ZM16 16l5 5",
};
export function Icon({ name }: { name: IconName }) {
  return (
    <svg
      aria-hidden="true"
      width="20"
      height="20"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d={paths[name]} />
    </svg>
  );
}
// All live avatars use a same-origin endpoint that rechecks profile authorization.
export function PlayerAvatar({
  name,
  large = false,
  uploadedSrc,
  src,
}: {
  name: string;
  large?: boolean;
  uploadedSrc?: string | null;
  src?: string | null;
}) {
  const safeImage = (value?: string | null) =>
    value &&
    (/^\/api\/v1\/users\/[A-Za-z][A-Za-z0-9_]{2,23}\/avatar\/[a-f0-9]{32}\.webp$/.test(
      value,
    ) ||
      /^\/avatars\/[A-Za-z0-9_-]+\.(?:png|jpe?g|webp)$/.test(value))
      ? value
      : undefined;
  return (
    <AvatarPrimitive
      name={name}
      src={safeImage(uploadedSrc) ?? safeImage(src)}
      size={large ? "l" : "m"}
      className={`avatar-placeholder${large ? " avatar-large" : ""}`}
      data-avatar={
        Array.from(name).reduce((n, c) => n + c.codePointAt(0)!, 0) % 4
      }
      aria-hidden="true"
    />
  );
}
export const Avatar = PlayerAvatar;
type ThumbnailSize = 28 | 32 | 36 | 40 | 44 | 48 | 56;
type GameArtProps = {
  title: string;
  appId?: number;
  visual?: GameVisual;
  variant?: GameArtVariant;
  /** Square list thumbnail; omitted on the existing wide detail preview. */
  thumbnailSize?: ThumbnailSize;
  /** Explicit bundled artwork for labeled illustrative content only. */
  demoSrc?: string;
  className?: string;
};
export function GameArt({
  title,
  appId,
  visual,
  variant = "card",
  thumbnailSize,
  demoSrc,
  className = "",
}: GameArtProps) {
  const [, retrySelection] = useState(0);
  const [iconSize, setIconSize] = useState<{ url: string; size: number }>();
  const source = gameArtSources(appId, visual, variant, demoSrc).find(
    (candidate) => !artFailedRecently(candidate.url),
  );
  const squareSize = variant === "thumbnail" ? thumbnailSize : undefined;
  const containedIconSize =
    squareSize && source?.kind === "icon"
      ? Math.min(
          32,
          squareSize,
          iconSize?.url === source.url ? iconSize.size : 32,
        )
      : undefined;
  return (
    <span
      className={`game-art${variant === "icon" ? " game-icon" : ""}${squareSize ? " game-thumbnail" : ""} ${className}`}
      style={
        squareSize
          ? {
              width: squareSize,
              height: squareSize,
              minHeight: squareSize,
              flexBasis: squareSize,
            }
          : undefined
      }
      data-game-id={appId}
      data-game={title}
      data-variant={variant}
      data-image-kind={source?.kind ?? "fallback"}
      data-art={
        Array.from(title).reduce((n, c) => n + c.codePointAt(0)!, 0) % 4
      }
    >
      {source ? (
        <Image
          key={source.url}
          src={source.url}
          alt={`${title} artwork`}
          width={source.width}
          height={source.height}
          sizes={squareSize ? `${squareSize}px` : undefined}
          style={
            containedIconSize
              ? { width: containedIconSize, height: containedIconSize }
              : undefined
          }
          unoptimized
          loading="lazy"
          referrerPolicy="no-referrer"
          onLoad={
            squareSize && source.kind === "icon"
              ? (event) => {
                  const image = event.currentTarget;
                  setIconSize({
                    url: source.url,
                    size: Math.min(image.naturalWidth, image.naturalHeight),
                  });
                }
              : undefined
          }
          onError={() => {
            rememberArtFailure(source.url);
            retrySelection((n) => n + 1);
          }}
        />
      ) : (
        <span
          className="game-art-fallback"
          role="img"
          aria-label={`Artwork unavailable for ${title}`}
        >
          <Icon name="games" />
        </span>
      )}
    </span>
  );
}
export function GameIcon(props: Omit<GameArtProps, "variant">) {
  return <GameArt {...props} variant="icon" />;
}
export function GameThumbnail({
  size = 44,
  ...props
}: Omit<GameArtProps, "variant" | "thumbnailSize"> & { size?: ThumbnailSize }) {
  return <GameArt {...props} variant="thumbnail" thumbnailSize={size} />;
}
export function GameChip(props: Omit<GameArtProps, "variant">) {
  return (
    <span className="game-chip">
      <GameThumbnail {...props} size={36} />
      <span>{props.title}</span>
    </span>
  );
}
export function StatusBadge({
  children,
  tone = "muted",
  detail,
}: {
  children: ReactNode;
  tone?: "muted" | "good" | "warning";
  detail?: string;
}) {
  return (
    <span className={`status-badge tone-${tone}`} title={detail}>
      {children}
    </span>
  );
}
export function EmptyState({
  title,
  children,
  icon = "games",
}: {
  title: string;
  children?: ReactNode;
  icon?: IconName;
}) {
  return (
    <EmptyPrimitive
      title={title}
      icon={<Icon name={icon} />}
      className="empty-state"
    >
      {children}
    </EmptyPrimitive>
  );
}
export function MoreActions({
  children,
  label = "More actions",
}: {
  children: ReactNode;
  label?: string;
}) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger className="more-actions-trigger" aria-label={label}>
        <Icon name="more" />
      </DropdownMenuTrigger>
      <DropdownMenuContent>
        {Children.map(children, (child) =>
          isValidElement<ComponentProps<"button">>(child) ? (
            <DropdownMenuItem
              render={child as ReactElement}
              disabled={child.props.disabled}
            />
          ) : (
            child
          ),
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

export function HelpDisclosure({
  title = "About this data",
  children,
}: {
  title?: string;
  children: ReactNode;
}) {
  return (
    <details className="help-disclosure">
      <summary>{title}</summary>
      <div>{children}</div>
    </details>
  );
}
