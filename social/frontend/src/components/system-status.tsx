"use client";
import { useQuery } from "@tanstack/react-query";
import { getStatus } from "@/lib/api/status";

export function SystemStatus() {
  const query = useQuery({
    queryKey: ["foundation-status"],
    queryFn: getStatus,
    staleTime: 0,
  });
  const title = query.isPending
    ? "Checking foundation services…"
    : query.isError
      ? "Status check unavailable"
      : query.data.status === "ready"
        ? "Foundation services connected"
        : "Foundation services unavailable";
  return (
    <section
      id="system-status"
      className="status-panel"
      aria-labelledby="status-heading"
    >
      <div className="status-copy">
        <span className="status-caption">Service connections</span>
        <h2 id="status-heading" aria-live="polite">
          {title}
        </h2>
        <p>
          Current database and cache connection health. This check does not
          request Steam data.
        </p>
      </div>
      <div className="status-results" aria-live="polite">
        {!query.isError && query.data ? (
          <>
            <span>
              PostgreSQL{" "}
              <strong data-state={query.data.dependencies.postgres}>
                {query.data.dependencies.postgres === "up"
                  ? "Connected"
                  : "Unavailable"}
              </strong>
            </span>
            <span>
              Redis{" "}
              <strong data-state={query.data.dependencies.redis}>
                {query.data.dependencies.redis === "up"
                  ? "Connected"
                  : "Unavailable"}
              </strong>
            </span>
          </>
        ) : (
          <p>
            {query.isPending
              ? "Waiting for an actual response."
              : "Could not obtain current service status. You can try again."}
          </p>
        )}
        <button
          className="text-button"
          disabled={query.isFetching}
          onClick={() => void query.refetch()}
        >
          {query.isFetching ? "Checking…" : "Check again ↗"}
        </button>
      </div>
    </section>
  );
}
