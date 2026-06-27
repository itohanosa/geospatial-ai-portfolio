from __future__ import annotations

import io
import math
import os
from typing import Any

import folium
import numpy as np
import pandas as pd
import requests
import streamlit as st
from folium.plugins import MarkerCluster
from streamlit_folium import st_folium


st.set_page_config(
    page_title="Wildfire Home Risk Intelligence",
    page_icon="🔥",
    layout="wide",
)


# =============================================================================
# PUBLIC DATA ENDPOINTS
# =============================================================================

NSI_ROOT = "https://nsi.sec.usace.army.mil/nsiapi"

FIRMS_ROOT = (
    "https://firms.modaps.eosdis.nasa.gov/"
    "api/area/csv"
)

CENSUS_GEOCODER = (
    "https://geocoding.geo.census.gov/"
    "geocoder/locations/onelineaddress"
)

PLACE_GEOCODER = (
    "https://geocoding-api.open-meteo.com/"
    "v1/search"
)

WEATHER_API = (
    "https://api.open-meteo.com/v1/forecast"
)

HEADERS = {
    "User-Agent": (
        "WildfireHomeRisk/1.0 "
        "(public geospatial demonstration)"
    )
}

MAX_STRUCTURES = 25_000
MAX_MAP_STRUCTURES = 2_500
MAX_MAP_FIRES = 1_000


# =============================================================================
# MOBILE-FRIENDLY STYLING
# =============================================================================

