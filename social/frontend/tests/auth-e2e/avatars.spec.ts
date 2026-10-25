import { expect, test } from "@playwright/test";
import { identity, login, steam } from "./helpers";
import { deflateSync } from "node:zlib";
import { mkdirSync } from "node:fs";
import { join } from "node:path";

// In-memory deterministic 32x32 PNG, no personal fixture or external image dependency.
function png() {
  function chunk(type: string, data: Buffer) {
    const body = Buffer.concat([Buffer.from(type), data]);
    let crc = 0xffffffff;
    for (const byte of body) {
      crc ^= byte;
      for (let i = 0; i < 8; i++)
        crc = (crc >>> 1) ^ (crc & 1 ? 0xedb88320 : 0);
    }
    const result = Buffer.alloc(data.length + 12);
    result.writeUInt32BE(data.length);
    body.copy(result, 4);
    result.writeUInt32BE((crc ^ 0xffffffff) >>> 0, result.length - 4);
    return result;
  }
  const header = Buffer.alloc(13);
  header.writeUInt32BE(32);
  header.writeUInt32BE(32, 4);
  header[8] = 8;
  header[9] = 2;
  const rows = Buffer.alloc(32 * (32 * 3 + 1));
  for (let y = 0; y < 32; y++)
    for (let x = 0; x < 32; x++) {
      const at = y * 97 + 1 + x * 3;
      rows[at] = 32 + x * 4;
      rows[at + 1] = 78 + y * 3;
      rows[at + 2] = 168;
    }
  return Buffer.concat([
    Buffer.from("89504e470d0a1a0a", "hex"),
    chunk("IHDR", header),
    chunk("IDAT", deflateSync(rows)),
    chunk("IEND", Buffer.alloc(0)),
  ]);
}

test("avatar preview, cancel, upload, persistence, replacement and removal use the real local API", async ({
  page,
  context,
}) => {
  await steam(context, identity());
  await login(page);
  const account = await (await page.request.get("/api/v1/me")).json();
  const before = await (
    await page.request.get("/api/v1/me/steam/sync-status")
  ).json();
  const uploads: string[] = [];
  page.on("request", (request) => {
    if (request.method() === "POST" && request.url().endsWith("/me/avatar"))
      uploads.push("upload");
  });
  await page.goto("/account/profile");
  await page
    .getByRole("button", { name: "Change avatar", exact: true })
    .click();
  await page.getByLabel("Choose image").setInputFiles({
    name: "synthetic.png",
    mimeType: "image/png",
    buffer: png(),
  });
  await expect(page.getByAltText("Selected avatar preview")).toBeVisible();
  expect(uploads).toHaveLength(0);
  if (process.env.AVATAR_CAPTURE_DIR) {
    mkdirSync(process.env.AVATAR_CAPTURE_DIR, { recursive: true });
    for (const width of [1440, 768, 390]) {
      await page.setViewportSize({ width, height: width === 390 ? 844 : 900 });
      await page.screenshot({
        animations: "disabled",
        path: join(
          process.env.AVATAR_CAPTURE_DIR,
          `avatar-dialog-${width}.png`,
        ),
      });
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      ).toBe(true);
    }
  }
  await page.getByRole("button", { name: "Cancel", exact: true }).click();
  expect(uploads).toHaveLength(0);
  await page
    .getByRole("button", { name: "Change avatar", exact: true })
    .click();
  await page.getByLabel("Choose image").setInputFiles({
    name: "synthetic.png",
    mimeType: "image/png",
    buffer: png(),
  });
  await page.getByRole("button", { name: "Save avatar", exact: true }).click();
  await expect(page.getByText("Avatar saved.")).toBeVisible();
  const first = (await (await page.request.get("/api/v1/me")).json())
    .avatar_url;
  const image = await page.request.get(first);
  expect(image.status()).toBe(200);
  expect(image.headers()["content-type"]).toBe("image/webp");
  await page.reload();
  await expect(page.locator(`img[src$="${first}"]`)).toBeVisible();
  await page.goto(`/users/${account.handle}`);
  await expect(page.locator(`img[src$="${first}"]`)).toBeVisible();
  // The accepted mobile layout hides the optional own-profile summary in Discover.
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/discover");
  await expect(page.locator(`img[src$="${first}"]`)).toBeVisible();
  await page.goto("/account/profile");
  await page
    .getByRole("button", { name: "Change avatar", exact: true })
    .click();
  await page.getByLabel("Choose image").setInputFiles({
    name: "replace.png",
    mimeType: "image/png",
    buffer: png(),
  });
  await page.getByRole("button", { name: "Save avatar", exact: true }).click();
  await expect(page.getByText("Avatar saved.")).toBeVisible();
  const second = (await (await page.request.get("/api/v1/me")).json())
    .avatar_url;
  expect(second).not.toBe(first);
  expect((await page.request.get(first)).status()).toBe(404);
  await page
    .getByRole("button", { name: "Change avatar", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Remove avatar", exact: true })
    .click();
  await expect(page.getByRole("dialog")).toBeHidden();
  expect(
    (await (await page.request.get("/api/v1/me")).json()).avatar_url,
  ).toBeNull();
  expect((await page.request.get(second)).status()).toBe(404);
  expect(
    await (await page.request.get("/api/v1/me/steam/sync-status")).json(),
  ).toEqual(before);
});
