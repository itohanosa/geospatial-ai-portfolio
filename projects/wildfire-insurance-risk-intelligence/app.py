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
    page_title="Wildfire Home Risk",
    page_icon="🔥",
    layout="wide",
)

NSI = "https://nsi.sec.usace.army.mil/nsiapi"
FIRMS = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"
GEOCODER = "https://geocoding-api.open-meteo.com/v1/search"
WEATHER = "https://api.open-meteo.com/v1/forecast"

HEADERS = {
    "User-Agent": "WildfireHomeRisk/1.0"
}

MAX_STRUCTURES = 15000


def firms_key() -> str:
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
def search_place(
    name: str,
) -> dict[str, Any]:
    data = get_json(
        GEOCODER,
        {
            "name": name,
            "count": 10,
            "language": "en",
            "format": "json",
            "countryCode": "US",
        },
        30,
    )

    results = data.get(
        "results",
        [],
    )

    if not results:
        raise ValueError(
            "No United States city or ZIP code was found."
        )

    return results[0]


def boxes(
    lat: float,
    lon: float,
    miles: float,
) -> tuple[str, str]:
    dy = miles / 69.0

    dx = miles / max(
        69.172
        * math.cos(
            math.radians(lat)
        ),
        10.0,
    )

    west = lon - dx
    east = lon + dx
    south = lat - dy
    north = lat + dy

    polygon = (
        f"{west:.6f},{south:.6f},"
        f"{east:.6f},{south:.6f},"
        f"{east:.6f},{north:.6f},"
        f"{west:.6f},{north:.6f},"
        f"{west:.6f},{south:.6f}"
    )

    rectangle = (
        f"{west:.6f},"
        f"{south:.6f},"
        f"{east:.6f},"
        f"{north:.6f}"
    )

    return polygon, rectangle


@st.cache_data(
    ttl=86400,
    show_spinner=False,
)
def nsi_stats(
    polygon: str,
) -> dict[str, Any]:
    return get_json(
        f"{NSI}/stats",
        {
            "bbox": polygon,
        },
        90,
    )


