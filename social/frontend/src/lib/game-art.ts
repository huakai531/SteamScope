export type GameVisual = {
  icon_url?: string | null;
  thumbnail_url?: string | null;
  card_url?: string | null;
  source?: "steam" | "unavailable";
};
export type GameArtVariant = "icon" | "thumbnail" | "card";
export type ArtSource = {
  url: string;
  kind: "icon" | "header" | "library" | "demo";
  width: number;
  height: number;
};

// URLs come from the canonical backend model. This only validates/selects them;
// it cannot guess URLs, proxy arbitrary hosts or expose hidden game membership.
export function gameArtSources(
  appId: number | undefined,
  visual: GameVisual | undefined,
  variant: GameArtVariant,
  demoSrc?: string,
): ArtSource[] {
  if (
    demoSrc &&
    /^\/preview-games\/[A-Za-z0-9_-]+\.(?:png|jpe?g|webp)$/.test(demoSrc)
  )
    return [{ url: demoSrc, kind: "demo", width: 460, height: 215 }];
  if (!Number.isInteger(appId) || !appId || appId < 1 || appId > 4294967295)
    return [];
  const sources: ArtSource[] = [];
  const add = (
    url: string | null | undefined,
    kind: ArtSource["kind"],
    width: number,
    height: number,
  ) => {
    if (!url) return;
    const match =
      kind === "icon"
        ? url.match(
            /^https:\/\/media\.steampowered\.com\/steamcommunity\/public\/images\/apps\/([1-9][0-9]{0,9})\/[a-f0-9]{40}\.jpg$/,
          )
        : url.match(
            /^https:\/\/shared\.fastly\.steamstatic\.com\/store_item_assets\/steam\/apps\/([1-9][0-9]{0,9})\/(header|library_hero)\.jpg$/,
          );
    if (!match || Number(match[1]) !== appId) return;
    if (
      (kind === "header" && match[2] !== "header") ||
      (kind === "library" && match[2] !== "library_hero")
    )
      return;
    sources.push({ url, kind, width, height });
  };
  // Reuse the proven card URL for compact crops, so a profile's card and rows
  // share the browser cache instead of downloading a softer alternate first.
  if (variant !== "icon") add(visual?.card_url, "library", 1920, 620);
  if (variant !== "icon") add(visual?.thumbnail_url, "header", 460, 215);
  add(visual?.icon_url, "icon", 48, 48);
  return sources;
}

// Per-tab bounded negative cache: remounts/refetches do not retry a failed URL on
// every render. No user data, localStorage, backend cache or persistent image file.
const failedUntil = new Map<string, number>();
const FAILURE_TTL = 5 * 60 * 1000;
export function artFailedRecently(url: string): boolean {
  return (failedUntil.get(url) ?? 0) > Date.now();
}
export function rememberArtFailure(url: string): void {
  if (failedUntil.size >= 512)
    failedUntil.delete(failedUntil.keys().next().value!);
  failedUntil.set(url, Date.now() + FAILURE_TTL);
}
