"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { Icon, type IconName } from "./ui";

export function AppShell({
  children,
  ownHandle,
}: {
  children: ReactNode;
  ownHandle?: string;
}) {
  const path = usePathname();
  const links: {
    href: string;
    label: string;
    icon: IconName;
    active: boolean;
  }[] = [
    {
      href: "/discover",
      label: "Discover",
      icon: "discover",
      active: path === "/discover",
    },
    {
      href: ownHandle ? `/users/${ownHandle}` : "/account",
      label: "Player profile",
      icon: "people",
      active: path.startsWith("/users/") && !path.includes("/games"),
    },
    {
      href: ownHandle ? `/users/${ownHandle}/games` : "/account",
      label: "Library",
      icon: "games",
      active: path.startsWith("/users/") && path.includes("/games"),
    },
    {
      href: "/connections",
      label: "Connections",
      icon: "people",
      active: path === "/connections",
    },
    {
      href: "/messages",
      label: "Messages",
      icon: "chat",
      active: path === "/messages",
    },
    {
      href: "/notifications",
      label: "Notifications",
      icon: "bell",
      active: path === "/notifications",
    },
    {
      href: "/account",
      label: "Account",
      icon: "settings",
      active: path.startsWith("/account"),
    },
  ];
  return (
    <div className="app-shell">
      <a className="skip-link" href="#app-content">
        Skip to content
      </a>
      <aside className="app-sidebar">
        <Link className="brand" href="/">
          SteamScope<span className="brand-dot">.</span>
        </Link>
        <span className="sidebar-caption">Games & community</span>
        <nav aria-label="Main navigation">
          {links.map((link) => (
            <Link
              key={link.label}
              href={link.href}
              className={
                link.label === "Account" || link.label === "Notifications"
                  ? "nav-utility"
                  : "nav-destination"
              }
              aria-label={link.label}
              aria-current={link.active ? "page" : undefined}
            >
              <Icon name={link.icon} />
              <span className="nav-label-desktop">{link.label}</span>
              <span className="nav-label-mobile" aria-hidden="true">
                {link.label === "Player profile"
                  ? "Profile"
                  : link.label === "Connections"
                    ? "People"
                    : link.label === "Notifications"
                      ? "Alerts"
                      : link.label}
              </span>
            </Link>
          ))}
        </nav>
        <div className="sidebar-footer">
          Gaming brings us together.<span>Independent Steam community</span>
        </div>
      </aside>
      <header className="mobile-app-header">
        <Link className="brand" href="/">
          SteamScope<span className="brand-dot">.</span>
        </Link>
        <nav aria-label="Account navigation">
          <Link href="/notifications" aria-label="Notifications">
            <Icon name="bell" />
          </Link>
          <Link href="/account" aria-label="Account">
            <Icon name="settings" />
          </Link>
        </nav>
      </header>
      <div className="app-content" id="app-content" tabIndex={-1}>
        {children}
      </div>
    </div>
  );
}