@st.cache_data(
    ttl=86400,
    show_spinner=False,
)
def nsi_structures(
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
    lat: float,
    lon: float,
) -> dict[str, Any]:
    data = get_json(
        WEATHER,
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
    area: str,
    days: int,
) -> pd.DataFrame:
    url = (
        f"{FIRMS}/"
        f"{key}/"
        f"{product}/"
        f"{area}/"
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
            "NASA FIRMS did not return coordinates."
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


def distances(
    lat: float,
    lon: float,
    latitudes: np.ndarray,
    longitudes: np.ndarray,
) -> np.ndarray:
    radius = 3958.7613

    lat1 = math.radians(
        lat
    )

    lon1 = math.radians(
        lon
    )

    lat2 = np.radians(
        latitudes.astype(float)
    )

    lon2 = np.radians(
        longitudes.astype(float)
    )

    delta_lat = (
        lat2 - lat1
    )

    delta_lon = (
        lon2 - lon1
    )

    value = (
        np.sin(
            delta_lat / 2
        )
        ** 2
        + math.cos(
            lat1
        )
        * np.cos(
            lat2
        )
        * np.sin(
            delta_lon / 2
        )
        ** 2
    )

    value = np.clip(
        value,
        0,
        1,
    )

    return (
        2
        * radius
        * np.arctan2(
            np.sqrt(
                value
            ),
            np.sqrt(
                1 - value
            ),
        )
    )


def fire_weather_score(
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


def proximity_score(
    distance: float | None,
) -> float:
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


def display_number(
    value: Any,
    decimals: int,
    suffix: str = "",
) -> str:
    value = pd.to_numeric(
        value,
        errors="coerce",
    )

    if pd.isna(
        value
    ):
        return "Unavailable"

    return (
        f"{float(value):.{decimals}f}"
        f"{suffix}"
    )


def make_map(
    lat: float,
    lon: float,
    zoom: int,
    show_marker: bool,
) -> folium.Map:
    map_object = folium.Map(
        location=[
            lat,
            lon,
        ],
        zoom_start=zoom,
        tiles=None,
        control_scale=True,
    )

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

    if show_marker:
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
            map_object
        )

    folium.LatLngPopup().add_to(
        map_object
    )

    folium.LayerControl(
        collapsed=False
    ).add_to(
        map_object
    )

    return map_object


default_values = {
    "lat": 39.8283,
    "lon": -98.5795,
    "zoom": 4,
    "selected": False,
    "results": None,
    "map_version": 0,
}

for name, value in default_values.items():
    if name not in st.session_state:
        st.session_state[name] = value


st.title(
    "🔥 Wildfire Home & Neighborhood Intelligence"
)

st.caption(
    "Search an area, zoom to a home, tap the building, "
    "and analyze real public data."
)


with st.sidebar:
    st.header(
        "1. Find an area"
    )

    place = st.text_input(
        "City, state, or ZIP code",
        "Paradise, California",
    )

    if st.button(
        "Search and zoom",
        use_container_width=True,
    ):
        try:
            found = search_place(
                place.strip()
            )

            st.session_state.lat = float(
                found[
                    "latitude"
                ]
            )

            st.session_state.lon = float(
                found[
                    "longitude"
                ]
            )

            st.session_state.zoom = 14
            st.session_state.selected = False
            st.session_state.results = None
            st.session_state.map_version += 1

            st.rerun()

        except Exception as error:
            st.error(
                f"Search failed: {error}"
            )

    st.header(
        "2. Analysis settings"
    )

    neighborhood = st.select_slider(
        "Neighborhood radius",
        options=[
            0.25,
            0.5,
            1.0,
            2.0,
        ],
        value=0.5,
    )

    fire_radius = st.select_slider(
        "Fire search radius",
        options=[
            10,
            25,
            50,
            75,
        ],
        value=50,
    )

    days = st.slider(
        "Recent NASA detection window",
        1,
        5,
        2,
    )

    product = st.selectbox(
        "NASA product",
        [
            "VIIRS_SNPP_NRT",
            "VIIRS_NOAA20_NRT",
            "VIIRS_NOAA21_NRT",
            "MODIS_NRT",
        ],
    )

    key = st.text_input(
        "NASA FIRMS MAP_KEY",
        firms_key(),
        type="password",
    )

    st.info(
        "Search first, switch to Satellite if needed, "
        "zoom in, and tap the exact building."
    )


st.subheader(
    "Tap the home or property"
)

map_event = st_folium(
    make_map(
        st.session_state.lat,
        st.session_state.lon,
        st.session_state.zoom,
        st.session_state.selected,
    ),
    height=560,
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
    map_event.get(
        "last_clicked"
    )
    if map_event
    else None
)


if clicked:
    new_lat = float(
        clicked[
            "lat"
        ]
    )

    new_lon = float(
        clicked[
            "lng"
        ]
    )

    changed = (
        not st.session_state.selected
        or abs(
            new_lat
            - st.session_state.lat
        )
        > 1e-7
        or abs(
            new_lon
            - st.session_state.lon
        )
        > 1e-7
    )

    if changed:
        st.session_state.lat = new_lat
        st.session_state.lon = new_lon

        st.session_state.zoom = int(
            map_event.get(
                "zoom"
            )
            or 18
        )

        st.session_state.selected = True
        st.session_state.results = None

        st.rerun()


if st.session_state.selected:
    st.success(
        "Selected: "
        f"{st.session_state.lat:.6f}, "
        f"{st.session_state.lon:.6f}"
    )

else:
    st.warning(
        "Tap the exact building before running the analysis."
    )


analyze = st.button(
    "Analyze this home/property",
    type="primary",
    use_container_width=True,
    disabled=not st.session_state.selected,
)


if analyze:
    if not key:
        st.error(
            "Add your NASA FIRMS MAP_KEY in the sidebar "
            "or Streamlit Secrets."
        )

        st.stop()

    latitude = float(
        st.session_state.lat
    )

    longitude = float(
        st.session_state.lon
    )

    structure_box, _ = boxes(
        latitude,
        longitude,
        float(
            neighborhood
        ),
    )

    _, fire_box = boxes(
        latitude,
        longitude,
        float(
            fire_radius
        ),
    )

    try:
        with st.spinner(
            "Checking and downloading real public data..."
        ):
            stats = nsi_stats(
                structure_box
            )

            expected = int(
                stats.get(
                    "num_structures"
                )
                or 0
            )

            if expected > MAX_STRUCTURES:
                st.error(
                    f"This area contains about "
                    f"{expected:,} structures. "
                    "Choose a smaller radius."
                )

                st.stop()

            structure_data = nsi_structures(
                structure_box
            )

            weather = current_weather(
                latitude,
                longitude,
            )

            fires = active_fires(
                key,
                product,
                fire_box,
                days,
            )

        nearest_structure = None

        if not structure_data.empty:
            structure_distances = distances(
                latitude,
                longitude,
                structure_data[
                    "latitude"
                ].to_numpy(),
                structure_data[
                    "longitude"
                ].to_numpy(),
            )

            structure_data[
                "distance_from_home_miles"
            ] = structure_distances

            nearest_structure = (
                structure_data.loc[
                    structure_distances.argmin()
                ].to_dict()
            )

        nearest_fire = None

        if not fires.empty:
            fire_distances = distances(
                latitude,
                longitude,
                fires[
                    "latitude"
                ].to_numpy(),
                fires[
                    "longitude"
                ].to_numpy(),
            )

            fires[
                "distance_from_home_miles"
            ] = fire_distances

            fires = (
                fires.sort_values(
                    "distance_from_home_miles"
                )
                .reset_index(
                    drop=True
                )
            )

            nearest_fire = float(
                fires.iloc[0][
                    "distance_from_home_miles"
                ]
            )

        weather_score = fire_weather_score(
            weather
        )

        watch_score = round(
            0.65
            * proximity_score(
                nearest_fire
            )
            + 0.35
            * weather_score,
            1,
        )

        st.session_state.results = {
            "lat": latitude,
            "lon": longitude,
            "neighborhood": neighborhood,
            "structures": structure_data,
            "fires": fires,
            "weather": weather,
            "nearest_structure": nearest_structure,
            "nearest_fire": nearest_fire,
            "weather_score": weather_score,
            "watch_score": watch_score,
        }

    except Exception as error:
        st.error(
            f"Analysis failed: {error}"
        )

        st.stop()


result = st.session_state.results


if result is None:
    st.stop()


structure_data = result[
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

nearest_fire = result[
    "nearest_fire"
]


st.divider()

st.subheader(
    "Home-level screening result"
)


metrics = st.columns(
    4
)


metrics[0].metric(
    "Current watch score",
    f"{result['watch_score']:.1f}/100",
)


metrics[1].metric(
    "Nearest recent detection",
    (
        "None found"
        if nearest_fire is None
        else f"{nearest_fire:.2f} mi"
    ),
)


metrics[2].metric(
    "Temperature",
    display_number(
        weather.get(
            "temperature_2m"
        ),
        1,
        " °F",
    ),
)


metrics[3].metric(
    "Humidity",
    display_number(
        weather.get(
            "relative_humidity_2m"
        ),
        0,
        "%",
    ),
)


weather_metrics = st.columns(
    3
)


weather_metrics[0].metric(
    "Wind",
    display_number(
        weather.get(
            "wind_speed_10m"
        ),
        1,
        " mph",
    ),
)


weather_metrics[1].metric(
    "Wind gusts",
    display_number(
        weather.get(
            "wind_gusts_10m"
        ),
        1,
        " mph",
    ),
)


weather_metrics[2].metric(
    "Precipitation",
    display_number(
        weather.get(
            "precipitation"
        ),
        3,
        " in",
    ),
)


if nearest_structure:
    st.markdown(
        "#### Nearest National Structure Inventory record"
    )

    structure_metrics = st.columns(
        4
    )

    structure_metrics[0].metric(
        "Distance from selected point",
        (
            f"{nearest_structure['distance_from_home_miles'] * 5280:.0f} ft"
        ),
    )

    structure_metrics[1].metric(
        "Estimated asset value",
        money(
            float(
                nearest_structure.get(
                    "estimated_asset_value"
                )
                or 0
            )
        ),
    )

    structure_metrics[2].metric(
        "Occupancy",
        str(
            nearest_structure.get(
                "occupancy"
            )
            or "Unknown"
        ),
    )

    structure_metrics[3].metric(
        "Median year built",
        display_number(
            nearest_structure.get(
                "median_year_built"
            ),
            0,
        ),
    )

else:
    st.warning(
        "No public structure record was found inside "
        "the selected neighborhood radius."
    )


st.subheader(
    "Neighborhood exposure"
)


exposure_metrics = st.columns(
    4
)


exposure_metrics[0].metric(
    "Structure records",
    f"{len(structure_data):,}",
)


exposure_metrics[1].metric(
    "Estimated asset value",
    (
        money(
            float(
                structure_data[
                    "estimated_asset_value"
                ].sum()
            )
        )
        if not structure_data.empty
        else "$0"
    ),
)


exposure_metrics[2].metric(
    "NASA detections",
    f"{len(fires):,}",
)


exposure_metrics[3].metric(
    "Fire-weather score",
    f"{result['weather_score']:.1f}/100",
)


st.subheader(
    "Results map"
)


result_map = folium.Map(
    location=[
        result[
            "lat"
        ],
        result[
            "lon"
        ],
    ],
    zoom_start=15,
    tiles=None,
    control_scale=True,
)


folium.TileLayer(
    "OpenStreetMap",
    name="Street map",
).add_to(
    result_map
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
    result_map
)


folium.Circle(
    [
        result[
            "lat"
        ],
        result[
            "lon"
        ],
    ],
    radius=(
        float(
            result[
                "neighborhood"
            ]
        )
        * 1609.344
    ),
    color="#2563eb",
    fill=True,
    fill_opacity=0.05,
    tooltip="Neighborhood radius",
).add_to(
    result_map
)


folium.Marker(
    [
        result[
            "lat"
        ],
        result[
            "lon"
        ],
    ],
    tooltip="Selected home/property",
    icon=folium.Icon(
        color="blue",
        icon="home",
        prefix="fa",
    ),
).add_to(
    result_map
)


if not structure_data.empty:
    structure_cluster = MarkerCluster(
        name="Public structure records"
    ).add_to(
        result_map
    )

    display_structures = structure_data.nsmallest(
        min(
            2500,
            len(
                structure_data
            ),
        ),
        "distance_from_home_miles",
    )

    for row in display_structures.itertuples():
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
                f"{money(float(row.estimated_asset_value))}"
            ),
        ).add_to(
            structure_cluster
        )


