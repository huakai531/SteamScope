"use client";

import Link from "next/link";
import { AvatarEditor } from "./avatar-editor";
import { ChoiceSelect } from "./choice-select";
import { Button } from "./ui";
import { Input, Textarea } from "./ui";
import { AppShell } from "./app-shell";
import { HelpDisclosure } from "./ui";
import { SteamSignIn } from "@/components/steam-sign-in";
import {
  useEffect,
  useRef,
  useState,
  type FormEvent,
  type ReactNode,
} from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AccountError,
  accountMessage,
  accountRequest,
  type Account,
  type Privacy,
  type Session,
} from "@/lib/api/account";
import type { components } from "@/lib/api/schema";
import { SteamData } from "@/components/steam-data";

type Section =
  "overview" | "profile" | "privacy" | "sessions" | "delete" | "steam";
const navigation: [Section, string, string][] = [
  ["overview", "/account", "Overview"],
  ["steam", "/account/steam", "My Steam Data"],
  ["profile", "/account/profile", "Profile"],
  ["privacy", "/account/privacy", "Privacy"],
  ["sessions", "/account/sessions", "Sessions"],
  ["delete", "/account/delete", "Delete account"],
];

export function AccountApp({ section }: { section: Section }) {
  const client = useQueryClient();
  const [closing, setClosing] = useState(false);
  const sessionChannel = useRef<BroadcastChannel | null>(null);
  const [error, setError] = useState<unknown>(null);
  const account = useQuery({
    queryKey: ["account"],
    queryFn: () => accountRequest<Account>("/me"),
    staleTime: 0,
    gcTime: 0,
    refetchOnMount: "always",
    refetchOnWindowFocus: true,
    retry: false,
  });

  useEffect(() => {
    const channel =
      typeof BroadcastChannel === "undefined"
        ? null
        : new BroadcastChannel("steamscope-session");
    const changed = () => {
      document.documentElement.style.visibility = "hidden";
      void client.cancelQueries();
      client.clear();
      window.location.replace("/login?status=session-changed");
    };
    sessionChannel.current = channel;
    if (channel) channel.onmessage = changed;
    const restored = (event: PageTransitionEvent) => {
      if (event.persisted) {
        document.documentElement.style.visibility = "hidden";
        window.location.reload();
      }
    };
    window.addEventListener("pageshow", restored);
    window.addEventListener("steamscope-auth-ended", changed);
    return () => {
      sessionChannel.current = null;
      channel?.close();
      window.removeEventListener("pageshow", restored);
      window.removeEventListener("steamscope-auth-ended", changed);
    };
  }, [client]);

  async function leave(status: string) {
    setClosing(true);
    await client.cancelQueries();
    client.clear();
    sessionChannel.current?.postMessage("session-ended");
    window.location.replace("/login?status=" + status);
  }

  async function logout() {
    setError(null);
    try {
      await accountRequest("/auth/logout", "POST");
      await leave("logged-out");
    } catch (failure) {
      setError(failure);
    }
  }

  let content: ReactNode;
  if (closing || account.isPending || (account.isFetching && !account.data)) {
    content = <p role="status">Checking your session…</p>;
  } else if (account.isError || !account.data) {
    content = (
      <section className="account-panel">
        <h1>Sign in to your account</h1>
        <p>{accountMessage(account.error)}</p>
        <SteamSignIn className="primary-action">
          Sign in through Steam
        </SteamSignIn>
      </section>
    );
  } else {
    const user = account.data;
    content = (
      <>
        <aside className="account-nav" aria-label="Account navigation">
          {navigation.map(([key, href, label]) => (
            <Link
              key={key}
              href={href}
              aria-current={key === section ? "page" : undefined}
            >
              {label}
            </Link>
          ))}
          <button type="button" onClick={logout}>
            Log out
          </button>
        </aside>
        <div className="account-content">
          {error ? (
            <p role="alert" className="form-error">
              {accountMessage(error)}
            </p>
          ) : null}
          {section === "overview" && (
            <section className="account-panel">
              <p className="eyebrow">YOUR STEAMSCOPE ACCOUNT</p>
              <AvatarEditor account={user} />
              <h1>{user.display_name}</h1>
              <p className="account-handle">@{user.handle}</p>
              <dl>
                <dt>Verified linked SteamID</dt>
                <dd className="steam-id">{user.steam_id}</dd>
                <dt>Platform identity</dt>
                <dd>
                  Your profile name and handle are chosen here, independently of
                  Steam.
                </dd>
              </dl>
              <p className="information-note">
                Identity verification does not import Steam data. Open My Steam
                Data to explicitly request your profile, game library and
                playtime.
              </p>
              <Link className="primary-action" href="/account/profile">
                Edit platform profile
              </Link>
            </section>
          )}
          {section === "profile" && (
            <ProfileForm key={user.id} account={user} />
          )}
          {section === "privacy" && <PrivacyForm />}
          {section === "sessions" && <Sessions onLeave={leave} />}
          {section === "delete" && <DeleteAccount onLeave={leave} />}
          {section === "steam" && <SteamData key={user.id} ownerId={user.id} />}
        </div>
      </>
    );
  }
  return (
    <AppShell ownHandle={account.data?.handle}>
      <main id="account-main" className="account-layout">
        {content}
      </main>
    </AppShell>
  );
}

