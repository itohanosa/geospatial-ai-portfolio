"use client";

import maplibregl, { type StyleSpecification } from "maplibre-gl";
import { useEffect, useRef } from "react";

const marylandBounds: maplibregl.LngLatBoundsLike = [
  [-79.55, 37.82],
  [-74.85, 39.78],
];

const baseMapStyle: StyleSpecification = {
  version: 8,
  sources: {
    openStreetMap: {
      type: "raster",
      tiles: [
        "https://a.tile.openstreetmap.org/{z}/{x}/{y}.png",
        "https://b.tile.openstreetmap.org/{z}/{x}/{y}.png",
        "https://c.tile.openstreetmap.org/{z}/{x}/{y}.png",
      ],
      tileSize: 256,
      attribution: "© OpenStreetMap contributors",
    },
  },
  layers: [
    {
      id: "open-street-map",
      type: "raster",
      source: "openStreetMap",
      minzoom: 0,
      maxzoom: 19,
    },
  ],
};

export default function GeoRiskMap() {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);

  useEffect(() => {
    if (!containerRef.current || mapRef.current) {
      return;
    }

    const map = new maplibregl.Map({
      container: containerRef.current,
      style: baseMapStyle,
      center: [-76.65, 39.05],
      zoom: 6.5,
      minZoom: 5,
      maxZoom: 16,
      attributionControl: true,
    });

    map.addControl(new maplibregl.NavigationControl(), "top-right");
    map.addControl(new maplibregl.ScaleControl({ unit: "imperial" }), "bottom-left");

    map.on("load", () => {
      map.fitBounds(marylandBounds, {
        padding: 36,
        duration: 0,
      });
    });

    mapRef.current = map;

    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, []);

  return (
    <div className="map-shell">
      <div className="map-toolbar">
        <div>
          <span className="eyebrow">Study region</span>
          <h2>Maryland and Washington, DC</h2>
        </div>
        <span className="map-stage-badge">Foundation map</span>
      </div>

      <div
        ref={containerRef}
        className="map-container"
        role="application"
        aria-label="Interactive GeoRiskOS map centered on Maryland and Washington, DC"
      />

      <div className="map-footer">
        <span>No risk layer has been loaded yet.</span>
        <span>Step 2 will add the modelling grid and static features.</span>
      </div>
    </div>
  );
}
