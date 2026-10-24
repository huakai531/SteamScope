import type { AnchorHTMLAttributes } from "react";

export function SteamSignIn(
  props: Omit<AnchorHTMLAttributes<HTMLAnchorElement>, "href">,
) {
  // OpenID starts a full browser navigation through an API redirect; it must not use SPA prefetch.
  // eslint-disable-next-line @next/next/no-html-link-for-pages
  return <a {...props} href="/api/v1/auth/steam/login" />;
}
