import { expect, test, type Page } from "@playwright/test";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";

async function snapshot(page: Page, name: string, fullPage = false) {
  if (!process.env.LV4_CAPTURE_DIR) return;
  const dir = process.env.LV4_CAPTURE_DIR;
  mkdirSync(dir, { recursive: true });
  await page.screenshot({
    path: join(dir, name + ".png"),
    fullPage,
    animations: "disabled",
  });
  // Review snapshots remain self-contained and never contact image CDNs or Steam.
  const bundledImages = Object.fromEntries(
    ["orbit-relay.svg", "mosslight-vale.svg", "ember-circuit.svg"].map(
      (name) => [
        `/preview-games/${name}`,
        `data:image/svg+xml;base64,${readFileSync(join(process.cwd(), "public/preview-games", name)).toString("base64")}`,
      ],
    ),
  );
  const source = await page.evaluate((images) => {
    const css = Array.from(document.styleSheets)
      .flatMap((s) => {
        try {
          return Array.from(s.cssRules).map((r) => r.cssText);
        } catch {
          return [];
        }
      })
      .join("\n");
    const html = document.documentElement.cloneNode(true) as HTMLElement;
    html
      .querySelectorAll("script,style,link,meta,base,nextjs-portal")
      .forEach((e) => e.remove());
    html.querySelectorAll("img").forEach((img) => {
      const source = img.getAttribute("src") ?? "";
      if (!images[source])
        throw new Error("Unrecognized image in public preview capture");
      img.src = images[source];
      img.removeAttribute("srcset");
      img.loading = "eager";
    });
    const head = html.querySelector("head")!;
    const meta = document.createElement("meta");
    meta.setAttribute("http-equiv", "Content-Security-Policy");
    meta.content =
      "default-src 'none'; style-src 'unsafe-inline'; img-src data:; font-src data:";
    head.appendChild(meta);
    const viewport = document.createElement("meta");
    viewport.name = "viewport";
    viewport.content = "width=device-width, initial-scale=1";
    head.appendChild(viewport);
    const style = document.createElement("style");
    style.textContent = css;
    head.appendChild(style);
    return "<!doctype html>" + html.outerHTML;
  }, bundledImages);
  writeFileSync(join(dir, name + ".html"), source);
}

test("logged-out product landing, keyboard preview, responsive hierarchy and no Steam requests", async ({
  page,
}) => {
  const requests: string[] = [];
  const externalRequests: string[] = [];
  page.on("request", (r) => {
    const url = new URL(r.url());
    if (!["127.0.0.1", "localhost"].includes(url.hostname))
      externalRequests.push(url.origin);
  });
  page.on("request", (r) =>
    requests.push(r.method() + " " + new URL(r.url()).pathname),
  );
  await page.route("**/api/v1/me", (route) =>
    route.fulfill({ status: 401, json: { error: { code: "AUTH_REQUIRED" } } }),
  );
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(
    "Find your people.Through play.",
  );
  const entry = page.getByRole("link", { name: "Continue with Steam" });
  await expect(entry).toHaveAttribute("href", "/api/v1/auth/steam/login");
  await expect(
    page
      .getByRole("navigation")
      .getByRole("link", { name: "Sign in", exact: true }),
  ).toHaveAttribute("href", "/api/v1/auth/steam/login");
  await page.keyboard.press("Tab");
  await expect(
    page.getByRole("link", { name: "Skip to content" }),
  ).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.locator("#landing-main")).toBeFocused();
  const game = page.getByRole("button", { name: "Ember Circuit", exact: true });
  await game.focus();
  await page.keyboard.press("Enter");
  await expect(game).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByText("You play Ember Circuit too?")).toBeVisible();
  await page.getByRole("button", { name: "Orbit Relay", exact: true }).click();
  for (const width of [1440, 1280, 820, 390]) {
    await page.setViewportSize({ width, height: 900 });
    await page.evaluate(() => {
      (document.activeElement as HTMLElement)?.blur();
      window.scrollTo({ top: 0, behavior: "instant" });
    });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    await expect
      .poll(() =>
        page
          .locator(".product-preview img")
          .evaluateAll((images) =>
            images.every(
              (image) =>
                (image as HTMLImageElement).complete &&
                (image as HTMLImageElement).naturalWidth > 0,
            ),
          ),
      )
      .toBe(true);
    const heading = await page.locator("h1").boundingBox();
    const font = await page.locator("h1").evaluate((e) => ({
      size: parseFloat(getComputedStyle(e).fontSize),
      line: parseFloat(getComputedStyle(e).lineHeight),
    }));
    expect(heading!.height).toBeLessThanOrEqual(font.line * 2 + 1);
    if (width === 1440) {
      expect(font.size).toBeGreaterThanOrEqual(52);
      expect(font.size).toBeLessThanOrEqual(64);
      const hero = await page.locator(".landing-hero").boundingBox();
      expect(hero!.height).toBeGreaterThanOrEqual(600);
      expect(hero!.height).toBeLessThanOrEqual(720);
      await expect(
        page.getByRole("heading", { name: "How it works", exact: true }),
      ).toBeInViewport();
      await snapshot(page, "landing-desktop");
      await snapshot(page, "landing-full", true);
    } else await snapshot(page, "landing-" + width, width === 390);
  }
  await page.getByText("Service status", { exact: true }).click();
  await expect(page.locator("#status-heading")).not.toContainText("Checking", {
    timeout: 10000,
  });
  await page.getByText("Your privacy", { exact: true }).click();
  await expect(page.getByText(/You choose what players can see/)).toBeVisible();
  expect(
    requests.filter((r) => r.startsWith("POST ") || /steam|sync/.test(r)),
  ).toEqual([]);
  expect(externalRequests).toEqual([]);
});