function FieldError({ error, name }: { error: unknown; name: string }) {
  if (!(error instanceof AccountError)) return null;
  const invalid =
    error.detail.fields?.some((field) => field.field === name) ||
    (name === "handle" && error.detail.code === "HANDLE_UNAVAILABLE");
  return invalid ? (
    <span id={name + "-error"} className="form-error">
      {name === "handle" && error.detail.code === "HANDLE_UNAVAILABLE"
        ? "This handle is already in use."
        : "Please check this value."}
    </span>
  ) : null;
}

function ProfileForm({ account }: { account: Account }) {
  const client = useQueryClient();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [saved, setSaved] = useState(false);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setSaved(false);
    const values = new FormData(event.currentTarget);
    try {
      const body = Object.fromEntries(
        ["handle", "display_name", "biography", "locale", "timezone"].map(
          (key) => [key, String(values.get(key) ?? "")],
        ),
      );
      const result = await accountRequest<Account>("/me", "PATCH", body);
      client.setQueryData(["account"], result);
      setSaved(true);
    } catch (failure) {
      setError(failure);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="account-panel">
      <h1>Platform profile</h1>
      <AvatarEditor account={account} />
      <p>
        These are your SteamScope fields. Your verified Steam identity cannot be
        edited here.
      </p>
      <form onSubmit={submit}>
        {error ? (
          <p role="alert" className="form-error">
            {accountMessage(error)}
          </p>
        ) : null}
        {saved && (
          <p role="status" className="form-success">
            Profile saved.
          </p>
        )}
        <fieldset disabled={busy}>
          <label htmlFor="handle">Handle</label>
          <Input
            id="handle"
            name="handle"
            required
            minLength={3}
            maxLength={24}
            pattern="[A-Za-z][A-Za-z0-9_]+"
            defaultValue={account.handle}
            aria-describedby="handle-help handle-error"
          />
          <small id="handle-help">
            3–24 letters, numbers or underscores. Start with a letter.
          </small>
          <FieldError error={error} name="handle" />
          <label htmlFor="display_name">Display name</label>
          <Input
            id="display_name"
            name="display_name"
            required
            maxLength={60}
            defaultValue={account.display_name}
            aria-describedby="display_name-error"
          />
          <FieldError error={error} name="display_name" />
          <label htmlFor="biography">
            Biography <span>(optional, plain text)</span>
          </label>
          <Textarea
            id="biography"
            name="biography"
            maxLength={500}
            rows={4}
            defaultValue={account.biography}
            aria-describedby="biography-error"
          />
          <FieldError error={error} name="biography" />
          <div className="form-columns">
            <div>
              <label htmlFor="locale">Locale</label>
              <select id="locale" name="locale" defaultValue={account.locale}>
                {[
                  "en",
                  "en-US",
                  "zh-CN",
                  "zh-TW",
                  "ja",
                  "ko",
                  "de",
                  "fr",
                  "es",
                  "pt-BR",
                ].map((locale) => (
                  <option key={locale}>{locale}</option>
                ))}
              </select>
              <FieldError error={error} name="locale" />
            </div>
            <div>
              <label htmlFor="timezone">IANA timezone</label>
              <Input
                id="timezone"
                name="timezone"
                required
                maxLength={64}
                list="timezones"
                defaultValue={account.timezone}
                aria-describedby="timezone-error"
              />
              <datalist id="timezones">
                {[
                  "UTC",
                  "America/Los_Angeles",
                  "America/New_York",
                  "Asia/Shanghai",
                  "Asia/Tokyo",
                  "Europe/London",
                ].map((zone) => (
                  <option key={zone} value={zone} />
                ))}
              </datalist>
              <FieldError error={error} name="timezone" />
            </div>
          </div>
          <button className="primary-action" type="submit">
            {busy ? "Saving…" : "Save profile"}
          </button>
        </fieldset>
      </form>
    </section>
  );
}

