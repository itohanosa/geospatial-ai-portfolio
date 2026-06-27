from __future__ import annotations

import io
import math
from typing import Any

import numpy as np
import pandas as pd
import requests
import streamlit as st


HEADERS = {
    "User-Agent": "WildfireExposureIntelligence/1.0"
}

NSI = "https://nsi.sec.usace.army.mil/nsiapi"

FIRMS = (
    "https://firms.modaps.eosdis.nasa.gov/"
    "api/area/csv"
)

GEOCODER = (
    "https://geocoding-api.open-meteo.com/"
    "v1/search"
)

WEATHER = (
    "https://api.open-meteo.com/v1/forecast"
)


COLORS = {
    "Low": [46, 204, 113, 190],
    "Moderate": [241, 196, 15, 210],
    "High": [230, 126, 34, 225],
    "Critical": [192, 57, 43, 240],
}


def get_json(
    url: str,
    params: dict[str, Any],
    timeout: int = 60,
) -> Any:
    response = requests.get(
        url,
        params=params,
        headers=HEADERS,
        timeout=timeout,
    )

    response.raise_for_status()

    return response.json()


@st.cache_data(
    ttl=86400,
    show_spinner=False,
)
def geocode(
    place: str,
) -> dict[str, Any]:
    data = get_json(
        GEOCODER,
        {
            "name": place,
            "count": 10,
            "language": "en",
            "format": "json",
        },
        30,
    )

    results = [
        row
        for row in data.get("results", [])
        if str(
            row.get(
                "country_code",
                "",
            )
        ).upper()
        == "US"
    ]

    if not results:
        raise ValueError(
            "No United States location was found. "
            "Try 'Paradise, California'."
        )

    return results[0]


def make_bbox(
    latitude: float,
    longitude: float,
    miles: float,
) -> dict[str, str]:
    latitude_change = miles / 69.0

    longitude_change = miles / (
        69.172
        * max(
            math.cos(
                math.radians(latitude)
            ),
            0.20,
        )
    )

    west = longitude - longitude_change
    east = longitude + longitude_change
    south = latitude - latitude_change
    north = latitude + latitude_change

    nsi_polygon = (
        f"{west:.6f},{south:.6f},"
        f"{east:.6f},{south:.6f},"
        f"{east:.6f},{north:.6f},"
        f"{west:.6f},{north:.6f},"
        f"{west:.6f},{south:.6f}"
    )

    firms_box = (
        f"{west:.6f},"
        f"{south:.6f},"
        f"{east:.6f},"
        f"{north:.6f}"
    )

    return {
        "nsi": nsi_polygon,
        "firms": firms_box,
    }


@st.cache_data(
    ttl=86400,
    show_spinner=False,
)
def structure_count(
    polygon: str,
) -> int:
    data = get_json(
        f"{NSI}/stats",
        {
            "bbox": polygon,
        },
        90,
    )

    return int(
        data.get(
            "num_structures",
        )
        or 0
    )


