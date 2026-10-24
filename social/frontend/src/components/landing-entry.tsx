"use client";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { accountRequest, type Account } from "@/lib/api/account";
import { SteamSignIn } from "./steam-sign-in";

// Only the existing read endpoint determines this presentation state.
// No identity is retained in the public page's query result or preview.
export function LandingEntry({ compact = false }: { compact?: boolean }) {
  const session = useQuery({
    queryKey: ["landing-session"],
    queryFn: async () => {
      const account = await accountRequest<Account>("/me");
      return typeof account.id === "string" && account.id.length > 0;
    },
    retry: false,
    staleTime: 0,
    gcTime: 0,
    refetchOnWindowFocus: true,
    refetchOnMount: "always",
  });
  const className = compact ? "landing-entry" : "primary-action landing-entry";
  return session.isSuccess && session.data ? (
    <Link href="/account" prefetch={false} className={className}>
      Open SteamScope {!compact && <span aria-hidden="true">↗</span>}
    </Link>
  ) : (
    <SteamSignIn className={className}>
      {compact ? "Sign in" : "Continue with Steam"}
      {!compact && <span aria-hidden="true">↗</span>}
    </SteamSignIn>
  );
}