test("session unavailable keeps a safe sign-in entry and never invents an identity", async ({
  page,
}) => {
  await page.route("**/api/v1/me", (route) =>
    route.fulfill({ status: 503, json: { error: { code: "UNAVAILABLE" } } }),
  );
  await page.goto("/");
  await expect(
    page.getByRole("link", { name: "Continue with Steam" }),
  ).toBeVisible();
  await expect(page.getByRole("link", { name: /Open SteamScope/ })).toHaveCount(
    0,
  );
});

test("reduced motion keeps all preview information available", async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/");
  for (const selector of [
    "h1",
    ".preview-profile",
    ".preview-mutual",
    ".preview-conversation",
  ]) {
    await expect(page.locator(selector)).toBeVisible();
    expect(
      await page
        .locator(selector)
        .evaluate((e) => getComputedStyle(e).animationName),
    ).toBe("none");
  }
  expect(
    await page
      .locator(".preview-game-art")
      .evaluateAll((elements) =>
        elements.every((e) => getComputedStyle(e).animationName === "none"),
      ),
  ).toBe(true);
  await expect(
    page.getByRole("button", { name: "Pause preview motion" }),
  ).toBeHidden();
});

test("art floats gently without moving text, and can be paused", async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: "no-preference" });
  await page.goto("/");
  const art = page.locator(".preview-library .preview-game-art").first();
  await expect(art).toBeVisible();
  const positions = await art.evaluate((e) => {
    const animation = e.getAnimations()[0];
    if (!animation) throw new Error("Preview art motion missing");
    animation.pause();
    animation.currentTime = 0;
    const start = e.getBoundingClientRect().y;
    const label = e.nextElementSibling!.getBoundingClientRect().y;
    animation.currentTime = Number(animation.effect!.getTiming().duration) / 2;
    const peak = e.getBoundingClientRect().y;
    const labelAfter = e.nextElementSibling!.getBoundingClientRect().y;
    animation.play();
    return { movement: start - peak, label, labelAfter };
  });
  expect(positions.movement).toBeGreaterThan(0);
  expect(positions.movement).toBeLessThanOrEqual(4.1);
  expect(positions.labelAfter).toBe(positions.label);
  await page.getByRole("button", { name: "Pause preview motion" }).click();
  await expect(
    page.getByRole("button", { name: "Resume preview motion" }),
  ).toBeVisible();
  await expect(art).toHaveCSS("animation-play-state", "paused");
  await page.getByRole("button", { name: "Resume preview motion" }).click();
  await page
    .getByRole("button", { name: "Ember Circuit", exact: true })
    .click();
  await expect(page.getByText("You play Ember Circuit too?")).toBeVisible();
  await page.locator("h1").click();
  await expect(art).toHaveCSS("animation-play-state", "running");
});