@st.cache_data(
    ttl=86400,
    show_spinner=False,
)
def structures(
    polygon: str,
) -> pd.DataFrame:
    data = get_json(
        f"{NSI}/structures",
        {
            "bbox": polygon,
            "fmt": "fc",
        },
        180,
    )

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
        ) or [
            None,
            None,
        ]

        if (
            len(coordinates) < 2
            or coordinates[0] is None
            or coordinates[1] is None
        ):
            continue

        rows.append(
            {
                "structure_id": properties.get(
                    "fd_id"
                ),
                "latitude": coordinates[1],
                "longitude": coordinates[0],
                "occupancy_type": properties.get(
                    "occtype",
                    "Unknown",
                ),
                "occupancy_group": properties.get(
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
                "ground_elevation_m": properties.get(
                    "ground_elv"
                ),
            }
        )

    dataframe = pd.DataFrame(
        rows
    )

    if dataframe.empty:
        raise ValueError(
            "The National Structure Inventory "
            "returned no structures."
        )

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
        dataframe[column] = pd.to_numeric(
            dataframe[column],
            errors="coerce",
        )

    value_columns = [
        "structure_value",
        "contents_value",
        "vehicle_value",
    ]

    dataframe[value_columns] = (
        dataframe[value_columns]
        .fillna(0)
        .clip(lower=0)
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
    ttl=900,
    show_spinner=False,
)
def current_weather(
    latitude: float,
    longitude: float,
) -> dict[str, Any]:
    data = get_json(
        WEATHER,
        {
            "latitude": latitude,
            "longitude": longitude,
            "current": (
                "temperature_2m,"
                "relative_humidity_2m,"
                "precipitation,"
                "wind_speed_10m,"
                "wind_gusts_10m"
            ),
            "temperature_unit": "fahrenheit",
            "wind_speed_unit": "mph",
            "precipitation_unit": "inch",
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
def active_fires(
    key: str,
    product: str,
    box: str,
    days: int,
) -> pd.DataFrame:
    url = (
        f"{FIRMS}/"
        f"{key}/"
        f"{product}/"
        f"{box}/"
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

    for column in [
        "latitude",
        "longitude",
        "frp",
    ]:
        if column in dataframe:
            dataframe[column] = pd.to_numeric(
                dataframe[column],
                errors="coerce",
            )

    if not {
        "latitude",
        "longitude",
    }.issubset(
        dataframe.columns
    ):
        raise ValueError(
            "NASA FIRMS did not return "
            "latitude and longitude fields."
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


def weather_score(
    weather: dict[str, Any],
) -> float:
    def number(
        name: str,
        default: float,
    ) -> float:
        value = pd.to_numeric(
            weather.get(
                name
            ),
            errors="coerce",
        )

        if pd.isna(
            value
        ):
            return default

        return float(
            value
        )

    temperature = number(
        "temperature_2m",
        70,
    )

    humidity = number(
        "relative_humidity_2m",
        50,
    )

    precipitation = number(
        "precipitation",
        0,
    )

    wind = number(
        "wind_speed_10m",
        0,
    )

    gust = number(
        "wind_gusts_10m",
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


def fire_distances(
    buildings: pd.DataFrame,
    fires: pd.DataFrame,
) -> tuple[
    np.ndarray,
    np.ndarray,
]:
    if fires.empty:
        return (
            np.full(
                len(buildings),
                np.nan,
            ),
            np.zeros(
                len(buildings),
                dtype=int,
            ),
        )

    earth_radius = 3958.7613

    fire_latitude = np.radians(
        fires[
            "latitude"
        ].to_numpy(
            float
        )
    )

    fire_longitude = np.radians(
        fires[
            "longitude"
        ].to_numpy(
            float
        )
    )

    building_latitude = np.radians(
        buildings[
            "latitude"
        ].to_numpy(
            float
        )
    )

    building_longitude = np.radians(
        buildings[
            "longitude"
        ].to_numpy(
            float
        )
    )

    nearest = np.empty(
        len(buildings)
    )

    counts = np.empty(
        len(buildings),
        dtype=int,
    )

    chunk_size = max(
        250,
        min(
            5000,
            int(
                5_000_000
                / max(
                    len(fires),
                    1,
                )
            ),
        ),
    )

    for start in range(
        0,
        len(buildings),
        chunk_size,
    ):
        end = min(
            start
            + chunk_size,
            len(buildings),
        )

        latitude_1 = building_latitude[
            start:end,
            None,
        ]

        longitude_1 = building_longitude[
            start:end,
            None,
        ]

        latitude_difference = (
            fire_latitude[
                None,
                :
            ]
            - latitude_1
        )

        longitude_difference = (
            fire_longitude[
                None,
                :
            ]
            - longitude_1
        )

        haversine = (
            np.sin(
                latitude_difference
                / 2
            )
            ** 2
            + np.cos(
                latitude_1
            )
            * np.cos(
                fire_latitude
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

        distance = (
            2
            * earth_radius
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

        nearest[
            start:end
        ] = distance.min(
            axis=1
        )

        counts[
            start:end
        ] = (
            distance
            <= 10
        ).sum(
            axis=1
        )

    return (
        nearest,
        counts,
    )


def proximity_score(
    distance: float,
) -> float:
    if not np.isfinite(
        distance
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


def score(
    buildings: pd.DataFrame,
    fires: pd.DataFrame,
    weather: dict[str, Any],
) -> pd.DataFrame:
    dataframe = buildings.copy()

    nearest, counts = fire_distances(
        dataframe,
        fires,
    )

    current_weather_score = weather_score(
        weather
    )

    dataframe[
        "nearest_fire_miles"
    ] = nearest

    dataframe[
        "fires_within_10_miles"
    ] = counts

    dataframe[
        "fire_proximity_score"
    ] = [
        proximity_score(
            value
        )
        for value in nearest
    ]

    dataframe[
        "fire_weather_score"
    ] = round(
        current_weather_score,
        1,
    )

    dataframe[
        "screening_score"
    ] = (
        0.70
        * dataframe[
            "fire_proximity_score"
        ]
        + 0.30
        * current_weather_score
        + np.clip(
            dataframe[
                "fires_within_10_miles"
            ]
            * 2,
            0,
            10,
        )
    ).clip(
        0,
        100,
    ).round(
        1
    )

    dataframe[
        "screening_level"
    ] = pd.cut(
        dataframe[
            "screening_score"
        ],
        [
            -0.1,
            34.99,
            59.99,
            79.99,
            100,
        ],
        labels=[
            "Low",
            "Moderate",
            "High",
            "Critical",
        ],
    ).astype(
        str
    )

    dataframe[
        "map_color"
    ] = dataframe[
        "screening_level"
    ].map(
        COLORS
    )

    return (
        dataframe.sort_values(
            [
                "screening_score",
                "estimated_asset_value",
            ],
            ascending=[
                False,
                False,
            ],
        )
        .reset_index(
            drop=True
        )
    )


def money(
    value: float,
) -> str:
    if value >= 1_000_000_000:
        return (
            f"${value / 1_000_000_000:.2f}B"
        )

    if value >= 1_000_000:
        return (
            f"${value / 1_000_000:.2f}M"
        )

    return f"${value:,.0f}"
