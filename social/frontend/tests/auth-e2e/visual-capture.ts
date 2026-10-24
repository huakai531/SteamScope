import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import type { Page } from "@playwright/test";

/** Isolated fixture output only. No credentials, scripts or external requests. */
export async function saveVisual(page: Page, directory: string, name: string) {
  mkdirSync(directory, { recursive: true });
  await page.screenshot({
    path: join(directory, name + ".png"),
    fullPage: false,
  });
  const images: Record<string, string> = {};
  for (const [file, mime] of [
    ["orbit-relay.svg", "image/svg+xml"],
    ["mosslight-vale.svg", "image/svg+xml"],
    ["ember-circuit.svg", "image/svg+xml"],
  ]) {
    images["/preview-games/" + file] =
      `data:${mime};base64,${readFileSync(join(process.cwd(), "public/preview-games", file)).toString("base64")}`;
  }
  const html = await page.evaluate((media) => {
    const css = Array.from(document.styleSheets)
      .flatMap((sheet) => {
        try {
          return Array.from(sheet.cssRules).map((rule) => rule.cssText);
        } catch {
          return [];
        }
      })
      .join("\n");
    const clone = document.documentElement.cloneNode(true) as HTMLElement;
    clone
      .querySelectorAll("script,style,link,meta,base,nextjs-portal")
      .forEach((node) => node.remove());
    clone.querySelectorAll("img").forEach((img) => {
      const source = media[new URL(img.src, location.href).pathname];
      if (source) {
        img.src = source;
        img.removeAttribute("srcset");
      } else img.remove();
    });
    clone.querySelectorAll("input").forEach((input) => {
      if (input.type === "hidden") input.remove();
    });
    const head = clone.querySelector("head")!;
    const meta = document.createElement("meta");
    meta.httpEquiv = "Content-Security-Policy";
    meta.content =
      "default-src 'none'; style-src 'unsafe-inline'; img-src data:; font-src data:; form-action 'none'; base-uri 'none'";
    head.append(meta);
    const viewport = document.createElement("meta");
    viewport.name = "viewport";
    viewport.content = "width=device-width, initial-scale=1";
    head.append(viewport);
    const style = document.createElement("style");
    style.textContent = css;
    head.append(style);
    return "<!doctype html>" + clone.outerHTML;
  }, images);
  writeFileSync(join(directory, name + ".html"), html);
}
