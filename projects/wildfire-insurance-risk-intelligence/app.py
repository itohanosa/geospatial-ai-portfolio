from __future__ import annotations

import io
import math
import os
import re
import time
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
# PUBLIC DATA SERVICES
# =============================================================================

NSI_ROOT = "https://nsi.sec.usace.army.mil/nsiapi"

FIRMS_ROOT = (
    "https://firms.modaps.eosdis.nasa.gov/api/area/csv"
)

NWS_ROOT = "https://api.weather.gov"

CENSUS_GEOCODER = (
    "https://geocoding.geo.census.gov/"
    "geocoder/locations/onelineaddress"
)

PLACE_GEOCODER = (
    "https://geocoding-api.open-meteo.com/v1/search"
)

APP_CONTACT = (
    "https://github.com/itohanosa/"
    "geospatial-ai-portfolio"
)

BASE_HEADERS = {
    "User-Agent": (
        f"WildfireHomeRisk/2.0 ({APP_CONTACT})"
    ),
}

NWS_HEADERS = {
    **BASE_HEADERS,
    "Accept": "application/geo+json",
}

MAX_STRUCTURES = 50_000
MAX_MAP_STRUCTURES = 2_500
MAX_MAP_FIRES = 1_000


# =============================================================================
# MOBILE-FRIENDLY PAGE STYLING
# =============================================================================

