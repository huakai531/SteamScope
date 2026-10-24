import type { Metadata } from "next";
import type { ReactNode } from "react";
import "./globals.css";
import "./landing.css";
import "./community.css";
import "./discover.css";
import "./beautiful-ui.css";
import "./product-polish.css";
import { Providers } from "@/components/providers";

export const metadata: Metadata = {
  title: "SteamScope — Your games. Your people.",
  description:
    "Turn your Steam library into a gaming identity. Discover players, connect and chat in real time, with privacy on your terms.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
