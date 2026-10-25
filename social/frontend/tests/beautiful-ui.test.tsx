import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { expect, test } from "vitest";
import { PlayerAvatar, GameIcon } from "@/components/ui";
import { ChoiceSelect } from "@/components/choice-select";

test("avatars prefer an approved local upload, fall back on load failure and reject remote URLs", async () => {
  const { container, rerender } = render(
    <PlayerAvatar
      name="Alex River"
      src="/preview-games/hades.png"
      uploadedSrc="/avatars/player.png"
    />,
  );
  expect(new URL(container.querySelector("img")!.src).pathname).toBe(
    "/avatars/player.png",
  );
  fireEvent.error(container.querySelector("img")!);
  expect(container.querySelector("img")).toBeNull();
  expect(container.textContent).toBe("AR");
  rerender(
    <PlayerAvatar
      name="Alex River"
      uploadedSrc="https://untrusted.example/pixel.png"
    />,
  );
  expect(container.querySelector("img")).toBeNull();
  rerender(
    <PlayerAvatar name="Alex River" uploadedSrc="/avatars/../private.png" />,
  );
  expect(container.querySelector("img")).toBeNull();
});

test("game pictures require supplied metadata with a matching app ID, not a title mapping", () => {
  const { container, rerender } = render(
    <GameIcon title="Hades" appId={999999} />,
  );
  expect(container.querySelector("img")).toBeNull();
  rerender(<GameIcon title="Hades" appId={1145360} />);
  expect(container.querySelector("img")).toBeNull();
  const icon =
    "https://media.steampowered.com/steamcommunity/public/images/apps/1145360/" +
    "a".repeat(40) +
    ".jpg";
  rerender(
    <GameIcon title="Hades" appId={1145360} visual={{ icon_url: icon }} />,
  );
  expect(container.querySelector("img")).toHaveAttribute("src", icon);
});

test("privacy choices submit the original enum value, not the presentation label", async () => {
  const { container } = render(
    <form>
      <ChoiceSelect
        label="Game library"
        name="library"
        defaultValue="private"
        options={[
          { value: "private", label: "Only me" },
          { value: "connections", label: "Connections" },
          { value: "public", label: "Public" },
        ]}
      />
    </form>,
  );
  expect(new FormData(container.querySelector("form")!).get("library")).toBe(
    "private",
  );
  fireEvent.click(screen.getByRole("combobox", { name: "Game library" }));
  const option = await screen.findByRole("option", { name: "Connections" });
  fireEvent.keyDown(option, { key: "Enter" });
  fireEvent.keyUp(option, { key: "Enter" });
  await waitFor(() =>
    expect(new FormData(container.querySelector("form")!).get("library")).toBe(
      "connections",
    ),
  );
});
