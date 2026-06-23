import ApiStatus from "@/components/ApiStatus";
import GeoRiskMap from "@/components/GeoRiskMap";

export default function Home() {
  return (
    <main>
      <header className="site-header">
        <a className="brand" href="#top" aria-label="GeoRiskOS home">
          <span className="brand-mark">G</span>
          <span>
            <strong>GeoRiskOS</strong>
            <small>Geospatial Risk Intelligence</small>
          </span>
        </a>

        <nav aria-label="Primary navigation">
          <a href="#platform">Platform</a>
          <a href="#map">Map</a>
          <a href="http://localhost:8000/docs" target="_blank" rel="noreferrer">
            API Docs
          </a>
        </nav>
      </header>

      <section id="top" className="hero">
        <div className="hero-copy">
          <span className="eyebrow">Step 1 · Platform foundation</span>
          <h1>Reliable geospatial intelligence starts with a testable system.</h1>
          <p>
            GeoRiskOS will combine weather, streamflow, satellite imagery,
            infrastructure, exposure, and social vulnerability to produce
            calibrated and explainable environmental-risk forecasts.
          </p>

          <div className="hero-actions">
            <a className="primary-button" href="#map">
              Open foundation map
            </a>
            <a
              className="secondary-button"
              href="http://localhost:8000/docs"
              target="_blank"
              rel="noreferrer"
            >
              Inspect the API
            </a>
          </div>
        </div>

        <aside className="hero-panel" aria-label="Current implementation scope">
          <span className="eyebrow">Current release</span>
          <strong>Foundation v0.1.0</strong>
          <ul>
            <li>Next.js application shell</li>
            <li>FastAPI health and readiness endpoints</li>
            <li>PostgreSQL with PostGIS</li>
            <li>Docker Compose development environment</li>
            <li>MapLibre Maryland foundation map</li>
          </ul>
        </aside>
      </section>

      <section id="platform" className="section-block">
        <div className="section-heading">
          <span className="eyebrow">Live system checks</span>
          <h2>Platform foundation</h2>
          <p>
            These cards are populated by the running FastAPI service and
            PostGIS database rather than hard-coded frontend text.
          </p>
        </div>
        <ApiStatus />
      </section>

      <section id="map" className="section-block map-section">
        <GeoRiskMap />
      </section>

      <section className="next-step-panel">
        <span className="eyebrow">Next milestone</span>
        <h2>Step 2: spatial database and modelling grid</h2>
        <p>
          The next release will create a reproducible Maryland grid, assign
          county and state identifiers, validate geometry, and expose the grid
          through a versioned API endpoint.
        </p>
      </section>

      <footer>
        <span>GeoRiskOS · Foundation release</span>
        <span>Built for reproducibility, reliability, and spatial transfer.</span>
      </footer>
    </main>
  );
}
