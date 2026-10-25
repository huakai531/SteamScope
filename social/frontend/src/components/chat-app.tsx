"use client";

import Link from "next/link";
import { Input, Textarea } from "./ui";
import { AppShell } from "./app-shell";
import { PlayerAvatar, EmptyState, Icon, MoreActions } from "./ui";
import { Fragment, useEffect, useLayoutEffect, useRef, useState } from "react";
import { Button } from "./ui";
import { ConfirmDialog } from "./confirm-dialog";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AccountError,
  accountMessage,
  accountRequest,
  type Account,
} from "@/lib/api/account";
import type { components } from "@/lib/api/schema";
import { mergeMessages, socketURL, type ChatMessage } from "@/lib/chat";
import {
  dayKey,
  dayLabel,
  clockTime,
  conversationTime,
  startsMessageGroup,
  presenceLabel,
} from "@/lib/chat-presentation";

type S = components["schemas"];
type Conversation = S["ConversationView"];
type Page = S["MessagePage"];
type Live = {
  can_send: boolean;
  presence: string;
  typing: boolean;
  peer_read_sequence: number;
};

export function ChatApp() {
  const [mobileList, setMobileList] = useState(false);
  const cache = useQueryClient();
  const account = useQuery({
    queryKey: ["chat", "account"],
    queryFn: () => accountRequest<Account>("/me"),
    retry: false,
  });
  const [list, setList] = useState<S["ConversationList"]>({ items: [] });
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<Conversation | null>(null);
  const [rows, setRows] = useState<ChatMessage[]>([]);
  const [older, setOlder] = useState<number | null>(null);
  const [live, setLive] = useState<Live | null>(null);
  const [connection, setConnection] = useState("Connecting");
  const [error, setError] = useState("");
  const [handle, setHandle] = useState("");
  const [draft, setDraft] = useState("");
  const [pending, setPending] = useState<{
    client_message_id: string;
    body: string;
  } | null>(null);
  const [busy, setBusy] = useState(false);
  const [report, setReport] = useState<ChatMessage | null>(null);
  const [reason, setReason] = useState("harassment");
  const [description, setDescription] = useState("");
  const [notice, setNotice] = useState("");
  const socket = useRef<WebSocket | null>(null);
  const reload = useRef<(reset?: boolean) => Promise<void>>(async () => {});
  const lastTyping = useRef(0);
  const historyRows = useRef<ChatMessage[]>([]);
  const historyPanel = useRef<HTMLOListElement>(null);
  const nearBottom = useRef(true);
  const historySize = useRef({ width: 0, height: 0 });
  const [awayFromLatest, setAwayFromLatest] = useState(false);
  const historyAnchor = useRef<{ height: number; top: number } | null>(null);
  const composer = useRef<HTMLTextAreaElement>(null);
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);

  // Presentation only: preserve the reading position when paging older messages.
  // New arrivals scroll only if the reader was already near the latest message.
  useLayoutEffect(() => {
    const panel = historyPanel.current;
    if (!panel) return;
    const anchor = historyAnchor.current;
    if (anchor) {
      panel.scrollTop = anchor.top + panel.scrollHeight - anchor.height;
      historyAnchor.current = null;
    } else if (nearBottom.current) panel.scrollTop = panel.scrollHeight;
  }, [rows, selected, connection, detail?.id]);

  // Keep the latest message anchored when the viewport/composer changes size.
  // A reader who has scrolled back keeps their position instead.
  useLayoutEffect(() => {
    const panel = historyPanel.current;
    if (!panel) return;
    historySize.current = {
      width: panel.clientWidth,
      height: panel.clientHeight,
    };
    const observer = new ResizeObserver(() => {
      if (nearBottom.current && !historyAnchor.current)
        panel.scrollTop = panel.scrollHeight;
      historySize.current = {
        width: panel.clientWidth,
        height: panel.clientHeight,
      };
    });
    observer.observe(panel);
    return () => observer.disconnect();
  }, [selected, connection, detail?.id]);

  useEffect(() => {
    const ended = () => {
      cache.clear();
      window.location.replace("/login");
    };
    const channel =
      typeof BroadcastChannel === "undefined"
        ? null
        : new BroadcastChannel("steamscope-session");
    if (channel) channel.onmessage = ended;
    const restore = (event: PageTransitionEvent) => {
      if (event.persisted) window.location.reload();
    };
    window.addEventListener("steamscope-auth-ended", ended);
    window.addEventListener("pageshow", restore);
    return () => {
      channel?.close();
      window.removeEventListener("steamscope-auth-ended", ended);
      window.removeEventListener("pageshow", restore);
    };
  }, [cache]);

  useEffect(() => {
    if (!account.data) return;
    let cancelled = false,
      running = false,
      again = false,
      resetNext = false;
    let known: ChatMessage[] = [],
      attempts = 0;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let ws: WebSocket | null = null;
    async function refresh(reset = false) {
      resetNext ||= reset;
      if (running) {
        again = true;
        return;
      }
      running = true;
      try {
        do {
          again = false;
          known = historyRows.current;
          const freshList =
            await accountRequest<S["ConversationList"]>("/conversations");
          if (cancelled) return;
          setList(freshList);
          if (selected) {
            const current = await accountRequest<Conversation>(
              `/conversations/${selected}`,
            );
            // Events are hints: recover durable gaps even after a lost Pub/Sub notification.
            let after = known.at(-1)?.sequence ?? 0;
            let gap: ChatMessage[] = [];
            for (
              let page = 0;
              known.length > 0 && page < 20 && after < current.latest_sequence;
              page++
            ) {
              const next = await accountRequest<Page>(
                `/conversations/${selected}/messages?after=${after}&limit=100`,
              );
              gap = mergeMessages(gap, next.items);
              if (next.next_after == null) break;
              after = next.next_after;
              if (page === 19) {
                // A very large gap resets to a contiguous recent window; older
                // history remains available through the normal cursor pager.
                gap = [];
                resetNext = true;
              }
            }
            const recent = await accountRequest<Page>(
              `/conversations/${selected}/messages?limit=50`,
            );
            if (cancelled) return;
            if (resetNext) known = [];
            known = mergeMessages(mergeMessages(known, gap), recent.items);
            resetNext = false;
            historyRows.current = known;
            setRows(known);
            setDetail(current);
            setOlder(
              known.length
                ? known[0].sequence > 1
                  ? known[0].sequence
                  : null
                : (recent.next_before ?? null),
            );
            if (
              current.latest_sequence > current.last_read_sequence &&
              document.visibilityState === "visible"
            )
              await accountRequest(`/conversations/${selected}/read`, "POST", {
                sequence: current.latest_sequence,
              });
          }
          if (!cancelled) setError("");
        } while (again && !cancelled);
      } catch (failure) {
        if (!cancelled) {
          setError(
            failure instanceof AccountError && failure.status === 404
              ? "Conversation unavailable. Messaging access may have changed."
              : accountMessage(failure),
          );
          setRows([]);
          setDetail(null);
          setLive(null);
        }
      } finally {
        running = false;
      }
    }
    reload.current = refresh;
    function connect() {
      if (cancelled) return;
      setConnection(attempts ? "Reconnecting" : "Connecting");
      ws = new WebSocket(socketURL(window.location.origin));
      socket.current = ws;
      ws.onmessage = (message) => {
        let event;
        try {
          event = JSON.parse(message.data);
        } catch {
          return;
        }
        if (cancelled || event.v !== 1) return;
        if (event.type === "ready") {
          attempts = 0;
          setConnection("Connected");
          ws?.send(
            JSON.stringify({ type: "watch", conversation_id: selected }),
          );
          void refresh(true);
        } else if (
          event.type === "conversation.unavailable" &&
          event.conversation_id === selected
        ) {
          setRows([]);
          setDetail(null);
          setLive(null);
          setError(
            "Conversation unavailable. Messaging access may have changed.",
          );
          void refresh(true);
        } else if (
          event.type === "conversation.state" &&
          event.conversation_id === selected
        ) {
          setLive(event);
          void refresh();
        } else if (
          [
            "message.created",
            "message.deleted",
            "conversation.read",
            "conversation.changed",
          ].includes(event.type)
        ) {
          void refresh(event.type === "message.deleted");
        } else if (event.type === "error")
          setError(
            "This chat action is unavailable. Check your connection or try again later.",
          );
      };
      ws.onclose = (event) => {
        if (cancelled) return;
        setLive(null);
        setConnection("Reconnecting");
        if (event.code === 4401) {
          window.dispatchEvent(new Event("steamscope-auth-ended"));
          return;
        }
        timer = setTimeout(connect, Math.min(1000 * 2 ** attempts++, 10000));
      };
      ws.onerror = () => ws?.close();
    }
    const start = setTimeout(() => {
      const conversation = new URL(window.location.href).searchParams.get(
        "conversation",
      );
      if (!selected && conversation && /^[0-9a-f-]{36}$/i.test(conversation)) {
        setSelected(conversation);
        return;
      }
      const supplied =
        new URL(window.location.href).searchParams.get("with") ?? "";
      if (/^[A-Za-z][A-Za-z0-9_]{2,23}$/.test(supplied)) setHandle(supplied);
      void refresh(true);
      connect();
    }, 0);
    const heartbeat = setInterval(() => {
      if (ws?.readyState === WebSocket.OPEN)
        ws.send(JSON.stringify({ type: "ping" }));
    }, 10000);
    // Bounded polling also recovers events lost without a transport disconnect.
    const reconcile = setInterval(() => {
      if (ws?.readyState === WebSocket.OPEN) void refresh();
    }, 15000);
    const visible = () => {
      if (document.visibilityState === "visible") void refresh();
    };
    document.addEventListener("visibilitychange", visible);
    return () => {
      cancelled = true;
      clearTimeout(start);
      clearTimeout(timer);
      clearInterval(heartbeat);
      clearInterval(reconcile);
      document.removeEventListener("visibilitychange", visible);
      ws?.close();
      socket.current = null;
    };
  }, [account.data, selected]);

  function typing(active: boolean) {
    if (
      !selected ||
      !live?.can_send ||
      socket.current?.readyState !== WebSocket.OPEN
    )
      return;
    if (active && Date.now() - lastTyping.current < 2000) return;
    lastTyping.current = Date.now();
    socket.current.send(
      JSON.stringify({ type: "typing", conversation_id: selected, active }),
    );
  }
  async function start() {
    setBusy(true);
    setError("");
    try {
      const c = await accountRequest<Conversation>(
        "/conversations/direct",
        "POST",
        { handle },
      );
      choose(c.id);
    } catch (failure) {
      setError(
        failure instanceof AccountError && failure.status === 404
          ? "Conversation unavailable. Both players must be connected and allow connection messages."
          : accountMessage(failure),
      );
    } finally {
      setBusy(false);
    }
  }
  function choose(id: string) {
    nearBottom.current = true;
    setAwayFromLatest(false);
    historyAnchor.current = null;
    setDeleteTarget(null);
    window.history.replaceState(null, "", `/messages?conversation=${id}`);
    historyRows.current = [];
    typing(false);
    setSelected(id);
    setRows([]);
    setDetail(null);
    setLive(null);
    setDraft("");
    setPending(null);
    setReport(null);
    setNotice("");
    setError("");
  }
  async function send() {
    if (!selected || busy || !live?.can_send) return;
    const payload = pending ?? {
      client_message_id: crypto.randomUUID(),
      body: draft,
    };
    setPending(payload);
    setBusy(true);
    setError("");
    typing(false);
    try {
      await accountRequest(
        `/conversations/${selected}/messages`,
        "POST",
        payload,
      );
      setPending(null);
      setDraft("");
      nearBottom.current = true;
      setAwayFromLatest(false);
      await reload.current();
    } catch (failure) {
      setError(accountMessage(failure));
    } finally {
      setBusy(false);
      requestAnimationFrame(() => composer.current?.focus());
    }
  }
  async function olderMessages() {
    if (!selected || older == null) return;
    setBusy(true);
    try {
      const page = await accountRequest<Page>(
        `/conversations/${selected}/messages?before=${older}&limit=50`,
      );
      if (historyPanel.current)
        historyAnchor.current = {
          height: historyPanel.current.scrollHeight,
          top: historyPanel.current.scrollTop,
        };
      historyRows.current = mergeMessages(page.items, historyRows.current);
      setRows(historyRows.current);
      setOlder(page.next_before ?? null);
    } catch (failure) {
      setError(accountMessage(failure));
    } finally {
      setBusy(false);
    }
  }
  async function remove(id: string) {
    setDeleting(true);
    try {
      await accountRequest(`/messages/${id}`, "DELETE");
      await reload.current(true);
      setDeleteTarget(null);
    } catch (failure) {
      setError(accountMessage(failure));
    } finally {
      setDeleting(false);
    }
  }
  async function submitReport() {
    if (!report) return;
    setBusy(true);
    try {
      await accountRequest(`/messages/${report.id}/report`, "POST", {
        reason,
        description,
      });
      setReport(null);
      setDescription("");
      setNotice("Message report received. The other player is not notified.");
    } catch (failure) {
      setError(accountMessage(failure));
    } finally {
      setBusy(false);
    }
  }

  return (
    <AppShell ownHandle={account.data?.handle}>
      <main className="player-main messages-main" id="messages-main">
        <h1>Messages</h1>
        {account.isPending ? (
          <p role="status">Checking your session…</p>
        ) : account.isError ? (
          <section className="player-card">
            <p>Sign in to view your messages.</p>
            <Link href="/login">Sign in through Steam</Link>
          </section>
        ) : (
          <>
            {connection !== "Connected" && (
              <p className="chat-connection" role="status">
                {connection === "Connecting"
                  ? "Connecting to your conversations…"
                  : "Connection interrupted. Reconnecting…"}
              </p>
            )}
            {error && <p role="alert">{error}</p>}
            {notice && <p role="status">{notice}</p>}
            <details className="chat-start">
              <summary>Open a conversation</summary>
              <form
                className="chat-start-form"
                onSubmit={(e) => {
                  e.preventDefault();
                  void start();
                }}
              >
                <label htmlFor="chat-handle">Connection handle</label>
                <Input
                  id="chat-handle"
                  value={handle}
                  maxLength={24}
                  onChange={(e) => setHandle(e.target.value)}
                  required
                />
                <button disabled={busy || !!pending}>Open conversation</button>
                <p>
                  Both players must allow messages from connections in{" "}
                  <Link href="/account/privacy">privacy settings</Link>.
                </p>
              </form>
            </details>
            <div
              className="chat-layout"
              data-selected={!!selected && !mobileList}
              data-connection={connection}
            >
              <aside className="player-card" aria-label="Conversations">
                <h2>Your conversations</h2>
                {list.items.length === 0 ? (
                  <p>
                    No conversations yet. Connect with another SteamScope player
                    to start chatting.
                  </p>
                ) : (
                  list.items.map((c) => (
                    <button
                      className="chat-conversation"
                      key={c.id}
                      aria-pressed={c.id === selected}
                      disabled={!!pending && c.id !== selected}
                      onClick={() => {
                        if (c.id !== selected) choose(c.id);
                        setMobileList(false);
                      }}
                    >
                      <span className="conversation-avatar">
                        <PlayerAvatar
                          name={c.person?.display_name ?? "Player"}
                          uploadedSrc={c.person?.avatar_url}
                        />
                        {c.id === selected &&
                          connection === "Connected" &&
                          live?.presence === "online" && (
                            <span
                              className="person-online-dot"
                              title="Online"
                            />
                          )}
                      </span>
                      <strong>
                        {c.person?.display_name ?? "Player unavailable"}
                      </strong>
                      <span className="conversation-preview">
                        {c.last_message?.deleted_at
                          ? "Message deleted"
                          : (c.last_message?.body?.slice(0, 100) ??
                            "No messages yet")}
                      </span>
                      <span className="conversation-time">
                        {c.last_message_at ? (
                          <time
                            dateTime={c.last_message_at}
                            title={new Date(c.last_message_at).toLocaleString()}
                          >
                            {conversationTime(c.last_message_at)}
                          </time>
                        ) : null}
                      </span>
                      <span
                        className={c.unread_count ? "unread-count" : "sr-only"}
                      >
                        {c.unread_count}
                        <span className="sr-only"> unread</span>
                      </span>
                    </button>
                  ))
                )}
                {list.next_cursor && (
                  <button
                    onClick={() =>
                      void accountRequest<S["ConversationList"]>(
                        `/conversations?cursor=${list.next_cursor}`,
                      )
                        .then((p) =>
                          setList((old) => ({
                            items: [
                              ...old.items,
                              ...p.items.filter(
                                (c) => !old.items.some((x) => x.id === c.id),
                              ),
                            ],
                            next_cursor: p.next_cursor,
                          })),
                        )
                        .catch((f) => setError(accountMessage(f)))
                    }
                  >
                    Load more conversations
                  </button>
                )}
              </aside>
              <section
                className="player-card chat-pane"
                aria-label="Conversation"
              >
                {!selected ? (
                  <EmptyState title="No conversation selected" icon="chat">
                    Select a conversation or open one with a connection.
                  </EmptyState>
                ) : connection !== "Connected" ? (
                  <p className="chat-reconnecting" role="status">
                    History is hidden while reconnecting. Persisted messages
                    will be recovered when the connection returns.
                  </p>
                ) : detail ? (
                  <>
                    <header className="conversation-header">
                      <button
                        className="mobile-conversation-back"
                        aria-label="Back to conversations"
                        onClick={() => setMobileList(true)}
                      >
                        <Icon name="arrow" />
                      </button>
                      <PlayerAvatar
                        name={detail.person?.display_name ?? "Player"}
                        uploadedSrc={detail.person?.avatar_url}
                      />
                      <div>
                        <h2>{detail.person?.display_name ?? "Conversation"}</h2>
                        <p
                          className="conversation-presence"
                          title="SteamScope presence, not Steam activity."
                        >
                          {detail.person && (
                            <span>@{detail.person.handle} · </span>
                          )}
                          <span data-online={live?.presence === "online"}>
                            {presenceLabel(live?.presence)}
                          </span>
                        </p>
                      </div>
                      <MoreActions label="Conversation actions">
                        <Link
                          href={
                            detail.person
                              ? `/users/${detail.person.handle}`
                              : "/connections"
                          }
                        >
                          View profile
                        </Link>
                        <Link href="/connections">Manage connection</Link>
                      </MoreActions>
                    </header>
                    {older != null && (
                      <button
                        disabled={busy}
                        onClick={() => void olderMessages()}
                      >
                        Load older messages
                      </button>
                    )}
                    <ol
                      ref={historyPanel}
                      className="chat-history"
                      aria-label="Message history"
                      tabIndex={0}
                      onScroll={(event) => {
                        const panel = event.currentTarget;
                        // Resize can emit scroll before ResizeObserver. Preserve the
                        // previous reading intent until the new geometry is handled.
                        if (
                          panel.clientWidth !== historySize.current.width ||
                          panel.clientHeight !== historySize.current.height
                        )
                          return;
                        nearBottom.current =
                          panel.scrollHeight -
                            panel.scrollTop -
                            panel.clientHeight <
                          72;
                        setAwayFromLatest(!nearBottom.current);
                      }}
                    >
                      {rows.map((m, index) => (
                        <Fragment key={m.id}>
                          {(index === 0 ||
                            dayKey(m.created_at) !==
                              dayKey(rows[index - 1].created_at)) && (
                            <li className="chat-day">
                              <time
                                dateTime={m.created_at}
                                title={new Date(
                                  m.created_at,
                                ).toLocaleDateString()}
                              >
                                {dayLabel(m.created_at)}
                              </time>
                            </li>
                          )}
                          <li
                            data-group-start={startsMessageGroup(
                              m,
                              rows[index - 1],
                            )}
                            className={m.mine ? "chat-mine" : "chat-peer"}
                            data-message-id={m.id}
                          >
                            <strong className="sr-only">
                              {m.mine ? "You" : "Other participant"}
                            </strong>
                            <p className="chat-body">
                              {m.deleted_at ? "Message deleted" : m.body}
                            </p>
                            <small>
                              <time
                                dateTime={m.created_at}
                                title={new Date(m.created_at).toLocaleString()}
                              >
                                {clockTime(m.created_at)}
                              </time>
                              {m.mine &&
                              m.sequence <=
                                (live?.peer_read_sequence ??
                                  detail.peer_read_sequence)
                                ? " · Read"
                                : ""}
                            </small>
                            {!m.deleted_at && (
                              <MoreActions label="Message actions">
                                {m.mine ? (
                                  <button onClick={() => setDeleteTarget(m.id)}>
                                    Delete message
                                  </button>
                                ) : (
                                  <button
                                    onClick={() => {
                                      setReport(m);
                                      setNotice("");
                                    }}
                                  >
                                    Report message
                                  </button>
                                )}
                              </MoreActions>
                            )}
                          </li>
                        </Fragment>
                      ))}
                    </ol>
                    {rows.length > 0 && awayFromLatest && (
                      <button
                        className="chat-jump"
                        type="button"
                        onClick={() => {
                          nearBottom.current = true;
                          setAwayFromLatest(false);
                          if (historyPanel.current)
                            historyPanel.current.scrollTop =
                              historyPanel.current.scrollHeight;
                        }}
                      >
                        Jump to latest
                      </button>
                    )}
                    {live?.typing && (
                      <p className="chat-typing" role="status">
                        {detail.person?.display_name ?? "The other player"} is
                        typing…
                      </p>
                    )}
                    {!live?.can_send && (
                      <p>
                        Sending is disabled. A current connection and both
                        messaging permissions are required.
                      </p>
                    )}
                    <form
                      className="chat-composer"
                      onSubmit={(e) => {
                        e.preventDefault();
                        void send();
                      }}
                    >
                      <label className="sr-only" htmlFor="chat-draft">
                        Message text
                      </label>
                      <div className="composer-surface">
                        <Textarea
                          ref={composer}
                          id="chat-draft"
                          aria-describedby="composer-help"
                          placeholder="Message..."
                          rows={1}
                          maxLength={2000}
                          value={draft}
                          disabled={!!pending || !live?.can_send}
                          onBlur={() => typing(false)}
                          onChange={(e) => {
                            setDraft(e.target.value);
                            typing(!!e.target.value.trim());
                          }}
                          onKeyDown={(e) => {
                            if (
                              e.key === "Enter" &&
                              !e.shiftKey &&
                              !e.nativeEvent.isComposing
                            ) {
                              e.preventDefault();
                              void send();
                            }
                          }}
                        />
                        <Button
                          type="submit"
                          className="composer-send"
                          aria-label={
                            pending ? "Retry same message" : "Send message"
                          }
                          title={
                            pending ? "Retry same message" : "Send message"
                          }
                          disabled={
                            busy ||
                            !live?.can_send ||
                            (!pending && !draft.trim())
                          }
                        >
                          <Icon name="arrow" />
                        </Button>
                      </div>
                      <p className="composer-help" id="composer-help">
                        Enter to send · Shift+Enter for a new line
                        <span className="sr-only">
                          {" "}
                          · 2,000 characters maximum
                        </span>
                      </p>
                      {pending && (
                        <p>
                          Acknowledgement is pending. Retry keeps the same
                          message ID and cannot create a second copy.
                        </p>
                      )}
                    </form>
                    {report && (
                      <form
                        className="chat-report"
                        onSubmit={(e) => {
                          e.preventDefault();
                          void submitReport();
                        }}
                      >
                        <h3>Report message</h3>
                        <label>
                          Report reason
                          <select
                            value={reason}
                            onChange={(e) => setReason(e.target.value)}
                          >
                            {[
                              "harassment",
                              "spam",
                              "impersonation",
                              "inappropriate_content",
                              "suspicious_behavior",
                              "other",
                            ].map((r) => (
                              <option key={r} value={r}>
                                {r.replaceAll("_", " ")}
                              </option>
                            ))}
                          </select>
                        </label>
                        <label>
                          Report description
                          <Textarea
                            maxLength={1000}
                            value={description}
                            onChange={(e) => setDescription(e.target.value)}
                          />
                        </label>
                        <button disabled={busy}>Submit message report</button>
                        <button type="button" onClick={() => setReport(null)}>
                          Cancel report
                        </button>
                      </form>
                    )}
                  </>
                ) : (
                  <p>Loading or unavailable conversation.</p>
                )}
              </section>
            </div>
            <ConfirmDialog
              open={deleteTarget !== null}
              title="Delete this message?"
              confirmLabel="Delete message"
              busy={deleting}
              onClose={() => setDeleteTarget(null)}
              onConfirm={() =>
                deleteTarget ? remove(deleteTarget) : undefined
              }
            >
              Other participants will see a tombstone. This cannot be undone.
            </ConfirmDialog>
          </>
        )}
      </main>
    </AppShell>
  );
}
