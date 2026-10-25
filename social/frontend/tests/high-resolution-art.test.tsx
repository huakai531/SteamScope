import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { GameArt, GameIcon, GameThumbnail } from "@/components/ui";
import {
  gameArtSources,
  artFailedRecently,
  rememberArtFailure,
} from "@/lib/game-art";

const visuals = (id: number) => ({
  card_url: `https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/${id}/library_hero.jpg`,
  thumbnail_url: `https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/${id}/header.jpg`,
  icon_url: `https://media.steampowered.com/steamcommunity/public/images/apps/${id}/${"c".repeat(40)}.jpg`,
});
afterEach(() => vi.restoreAllMocks());

test("card and thumbnail select the same artwork while inline icons stay icon-only", () => {
  const visual = visuals(101);
  const { rerender, container } = render(
    <GameArt title="Synthetic" appId={101} visual={visual} variant="card" />,
  );
  expect(container.querySelectorAll("img")).toHaveLength(1);
  expect(screen.getByAltText("Synthetic artwork")).toHaveAttribute(
    "src",
    visual.card_url,
  );
  expect(screen.getByAltText("Synthetic artwork")).toHaveAttribute(
    "loading",
    "lazy",
  );
  rerender(
    <GameArt
      title="Synthetic"
      appId={101}
      visual={visual}
      variant="thumbnail"
    />,
  );
  expect(screen.getByAltText("Synthetic artwork")).toHaveAttribute(
    "src",
    visual.card_url,
  );
  fireEvent.error(screen.getByAltText("Synthetic artwork"));
  expect(screen.getByAltText("Synthetic artwork")).toHaveAttribute(
    "src",
    visual.thumbnail_url,
  );
  rerender(<GameIcon title="Synthetic" appId={101} visual={visual} />);
  expect(screen.getByAltText("Synthetic artwork")).toHaveAttribute(
    "src",
    visual.icon_url,
  );
  expect(screen.getByAltText("Synthetic artwork")).toHaveAttribute(
    "width",
    "48",
  );
  expect(gameArtSources(101, visual, "icon").map((s) => s.kind)).toEqual([
    "icon",
  ]);
});

test("square thumbnails have explicit display sizes and enough original pixels for high DPI", () => {
  const visual = visuals(107);
  const { container, rerender } = render(
    <GameThumbnail title="Crisp" appId={107} visual={visual} size={48} />,
  );
  expect(container.firstElementChild).toHaveStyle({
    width: "48px",
    height: "48px",
  });
  const img = screen.getByAltText("Crisp artwork");
  // Next's explicit unoptimized mode omits sizes/srcset: the full original is
  // used, never a 32px responsive candidate accidentally selected for 2x DPR.
  expect(img).not.toHaveAttribute("sizes");
  expect(img).not.toHaveAttribute("srcset");
  expect(img).toHaveAttribute("width", "1920");
  expect(img).toHaveAttribute("height", "620");
  expect(img).toHaveAttribute("loading", "lazy");
  expect(container.querySelectorAll("img")).toHaveLength(1);
  for (const size of [28, 32, 40] as const) {
    rerender(
      <GameThumbnail title="Crisp" appId={107} visual={visual} size={size} />,
    );
    expect(container.firstElementChild).toHaveStyle({
      width: `${size}px`,
      height: `${size}px`,
    });
    expect(screen.getByAltText("Crisp artwork")).toHaveAttribute(
      "src",
      visual.card_url,
    );
  }
});

test("thumbnail failures fall through to a contained native-size icon and finally a glyph", async () => {
  const visual = visuals(108);
  const { container, rerender } = render(
    <GameThumbnail
      title="Small fallback"
      appId={108}
      visual={visual}
      size={48}
    />,
  );
  for (const expected of [visual.card_url, visual.thumbnail_url]) {
    expect(screen.getByAltText("Small fallback artwork")).toHaveAttribute(
      "src",
      expected,
    );
    fireEvent.error(screen.getByAltText("Small fallback artwork"));
  }
  const img = screen.getByAltText("Small fallback artwork");
  expect(img).toHaveAttribute("src", visual.icon_url);
  expect(img).toHaveStyle({ width: "32px", height: "32px" });
  Object.defineProperty(img, "naturalWidth", { value: 24 });
  Object.defineProperty(img, "naturalHeight", { value: 24 });
  fireEvent.load(img);
  await waitFor(() =>
    expect(img).toHaveStyle({ width: "24px", height: "24px" }),
  );
  fireEvent.error(img);
  expect(
    screen.getByRole("img", { name: "Artwork unavailable for Small fallback" }),
  ).toBeVisible();
  expect(container.querySelector("img")).toBeNull();
  rerender(
    <GameThumbnail
      title="Small fallback"
      appId={108}
      visual={visual}
      size={48}
    />,
  );
  expect(container.querySelector("img")).toBeNull();
});

test("404 follows library to header to contained icon to stable glyph without looping", () => {
  const visual = visuals(102);
  const { rerender, unmount } = render(
    <GameArt title="Unavailable" appId={102} visual={visual} />,
  );
  for (const expected of [
    visual.card_url,
    visual.thumbnail_url,
    visual.icon_url,
  ]) {
    expect(screen.getByAltText("Unavailable artwork")).toHaveAttribute(
      "src",
      expected,
    );
    fireEvent.error(screen.getByAltText("Unavailable artwork"));
  }
  expect(
    screen.getByRole("img", { name: "Artwork unavailable for Unavailable" }),
  ).toBeVisible();
  rerender(<GameArt title="Unavailable" appId={102} visual={{ ...visual }} />);
  expect(screen.queryByAltText("Unavailable artwork")).toBeNull();
  unmount();
  render(<GameArt title="Remounted" appId={102} visual={visual} />);
  expect(screen.queryByAltText("Remounted artwork")).toBeNull();
});

test("missing art and failed high-resolution art retain an independently valid icon", () => {
  const visual = visuals(103);
  const { container } = render(
    <GameArt
      title="Fallback"
      appId={103}
      visual={{ card_url: visual.card_url, icon_url: visual.icon_url }}
    />,
  );
  fireEvent.error(screen.getByAltText("Fallback artwork"));
  expect(screen.getByAltText("Fallback artwork")).toHaveAttribute(
    "src",
    visual.icon_url,
  );
  expect(container.firstElementChild).toHaveAttribute(
    "data-image-kind",
    "icon",
  );
});

test("allowlist rejects wrong app, host, path, credentials and arbitrary query strings", () => {
  const visual = visuals(104);
  for (const card_url of [
    visuals(105).card_url,
    visual.card_url.replace("shared.fastly.steamstatic.com", "evil.example"),
    visual.card_url + "?url=https://evil.example",
    visual.card_url.replace("https://", "https://user:secret@"),
    visual.card_url.replace("library_hero", "other"),
  ])
    expect(gameArtSources(104, { card_url }, "card")).toEqual([]);
  expect(gameArtSources(0, visual, "card")).toEqual([]);
  expect(gameArtSources(104, undefined, "card")).toEqual([]);
});

test("negative cache expires after five minutes without a persistent browser store", () => {
  const clock = vi.spyOn(Date, "now").mockReturnValue(1000);
  rememberArtFailure(visuals(106).card_url);
  expect(artFailedRecently(visuals(106).card_url)).toBe(true);
  clock.mockReturnValue(301001);
  expect(artFailedRecently(visuals(106).card_url)).toBe(false);
});
