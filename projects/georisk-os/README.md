# GeoRiskOS

GeoRiskOS is a production-oriented multimodal geospatial risk-intelligence platform. The completed platform will combine weather, streamflow, satellite imagery, flood-hazard context, infrastructure, population exposure, social vulnerability, uncertainty calibration, and reliable model explanations.

This repository currently contains **Step 1: the platform foundation**.

## Portfolio location

This project is designed to live inside the existing portfolio repository at:

```text
geospatial-ai-portfolio/projects/georisk-os/
```

Run Docker and project commands from the `projects/georisk-os` directory. Run Git commit and push commands from the `geospatial-ai-portfolio` repository root.

## Included in Step 1

- Next.js frontend
- MapLibre Maryland and Washington, DC foundation map
- FastAPI backend
- `/health`, `/ready`, and `/version` endpoints
- PostgreSQL with PostGIS
- Docker Compose orchestration
- Backend smoke tests
- Initial architecture documentation

## Prerequisites

Install:

- Git
- Docker Desktop

Docker Desktop must be running before the commands below are used.

## Start the complete platform

### Windows PowerShell

```powershell
Copy-Item .env.example .env

docker compose up --build
```

You can instead run:

```powershell
.\scripts\start.ps1
```

### macOS or Linux

```bash
cp .env.example .env
./scripts/start.sh
```

## Open the services

- Frontend: http://localhost:3000
- Backend root: http://localhost:8000
- Interactive API documentation: http://localhost:8000/docs
- Liveness check: http://localhost:8000/health
- Readiness and PostGIS check: http://localhost:8000/ready

## Verify the database manually

```bash
docker compose exec database psql -U georisk -d georisk -c "SELECT PostGIS_Full_Version();"
```

## Run backend tests

```bash
docker compose exec backend pytest
```

## Run frontend checks

```bash
docker compose exec frontend npm run typecheck
docker compose exec frontend npm run lint
```

## Stop the platform

```bash
docker compose down
```

To remove the local database volume as well:

```bash
docker compose down -v
```

Only use `-v` when you intentionally want to delete local database data.

## Troubleshooting

### Port already in use

Edit `.env` and change one or more of:

```text
POSTGRES_PORT=5433
BACKEND_PORT=8001
FRONTEND_PORT=3001
NEXT_PUBLIC_API_BASE_URL=http://localhost:8001
```

Then restart Docker Compose.

### Frontend says the API is offline

Confirm that:

1. `http://localhost:8000/health` opens in the browser.
2. `.env` contains `NEXT_PUBLIC_API_BASE_URL=http://localhost:8000`.
3. The backend container is healthy:

```bash
docker compose ps
```

### Reset a broken first run

```bash
docker compose down -v
docker compose build --no-cache
docker compose up
```

## Commit Step 1

```bash
git add .
git commit -m "feat: initialize GeoRiskOS platform architecture"
git push origin main
```

## Step 1 definition of done

- All three containers are running.
- The frontend shows the foundation map.
- The API status card says `Online`.
- The PostGIS card says `Connected`.
- `/ready` returns a PostGIS version.
- Backend tests pass.

## Next milestone

Step 2 will add a reproducible Maryland modelling grid, spatial database tables, geometry validation, county and state assignment, spatial indexes, and a versioned API endpoint for serving the grid.
