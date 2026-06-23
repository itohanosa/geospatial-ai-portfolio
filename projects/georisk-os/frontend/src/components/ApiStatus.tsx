"use client";

import { useEffect, useState } from "react";

type ReadinessPayload = {
  status?: string;
  database?: {
    ready?: boolean;
    database_name?: string;
    postgis_version?: string;
  };
};

type VersionPayload = {
  version?: string;
  environment?: string;
};

type StatusState = {
  loading: boolean;
  apiReady: boolean;
  databaseReady: boolean;
  databaseName: string;
  postgisVersion: string;
  version: string;
  environment: string;
  error: string;
};

const initialState: StatusState = {
  loading: true,
  apiReady: false,
  databaseReady: false,
  databaseName: "—",
  postgisVersion: "—",
  version: "—",
  environment: "—",
  error: "",
};

export default function ApiStatus() {
  const [status, setStatus] = useState<StatusState>(initialState);

  useEffect(() => {
    const controller = new AbortController();
    const apiBaseUrl =
      process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

    async function loadStatus() {
      try {
        const [readyResponse, versionResponse] = await Promise.all([
          fetch(`${apiBaseUrl}/ready`, {
            cache: "no-store",
            signal: controller.signal,
          }),
          fetch(`${apiBaseUrl}/version`, {
            cache: "no-store",
            signal: controller.signal,
          }),
        ]);

        if (!readyResponse.ok || !versionResponse.ok) {
          throw new Error(
            `API returned ${readyResponse.status}/${versionResponse.status}`,
          );
        }

        const ready = (await readyResponse.json()) as ReadinessPayload;
        const version = (await versionResponse.json()) as VersionPayload;

        setStatus({
          loading: false,
          apiReady: ready.status === "ready",
          databaseReady: Boolean(ready.database?.ready),
          databaseName: ready.database?.database_name ?? "—",
          postgisVersion: ready.database?.postgis_version ?? "—",
          version: version.version ?? "—",
          environment: version.environment ?? "—",
          error: "",
        });
      } catch (error) {
        if (controller.signal.aborted) {
          return;
        }

        setStatus({
          ...initialState,
          loading: false,
          error: error instanceof Error ? error.message : "Unknown API error",
        });
      }
    }

    void loadStatus();

    return () => controller.abort();
  }, []);

  const apiLabel = status.loading
    ? "Checking"
    : status.apiReady
      ? "Online"
      : "Offline";

  const databaseLabel = status.loading
    ? "Checking"
    : status.databaseReady
      ? "Connected"
      : "Unavailable";

  return (
    <section className="status-grid" aria-label="Platform status">
      <article className="status-card">
        <div className="status-card-heading">
          <span
            className={`status-dot ${status.apiReady ? "status-dot-online" : ""}`}
            aria-hidden="true"
          />
          <span>FastAPI service</span>
        </div>
        <strong>{apiLabel}</strong>
        <small>Version {status.version}</small>
      </article>

      <article className="status-card">
        <div className="status-card-heading">
          <span
            className={`status-dot ${status.databaseReady ? "status-dot-online" : ""}`}
            aria-hidden="true"
          />
          <span>PostGIS database</span>
        </div>
        <strong>{databaseLabel}</strong>
        <small>{status.databaseName}</small>
      </article>

      <article className="status-card">
        <div className="status-card-heading">
          <span className="status-dot status-dot-neutral" aria-hidden="true" />
          <span>Environment</span>
        </div>
        <strong>{status.environment}</strong>
        <small>{status.postgisVersion}</small>
      </article>

      {status.error ? (
        <p className="status-error">
          The frontend could not reach the backend: {status.error}
        </p>
      ) : null}
    </section>
  );
}