const visibilityFields = [
  "profile",
  "library",
  "playtime",
  "achievements",
  "presence",
] as const;
function PrivacyForm() {
  const data = useQuery({
    queryKey: ["privacy"],
    queryFn: () => accountRequest<Privacy>("/me/privacy"),
    gcTime: 0,
  });
  const client = useQueryClient();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [saved, setSaved] = useState(false);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setSaved(false);
    const form = new FormData(event.currentTarget);
    const values = Object.fromEntries(
      [...visibilityFields, "connection_requests", "messaging"].map((key) => [
        key,
        form.get(key),
      ]),
    );
    try {
      const result = await accountRequest<Privacy>("/me/privacy", "PATCH", {
        ...values,
        discovery: form.get("discovery") === "on",
      });
      client.setQueryData(["privacy"], result);
      setSaved(true);
    } catch (failure) {
      setError(failure);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="account-panel">
      <h1>Privacy preferences</h1>
      <p>Choose what you share, and who you share it with.</p>
      <HelpDisclosure title="How visibility works">
        <p>
          Public shares permitted fresh data with other signed-in players.
          Accepted SteamScope connections can access connections-only resources.
          Imported Steam friends grant no access. Presence controls SteamScope
          online visibility; messages require an accepted connection and both
          players allowing messages.
        </p>
      </HelpDisclosure>
      {data.isPending ? (
        <p role="status">Loading preferences…</p>
      ) : data.isError ? (
        <p role="alert">{accountMessage(data.error)}</p>
      ) : (
        <form onSubmit={submit}>
          {error ? (
            <p role="alert" className="form-error">
              {accountMessage(error)}
            </p>
          ) : null}
          {saved && (
            <p role="status" className="form-success">
              Privacy preferences saved.
            </p>
          )}
          <fieldset disabled={busy}>
            <legend>Player visibility and social preferences</legend>
            <div className="settings-visibility">
              {visibilityFields.map((field) => (
                <div className="settings-row" key={field}>
                  {(field === "profile" ||
                    field === "library" ||
                    field === "presence") && (
                    <h3 className="settings-group-title">
                      {field === "library"
                        ? "Steam data"
                        : field === "profile"
                          ? "Profile visibility"
                          : "Presence"}
                    </h3>
                  )}
                  <label htmlFor={field}>
                    {field[0].toUpperCase() + field.slice(1)} visibility
                    <span>
                      {field === "profile"
                        ? "Who can view your player profile."
                        : field === "presence"
                          ? "Who can see your SteamScope online status."
                          : `Who can view your saved ${field}.`}
                    </span>
                  </label>
                  <ChoiceSelect
                    id={field}
                    name={field}
                    label={`${field[0].toUpperCase() + field.slice(1)} visibility`}
                    defaultValue={data.data[field]}
                    disabled={busy}
                    options={[
                      { value: "private", label: "Only me" },
                      {
                        value: "connections",
                        label: "Accepted SteamScope connections",
                      },
                      { value: "public", label: "Public (signed-in players)" },
                    ]}
                  />
                  <FieldError name={field} error={error} />
                </div>
              ))}
            </div>
            <section className="settings-social">
              <h3>Social</h3>
              <label className="check-label" htmlFor="discovery">
                <input
                  type="checkbox"
                  id="discovery"
                  name="discovery"
                  defaultChecked={data.data.discovery}
                />
                Allow discovery and search participation
              </label>
              <div className="settings-row">
                <label htmlFor="connection_requests">
                  Connection requests
                  <span>Who can send you an invitation.</span>
                </label>
                <select
                  name="connection_requests"
                  id="connection_requests"
                  defaultValue={data.data.connection_requests}
                >
                  <option value="nobody">Nobody</option>
                  <option value="discoverable">Discoverable members</option>
                </select>
              </div>
              <div className="settings-row">
                <label htmlFor="messaging">
                  Messaging<span>Who can start a conversation with you.</span>
                </label>
                <select
                  id="messaging"
                  name="messaging"
                  defaultValue={data.data.messaging}
                >
                  <option value="nobody">Nobody</option>
                  <option value="connections">Accepted connections</option>
                </select>
              </div>
            </section>
            <Button type="submit" loading={busy}>
              {busy ? "Saving…" : "Save privacy preferences"}
            </Button>
          </fieldset>
        </form>
      )}
    </section>
  );
}