if not fires.empty:
    fire_group = folium.FeatureGroup(
        name="NASA fire detections"
    ).add_to(
        result_map
    )

    for row in fires.head(
        1000
    ).itertuples():
        folium.CircleMarker(
            [
                row.latitude,
                row.longitude,
            ],
            radius=6,
            color="#991b1b",
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
    collapsed=False
).add_to(
    result_map
)


st_folium(
    result_map,
    height=620,
    use_container_width=True,
    key="result_map",
    returned_objects=[],
)


if not structure_data.empty:
    st.subheader(
        "Nearby public structure records"
    )

    table_columns = [
        "structure_id",
        "occupancy",
        "category",
        "estimated_asset_value",
        "square_feet",
        "median_year_built",
        "distance_from_home_miles",
        "latitude",
        "longitude",
    ]

    st.dataframe(
        structure_data.sort_values(
            "distance_from_home_miles"
        )[
            table_columns
        ].head(
            1000
        ),
        use_container_width=True,
        hide_index=True,
    )

    st.download_button(
        "Download neighborhood results",
        structure_data.to_csv(
            index=False
        ).encode(
            "utf-8"
        ),
        "wildfire_home_results.csv",
        "text/csv",
        use_container_width=True,
    )


st.warning(
    "Screening demonstration only. NASA points are "
    "satellite thermal detections, not verified fire "
    "perimeters. National Structure Inventory locations "
    "and values are modeled public estimates, not actual "
    "insurance policy data or a property-level insurance quote."
  )
