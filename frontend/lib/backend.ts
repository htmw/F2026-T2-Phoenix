/**
 * Server-side access to the backend API.
 *
 * Only server components and route handlers import this module. Browser code must go
 * through the backend's public API and never hold provider credentials, so the internal
 * base URL lives here rather than in a NEXT_PUBLIC_* variable.
 */

const INTERNAL_BASE_URL = process.env.BACKEND_INTERNAL_URL ?? "http://localhost:8000";

export type DependencyReport = {
  name: string;
  healthy: boolean;
  detail: string | null;
  latency_ms: number | null;
};

export type ReadinessReport = {
  status: "ready" | "degraded";
  dependencies: DependencyReport[];
};

export type BackendStatus =
  | { reachable: true; readiness: ReadinessReport }
  | { reachable: false; error: string };

/**
 * Fetch backend readiness.
 *
 * A degraded backend answers with 503 and a useful body, so a non-OK status is parsed
 * rather than treated as a transport failure. Only an actual transport error (backend
 * down, DNS failure, timeout) is reported as unreachable.
 */
export async function fetchBackendStatus(): Promise<BackendStatus> {
  try {
    const response = await fetch(`${INTERNAL_BASE_URL}/readyz`, {
      cache: "no-store",
      signal: AbortSignal.timeout(5000),
    });

    if (response.status !== 200 && response.status !== 503) {
      return { reachable: false, error: `Unexpected status ${response.status}` };
    }

    const readiness = (await response.json()) as ReadinessReport;
    return { reachable: true, readiness };
  } catch (error) {
    return {
      reachable: false,
      error: error instanceof Error ? error.message : "Unknown error",
    };
  }
}
