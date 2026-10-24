import type { components } from "./schema";

export type Readiness = components["schemas"]["Readiness"];

export function isReadiness(value: unknown): value is Readiness {
  if (!value || typeof value !== "object") return false;
  const record = value as Record<string, unknown>;
  if (
    record.scope !== "foundation" ||
    !["ready", "unavailable"].includes(String(record.status))
  )
    return false;
  if (!record.dependencies || typeof record.dependencies !== "object")
    return false;
  const dependencies = record.dependencies as Record<string, unknown>;
  if (
    !["up", "down"].includes(String(dependencies.postgres)) ||
    !["up", "down"].includes(String(dependencies.redis))
  )
    return false;
  return (
    (record.status === "ready") ===
    (dependencies.postgres === "up" && dependencies.redis === "up")
  );
}

export async function getStatus(): Promise<Readiness> {
  const response = await fetch("/api/status", {
    cache: "no-store",
    signal: AbortSignal.timeout(5000),
  });
  const payload: unknown = await response.json();
  if (![200, 503].includes(response.status) || !isReadiness(payload))
    throw new Error("Status request unavailable");
  return payload;
}
