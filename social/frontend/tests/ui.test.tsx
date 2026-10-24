import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { expect, test } from "vitest";
import { MoreActions, Avatar, GameArt } from "@/components/ui";

test("secondary actions close after selection and Escape restores trigger focus", async () => {
  render(
    <MoreActions label="Player options">
      <button>Report</button>
    </MoreActions>,
  );
  const trigger = screen.getByLabelText("Player options");
  fireEvent.click(trigger);
  expect(trigger).toHaveAttribute("aria-expanded", "true");
  fireEvent.keyDown(await screen.findByRole("menuitem", { name: "Report" }), {
    key: "Escape",
  });
  await waitFor(() =>
    expect(trigger).toHaveAttribute("aria-expanded", "false"),
  );
  await waitFor(() => expect(trigger).toHaveFocus());
  fireEvent.click(trigger);
  fireEvent.click(await screen.findByRole("menuitem", { name: "Report" }));
  await waitFor(() =>
    expect(trigger).toHaveAttribute("aria-expanded", "false"),
  );
});

test("identity and artwork placeholders render text without external asset requests", () => {
  const { container } = render(
    <>
      <Avatar name="<img>" />
      <GameArt title="<script>" />
    </>,
  );
  expect(container.querySelectorAll("img,script,iframe")).toHaveLength(0);
  expect(container.textContent).toContain("<");
});
