import requests
import pandas as pd
import streamlit as st
import folium
from streamlit_folium import st_folium

st.set_page_config(page_title="FloodClaims Intelligence", layout="wide")

st.title("🌊 FloodClaims Intelligence")
st.write("Flood exposure, weather alerts, stream gauges, and claims-triage support.")

def geocode_location(query):
    url = "https://nominatim.openstreetmap.org/search"
    params = {"q": query, "format": "json", "limit": 1, "countrycodes": "us"}
    headers = {"User-Agent": "FloodClaims-Intelligence-Demo"}
    r = requests.get(url, params=params, headers=headers, timeout=20)
    data = r.json()
    if not data:
        return None
    return {
        "name": data[0]["display_name"],
        "lat": float(data[0]["lat"]),
        "lon": float(data[0]["lon"])
    }

def get_alerts(lat, lon):
    try:
        url = "https://api.weather.gov/alerts/active"
        headers = {"User-Agent": "FloodClaims-Intelligence-Demo"}
        params = {"point": f"{lat},{lon}"}
        r = requests.get(url, params=params, headers=headers, timeout=20)
        return r.json().get("features", [])
    except Exception:
        return []

def get_weather(lat, lon):
    try:
        headers = {"User-Agent": "FloodClaims-Intelligence-Demo"}
        point = requests.get(
            f"https://api.weather.gov/points/{lat},{lon}",
            headers=headers,
            timeout=20
        ).json()
        forecast_url = point["properties"]["forecast"]
        forecast = requests.get(forecast_url, headers=headers, timeout=20).json()
        return forecast["properties"]["periods"][:3]
    except Exception:
        return []

def make_demo_properties(lat, lon):
    data = [
        ["Property A", lat + 0.004, lon + 0.003, 850000, "Immediate inspection"],
        ["Property B", lat - 0.003, lon + 0.004, 420000, "Priority remote review"],
        ["Property C", lat + 0.002, lon - 0.004, 300000, "Desk review"],
        ["Property D", lat - 0.004, lon - 0.003, 250000, "No visible flood signal"],
        ["Property E", lat + 0.006, lon, 180000, "Insufficient evidence"],
    ]
    return pd.DataFrame(
        data,
        columns=["property", "latitude", "longitude", "estimated_exposure_usd", "claims_triage_category"]
    )

location = st.text_input("Enter a United States address or location", "New Orleans, Louisiana")
run = st.button("Run analysis")

if run:
    with st.spinner("Searching location and building results..."):
        place = geocode_location(location)

    if place is None:
        st.error("Location not found. Try another United States city or address.")
        st.stop()

    lat = place["lat"]
    lon = place["lon"]

    alerts = get_alerts(lat, lon)
    weather = get_weather(lat, lon)
    properties = make_demo_properties(lat, lon)

    st.success(f"Location found: {place['name']}")

    col1, col2, col3 = st.columns(3)
    col1.metric("Properties Reviewed", len(properties))
    col2.metric("Active Weather Alerts", len(alerts))
    col3.metric("Estimated Exposure", f"${properties['estimated_exposure_usd'].sum():,.0f}")

    st.subheader("Map")

    m = folium.Map(location=[lat, lon], zoom_start=13)

    folium.Marker(
        [lat, lon],
        popup="Searched Location",
        tooltip="Searched Location"
    ).add_to(m)

    folium.Circle(
        [lat, lon],
        radius=900,
        color="red",
        fill=True,
        fill_opacity=0.15,
        popup="Simulated probable flood signal"
    ).add_to(m)

    colors = {
        "Immediate inspection": "red",
        "Priority remote review": "orange",
        "Desk review": "blue",
        "No visible flood signal": "green",
        "Insufficient evidence": "gray"
    }

    for _, row in properties.iterrows():
        folium.CircleMarker(
            location=[row["latitude"], row["longitude"]],
            radius=7,
            color=colors[row["claims_triage_category"]],
            fill=True,
            fill_opacity=0.9,
            popup=f"{row['property']}<br>${row['estimated_exposure_usd']:,.0f}<br>{row['claims_triage_category']}"
        ).add_to(m)

    st_folium(m, width=700, height=450)

    st.subheader("Claims-Triage Results")
    st.dataframe(properties, use_container_width=True)

    st.download_button(
        "Download CSV",
        properties.to_csv(index=False).encode("utf-8"),
        "floodclaims_results.csv",
        "text/csv"
    )

    st.subheader("Weather Forecast")
    if weather:
        for w in weather:
            st.write(f"**{w['name']}**: {w['detailedForecast']}")
    else:
        st.info("Weather forecast unavailable.")

    st.subheader("Flood / Weather Alerts")
    if alerts:
        for a in alerts[:5]:
            p = a.get("properties", {})
            st.warning(p.get("headline", "Weather alert"))
    else:
        st.success("No active alerts returned for this location.")

    st.caption(
        "Disclaimer: This is a portfolio decision-support demo, not an insurance decision, claim decision, official flood determination, or emergency guidance tool."
        )