function Sessions({ onLeave }: { onLeave: (status: string) => Promise<void> }) {
  const client = useQueryClient();
  const sessions = useQuery({
    queryKey: ["sessions"],
    queryFn: () => accountRequest<Session[]>("/me/sessions"),
    gcTime: 0,
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  async function revoke(session: Session) {
    setBusy(true);
    setError(null);
    try {
      await accountRequest("/me/sessions/" + session.id, "DELETE");
      if (session.current) await onLeave("logged-out");
      else await client.invalidateQueries({ queryKey: ["sessions"] });
    } catch (failure) {
      setError(failure);
    } finally {
      setBusy(false);
    }
  }
  async function all() {
    setBusy(true);
    setError(null);
    try {
      await accountRequest("/auth/logout-all", "POST");
      await onLeave("logged-out-all");
    } catch (failure) {
      setError(failure);
      dialog.current?.close();
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="account-panel">
      <h1>Your sessions</h1>
      <p>
        Only your active sessions are shown. Revocation takes effect on the next
        request. Tokens, IP addresses and device fingerprints are never
        displayed.
      </p>
      {error ? (
        <p role="alert" className="form-error">
          {accountMessage(error)}
        </p>
      ) : null}
      {sessions.isPending ? (
        <p role="status">Loading sessions…</p>
      ) : sessions.isError ? (
        <p role="alert">{accountMessage(sessions.error)}</p>
      ) : (
        <ul className="session-list">
          {sessions.data.map((session) => (
            <li key={session.id}>
              <div>
                <strong>
                  {session.current ? "This session" : "Another session"}
                </strong>
                <p>
                  Signed in:{" "}
                  <time dateTime={session.authenticated_at}>
                    {new Date(session.authenticated_at).toLocaleString()}
                  </time>
                </p>
                <p>
                  Expires:{" "}
                  <time dateTime={session.expires_at}>
                    {new Date(session.expires_at).toLocaleString()}
                  </time>
                </p>
              </div>
              <button disabled={busy} onClick={() => revoke(session)}>
                {session.current ? "Revoke this session" : "Revoke session"}
              </button>
            </li>
          ))}
        </ul>
      )}
      <button
        className="danger-action"
        disabled={busy}
        onClick={() => dialog.current?.showModal()}
      >
        Log out all sessions
      </button>
      <dialog ref={dialog} aria-labelledby="logout-all-title">
        <h2 id="logout-all-title">Log out everywhere?</h2>
        <p>
          This includes your current session and cancels account-bound pending
          logins.
        </p>
        <div className="dialog-actions">
          <button disabled={busy} onClick={() => dialog.current?.close()}>
            Cancel
          </button>
          <button className="danger-action" disabled={busy} onClick={all}>
            {busy ? "Logging out…" : "Confirm logout all"}
          </button>
        </div>
      </dialog>
    </section>
  );
}

function DeleteAccount({
  onLeave,
}: {
  onLeave: (status: string) => Promise<void>;
}) {
  const [confirmation, setConfirmation] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  async function remove(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await accountRequest("/me", "DELETE", { confirmation });
      await onLeave("deleted");
    } catch (failure) {
      setError(failure);
      dialog.current?.close();
    } finally {
      setBusy(false);
    }
  }
  async function reauth() {
    setBusy(true);
    setError(null);
    try {
      const start = await accountRequest<components["schemas"]["LoginView"]>(
        "/auth/steam/reauth",
        "POST",
      );
      window.location.assign(start.url);
    } catch (failure) {
      setError(failure);
      setBusy(false);
    }
  }
  return (
    <section className="account-panel">
      <h1>Delete your account</h1>
      <p>
        Your SteamScope profile, Steam association, privacy settings, sessions
        and account-bound pending logins will be erased together. Steam itself
        is not changed.
      </p>
      <p>
        Minimal audit events lose their account identifier. Maintenance removes
        events older than 90 days. A later sign-in creates a new account with a
        new ID and private defaults.
      </p>
      <p className="information-note">
        Deletion requires recent Steam identity verification (10 minutes by
        default). Reverification may reuse Steam’s existing session; it does not
        guarantee a password or Steam Guard prompt.
      </p>
      {error ? (
        <p role="alert" className="form-error">
          {accountMessage(error)}
        </p>
      ) : null}
      <div className="dialog-actions">
        <button disabled={busy} onClick={reauth}>
          Verify Steam identity again
        </button>
        <button
          className="danger-action"
          disabled={busy}
          onClick={() => dialog.current?.showModal()}
        >
          Delete my account
        </button>
      </div>
      <dialog ref={dialog} aria-labelledby="delete-title">
        <form onSubmit={remove}>
          <h2 id="delete-title">Delete SteamScope account?</h2>
          <p>This action cannot be undone. Type DELETE to confirm.</p>
          <label htmlFor="delete-confirmation">Confirmation</label>
          <Input
            id="delete-confirmation"
            value={confirmation}
            onChange={(event) => setConfirmation(event.target.value)}
            autoComplete="off"
          />
          <div className="dialog-actions">
            <button
              type="button"
              disabled={busy}
              onClick={() => dialog.current?.close()}
            >
              Cancel
            </button>
            <button
              className="danger-action"
              disabled={busy || confirmation !== "DELETE"}
              type="submit"
            >
              {busy ? "Deleting…" : "Permanently delete account"}
            </button>
          </div>
        </form>
      </dialog>
    </section>
  );
}
