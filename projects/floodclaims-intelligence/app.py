import math
import requests
import pandas as pd
import streamlit as st
import folium
from streamlit_folium import st_folium

st.set_page_config(
    page_title="FloodClaims Intelligence",
    page_icon="🌊",
    layout="wide"
)

APP_TITLE = "FloodClaims Intelligence"

st.markdown("""
<style>
.block-container {padding-top: 1.2rem;}
.metric-card {
    background: #f7f9fb;
    padding: 1rem;
    border-radius: 14px;
    border: 1px solid #e5e7eb;
}
.big-title {
    font-size: 2.1rem;
    font-weight: 800;
    color: #042E41;
}
.small-muted {
    color: #6b7280;
    font-size: 0.95rem;
}
</style>
""", unsafe_allow_html=True)


def geocode_location(query):
    url = "https://nominatim.openstreetmap.org/search"
    params = {"q": query, "format": "json", "limit": 1}
    headers = {"User-Agent": "FloodClaims-Intelligence-Demo"}
    r = requests.get(url, params=params, headers=headers, timeout=20)
    r.raise_for_status()
    data = r.json()
    if not data:
        return None
    item = data[0]
    return {
        "display_name": item["display_name"],
        "lat": float(item["lat"]),
        "lon": float(item["lon"])
    }


def get_nws_point(lat, lon):
    try:
        headers = {"User-Agent": "FloodClaims-Intelligence-Demo"}
        point_url = f"https://api.weather.gov/points/{lat},{lon}"
        p = requests.get(point_url, headers=headers, timeout=20).json()
        forecast_url = p["properties"]["forecast"]
        forecast = requests.get(forecast_url, headers=headers, timeout=20).json()
        periods = forecast["properties"]["periods"][:3]
        return periods
    except Exception:
        return []


def get_nws_alerts(lat, lon):
    try:
        headers = {"User-Agent": "FloodClaims-Intelligence-Demo"}
        url = "https://api.weather.gov/alerts/active"
        params = {"point": f"{lat},{lon}"}
        data = requests.get(url, params=params, headers=headers, timeout=20).json()
        return data.get("features", [])
    except Exception:
        return []


def get_usgs_gauges(lat, lon, radius_miles=20):
    try:
        delta = radius_miles / 69
        bbox = f"{lon-delta},{lat-delta},{lon+delta},{lat+delta}"
        url = "https://waterservices.usgs.gov/nwis/iv/"
        params = {
            "format": "json",
            "bBox": bbox,
            "parameterCd": "00065",
            "siteStatus": "active"
        }
        data = requests.get(url, params=params, timeout=25).json()
        series = data.get("value", {}).get("timeSeries", [])
        rows = []
        for s in series[:10]:
            source = s.get("sourceInfo", {})
            values = s.get("values", [{}])[0].get("value", [])
            latest = values[-1] if values else {}
            rows.append({
                "station": source.get("siteName", "Unknown"),
                "site_code": source.get("siteCode", [{}])[0].get("value", ""),
                "latitude": source.get("geoLocation", {}).get("geogLocation", {}).get("latitude"),
                "longitude": source.get("geoLocation", {}).get("geogLocation", {}).get("longitude"),
                "latest_stage_ft": latest.get("value"),
                "time": latest.get("dateTime")
            })
        return pd.DataFrame(rows)
    except Exception:
        return pd.DataFrame()


def get_osm_structures(lat, lon, radius_m=1200):
    query = f"""
    [out:json][timeout:25];
    (
      way["building"](around:{radius_m},{lat},{lon});
      relation["building"](around:{radius_m},{lat},{lon});
    );
    out center tags 60;
    """
    try:
        url = "https://overpass-api.de/api/interpreter"
        data = requests.post(url, data={"data": query}, timeout=30).json()
        rows = []
        for item in data.get("elements", []):
            center = item.get("center", {})
            tags = item.get("tags", {})
            if "lat" in center and "lon" in center:
                btype = tags.get("building", "structure")
                value = estimate_structure_value(btype)
                rows.append({
                    "building_type": btype,
                    "latitude": center["lat"],
                    "longitude": center["lon"],
                    "estimated_structure_value_usd": value,
                    "estimated_contents_value_usd": round(value * 0.45, 0)
                })
        return pd.DataFrame(rows)
    except Exception:
        return pd.DataFrame()


