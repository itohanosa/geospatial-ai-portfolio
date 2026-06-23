# GeoRiskOS Step 1 architecture

```text
Browser
  |
  | HTTP :3000
  v
Next.js + MapLibre
  |
  | JSON HTTP :8000
  v
FastAPI
  |
  | SQL :5432
  v
PostgreSQL + PostGIS
```

## Current responsibilities

- **Next.js:** application shell, map rendering, platform-status display.
- **FastAPI:** versioned service foundation and liveness/readiness checks.
- **PostGIS:** spatially enabled system of record.
- **Docker Compose:** repeatable local orchestration and service networking.

## Step 1 acceptance tests

1. `docker compose up --build` starts all three services.
2. `http://localhost:3000` displays the Maryland foundation map.
3. `http://localhost:8000/health` reports `healthy`.
4. `http://localhost:8000/ready` reports `ready` and returns a PostGIS version.
5. `http://localhost:8000/docs` displays interactive API documentation.