st.markdown(
    """
    <style>
    .block-container {
        padding-top: 0.8rem;
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

    @media (max-width: 700px) {
        .block-container {
            padding-left: 0.55rem;
            padding-right: 0.55rem;
        }

        h1 {
            font-size: 1.75rem !important;
        }

        h2 {
            font-size: 1.3rem !important;
        }

        h3 {
            font-size: 1.1rem !important;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# =============================================================================
# GENERAL HELPERS
# =============================================================================


def saved_firms_key() -> str:
    """
    Read the NASA FIRMS key without exposing it
    in the public user interface.
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


def request_json(
    url: str,
    params: dict[str, Any] | None = None,
    method: str = "GET",
    json_body: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 60,
    attempts: int = 3,
) -> Any:
    """
    Request JSON with short retries for rate limits
    and temporary server errors.
    """

    merged_headers = {
        **BASE_HEADERS,
        **(headers or {}),
    }

    last_error: Exception | None = None

    for attempt in range(
        attempts
    ):
        try:
            response = requests.request(
                method=method,
                url=url,
                params=params,
                json=json_body,
                headers=merged_headers,
                timeout=timeout,
            )

            if (
                response.status_code == 429
                or response.status_code >= 500
            ):
                if attempt < attempts - 1:
                    retry_after = (
                        response.headers.get(
                            "Retry-After",
                            "",
                        )
                    )

                    wait_seconds = (
                        int(
                            retry_after
                        )
                        if retry_after.isdigit()
                        else 2**attempt
                    )

                    time.sleep(
                        min(
                            wait_seconds,
                            8,
                        )
                    )

                    continue

            response.raise_for_status()

            return response.json()

        except Exception as error:
            last_error = error

            if attempt < attempts - 1:
                time.sleep(
                    2**attempt
                )

    raise RuntimeError(
        str(
            last_error
            or "The data request failed."
        )
    )


def number(
    value: Any,
    default: float = np.nan,
) -> float:
    """
    Convert a value to float without raising
    an exception.
    """

    converted = pd.to_numeric(
        value,
        errors="coerce",
    )

    if pd.isna(
        converted
    ):
        return default

    return float(
        converted
    )


def shown(
    value: Any,
    decimals: int = 1,
    suffix: str = "",
) -> str:
    """
    Format a possibly missing numeric value.
    """

    converted = number(
        value
    )

    if not np.isfinite(
        converted
    ):
        return "Unavailable"

    return (
        f"{converted:.{decimals}f}"
        f"{suffix}"
    )


def money(
    value: Any,
) -> str:
    """
    Format an estimated monetary value.
    """

    converted = number(
        value,
        0.0,
    )

    if converted >= 1_000_000_000:
        return (
            f"${converted / 1_000_000_000:.2f}B"
        )

    if converted >= 1_000_000:
        return (
            f"${converted / 1_000_000:.2f}M"
        )

    return f"${converted:,.0f}"


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
    Geocode a United States street address,
    city, community, or ZIP code.
    """

    query = query.strip()

    if not query:
        raise ValueError(
            "Enter a U.S. address, city, "
            "or ZIP code."
        )

    # Attempt an exact street-address match first.
    try:
        census_data = request_json(
            CENSUS_GEOCODER,
            params={
                "address": query,
                "benchmark": (
                    "Public_AR_Current"
                ),
                "format": "json",
            },
            timeout=45,
        )

        matches = (
            census_data
            .get(
                "result",
                {},
            )
            .get(
                "addressMatches",
                [],
            )
        )

        if matches:
            match = matches[
                0
            ]

            coordinates = (
                match.get(
                    "coordinates",
                    {},
                )
            )

            return {
                "lat": float(
                    coordinates[
                        "y"
                    ]
                ),
                "lon": float(
                    coordinates[
                        "x"
                    ]
                ),
                "label": match.get(
                    "matchedAddress",
                    query,
                ),
                "zoom": 18,
                "source": (
                    "U.S. Census Geocoder"
                ),
            }

    except Exception:
        pass

    # Fall back to a city, place, or ZIP search.
    place_data = request_json(
        PLACE_GEOCODER,
        params={
            "name": query,
            "count": 10,
            "language": "en",
            "format": "json",
        },
        timeout=30,
    )

    results = place_data.get(
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
            "No location was found. Try a complete "
            "street address or a city and state."
        )

    row = rows[
        0
    ]

    label = ", ".join(
        str(
            row.get(
                field
            )
        )
        for field in [
            "name",
            "admin2",
            "admin1",
            "country",
        ]
        if row.get(
            field
        )
    )

    return {
        "lat": float(
            row[
                "latitude"
            ]
        ),
        "lon": float(
            row[
                "longitude"
            ]
        ),
        "label": label,
        "zoom": 14,
        "source": (
            "Place geocoder"
        ),
    }


# =============================================================================
# GEOMETRY AND DISTANCE
# =============================================================================


def query_geometries(
    lat: float,
    lon: float,
    miles: float,
) -> tuple[
    str,
    str,
    dict[str, Any],
]:
    """
    Create National Structure Inventory and
    NASA FIRMS query geometries.
    """

    latitude_change = (
        miles
        / 69.0
    )

    longitude_change = (
        miles
        / max(
            69.172
            * math.cos(
                math.radians(
                    lat
                )
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
        "type": (
            "FeatureCollection"
        ),
        "features": [
            {
                "type": (
                    "Feature"
                ),
                "geometry": {
                    "type": (
                        "Polygon"
                    ),
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


def distances_miles(
    origin_lat: float,
    origin_lon: float,
    target_latitudes: np.ndarray,
    target_longitudes: np.ndarray,
) -> np.ndarray:
    """
    Calculate great-circle distance in miles
    from one point to many points.
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
        origin_lat
    )

    longitude_1 = math.radians(
        origin_lon
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
    Convert a National Structure Inventory
    GeoJSON response into a table.
    """

    rows: list[
        dict[str, Any]
    ] = []

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
                "structure_id": (
                    properties.get(
                        "fd_id"
                    )
                ),
                "building_id": (
                    properties.get(
                        "bid"
                    )
                ),
                "latitude": (
                    coordinates[
                        1
                    ]
                ),
                "longitude": (
                    coordinates[
                        0
                    ]
                ),
                "occupancy": (
                    properties.get(
                        "occtype",
                        "Unknown",
                    )
                ),
                "category": (
                    properties.get(
                        "st_damcat",
                        "Unknown",
                    )
                ),
                "square_feet": (
                    properties.get(
                        "sqft"
                    )
                ),
                "stories": (
                    properties.get(
                        "num_story"
                    )
                ),
                "median_year_built": (
                    properties.get(
                        "med_yr_blt"
                    )
                ),
                "structure_value": (
                    properties.get(
                        "val_struct"
                    )
                ),
                "contents_value": (
                    properties.get(
                        "val_cont"
                    )
                ),
                "vehicle_value": (
                    properties.get(
                        "val_vehic"
                    )
                ),
                "ground_elevation_m": (
                    properties.get(
                        "ground_elv"
                    )
                ),
                "footprint_source": (
                    properties.get(
                        "ftprntsrc"
                    )
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
        "ground_elevation_m",
    ]

    for column in numeric_columns:
        dataframe[
            column
        ] = pd.to_numeric(
            dataframe[
                column
            ],
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
        .fillna(
            0
        )
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
        dataframe
        .dropna(
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
    Retrieve structures using a bounding-box
    GET request, with a GeoJSON POST fallback.
    """

    endpoint = (
        f"{NSI_ROOT}/structures"
    )

    errors: list[
        str
    ] = []

    try:
        response = requests.get(
            endpoint,
            params={
                "bbox": nsi_bbox,
                "fmt": "fc",
            },
            headers=BASE_HEADERS,
            timeout=180,
        )

        if response.ok:
            return parse_structures(
                response.json()
            )

        errors.append(
            "GET returned HTTP "
            f"{response.status_code}"
        )

    except Exception as error:
        errors.append(
            f"GET failed: {error}"
        )

    try:
        response = requests.post(
            endpoint,
            params={
                "fmt": "fc",
            },
            json=geojson,
            headers={
                **BASE_HEADERS,
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

        errors.append(
            "POST returned HTTP "
            f"{response.status_code}"
        )

    except Exception as error:
        errors.append(
            f"POST failed: {error}"
        )

    raise RuntimeError(
        " | ".join(
            errors
        )
    )


# =============================================================================
# NOAA NATIONAL WEATHER SERVICE
# =============================================================================


def empty_weather(
    message: str = (
        "Weather is unavailable."
    ),
) -> dict[str, Any]:
    """
    Create a consistent missing-weather result.
    """

    return {
        "temperature_f": np.nan,
        "humidity_pct": np.nan,
        "precipitation_in": np.nan,
        "wind_mph": np.nan,
        "gust_mph": np.nan,
        "time": None,
        "source": (
            "NOAA National Weather Service"
        ),
        "summary": (
            "Unavailable"
        ),
        "available": False,
        "warning": message,
    }


def quantitative_value(
    properties: dict[str, Any],
    name: str,
) -> tuple[
    float,
    str,
]:
    """
    Read a National Weather Service
    quantitative-value object.
    """

    item = (
        properties.get(
            name
        )
        or {}
    )

    return (
        number(
            item.get(
                "value"
            )
        ),
        str(
            item.get(
                "unitCode",
                "",
            )
        ),
    )


def temperature_to_f(
    value: float,
    unit: str,
) -> float:
    """
    Convert Celsius temperatures to Fahrenheit.
    """

    if not np.isfinite(
        value
    ):
        return np.nan

    lowered = unit.lower()

    if "degc" in lowered:
        return (
            value
            * 9
            / 5
            + 32
        )

    return value


def speed_to_mph(
    value: float,
    unit: str,
) -> float:
    """
    Convert common wind-speed units to miles
    per hour.
    """

    if not np.isfinite(
        value
    ):
        return np.nan

    lowered = unit.lower()

    if (
        "km_h-1" in lowered
        or "km/h" in lowered
    ):
        return (
            value
            * 0.621371
        )

    if (
        "m_s-1" in lowered
        or "m/s" in lowered
    ):
        return (
            value
            * 2.23694
        )

    if (
        "kt" in lowered
        or "knot" in lowered
    ):
        return (
            value
            * 1.15078
        )

    return value


def precipitation_to_inches(
    value: float,
    unit: str,
) -> float:
    """
    Convert precipitation to inches.
    """

    if not np.isfinite(
        value
    ):
        return np.nan

    lowered = unit.lower()

    if (
        "unit:mm" in lowered
        or lowered.endswith(
            ":mm"
        )
    ):
        return (
            value
            / 25.4
        )

    if (
        "unit:cm" in lowered
        or lowered.endswith(
            ":cm"
        )
    ):
        return (
            value
            / 2.54
        )

    if (
        "unit:m" in lowered
        or lowered.endswith(
            ":m"
        )
    ):
        return (
            value
            * 39.3701
        )

    return value


@st.cache_data(
    ttl=900,
    show_spinner=False,
)
def get_weather(
    lat: float,
    lon: float,
) -> dict[str, Any]:
    """
    Retrieve a nearby official weather observation.

    If the observation is unavailable, use the
    official hourly forecast.
    """

    rounded_lat = round(
        float(
            lat
        ),
        4,
    )

    rounded_lon = round(
        float(
            lon
        ),
        4,
    )

    try:
        point_data = request_json(
            (
                f"{NWS_ROOT}/points/"
                f"{rounded_lat},"
                f"{rounded_lon}"
            ),
            headers=NWS_HEADERS,
            timeout=45,
        )

        point_properties = (
            point_data.get(
                "properties"
            )
            or {}
        )

    except Exception as error:
        return empty_weather(
            "Point forecast lookup failed: "
            f"{error}"
        )

    observation_warning = ""

    try:
        stations_url = (
            point_properties.get(
                "observationStations"
            )
        )

        if not stations_url:
            raise RuntimeError(
                "No observation-station link "
                "was returned."
            )

        station_data = request_json(
            stations_url,
            headers=NWS_HEADERS,
            timeout=45,
        )

        station_features = (
            station_data.get(
                "features"
            )
            or []
        )

        if not station_features:
            raise RuntimeError(
                "No nearby observation station "
                "was returned."
            )

        station_url = (
            station_features[
                0
            ].get(
                "id"
            )
        )

        if not station_url:
            raise RuntimeError(
                "The nearest station record "
                "had no URL."
            )

        observation = request_json(
            (
                f"{station_url}/"
                "observations/latest"
            ),
            headers=NWS_HEADERS,
            timeout=45,
        )

        properties = (
            observation.get(
                "properties"
            )
            or {}
        )

        (
            temperature_value,
            temperature_unit,
        ) = quantitative_value(
            properties,
            "temperature",
        )

        (
            humidity_value,
            _,
        ) = quantitative_value(
            properties,
            "relativeHumidity",
        )

        (
            wind_value,
            wind_unit,
        ) = quantitative_value(
            properties,
            "windSpeed",
        )

        (
            gust_value,
            gust_unit,
        ) = quantitative_value(
            properties,
            "windGust",
        )

        (
            rain_value,
            rain_unit,
        ) = quantitative_value(
            properties,
            "precipitationLastHour",
        )

        result = {
            "temperature_f": (
                temperature_to_f(
                    temperature_value,
                    temperature_unit,
                )
            ),
            "humidity_pct": (
                humidity_value
            ),
            "precipitation_in": (
                precipitation_to_inches(
                    rain_value,
                    rain_unit,
                )
            ),
            "wind_mph": (
                speed_to_mph(
                    wind_value,
                    wind_unit,
                )
            ),
            "gust_mph": (
                speed_to_mph(
                    gust_value,
                    gust_unit,
                )
            ),
            "time": (
                properties.get(
                    "timestamp"
                )
            ),
            "source": (
                "NOAA National Weather Service "
                "observation"
            ),
            "summary": str(
                properties.get(
                    "textDescription"
                )
                or "Observed conditions"
            ),
            "available": False,
            "warning": "",
        }

        result[
            "available"
        ] = any(
            np.isfinite(
                number(
                    result[
                        field
                    ]
                )
            )
            for field in [
                "temperature_f",
                "humidity_pct",
                "wind_mph",
            ]
        )

        if result[
            "available"
        ]:
            return result

        raise RuntimeError(
            "The nearest observation contained "
            "no usable values."
        )

    except Exception as error:
        observation_warning = str(
            error
        )

    try:
        forecast_url = (
            point_properties.get(
                "forecastHourly"
            )
        )

        if not forecast_url:
            raise RuntimeError(
                "No hourly forecast link "
                "was returned."
            )

        forecast = request_json(
            forecast_url,
            headers=NWS_HEADERS,
            timeout=45,
        )

        periods = (
            forecast.get(
                "properties",
                {},
            ).get(
                "periods",
                [],
            )
        )

        if not periods:
            raise RuntimeError(
                "The hourly forecast contained "
                "no periods."
            )

        period = periods[
            0
        ]

        temperature = number(
            period.get(
                "temperature"
            )
        )

        if str(
            period.get(
                "temperatureUnit",
                "F",
            )
        ).upper() == "C":
            temperature = (
                temperature_to_f(
                    temperature,
                    "degC",
                )
            )

        humidity = number(
            (
                period.get(
                    "relativeHumidity"
                )
                or {}
            ).get(
                "value"
            )
        )

        wind_values = [
            float(
                value
            )
            for value in re.findall(
                r"\d+(?:\.\d+)?",
                str(
                    period.get(
                        "windSpeed",
                        "",
                    )
                ),
            )
        ]

        wind_speed = (
            max(
                wind_values
            )
            if wind_values
            else np.nan
        )

        result = {
            "temperature_f": (
                temperature
            ),
            "humidity_pct": (
                humidity
            ),
            "precipitation_in": (
                np.nan
            ),
            "wind_mph": (
                wind_speed
            ),
            "gust_mph": (
                np.nan
            ),
            "time": (
                period.get(
                    "startTime"
                )
            ),
            "source": (
                "NOAA National Weather Service "
                "hourly forecast"
            ),
            "summary": str(
                period.get(
                    "shortForecast"
                )
                or "Hourly forecast"
            ),
            "available": False,
            "warning": (
                "The nearest station observation "
                "was unavailable: "
                f"{observation_warning}"
            ),
        }

        result[
            "available"
        ] = any(
            np.isfinite(
                number(
                    result[
                        field
                    ]
                )
            )
            for field in [
                "temperature_f",
                "humidity_pct",
                "wind_mph",
            ]
        )

        return result

    except Exception as error:
        return empty_weather(
            "Observation failed: "
            f"{observation_warning}; "
            "hourly forecast failed: "
            f"{error}"
        )


@st.cache_data(
    ttl=300,
    show_spinner=False,
)
def get_alerts(
    lat: float,
    lon: float,
) -> pd.DataFrame:
    """
    Retrieve active National Weather Service
    alerts for the selected point.
    """

    data = request_json(
        f"{NWS_ROOT}/alerts/active",
        params={
            "point": (
                f"{round(lat, 4)},"
                f"{round(lon, 4)}"
            )
        },
        headers=NWS_HEADERS,
        timeout=45,
    )

    rows: list[
        dict[str, Any]
    ] = []

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

        rows.append(
            {
                "event": (
                    properties.get(
                        "event"
                    )
                ),
                "severity": (
                    properties.get(
                        "severity"
                    )
                ),
                "urgency": (
                    properties.get(
                        "urgency"
                    )
                ),
                "certainty": (
                    properties.get(
                        "certainty"
                    )
                ),
                "headline": (
                    properties.get(
                        "headline"
                    )
                ),
                "description": (
                    properties.get(
                        "description"
                    )
                ),
                "instruction": (
                    properties.get(
                        "instruction"
                    )
                ),
                "onset": (
                    properties.get(
                        "onset"
                    )
                ),
                "expires": (
                    properties.get(
                        "expires"
                    )
                ),
            }
        )

    return pd.DataFrame(
        rows
    )


# =============================================================================
# NASA FIRMS ACTIVE-FIRE DATA
# =============================================================================


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
    Retrieve recent NASA FIRMS active-fire
    and thermal-anomaly detections.
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

    last_error: Exception | None = None

    for attempt in range(
        3
    ):
        try:
            response = requests.get(
                url,
                headers=BASE_HEADERS,
                timeout=120,
            )

            if (
                response.status_code == 429
                or response.status_code >= 500
            ):
                if attempt < 2:
                    time.sleep(
                        2**attempt
                    )

                    continue

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
                    "NASA FIRMS did not return "
                    "coordinate fields."
                )

            for column in [
                "latitude",
                "longitude",
                "frp",
            ]:
                if column in (
                    dataframe.columns
                ):
                    dataframe[
                        column
                    ] = pd.to_numeric(
                        dataframe[
                            column
                        ],
                        errors="coerce",
                    )

            if "frp" not in dataframe:
                dataframe[
                    "frp"
                ] = np.nan

            if "confidence" not in dataframe:
                dataframe[
                    "confidence"
                ] = "Unknown"

            return (
                dataframe
                .dropna(
                    subset=[
                        "latitude",
                        "longitude",
                    ]
                )
                .reset_index(
                    drop=True
                )
            )

        except Exception as error:
            last_error = error

            if attempt < 2:
                time.sleep(
                    2**attempt
                )

    raise RuntimeError(
        str(
            last_error
            or "NASA FIRMS request failed."
        )
    )


# =============================================================================
# TRANSPARENT SCREENING SCORE
# =============================================================================


def fire_weather_score(
    weather: dict[str, Any],
) -> float:
    """
    Calculate a transparent 0-100
    current fire-weather score.
    """

    if not weather.get(
        "available",
        False,
    ):
        return 0.0

    components: list[
        tuple[
            float,
            float,
        ]
    ] = []

    humidity = number(
        weather.get(
            "humidity_pct"
        )
    )

    if np.isfinite(
        humidity
    ):
        components.append(
            (
                float(
                    np.clip(
                        (
                            55
                            - humidity
                        )
                        / 45,
                        0,
                        1,
                    )
                )
                * 35,
                35,
            )
        )

    wind = number(
        weather.get(
            "wind_mph"
        )
    )

    if np.isfinite(
        wind
    ):
        components.append(
            (
                float(
                    np.clip(
                        wind
                        / 30,
                        0,
                        1,
                    )
                )
                * 25,
                25,
            )
        )

    gust = number(
        weather.get(
            "gust_mph"
        )
    )

    if np.isfinite(
        gust
    ):
        components.append(
            (
                float(
                    np.clip(
                        gust
                        / 50,
                        0,
                        1,
                    )
                )
                * 20,
                20,
            )
        )

    temperature = number(
        weather.get(
            "temperature_f"
        )
    )

    if np.isfinite(
        temperature
    ):
        components.append(
            (
                float(
                    np.clip(
                        (
                            temperature
                            - 60
                        )
                        / 40,
                        0,
                        1,
                    )
                )
                * 20,
                20,
            )
        )

    if not components:
        return 0.0

    score = (
        sum(
            value
            for value, _ in components
        )
        / sum(
            weight
            for _, weight in components
        )
        * 100
    )

    precipitation = number(
        weather.get(
            "precipitation_in"
        )
    )

    if np.isfinite(
        precipitation
    ):
        score -= (
            float(
                np.clip(
                    precipitation
                    / 0.15,
                    0,
                    1,
                )
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
    Convert distance to the nearest NASA
    detection into a screening score.
    """

    if (
        distance is None
        or not np.isfinite(
            distance
        )
    ):
        return 0.0

    if distance <= 1:
        return 100.0

    if distance <= 3:
        return 90.0

    if distance <= 5:
        return 80.0

    if distance <= 10:
        return 65.0

    if distance <= 25:
        return 40.0

    if distance <= 50:
        return 20.0

    return 0.0


def screening_level(
    score: float,
) -> str:
    """
    Convert the current screening score
    to a descriptive category.
    """

    if score >= 80:
        return "Critical"

    if score >= 60:
        return "High"

    if score >= 35:
        return "Moderate"

    return "Low"


# =============================================================================
# MAPS
# =============================================================================


def add_mobile_map_css(
    map_object: folium.Map,
) -> None:
    """
    Reduce map control and attribution size
    on phone screens.
    """

    map_object.get_root().header.add_child(
        folium.Element(
            """
            <style>
            .leaflet-control-attribution,
            .leaflet-control-attribution a {
                font-size: 8px !important;
                line-height: 10px !important;
            }

            .leaflet-control-attribution {
                max-width: 72vw !important;
                white-space: normal !important;
                padding: 1px 3px !important;
                background:
                    rgba(255,255,255,0.78)
                    !important;
            }

            .leaflet-control-layers {
                font-size: 12px !important;
            }
            </style>
            """
        )
    )


def add_base_maps(
    map_object: folium.Map,
) -> None:
    """
    Add street and satellite background maps.
    """

    folium.TileLayer(
        "OpenStreetMap",
        name="Street map",
        control=True,
    ).add_to(
        map_object
    )

    folium.TileLayer(
        (
            "https://server.arcgisonline.com/"
            "ArcGIS/rest/services/"
            "World_Imagery/MapServer/"
            "tile/{z}/{y}/{x}"
        ),
        attr="Esri World Imagery",
        name="Satellite",
        control=True,
    ).add_to(
        map_object
    )


def selection_map(
    lat: float,
    lon: float,
    zoom: int,
    selected: bool,
) -> folium.Map:
    """
    Create the property-selection map.
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

    add_mobile_map_css(
        result
    )

    add_base_maps(
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


def results_map(
    lat: float,
    lon: float,
    structure_radius_miles: float,
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

    add_mobile_map_css(
        result
    )

    add_base_maps(
        result
    )

    folium.Circle(
        [
            lat,
            lon,
        ],
        radius=(
            structure_radius_miles
            * 1609.344
        ),
        color="#2563eb",
        weight=2,
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
                "Public structure records"
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
                color="#b45309",
                weight=1,
                fill=True,
                fill_color="#f59e0b",
                fill_opacity=0.85,
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
                "NASA fire detections"
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
                weight=2,
                fill=True,
                fill_color="#ef4444",
                fill_opacity=0.9,
                tooltip=(
                    "NASA thermal detection | "
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


def initialize_session() -> None:
    """
    Initialize the map and analysis session.
    """

    defaults = {
        "lat": 39.8283,
        "lon": -98.5795,
        "label": "United States",
        "zoom": 4,
        "selected": False,
        "selection_map_version": 0,
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


initialize_session()


# =============================================================================
# USER INTERFACE
# =============================================================================

st.title(
    "🔥 Wildfire Home & Neighborhood Intelligence"
)

st.caption(
    "Search a U.S. address, zoom to the exact "
    "property, tap the roof, and analyze real "
    "public structure estimates, official weather, "
    "weather alerts, and recent NASA fire detections."
)


with st.expander(
    "Search and analysis settings",
    expanded=True,
):
    query = st.text_input(
        "Full U.S. address, city, or ZIP code",
        value="Paradise, California",
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
                found[
                    "lat"
                ]
            )

            st.session_state.lon = (
                found[
                    "lon"
                ]
            )

            st.session_state.label = (
                found[
                    "label"
                ]
            )

            st.session_state.zoom = (
                found[
                    "zoom"
                ]
            )

            st.session_state.selected = (
                True
            )

            st.session_state.analysis = (
                None
            )

            st.session_state[
                "selection_map_version"
            ] += 1

            st.rerun()

        except Exception as error:
            st.error(
                f"Search failed: {error}"
            )

    setting_columns = st.columns(
        2
    )

    with setting_columns[
        0
    ]:
        structure_radius = (
            st.select_slider(
                "Structure exposure radius (miles)",
                options=[
                    0.10,
                    0.25,
                    0.50,
                ],
                value=0.25,
            )
        )

        days = st.slider(
            "Recent NASA detection window (days)",
            min_value=1,
            max_value=5,
            value=2,
        )

    with setting_columns[
        1
    ]:
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

        product = st.selectbox(
            "NASA satellite product",
            [
                "VIIRS_SNPP_NRT",
                "VIIRS_NOAA20_NRT",
                "VIIRS_NOAA21_NRT",
                "MODIS_NRT",
            ],
        )

    configured_key = (
        saved_firms_key()
    )

    if configured_key:
        st.success(
            "NASA FIRMS connection is "
            "securely configured."
        )

        entered_key = ""

    else:
        entered_key = st.text_input(
            "NASA FIRMS MAP_KEY",
            type="password",
            help=(
                "Enter your own NASA key. "
                "It is not saved to GitHub."
            ),
        )

        st.warning(
            "No NASA key is configured in "
            "Streamlit Secrets. The app can "
            "still return structures, weather, "
            "and official alerts."
        )

    active_key = (
        configured_key
        or entered_key.strip()
    )


st.info(
    "Switch the map to **Satellite**, zoom in, "
    "and tap the center of the roof. The blue "
    "marker is the point that will be analyzed."
)


st.subheader(
    "Select the exact home or property"
)


selection = st_folium(
    selection_map(
        st.session_state.lat,
        st.session_state.lon,
        st.session_state.zoom,
        st.session_state.selected,
    ),
    height=520,
    use_container_width=True,
    key=(
        "selection_map_"
        f"{st.session_state.selection_map_version}"
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
        clicked[
            "lat"
        ]
    )

    new_longitude = float(
        clicked[
            "lng"
        ]
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
        "Search for a location or tap "
        "the map before analyzing."
    )


run_analysis = st.button(
    "Analyze this home/property",
    type="primary",
    use_container_width=True,
    disabled=(
        not st.session_state.selected
    ),
)


# =============================================================================
# ANALYSIS
# =============================================================================

if run_analysis:
    latitude = float(
        st.session_state.lat
    )

    longitude = float(
        st.session_state.lon
    )

    (
        nsi_bbox,
        _,
        nsi_geojson,
    ) = query_geometries(
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
    ) = query_geometries(
        latitude,
        longitude,
        float(
            fire_radius
        ),
    )

    source_messages: dict[
        str,
        str,
    ] = {}

    with st.spinner(
        "Retrieving public structure records..."
    ):
        try:
            structures = get_structures(
                nsi_bbox,
                nsi_geojson,
            )

            source_messages[
                "structures"
            ] = "available"

        except Exception as error:
            structures = pd.DataFrame()

            source_messages[
                "structures"
            ] = str(
                error
            )

    if len(
        structures
    ) > MAX_STRUCTURES:
        st.error(
            "The selected area returned "
            f"{len(structures):,} structures. "
            "Choose a smaller structure radius."
        )

        st.stop()

    with st.spinner(
        "Retrieving official weather and alerts..."
    ):
        weather = get_weather(
            latitude,
            longitude,
        )

        try:
            alerts = get_alerts(
                latitude,
                longitude,
            )

            source_messages[
                "alerts"
            ] = "available"

        except Exception as error:
            alerts = pd.DataFrame()

            source_messages[
                "alerts"
            ] = str(
                error
            )

    with st.spinner(
        "Retrieving recent NASA "
        "fire detections..."
    ):
        if active_key:
            try:
                fires = get_fires(
                    active_key,
                    product,
                    firms_bbox,
                    days,
                )

                source_messages[
                    "fires"
                ] = "available"

            except Exception as error:
                fires = pd.DataFrame()

                source_messages[
                    "fires"
                ] = str(
                    error
                )

        else:
            fires = pd.DataFrame()

            source_messages[
                "fires"
            ] = (
                "NASA FIRMS key was not provided."
            )

    nearest_structure: (
        dict[str, Any]
        | None
    ) = None

    if not structures.empty:
        structures = (
            structures.copy()
        )

        structures[
            "distance_from_home_miles"
        ] = distances_miles(
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
            structures
            .sort_values(
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

    nearest_fire: (
        float
        | None
    ) = None

    if not fires.empty:
        fires = fires.copy()

        fires[
            "distance_from_home_miles"
        ] = distances_miles(
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
            fires
            .sort_values(
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

    weather_score = (
        fire_weather_score(
            weather
        )
    )

    fire_score = proximity_score(
        nearest_fire
    )

    if weather.get(
        "available",
        False,
    ):
        watch_score = round(
            0.65
            * fire_score
            + 0.35
            * weather_score,
            1,
        )

    else:
        watch_score = round(
            fire_score,
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
        "alerts": alerts,
        "weather_score": (
            weather_score
        ),
        "fire_score": (
            fire_score
        ),
        "watch_score": (
            watch_score
        ),
        "level": screening_level(
            watch_score
        ),
        "source_messages": (
            source_messages
        ),
    }


result = (
    st.session_state.analysis
)


if result is None:
    st.caption(
        "Privacy note: analysis sends the "
        "selected coordinates to the public "
        "data services used by this application."
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

alerts = result[
    "alerts"
]

nearest_structure = result[
    "nearest_structure"
]

source_messages = result[
    "source_messages"
]


# =============================================================================
# RESULTS
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
    result[
        "level"
    ]
]


st.markdown(
    f"""
    <div style="
        padding: 0.9rem 1rem;
        border-left: 8px solid {risk_color};
        background: rgba(128,128,128,0.10);
        border-radius: 0.5rem;
        margin-bottom: 0.8rem;
    ">
        <b>
            Current screening level:
            {result["level"]}
        </b>
        <br>
        <span style="
            font-size:1.65rem;
            font-weight:800;
        ">
            {result["watch_score"]:.1f}/100
        </span>
    </div>
    """,
    unsafe_allow_html=True,
)


primary_metrics = st.columns(
    4
)


primary_metrics[
    0
].metric(
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


primary_metrics[
    1
].metric(
    "Temperature",
    shown(
        weather.get(
            "temperature_f"
        ),
        1,
        " °F",
    ),
)


primary_metrics[
    2
].metric(
    "Humidity",
    shown(
        weather.get(
            "humidity_pct"
        ),
        0,
        "%",
    ),
)


primary_metrics[
    3
].metric(
    "Fire-weather score",
    (
        f"{result['weather_score']:.1f}/100"
        if weather.get(
            "available",
            False,
        )
        else "Unavailable"
    ),
)


weather_metrics = st.columns(
    3
)


weather_metrics[
    0
].metric(
    "Wind",
    shown(
        weather.get(
            "wind_mph"
        ),
        1,
        " mph",
    ),
)


weather_metrics[
    1
].metric(
    "Wind gusts",
    shown(
        weather.get(
            "gust_mph"
        ),
        1,
        " mph",
    ),
)


weather_metrics[
    2
].metric(
    "Precipitation last hour",
    shown(
        weather.get(
            "precipitation_in"
        ),
        3,
        " in",
    ),
)


if weather.get(
    "available",
    False,
):
    st.caption(
        "Weather source: "
        f"{weather.get('source')} | "
        "Condition: "
        f"{weather.get('summary')} | "
        "Time: "
        f"{weather.get('time') or 'not supplied'}"
    )

    if weather.get(
        "warning"
    ):
        st.caption(
            str(
                weather.get(
                    "warning"
                )
            )
        )

else:
    st.warning(
        "Official weather is temporarily "
        "unavailable. The current screening "
        "score therefore uses NASA fire "
        "proximity only."
    )

    if weather.get(
        "warning"
    ):
        st.caption(
            str(
                weather.get(
                    "warning"
                )
            )
        )


if source_messages.get(
    "structures"
) != "available":
    st.warning(
        "National Structure Inventory data "
        "could not be retrieved: "
        f"{source_messages.get('structures')}"
    )


if source_messages.get(
    "fires"
) != "available":
    st.warning(
        "NASA FIRMS data could not be retrieved: "
        f"{source_messages.get('fires')}"
    )


if source_messages.get(
    "alerts"
) != "available":
    st.caption(
        "National Weather Service alerts "
        "could not be retrieved: "
        f"{source_messages.get('alerts')}"
    )


# =============================================================================
# OFFICIAL ALERTS
# =============================================================================

st.subheader(
    "Official weather alerts"
)


if alerts.empty:
    st.success(
        "No active National Weather Service "
        "alerts were returned for this point."
    )

else:
    for alert in alerts.head(
        8
    ).to_dict(
        "records"
    ):
        event = str(
            alert.get(
                "event"
            )
            or "Weather alert"
        )

        severity = str(
            alert.get(
                "severity"
            )
            or "Unknown severity"
        )

        with st.expander(
            f"{event} — {severity}"
        ):
            if alert.get(
                "headline"
            ):
                st.markdown(
                    f"**{alert['headline']}**"
                )

            if alert.get(
                "description"
            ):
                st.write(
                    alert[
                        "description"
                    ]
                )

            if alert.get(
                "instruction"
            ):
                st.markdown(
                    "**Instructions**"
                )

                st.write(
                    alert[
                        "instruction"
                    ]
                )

            st.caption(
                "Urgency: "
                f"{alert.get('urgency') or 'Unknown'} | "
                "Certainty: "
                f"{alert.get('certainty') or 'Unknown'} | "
                "Expires: "
                f"{alert.get('expires') or 'Not supplied'}"
            )


# =============================================================================
# NEAREST STRUCTURE
# =============================================================================

st.subheader(
    "Nearest public structure estimate"
)


if nearest_structure:
    structure_metrics = st.columns(
        4
    )

    structure_metrics[
        0
    ].metric(
        "Distance from selected point",
        (
            f"{nearest_structure['distance_from_home_miles'] * 5280:.0f} ft"
        ),
    )

    structure_metrics[
        1
    ].metric(
        "Estimated asset value",
        money(
            nearest_structure.get(
                "estimated_asset_value"
            )
        ),
    )

    structure_metrics[
        2
    ].metric(
        "Occupancy",
        str(
            nearest_structure.get(
                "occupancy"
            )
            or "Unknown"
        ),
    )

    structure_metrics[
        3
    ].metric(
        "Median year built",
        shown(
            nearest_structure.get(
                "median_year_built"
            ),
            0,
        ),
    )

else:
    st.info(
        "No National Structure Inventory "
        "record was returned within the "
        "selected structure radius."
    )


# =============================================================================
# NEIGHBORHOOD EXPOSURE
# =============================================================================

st.subheader(
    "Neighborhood exposure"
)


exposure_metrics = st.columns(
    4
)


exposure_metrics[
    0
].metric(
    "Structure records",
    f"{len(structures):,}",
)


exposure_metrics[
    1
].metric(
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


exposure_metrics[
    2
].metric(
    "NASA detections",
    f"{len(fires):,}",
)


exposure_metrics[
    3
].metric(
    "Structures within 0.25 mi",
    (
        f"{int((structures['distance_from_home_miles'] <= 0.25).sum()):,}"
        if not structures.empty
        else "0"
    ),
)


if (
    active_key
    and fires.empty
    and source_messages.get(
        "fires"
    )
    == "available"
):
    st.info(
        "NASA returned no "
        f"{result['product']} detections "
        f"within {result['fire_radius']} miles "
        "during the latest "
        f"{result['days']} day(s)."
    )


# =============================================================================
# RESULTS MAP
# =============================================================================

st.subheader(
    "Interactive results map"
)


st_folium(
    results_map(
        result[
            "lat"
        ],
        result[
            "lon"
        ],
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
    key="results_map",
    returned_objects=[],
)


# =============================================================================
# STRUCTURE TABLE AND DOWNLOAD
# =============================================================================

if not structures.empty:
    st.subheader(
        "Nearby public structure records"
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

    structure_export = (
        structures.copy()
    )

    structure_export.insert(
        0,
        "selected_location",
        result[
            "label"
        ],
    )

    structure_export.insert(
        1,
        "selected_latitude",
        result[
            "lat"
        ],
    )

    structure_export.insert(
        2,
        "selected_longitude",
        result[
            "lon"
        ],
    )

    structure_export.insert(
        3,
        "screening_score",
        result[
            "watch_score"
        ],
    )

    structure_export.insert(
        4,
        "screening_level",
        result[
            "level"
        ],
    )

    structure_export.insert(
        5,
        "nearest_nasa_detection_miles",
        result[
            "nearest_fire"
        ],
    )

    structure_export.insert(
        6,
        "fire_weather_score",
        result[
            "weather_score"
        ],
    )

    st.download_button(
        "Download complete neighborhood results",
        structure_export.to_csv(
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
# FIRE TABLE AND DOWNLOAD
# =============================================================================

if not fires.empty:
    st.subheader(
        "Recent NASA detections"
    )

    fire_columns = [
        column
        for column in [
            "acq_date",
            "acq_time",
            "satellite",
            "instrument",
            "confidence",
            "frp",
            "distance_from_home_miles",
            "latitude",
            "longitude",
        ]
        if column in fires.columns
    ]

    st.dataframe(
        fires[
            fire_columns
        ].head(
            250
        ),
        use_container_width=True,
        hide_index=True,
    )

    st.download_button(
        "Download NASA detection results",
        fires.to_csv(
            index=False
        ).encode(
            "utf-8"
        ),
        "wildfire_nasa_detections.csv",
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
        - **65% recent-fire proximity:** distance
          to the nearest recent NASA FIRMS thermal
          detection.
        - **35% current fire weather:** relative
          humidity, temperature, wind, gusts, and
          recent precipitation when those variables
          are available.
        - When official weather is temporarily
          unavailable, the score uses fire proximity
          only and clearly labels the missing weather
          component.

        This is a transparent review-prioritization
        score. It is not an ignition probability,
        claim probability, premium recommendation,
        evacuation decision, or filed insurance
        rating model.
        """
    )


st.warning(
    "Decision-support demonstration only. NASA "
    "FIRMS points are satellite thermal detections "
    "rather than verified wildfire perimeters. "
    "National Structure Inventory locations and "
    "values are modeled public estimates, not actual "
    "insurance policy limits, a property inspection, "
    "or an insurance quote. Always follow official "
    "emergency instructions."
                  )