def estimate_structure_value(building_type):
    base = {
        "house": 320000,
        "residential": 280000,
        "apartments": 750000,
        "commercial": 1200000,
        "retail": 900000,
        "industrial": 1500000,
        "school": 2200000,
        "hospital": 5000000,
        "warehouse": 1600000
    }
    return base.get(str(building_type).lower(), 250000)


def haversine_m(lat1, lon1, lat2, lon2):
    r = 6371000
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp/2)**2 + math.cos(p1) * math.cos(p2) * math.sin(dl/2)**2
    return r * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))


def classify_claim(row, flood_signal, alert_count):
    value = row["estimated_structure_value_usd"] + row["estimated_contents_value_usd"]
    if flood_signal and value >= 1000000:
        return "Immediate inspection"
    if flood_signal:
        return "Priority remote review"
    if alert_count > 0 and value >= 500000:
        return "Desk review"
    if alert_count == 0:
        return "No visible flood signal"
    return "Insufficient evidence"


def add_nfhl_layer(m):
    folium.raster_layers.WmsTileLayer(
        url="https://hazards.fema.gov/gis/nfhl/services/public/NFHL/MapServer/WMSServer",
        layers="28,29,30",
        name="FEMA NFHL Flood Zones / Floodways",
        fmt="image/png",
        transparent=True,
        overlay=True,
        control=True
    ).add_to(m)


st.markdown(f"<div class='big-title'>{APP_TITLE}</div>", unsafe_allow_html=True)
st.markdown(
    "A geospatial flood exposure and satellite damage-assessment platform for underwriting, catastrophe response, claims triage, and resilience consulting."
)

with st.sidebar:
    st.header("Search")
    location = st.text_input("United States address or location", "Baltimore, Maryland")
    radius_m = st.slider("Structure search radius", 300, 3000, 1200, 100)
    flood_signal = st.checkbox("Simulate Sentinel-1 probable floodwater signal", value=True)
    run = st.button("Run FloodClaims Intelligence", use_container_width=True)

    st.divider()
    st.caption("Author: Itohan-Osa Abu")
    st.caption("Remote Sensing | GIS | Geospatial AI | Climate Risk | Insurance Analytics")