st.markdown(
    """
    <style>
    .block-container {
        padding-top: 1rem;
        padding-bottom: 2rem;
        max-width: 1500px;
    }

    .stButton > button,
    .stDownloadButton > button {
        min-height: 3rem;
        font-weight: 700;
    }

    iframe {
        border-radius: 0.65rem;
    }

    .leaflet-control-attribution {
        font-size: 8px !important;
        line-height: 10px !important;
        max-width: 70% !important;
        padding: 1px 3px !important;
    }

    .leaflet-control-layers {
        font-size: 12px !important;
    }

    @media (max-width: 700px) {
        .block-container {
            padding-left: 0.65rem;
            padding-right: 0.65rem;
        }

        h1 {
            font-size: 1.8rem !important;
        }

        h2 {
            font-size: 1.35rem !important;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# =============================================================================
# GENERAL HELPERS
# =============================================================================

def nasa_key() -> str:
    """
    Read the NASA FIRMS key from Streamlit Secrets
    or an environment variable.
    """

    try:
        return str(
            st.secrets.get(
                "FIRMS_MAP_KEY",
                "",
            )
        ).strip()

    except Exception:
        return os.getenv(
            "FIRMS_MAP_KEY",
            "",
        ).strip()


def get_json(
    url: str,
    params: dict[str, Any] | None = None,
    timeout: int = 60,
) -> Any:
    """
    Make a GET request and return JSON.
    """

    response = requests.get(
        url,
        params=params,
        headers=HEADERS,
        timeout=timeout,
    )

    response.raise_for_status()

    return response.json()


def number(
    value: Any,
    default: float = np.nan,
) -> float:
    """
    Convert a value to a number.
    """

    value = pd.to_numeric(
        value,
        errors="coerce",
    )

    if pd.isna(value):
        return default

    return float(value)


def shown(
    value: Any,
    decimals: int = 1,
    suffix: str = "",
) -> str:
    """
    Format a number for display.
    """

    value = number(value)

    if not np.isfinite(value):
        return "Unavailable"

    return (
        f"{value:.{decimals}f}"
        f"{suffix}"
    )


def money(
    value: float,
) -> str:
    """
    Format monetary values.
    """

    value = float(
        value or 0
    )

    if value >= 1_000_000_000:
        return (
            f"${value / 1_000_000_000:.2f}B"
        )

    if value >= 1_000_000:
        return (
            f"${value / 1_000_000:.2f}M"
        )

    return f"${value:,.0f}"


# =============================================================================
# ADDRESS AND PLACE SEARCH
# =============================================================================

@st.cache_data(
    ttl=86_400,
    show_spinner=False,
)
def geocode(
    query: str,
) -> dict[str, Any]:
    """
    Search first with the U.S. Census address geocoder.

    If no exact address is found, fall back to the
    Open-Meteo city and place geocoder.
    """

    query = query.strip()

    if not query:
        raise ValueError(
            "Enter a U.S. address, city, or ZIP code."
        )

    # Try exact U.S. address search first.
    try:
        data = get_json(
            CENSUS_GEOCODER,
            {
                "address": query,
                "benchmark": "Public_AR_Current",
                "format": "json",
            },
            45,
        )

        matches = (
            data.get(
                "result",
                {},
            )
            .get(
                "addressMatches",
                [],
            )
        )

        if matches:
            match = matches[0]

            coordinates = match[
                "coordinates"
            ]

            return {
                "lat": float(
                    coordinates["y"]
                ),
                "lon": float(
                    coordinates["x"]
                ),
                "label": match.get(
                    "matchedAddress",
                    query,
                ),
                "zoom": 18,
            }

    except Exception:
        pass

    # Fall back to city, community, or ZIP search.
    data = get_json(
        PLACE_GEOCODER,
        {
            "name": query,
            "count": 10,
            "language": "en",
            "format": "json",
        },
        30,
    )

    results = data.get(
        "results",
        [],
    )

    us_results = [
        row
        for row in results
        if str(
            row.get(
                "country_code",
                "",
            )
        ).upper()
        == "US"
    ]

    rows = (
        us_results
        or results
    )

    if not rows:
        raise ValueError(
            "No location was found. "
            "Try a complete address or a city and state."
        )

    row = rows[0]

    label = ", ".join(
        str(
            row.get(field)
        )
        for field in [
            "name",
            "admin2",
            "admin1",
            "country",
        ]
        if row.get(field)
    )

    return {
        "lat": float(
            row["latitude"]
        ),
        "lon": float(
            row["longitude"]
        ),
        "label": label,
        "zoom": 14,
    }


# =============================================================================
# GEOMETRY
# =============================================================================

def geometry(
    lat: float,
    lon: float,
    miles: float,
) -> tuple[
    str,
    str,
    dict[str, Any],
]:
    """
    Create:

    1. NSI polygon string.
    2. NASA FIRMS rectangular bounding box.
    3. GeoJSON polygon for NSI POST fallback.
    """

    latitude_change = (
        miles / 69.0
    )

    longitude_change = (
        miles
        / max(
            69.172
            * math.cos(
                math.radians(lat)
            ),
            10.0,
        )
    )

    west = (
        lon
        - longitude_change
    )

    east = (
        lon
        + longitude_change
    )

    south = (
        lat
        - latitude_change
    )

    north = (
        lat
        + latitude_change
    )

    ring = [
        [
            west,
            south,
        ],
        [
            east,
            south,
        ],
        [
            east,
            north,
        ],
        [
            west,
            north,
        ],
        [
            west,
            south,
        ],
    ]

    nsi_bbox = ",".join(
        f"{coordinate:.6f}"
        for point in ring
        for coordinate in point
    )

    firms_bbox = (
        f"{west:.6f},"
        f"{south:.6f},"
        f"{east:.6f},"
        f"{north:.6f}"
    )

    geojson = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        ring
                    ],
                },
                "properties": {},
            }
        ],
    }

    return (
        nsi_bbox,
        firms_bbox,
        geojson,
    )


def distances(
    lat: float,
    lon: float,
    target_latitudes: np.ndarray,
    target_longitudes: np.ndarray,
) -> np.ndarray:
    """
    Calculate great-circle distance in miles
    from one selected property to many points.
    """

    if len(
        target_latitudes
    ) == 0:
        return np.array(
            [],
            dtype=float,
        )

    earth_radius_miles = (
        3958.7613
    )

    latitude_1 = math.radians(
        lat
    )

    longitude_1 = math.radians(
        lon
    )

    latitude_2 = np.radians(
        target_latitudes.astype(
            float
        )
    )

    longitude_2 = np.radians(
        target_longitudes.astype(
            float
        )
    )

    latitude_difference = (
        latitude_2
        - latitude_1
    )

    longitude_difference = (
        longitude_2
        - longitude_1
    )

    haversine = (
        np.sin(
            latitude_difference
            / 2
        )
        ** 2
        + math.cos(
            latitude_1
        )
        * np.cos(
            latitude_2
        )
        * np.sin(
            longitude_difference
            / 2
        )
        ** 2
    )

    haversine = np.clip(
        haversine,
        0,
        1,
    )

    return (
        2
        * earth_radius_miles
        * np.arctan2(
            np.sqrt(
                haversine
            ),
            np.sqrt(
                1
                - haversine
            ),
        )
    )


# =============================================================================
# NATIONAL STRUCTURE INVENTORY
# =============================================================================

def parse_structures(
    data: dict[str, Any],
) -> pd.DataFrame:
    """
    Convert the NSI GeoJSON response into a table.
    """

    rows = []

    for feature in data.get(
        "features",
        [],
    ):
        properties = (
            feature.get(
                "properties"
            )
            or {}
        )

        coordinates = (
            feature.get(
                "geometry"
            )
            or {}
        ).get(
            "coordinates"
        ) or []

        if len(
            coordinates
        ) < 2:
            continue

        rows.append(
            {
                "structure_id": properties.get(
                    "fd_id"
                ),
                "latitude": coordinates[1],
                "longitude": coordinates[0],
                "occupancy": properties.get(
                    "occtype",
                    "Unknown",
                ),
                "category": properties.get(
                    "st_damcat",
                    "Unknown",
                ),
                "square_feet": properties.get(
                    "sqft"
                ),
                "stories": properties.get(
                    "num_story"
                ),
                "median_year_built": properties.get(
                    "med_yr_blt"
                ),
                "structure_value": properties.get(
                    "val_struct"
                ),
                "contents_value": properties.get(
                    "val_cont"
                ),
                "vehicle_value": properties.get(
                    "val_vehic"
                ),
            }
        )

    dataframe = pd.DataFrame(
        rows
    )

    if dataframe.empty:
        return dataframe

    numeric_columns = [
        "latitude",
        "longitude",
        "square_feet",
        "stories",
        "median_year_built",
        "structure_value",
        "contents_value",
        "vehicle_value",
    ]

    for column in numeric_columns:
        dataframe[column] = pd.to_numeric(
            dataframe[column],
            errors="coerce",
        )

    value_columns = [
        "structure_value",
        "contents_value",
        "vehicle_value",
    ]

    dataframe[
        value_columns
    ] = (
        dataframe[
            value_columns
        ]
        .fillna(0)
        .clip(
            lower=0
        )
    )

    dataframe[
        "estimated_asset_value"
    ] = dataframe[
        value_columns
    ].sum(
        axis=1
    )

    return (
        dataframe.dropna(
            subset=[
                "latitude",
                "longitude",
            ]
        )
        .reset_index(
            drop=True
        )
    )


@st.cache_data(
    ttl=86_400,
    show_spinner=False,
)
def get_structures(
    nsi_bbox: str,
    geojson: dict[str, Any],
) -> pd.DataFrame:
    """
    Retrieve NSI structures.

    First try the official GET bounding-box request.
    If that fails, retry using the official POST GeoJSON method.
    """

    endpoint = (
        f"{NSI_ROOT}/structures"
    )

    messages = []

    # First attempt: official bounding-box GET request.
    try:
        response = requests.get(
            endpoint,
            params={
                "bbox": nsi_bbox,
                "fmt": "fc",
            },
            headers=HEADERS,
            timeout=180,
        )

        if response.ok:
            return parse_structures(
                response.json()
            )

        messages.append(
            f"GET HTTP "
            f"{response.status_code}"
        )

    except Exception as error:
        messages.append(
            f"GET failed: {error}"
        )

    # Second attempt: official GeoJSON POST request.
    try:
        response = requests.post(
            endpoint,
            params={
                "fmt": "fc",
            },
            json=geojson,
            headers={
                **HEADERS,
                "Content-Type": (
                    "application/json"
                ),
            },
            timeout=180,
        )

        if response.ok:
            return parse_structures(
                response.json()
            )

        messages.append(
            f"POST HTTP "
            f"{response.status_code}"
        )

    except Exception as error:
        messages.append(
            f"POST failed: {error}"
        )

    raise RuntimeError(
        "National Structure Inventory request failed. "
        + " | ".join(
            messages
        )
    )


# =============================================================================
# WEATHER AND NASA FIRE DATA
# =============================================================================

@st.cache_data(
    ttl=900,
    show_spinner=False,
)
def get_weather(
    lat: float,
    lon: float,
) -> dict[str, Any]:
    """
    Retrieve current weather.
    """

    data = get_json(
        WEATHER_API,
        {
            "latitude": lat,
            "longitude": lon,
            "current": (
                "temperature_2m,"
                "relative_humidity_2m,"
                "precipitation,"
                "wind_speed_10m,"
                "wind_gusts_10m"
            ),
            "temperature_unit": (
                "fahrenheit"
            ),
            "wind_speed_unit": (
                "mph"
            ),
            "precipitation_unit": (
                "inch"
            ),
            "timezone": "auto",
        },
    )

    return data.get(
        "current",
        {},
    )


@st.cache_data(
    ttl=900,
    show_spinner=False,
)
def get_fires(
    key: str,
    product: str,
    firms_bbox: str,
    days: int,
) -> pd.DataFrame:
    """
    Retrieve recent NASA FIRMS thermal detections.
    """

    if not key:
        return pd.DataFrame(
            columns=[
                "latitude",
                "longitude",
                "frp",
                "confidence",
            ]
        )

    url = (
        f"{FIRMS_ROOT}/"
        f"{key}/"
        f"{product}/"
        f"{firms_bbox}/"
        f"{days}"
    )

    response = requests.get(
        url,
        headers=HEADERS,
        timeout=120,
    )

    response.raise_for_status()

    text = response.text.strip()

    if not text:
        return pd.DataFrame(
            columns=[
                "latitude",
                "longitude",
                "frp",
                "confidence",
            ]
        )

    if text.lower().startswith(
        (
            "invalid",
            "error",
        )
    ):
        raise ValueError(
            text
        )

    dataframe = pd.read_csv(
        io.StringIO(
            text
        )
    )

    if dataframe.empty:
        return dataframe

    if not {
        "latitude",
        "longitude",
    }.issubset(
        dataframe.columns
    ):
        raise ValueError(
            "NASA FIRMS did not return coordinates."
        )

    for column in [
        "latitude",
        "longitude",
        "frp",
    ]:
        if column in dataframe.columns:
            dataframe[
                column
            ] = pd.to_numeric(
                dataframe[
                    column
                ],
                errors="coerce",
            )

    if "frp" not in dataframe:
        dataframe["frp"] = np.nan

    if "confidence" not in dataframe:
        dataframe[
            "confidence"
        ] = "Unknown"

    return (
        dataframe.dropna(
            subset=[
                "latitude",
                "longitude",
            ]
        )
        .reset_index(
            drop=True
        )
    )


# =============================================================================
# TRANSPARENT SCREENING SCORE
# =============================================================================

def fire_weather_score(
    weather: dict[str, Any],
) -> float:
    """
    Calculate a transparent current-condition
    fire-weather screening score.
    """

    temperature = number(
        weather.get(
            "temperature_2m"
        ),
        70,
    )

    humidity = number(
        weather.get(
            "relative_humidity_2m"
        ),
        50,
    )

    precipitation = number(
        weather.get(
            "precipitation"
        ),
        0,
    )

    wind = number(
        weather.get(
            "wind_speed_10m"
        ),
        0,
    )

    gust = number(
        weather.get(
            "wind_gusts_10m"
        ),
        0,
    )

    score = (
        np.clip(
            (
                55
                - humidity
            )
            / 45,
            0,
            1,
        )
        * 35
        + np.clip(
            wind / 30,
            0,
            1,
        )
        * 25
        + np.clip(
            gust / 50,
            0,
            1,
        )
        * 20
        + np.clip(
            (
                temperature
                - 60
            )
            / 40,
            0,
            1,
        )
        * 20
        - np.clip(
            precipitation
            / 0.15,
            0,
            1,
        )
        * 30
    )

    return float(
        np.clip(
            score,
            0,
            100,
        )
    )


def proximity_score(
    distance: float | None,
) -> float:
    """
    Convert nearest NASA detection distance
    into a transparent proximity score.
    """

    if (
        distance is None
        or not np.isfinite(
            distance
        )
    ):
        return 0

    if distance <= 1:
        return 100

    if distance <= 3:
        return 90

    if distance <= 5:
        return 80

    if distance <= 10:
        return 65

    if distance <= 25:
        return 40

    if distance <= 50:
        return 20

    return 0


def risk_level(
    score: float,
) -> str:
    """
    Convert the screening score to a category.
    """

    if score >= 80:
        return "Critical"

    if score >= 60:
        return "High"

    if score >= 35:
        return "Moderate"

    return "Low"


# =============================================================================
# MAP FUNCTIONS
# =============================================================================

def add_tiles(
    map_object: folium.Map,
) -> None:
    """
    Add street and satellite maps.
    """

    folium.TileLayer(
        "OpenStreetMap",
        name="Street map",
    ).add_to(
        map_object
    )

    folium.TileLayer(
        (
            "https://server.arcgisonline.com/"
            "ArcGIS/rest/services/World_Imagery/"
            "MapServer/tile/{z}/{y}/{x}"
        ),
        attr="Esri World Imagery",
        name="Satellite",
    ).add_to(
        map_object
    )


def make_selection_map(
    lat: float,
    lon: float,
    zoom: int,
    selected: bool,
) -> folium.Map:
    """
    Create the home-selection map.
    """

    result = folium.Map(
        location=[
            lat,
            lon,
        ],
        zoom_start=zoom,
        tiles=None,
        control_scale=True,
    )

    add_tiles(
        result
    )

    if selected:
        folium.Marker(
            [
                lat,
                lon,
            ],
            tooltip=(
                "Selected home/property"
            ),
            icon=folium.Icon(
                color="blue",
                icon="home",
                prefix="fa",
            ),
        ).add_to(
            result
        )

    folium.LatLngPopup().add_to(
        result
    )

    folium.LayerControl(
        collapsed=True
    ).add_to(
        result
    )

    return result


def make_result_map(
    lat: float,
    lon: float,
    radius_miles: float,
    structures: pd.DataFrame,
    fires: pd.DataFrame,
) -> folium.Map:
    """
    Create the final result map.
    """

    result = folium.Map(
        location=[
            lat,
            lon,
        ],
        zoom_start=16,
        tiles=None,
        control_scale=True,
    )

    add_tiles(
        result
    )

    folium.Circle(
        [
            lat,
            lon,
        ],
        radius=(
            radius_miles
            * 1609.344
        ),
        color="#2563eb",
        fill=True,
        fill_opacity=0.06,
        tooltip=(
            "Structure exposure radius"
        ),
    ).add_to(
        result
    )

    folium.Marker(
        [
            lat,
            lon,
        ],
        tooltip=(
            "Selected home/property"
        ),
        icon=folium.Icon(
            color="blue",
            icon="home",
            prefix="fa",
        ),
    ).add_to(
        result
    )

    if not structures.empty:
        cluster = MarkerCluster(
            name=(
                "National Structure "
                "Inventory records"
            )
        ).add_to(
            result
        )

        display_structures = (
            structures.nsmallest(
                min(
                    MAX_MAP_STRUCTURES,
                    len(
                        structures
                    ),
                ),
                "distance_from_home_miles",
            )
        )

        for row in (
            display_structures.itertuples()
        ):
            folium.CircleMarker(
                [
                    row.latitude,
                    row.longitude,
                ],
                radius=3,
                color="#f59e0b",
                fill=True,
                fill_opacity=0.8,
                tooltip=(
                    f"{row.occupancy} | "
                    f"{money(row.estimated_asset_value)} | "
                    f"{row.distance_from_home_miles:.3f} mi"
                ),
            ).add_to(
                cluster
            )

    if not fires.empty:
        fire_group = folium.FeatureGroup(
            name=(
                "NASA FIRMS detections"
            )
        ).add_to(
            result
        )

        for row in fires.head(
            MAX_MAP_FIRES
        ).itertuples():
            folium.CircleMarker(
                [
                    row.latitude,
                    row.longitude,
                ],
                radius=6,
                color="#7f1d1d",
                fill=True,
                fill_color="#ef4444",
                fill_opacity=0.9,
                tooltip=(
                    "NASA detection | "
                    f"{row.distance_from_home_miles:.2f} mi"
                ),
            ).add_to(
                fire_group
            )

    folium.LayerControl(
        collapsed=True
    ).add_to(
        result
    )

    return result


# =============================================================================
# SESSION STATE
# =============================================================================

def initialize() -> None:
    """
    Initialize Streamlit session values.
    """

    defaults = {
        "lat": 39.8283,
        "lon": -98.5795,
        "label": "United States",
        "zoom": 4,
        "selected": False,
        "map_version": 0,
        "analysis": None,
    }

    for key, value in (
        defaults.items()
    ):
        if key not in (
            st.session_state
        ):
            st.session_state[
                key
            ] = value


initialize()


# =============================================================================
# USER INTERFACE
# =============================================================================

st.title(
    "🔥 Wildfire Home & Neighborhood Intelligence"
)

st.caption(
    "Search a U.S. address, zoom to the exact property, "
    "tap the roof, and analyze real public structures, "
    "current weather, and recent NASA fire detections."
)


with st.sidebar:
    st.header(
        "1. Find the property"
    )

    query = st.text_input(
        "Full U.S. address, city, or ZIP code",
        placeholder=(
            "123 Main St, "
            "Paradise, CA 95969"
        ),
    )

    if st.button(
        "Search and zoom",
        use_container_width=True,
    ):
        try:
            with st.spinner(
                "Locating the property..."
            ):
                found = geocode(
                    query
                )

            st.session_state.lat = (
                found["lat"]
            )

            st.session_state.lon = (
                found["lon"]
            )

            st.session_state.label = (
                found["label"]
            )

            st.session_state.zoom = (
                found["zoom"]
            )

            st.session_state.selected = (
                True
            )

            st.session_state.map_version += (
                1
            )

            st.session_state.analysis = (
                None
            )

            st.rerun()

        except Exception as error:
            st.error(
                f"Search failed: {error}"
            )

    st.header(
        "2. Analysis settings"
    )

    structure_radius = (
        st.select_slider(
            "Structure exposure radius (miles)",
            options=[
                0.10,
                0.25,
                0.50,
                1.00,
            ],
            value=0.25,
        )
    )

    fire_radius = (
        st.select_slider(
            "NASA fire search radius (miles)",
            options=[
                10,
                25,
                50,
                75,
            ],
            value=50,
        )
    )

    days = st.slider(
        "Recent NASA detection window (days)",
        1,
        5,
        2,
    )

    product = st.selectbox(
        "NASA satellite product",
        [
            "VIIRS_SNPP_NRT",
            "VIIRS_NOAA20_NRT",
            "VIIRS_NOAA21_NRT",
            "MODIS_NRT",
        ],
    )

    key = st.text_input(
        "NASA FIRMS MAP_KEY",
        nasa_key(),
        type="password",
    )

    st.info(
        "Switch to Satellite, zoom in, and tap "
        "the center of the roof for the most "
        "precise result."
    )


st.subheader(
    "Select the exact home or property"
)

selection = st_folium(
    make_selection_map(
        st.session_state.lat,
        st.session_state.lon,
        st.session_state.zoom,
        st.session_state.selected,
    ),
    height=520,
    use_container_width=True,
    key=(
        f"selection_map_"
        f"{st.session_state.map_version}"
    ),
    returned_objects=[
        "last_clicked",
        "zoom",
    ],
)


clicked = (
    selection.get(
        "last_clicked"
    )
    if selection
    else None
)


if clicked:
    new_latitude = float(
        clicked["lat"]
    )

    new_longitude = float(
        clicked["lng"]
    )

    changed = (
        not st.session_state.selected
        or abs(
            new_latitude
            - st.session_state.lat
        )
        > 1e-7
        or abs(
            new_longitude
            - st.session_state.lon
        )
        > 1e-7
    )

    if changed:
        st.session_state.lat = (
            new_latitude
        )

        st.session_state.lon = (
            new_longitude
        )

        st.session_state.label = (
            "Map-selected property"
        )

        st.session_state.zoom = int(
            selection.get(
                "zoom"
            )
            or 18
        )

        st.session_state.selected = (
            True
        )

        st.session_state.analysis = (
            None
        )

        st.rerun()


if st.session_state.selected:
    st.success(
        f"Selected: **{st.session_state.label}**  \n"
        f"Coordinates: "
        f"`{st.session_state.lat:.6f}, "
        f"{st.session_state.lon:.6f}`"
    )

else:
    st.warning(
        "Search for a location or tap the map "
        "before analyzing."
    )


run = st.button(
    "Analyze this home/property",
    type="primary",
    use_container_width=True,
    disabled=(
        not st.session_state.selected
    ),
)


# =============================================================================
# RUN ANALYSIS
# =============================================================================

if run:
    latitude = float(
        st.session_state.lat
    )

    longitude = float(
        st.session_state.lon
    )

    (
        nsi_bbox,
        _,
        geojson,
    ) = geometry(
        latitude,
        longitude,
        float(
            structure_radius
        ),
    )

    (
        _,
        firms_bbox,
        _,
    ) = geometry(
        latitude,
        longitude,
        float(
            fire_radius
        ),
    )

    try:
        with st.spinner(
            "Retrieving real public structure records..."
        ):
            structures = get_structures(
                nsi_bbox,
                geojson,
            )

        if len(
            structures
        ) > MAX_STRUCTURES:
            st.error(
                "The selected radius returned "
                f"{len(structures):,} structures. "
                "Choose a smaller structure exposure radius."
            )

            st.stop()

        with st.spinner(
            "Retrieving weather and NASA fire detections..."
        ):
            weather = get_weather(
                latitude,
                longitude,
            )

            fires = get_fires(
                key,
                product,
                firms_bbox,
                days,
            )

        nearest_structure = None

        if not structures.empty:
            structures = (
                structures.copy()
            )

            structures[
                "distance_from_home_miles"
            ] = distances(
                latitude,
                longitude,
                structures[
                    "latitude"
                ].to_numpy(),
                structures[
                    "longitude"
                ].to_numpy(),
            )

            structures = (
                structures.sort_values(
                    "distance_from_home_miles"
                )
                .reset_index(
                    drop=True
                )
            )

            nearest_structure = (
                structures.iloc[
                    0
                ].to_dict()
            )

        nearest_fire = None

        if not fires.empty:
            fires = fires.copy()

            fires[
                "distance_from_home_miles"
            ] = distances(
                latitude,
                longitude,
                fires[
                    "latitude"
                ].to_numpy(),
                fires[
                    "longitude"
                ].to_numpy(),
            )

            fires = (
                fires.sort_values(
                    "distance_from_home_miles"
                )
                .reset_index(
                    drop=True
                )
            )

            nearest_fire = float(
                fires.iloc[
                    0
                ][
                    "distance_from_home_miles"
                ]
            )

        weather_risk = (
            fire_weather_score(
                weather
            )
        )

        score = round(
            min(
                100,
                0.65
                * proximity_score(
                    nearest_fire
                )
                + 0.35
                * weather_risk,
            ),
            1,
        )

        st.session_state.analysis = {
            "lat": latitude,
            "lon": longitude,
            "label": (
                st.session_state.label
            ),
            "structure_radius": (
                structure_radius
            ),
            "fire_radius": (
                fire_radius
            ),
            "days": days,
            "product": product,
            "structures": structures,
            "nearest_structure": (
                nearest_structure
            ),
            "fires": fires,
            "nearest_fire": (
                nearest_fire
            ),
            "weather": weather,
            "weather_score": (
                weather_risk
            ),
            "score": score,
            "level": risk_level(
                score
            ),
        }

    except Exception as error:
        st.error(
            f"Analysis failed: {error}"
        )

        st.info(
            "The old /stats call has been removed. "
            "This version queries the official structure "
            "endpoint directly and automatically retries "
            "with the GeoJSON POST method if the "
            "bounding-box GET request fails."
        )

        st.stop()


result = (
    st.session_state.analysis
)


if result is None:
    st.caption(
        "Privacy note: analyzing sends the selected "
        "coordinates to the public data services used "
        "by this application."
    )

    st.stop()


structures = result[
    "structures"
]

fires = result[
    "fires"
]

weather = result[
    "weather"
]

nearest_structure = result[
    "nearest_structure"
]


# =============================================================================
# DISPLAY PROPERTY RESULTS
# =============================================================================

st.divider()

st.subheader(
    "Property screening result"
)


risk_color = {
    "Low": "#16a34a",
    "Moderate": "#eab308",
    "High": "#f97316",
    "Critical": "#dc2626",
}[
    result["level"]
]


st.markdown(
    f"""
    <div style="
        padding: 0.9rem 1rem;
        border-left: 8px solid {risk_color};
        background: rgba(128,128,128,0.1);
        border-radius: 0.5rem;
    ">
        <b>
            Current screening level:
            {result["level"]}
        </b>
        <br>
        <span style="
            font-size: 1.6rem;
            font-weight: 800;
        ">
            {result["score"]:.1f}/100
        </span>
    </div>
    """,
    unsafe_allow_html=True,
)


metrics = st.columns(
    4
)


metrics[0].metric(
    "Nearest NASA detection",
    (
        "None found"
        if result[
            "nearest_fire"
        ]
        is None
        else (
            f"{result['nearest_fire']:.2f} mi"
        )
    ),
)


metrics[1].metric(
    "Temperature",
    shown(
        weather.get(
            "temperature_2m"
        ),
        1,
        " °F",
    ),
)


metrics[2].metric(
    "Humidity",
    shown(
        weather.get(
            "relative_humidity_2m"
        ),
        0,
        "%",
    ),
)


metrics[3].metric(
    "Fire-weather score",
    f"{result['weather_score']:.1f}/100",
)


weather_metrics = st.columns(
    3
)


weather_metrics[0].metric(
    "Wind",
    shown(
        weather.get(
            "wind_speed_10m"
        ),
        1,
        " mph",
    ),
)


weather_metrics[1].metric(
    "Wind gusts",
    shown(
        weather.get(
            "wind_gusts_10m"
        ),
        1,
        " mph",
    ),
)


weather_metrics[2].metric(
    "Precipitation",
    shown(
        weather.get(
            "precipitation"
        ),
        3,
        " in",
    ),
)


# =============================================================================
# NEAREST STRUCTURE
# =============================================================================

st.subheader(
    "Nearest public structure estimate"
)


if nearest_structure:
    columns = st.columns(
        4
    )

    columns[0].metric(
        "Distance from selected point",
        (
            f"{nearest_structure['distance_from_home_miles'] * 5280:.0f} ft"
        ),
    )

    columns[1].metric(
        "Estimated asset value",
        money(
            nearest_structure[
                "estimated_asset_value"
            ]
        ),
    )

    columns[2].metric(
        "Occupancy",
        str(
            nearest_structure.get(
                "occupancy"
            )
            or "Unknown"
        ),
    )

    columns[3].metric(
        "Median year built",
        shown(
            nearest_structure.get(
                "median_year_built"
            ),
            0,
        ),
    )

else:
    st.warning(
        "No National Structure Inventory record "
        "was returned in this radius."
    )


# =============================================================================
# NEIGHBORHOOD EXPOSURE
# =============================================================================

st.subheader(
    "Neighborhood exposure"
)


exposure = st.columns(
    4
)


exposure[0].metric(
    "Structure records",
    f"{len(structures):,}",
)


exposure[1].metric(
    "Estimated asset value",
    (
        money(
            structures[
                "estimated_asset_value"
            ].sum()
        )
        if not structures.empty
        else "$0"
    ),
)


exposure[2].metric(
    "NASA detections",
    f"{len(fires):,}",
)


exposure[3].metric(
    "Structures within 1 mile",
    (
        f"{int((structures['distance_from_home_miles'] <= 1).sum()):,}"
        if not structures.empty
        else "0"
    ),
)


if not key:
    st.warning(
        "No NASA FIRMS key was available, so the "
        "fire-proximity component is unavailable."
    )

elif fires.empty:
    st.info(
        f"NASA returned no {result['product']} "
        f"detections within {result['fire_radius']} miles "
        f"during the latest {result['days']} day(s)."
    )


# =============================================================================
# RESULTS MAP
# =============================================================================

st.subheader(
    "Interactive results map"
)


st_folium(
    make_result_map(
        result["lat"],
        result["lon"],
        float(
            result[
                "structure_radius"
            ]
        ),
        structures,
        fires,
    ),
    height=620,
    use_container_width=True,
    key="result_map",
    returned_objects=[],
)


# =============================================================================
# STRUCTURE TABLE AND DOWNLOAD
# =============================================================================

if not structures.empty:
    st.subheader(
        "Nearby structure records"
    )

    table_columns = [
        "structure_id",
        "occupancy",
        "category",
        "estimated_asset_value",
        "structure_value",
        "contents_value",
        "square_feet",
        "median_year_built",
        "distance_from_home_miles",
        "latitude",
        "longitude",
    ]

    st.dataframe(
        structures[
            table_columns
        ].head(
            1000
        ),
        use_container_width=True,
        hide_index=True,
        column_config={
            "estimated_asset_value": (
                st.column_config.NumberColumn(
                    "Estimated asset value",
                    format="$%.0f",
                )
            ),
            "structure_value": (
                st.column_config.NumberColumn(
                    "Structure value",
                    format="$%.0f",
                )
            ),
            "contents_value": (
                st.column_config.NumberColumn(
                    "Contents value",
                    format="$%.0f",
                )
            ),
            "distance_from_home_miles": (
                st.column_config.NumberColumn(
                    "Distance (mi)",
                    format="%.3f",
                )
            ),
        },
    )

    export = structures.copy()

    export.insert(
        0,
        "selected_location",
        result["label"],
    )

    export.insert(
        1,
        "selected_latitude",
        result["lat"],
    )

    export.insert(
        2,
        "selected_longitude",
        result["lon"],
    )

    export.insert(
        3,
        "screening_score",
        result["score"],
    )

    export.insert(
        4,
        "screening_level",
        result["level"],
    )

    export.insert(
        5,
        "nearest_nasa_detection_miles",
        result["nearest_fire"],
    )

    export.insert(
        6,
        "fire_weather_score",
        result["weather_score"],
    )

    st.download_button(
        "Download complete neighborhood results",
        export.to_csv(
            index=False
        ).encode(
            "utf-8"
        ),
        (
            "wildfire_home_"
            "neighborhood_results.csv"
        ),
        "text/csv",
        use_container_width=True,
    )


# =============================================================================
# METHOD AND LIMITATIONS
# =============================================================================

with st.expander(
    "How the screening score works"
):
    st.markdown(
        """
        - **65% recent-fire proximity:** distance to the nearest NASA FIRMS thermal detection.
        - **35% current fire weather:** humidity, temperature, wind, gusts, and precipitation.

        The score prioritizes review. It is not an ignition probability,
        claim probability, premium recommendation, or deterministic
        wildfire forecast.
        """
    )


st.warning(
    "Decision-support demonstration only. NASA FIRMS "
    "points are satellite thermal detections, not "
    "verified wildfire perimeters. National Structure "
    "Inventory locations and values are modeled public "
    "estimates, not actual policy limits, a property "
    "inspection, or an insurance quote."
  )
