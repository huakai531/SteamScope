"use client";
import Link from "next/link";
import { SteamSignIn } from "@/components/steam-sign-in";
import { useSearchParams } from "next/navigation";

export function LoginState() {
  const params = useSearchParams();
  const code = params.get("error");
  const status = params.get("status");
  const errors: Record<string, string> = {
    LOGIN_CANCELLED:
      "Steam sign-in was cancelled. Your account was not changed.",
    REAUTH_IDENTITY_MISMATCH:
      "That Steam identity does not match the account being protected. Your account was not switched.",
    RATE_LIMITED: "Too many sign-in attempts. Wait five minutes and try again.",
    AUTH_DEPENDENCY_UNAVAILABLE:
      "Sign-in is temporarily unavailable. Please retry when services recover.",
  };
  const statuses: Record<string, string> = {
    "logged-out": "You are logged out.",
    "logged-out-all": "All your sessions have been revoked.",
    deleted: "Your SteamScope account has been deleted.",
    "session-changed": "Your session changed in another tab. Sign in again.",
  };
  return (
    <main className="login-page">
      <Link className="brand" href="/">
        SteamScope<span className="brand-dot">.</span>
      </Link>
      <section className="account-panel">
        <p className="login-intro">Good games. Better company.</p>
        <h1>Sign in through Steam</h1>
        {code && (
          <p role="alert" className="form-error">
            {errors[code] ??
              "Steam sign-in could not be verified. Start a new sign-in attempt."}
          </p>
        )}
        {status && (
          <p role="status" className="form-success">
            {statuses[status] ?? "Sign in to continue."}
          </p>
        )}
        <p>
          Continue on Steam’s official site to verify your identity. SteamScope
          never receives your Steam password or Steam Guard code.
        </p>
        <p>
          Your game library is imported separately, when you choose to sync. You
          control what other players can see.
        </p>
        <SteamSignIn className="primary-action">Continue to Steam</SteamSignIn>
        <p>
          <Link href="/">Back to SteamScope</Link>
        </p>
      </section>
      <p className="small-note">
        Independent project. Not affiliated with or endorsed by Valve
        Corporation.
      </p>
    </main>
  );
}