if run:
    result = geocode_location(location)

    if not result:
        st.error("Location not found. Try a clearer United States address or city.")
        st.stop()

    lat, lon = result["lat"], result["lon"]

    st.success(f"Location found: {result['display_name']}")

    weather = get_nws_point(lat, lon)
    alerts = get_nws_alerts(lat, lon)
    gauges = get_usgs_gauges(lat, lon)
    structures = get_osm_structures(lat, lon, radius_m)

    if not structures.empty:
        structures["distance_m"] = structures.apply(
            lambda r: round(haversine_m(lat, lon, r["latitude"], r["longitude"]), 1),
            axis=1
        )
        structures["claims_triage_category"] = structures.apply(
            lambda r: classify_claim(r, flood_signal, len(alerts)),
            axis=1
        )
        structures = structures.sort_values(
            by=["claims_triage_category", "estimated_structure_value_usd"],
            ascending=[True, False]
        )

    c1, c2, c3, c4 = st.columns(4)

    with c1:
        st.metric("Nearby Structures", len(structures))
    with c2:
        total_exposure = 0 if structures.empty else (
            structures["estimated_structure_value_usd"].sum()
            + structures["estimated_contents_value_usd"].sum()
        )
        st.metric("Estimated Exposure", f"${total_exposure:,.0f}")
    with c3:
        st.metric("Active Weather Alerts", len(alerts))
    with c4:
        st.metric("Probable Flood Signal", "Yes" if flood_signal else "No")

    left, right = st.columns([1.35, 1])

    with left:
        st.subheader("Interactive Flood Intelligence Map")

        m = folium.Map(location=[lat, lon], zoom_start=13, tiles="OpenStreetMap")

        folium.Marker(
            [lat, lon],
            popup="Searched Location",
            tooltip="Searched Location",
            icon=folium.Icon(color="blue", icon="home")
        ).add_to(m)

        add_nfhl_layer(m)

        if flood_signal:
            folium.Circle(
                location=[lat, lon],
                radius=radius_m * 0.55,
                color="red",
                fill=True,
                fill_opacity=0.18,
                popup="Probable floodwater signal from Sentinel-1 radar simulation"
            ).add_to(m)

        if not structures.empty:
            for _, row in structures.head(60).iterrows():
                category = row["claims_triage_category"]
                color = {
                    "Immediate inspection": "red",
                    "Priority remote review": "orange",
                    "Desk review": "blue",
                    "No visible flood signal": "green",
                    "Insufficient evidence": "gray"
                }.get(category, "gray")

                popup = f"""
                <b>Type:</b> {row['building_type']}<br>
                <b>Distance:</b> {row['distance_m']} m<br>
                <b>Structure value:</b> ${row['estimated_structure_value_usd']:,.0f}<br>
                <b>Contents value:</b> ${row['estimated_contents_value_usd']:,.0f}<br>
                <b>Triage:</b> {category}
                """

                folium.CircleMarker(
                    location=[row["latitude"], row["longitude"]],
                    radius=5,
                    color=color,
                    fill=True,
                    fill_opacity=0.85,
                    popup=popup
                ).add_to(m)

        if not gauges.empty:
            for _, g in gauges.iterrows():
                if pd.notna(g["latitude"]) and pd.notna(g["longitude"]):
                    folium.Marker(
                        [g["latitude"], g["longitude"]],
                        tooltip="USGS Stream Gauge",
                        popup=f"{g['station']}<br>Stage: {g['latest_stage_ft']} ft",
                        icon=folium.Icon(color="cadetblue", icon="tint")
                    ).add_to(m)

        folium.LayerControl().add_to(m)
        st_folium(m, width=None, height=620)

    with right:
        st.subheader("Weather and Flood Alerts")

        if weather:
            for period in weather:
                st.markdown(f"**{period.get('name')}**")
                st.write(period.get("detailedForecast"))
        else:
            st.info("Weather forecast unavailable for this location.")

        st.divider()

        if alerts:
            for alert in alerts[:5]:
                p = alert.get("properties", {})
                st.warning(f"{p.get('event', 'Alert')}: {p.get('headline', '')}")
        else:
            st.success("No active National Weather Service alerts returned for this point.")

    st.subheader("Claims-Triage Table")

    if structures.empty:
        st.info("No nearby OpenStreetMap building records were retrieved.")
    else:
        display_cols = [
            "building_type",
            "distance_m",
            "estimated_structure_value_usd",
            "estimated_contents_value_usd",
            "claims_triage_category",
            "latitude",
            "longitude"
        ]
        st.dataframe(structures[display_cols], use_container_width=True)

        csv = structures[display_cols].to_csv(index=False).encode("utf-8")
        st.download_button(
            "Download Property / Neighborhood Results CSV",
            csv,
            file_name="floodclaims_intelligence_results.csv",
            mime="text/csv"
        )

    st.subheader("USGS Stream Gauge Conditions")

    if gauges.empty:
        st.info("No nearby active USGS gauge stage records returned.")
    else:
        st.dataframe(gauges, use_container_width=True)

    st.subheader("Professional Interpretation")

    st.write("""
    This application combines public flood-zone mapping, open structure records,
    weather alerts, stream-gauge conditions, and simulated satellite floodwater evidence
    to support insurance inspection prioritization, catastrophe response, underwriting review,
    and resilience consulting.
    """)

    st.info("""
    Disclaimer: This application is a decision-support and portfolio demonstration tool.
    It is not a flood guarantee, insurance quote, claim decision, property appraisal,
    or substitute for official emergency guidance and field inspection.
    Public structure values are modeled estimates and are not actual insurance policy limits.
    """)

else:
    st.info("Enter a United States address or location, then tap **Run FloodClaims Intelligence**.")
