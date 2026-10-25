import { fireEvent, render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { GameArt, GameChip, PlayerAvatar } from "@/components/ui";

const url =
  "https://media.steampowered.com/steamcommunity/public/images/apps/123/" +
  "a".repeat(40) +
  ".jpg";
test("canonical artwork loads only matching official metadata and falls back on error", () => {
  const { rerender } = render(
    <GameArt
      title="Synthetic game"
      appId={123}
      visual={{ icon_url: url, source: "steam" }}
    />,
  );
  const image = screen.getByAltText("Synthetic game artwork");
  expect(image).toHaveAttribute("src", url);
  expect(image).toHaveAttribute("referrerpolicy", "no-referrer");
  fireEvent.error(image);
  expect(
    screen.getByRole("img", { name: "Artwork unavailable for Synthetic game" }),
  ).toBeVisible();
  rerender(
    <GameArt title="Different game" appId={456} visual={{ icon_url: url }} />,
  );
  expect(screen.queryByAltText("Different game artwork")).toBeNull();
  rerender(
    <GameChip
      title="Unsafe"
      appId={123}
      visual={{ icon_url: "https://evil.example/a.jpg" }}
    />,
  );
  expect(screen.queryByAltText("Unsafe artwork")).toBeNull();
});
test("avatar accepts only authorized serving path; a broken image falls back", () => {
  const src =
    "/api/v1/users/synthetic/ avatar/".replace(" ", "") +
    "a".repeat(32) +
    ".webp";
  const { container, rerender } = render(
    <PlayerAvatar name="Synthetic" uploadedSrc={src} />,
  );
  expect(new URL(container.querySelector("img")!.src).pathname).toBe(src);
  fireEvent.error(container.querySelector("img")!);
  expect(container.textContent).toContain("S");
  rerender(
    <PlayerAvatar name="Synthetic" uploadedSrc="https://evil.example/x.png" />,
  );
  expect(container.querySelector("img")).toBeNull();
});
