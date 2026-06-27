from __future__ import annotations

import os

import numpy as np
import pydeck as pdk
import streamlit as st

from engine import (
    active_fires,
    current_weather,
    geocode,
    make_bbox,
    money,
    score,
    structure_count,
    structures,
    weather_score,
)


st.set_page_config(
    page_title="Wildfire Exposure Intelligence",
    page_icon="🔥",
    layout="wide",
)


MAX_STRUCTURES = 150_000
MAP_LIMIT = 15_000


def saved_key() -> str:
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


st.title(
    "🔥 Wildfire Exposure Intelligence"
)

st.caption(
    "Real public structures, near-real-time satellite "
    "fire detections, and current weather for insurance "
    "exposure triage and catastrophe monitoring."
)


with st.sidebar:
    st.header(
        "Select a real study area"
    )

    with st.form(
        "analysis"
    ):
        place = st.text_input(
            "United States city, place, or ZIP",
            "Paradise, California",
        )

        radius = st.select_slider(
            "Analysis radius (miles)",
            [
                3,
                5,
                8,
                10,
                15,
            ],
            value=5,
        )

        product = st.selectbox(
            "NASA satellite product",
            [
                "VIIRS_SNPP_NRT",
                "VIIRS_NOAA20_NRT",
                "MODIS_NRT",
            ],
        )

        days = st.slider(
            "Recent fire window (days)",
            1,
            5,
            2,
        )

        key = st.text_input(
            "NASA FIRMS MAP_KEY",
            saved_key(),
            type="password",
        )

        run = st.form_submit_button(
            "Run real-data analysis",
            type="primary",
            use_container_width=True,
        )

    st.markdown(
        "---"
    )

    st.markdown(
        "**Live/public data**\n\n"
        "- USACE National Structure Inventory\n"
        "- NASA FIRMS active-fire detections\n"
        "- Open-Meteo current weather"
    )

    st.caption(
        "No invented properties or synthetic "
        "fire points are used."
    )


if not run:
    st.info(
        "Enter a location and your free NASA FIRMS "
        "key, then run the analysis."
    )

    st.markdown(
        "### Outputs\n"
        "- Real structure count and estimated asset value\n"
        "- Structures and value close to recent fires\n"
        "- Current wind, humidity, heat, gusts, and rain\n"
        "- Interactive map and ranked review queue\n"
        "- Complete downloadable CSV"
    )

    st.stop()


if not place.strip():
    st.error(
        "Enter a United States location."
    )

    st.stop()


if not key:
    st.error(
        "Add a free NASA FIRMS MAP_KEY. "
        "This version does not substitute "
        "synthetic fire data."
    )

    st.stop()


try:
    with st.spinner(
        "Resolving the location..."
    ):
        location = geocode(
            place.strip()
        )

        latitude = float(
            location[
                "latitude"
            ]
        )

        longitude = float(
            location[
                "longitude"
            ]
        )

        boxes = make_bbox(
            latitude,
            longitude,
            float(
                radius
            ),
        )

        label = ", ".join(
            str(
                location.get(
                    field,
                    "",
                )
            )
            for field in [
                "name",
                "admin2",
                "admin1",
                "country",
            ]
            if location.get(
                field
            )
        )

    with st.spinner(
        "Checking the public structure inventory..."
    ):
        expected = structure_count(
            boxes[
                "nsi"
            ]
        )

    if expected == 0:
        st.warning(
            "No National Structure Inventory records "
            "were found. Try a nearby place."
        )

        st.stop()

    if expected > MAX_STRUCTURES:
        st.error(
            f"This area has approximately "
            f"{expected:,} structures. "
            f"Choose a smaller radius to remain below "
            f"the public-app limit of "
            f"{MAX_STRUCTURES:,} structures."
        )

        st.stop()

    with st.spinner(
        f"Downloading {expected:,} real "
        f"structure records..."
    ):
        buildings = structures(
            boxes[
                "nsi"
            ]
        )

    with st.spinner(
        "Downloading current weather and "
        "NASA fire detections..."
    ):
        weather = current_weather(
            latitude,
            longitude,
        )

        fires = active_fires(
            key,
            product,
            boxes[
                "firms"
            ],
            days,
        )

    with st.spinner(
        "Calculating current exposure..."
    ):
        results = score(
            buildings,
            fires,
            weather,
        )

except Exception as error:
    st.error(
        "The analysis could not be completed: "
        f"{error}"
    )

    st.stop()


st.success(
    f"Real-data analysis completed for "
    f"**{label}**, approximately "
    f"{radius} miles around the center."
)


if fires.empty:
    st.warning(
        f"NASA returned no {product} detections "
        f"in this area during the latest "
        f"{days} day(s). The structure and weather "
        f"results remain real, but current "
        f"active-fire proximity is zero."
    )


near_fire = (
    results[
        "nearest_fire_miles"
    ]
    .le(
        10
    )
    .fillna(
        False
    )
)


metrics = st.columns(
    5
)


metrics[0].metric(
    "Real structures",
    f"{len(results):,}",
)


metrics[1].metric(
    "Estimated asset value",
    money(
        results[
            "estimated_asset_value"
        ].sum()
    ),
    help=(
        "United States Army Corps of Engineers "
        "estimated structure, contents, and "
        "vehicle value. These are not policy limits."
    ),
)


metrics[2].metric(
    "Recent fire detections",
    f"{len(fires):,}",
)


metrics[3].metric(
    "Structures within 10 mi",
    f"{int(near_fire.sum()):,}",
)


metrics[4].metric(
    "Value within 10 mi",
    money(
        results.loc[
            near_fire,
            "estimated_asset_value",
        ].sum()
    ),
)


weather_metrics = st.columns(
    5
)


weather_metrics[0].metric(
    "Temperature",
    (
        f"{float(weather.get('temperature_2m', np.nan)):.1f} °F"
    ),
)


weather_metrics[1].metric(
    "Humidity",
    (
        f"{float(weather.get('relative_humidity_2m', np.nan)):.0f}%"
    ),
)


weather_metrics[2].metric(
    "Wind",
    (
        f"{float(weather.get('wind_speed_10m', np.nan)):.1f} mph"
    ),
)


weather_metrics[3].metric(
    "Wind gusts",
    (
        f"{float(weather.get('wind_gusts_10m', np.nan)):.1f} mph"
    ),
)


weather_metrics[4].metric(
    "Fire-weather score",
    (
        f"{weather_score(weather):.1f}/100"
    ),
    help=(
        "Transparent current-condition screening "
        "score, not a wildfire probability."
    ),
)


st.subheader(
    "Current exposure map"
)


map_data = results.head(
    MAP_LIMIT
).copy()


if len(
    results
) > MAP_LIMIT:
    st.caption(
        f"The map displays the "
        f"{MAP_LIMIT:,} highest-priority structures. "
        f"Metrics and downloads use all "
        f"{len(results):,} records."
    )


layers = [
    pdk.Layer(
        "ScatterplotLayer",
        map_data,
        get_position=(
            "[longitude, latitude]"
        ),
        get_fill_color=(
            "map_color"
        ),
        get_radius=60,
        radius_min_pixels=2,
        radius_max_pixels=8,
        pickable=True,
    )
]


if not fires.empty:
    layers.append(
        pdk.Layer(
            "ScatterplotLayer",
            fires,
            get_position=(
                "[longitude, latitude]"
            ),
            get_fill_color=[
                255,
                0,
                0,
                235,
            ],
            get_radius=250,
            radius_min_pixels=5,
            radius_max_pixels=14,
            pickable=True,
        )
    )


st.pydeck_chart(
    pdk.Deck(
        map_style="light",
        initial_view_state=pdk.ViewState(
            latitude=latitude,
            longitude=longitude,
            zoom=(
                10
                if radius <= 5
                else 9
            ),
        ),
        layers=layers,
        tooltip={
            "html": (
                "<b>Structure {structure_id}</b><br/>"
                "Occupancy: {occupancy_type}<br/>"
                "Estimated asset value: "
                "${estimated_asset_value}<br/>"
                "Screening: {screening_level} "
                "({screening_score})<br/>"
                "Nearest detection: "
                "{nearest_fire_miles} miles"
            )
        },
    ),
    use_container_width=True,
)


left_column, right_column = st.columns(
    2
)


with left_column:
    st.subheader(
        "Value by occupancy group"
    )

    occupancy_values = (
        results.groupby(
            "occupancy_group"
        )[
            "estimated_asset_value"
        ]
        .sum()
        .sort_values(
            ascending=False
        )
        .head(
            10
        )
    )

    st.bar_chart(
        occupancy_values
    )


with right_column:
    st.subheader(
        "Structures by screening level"
    )

    level_counts = (
        results[
            "screening_level"
        ]
        .value_counts()
        .reindex(
            [
                "Critical",
                "High",
                "Moderate",
                "Low",
            ],
            fill_value=0,
        )
    )

    st.bar_chart(
        level_counts
    )


st.subheader(
    "Insurance review queue"
)


columns = [
    "structure_id",
    "occupancy_type",
    "occupancy_group",
    "estimated_asset_value",
    "square_feet",
    "median_year_built",
    "nearest_fire_miles",
    "fires_within_10_miles",
    "fire_weather_score",
    "screening_score",
    "screening_level",
    "latitude",
    "longitude",
]


st.dataframe(
    results[
        columns
    ].head(
        5000
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
        "nearest_fire_miles": (
            st.column_config.NumberColumn(
                "Nearest detection (mi)",
                format="%.2f",
            )
        ),
        "screening_score": (
            st.column_config.ProgressColumn(
                "Screening score",
                min_value=0,
                max_value=100,
                format="%.1f",
            )
        ),
    },
)


st.caption(
    "The table is limited to 5,000 rows for "
    "browser performance. The CSV download "
    "contains every structure."
)


export = results.drop(
    columns="map_color"
).copy()


export.insert(
    0,
    "analysis_location",
    label,
)


export.insert(
    1,
    "analysis_radius_miles",
    radius,
)


export.insert(
    2,
    "fire_product",
    product,
)


export.insert(
    3,
    "fire_window_days",
    days,
)


export.insert(
    4,
    "weather_time",
    weather.get(
        "time"
    ),
)


st.download_button(
    "Download all real-data results",
    export.to_csv(
        index=False
    ).encode(
        "utf-8"
    ),
    "wildfire_real_structure_exposure.csv",
    "text/csv",
    use_container_width=True,
)


with st.expander(
    "Method and interpretation"
):
    st.markdown(
        "- **70%** nearest active-fire-detection "
        "proximity.\n"
        "- **30%** current fire-weather conditions.\n"
        "- Up to 10 additional points for multiple "
        "detections within 10 miles.\n\n"
        "The score ranks structures for human review. "
        "It is not an ignition probability, loss "
        "probability, premium indication, or filed "
        "insurance rating model."
    )


st.warning(
    "NASA FIRMS points are satellite thermal "
    "detections, not verified wildfire perimeters. "
    "National Structure Inventory values are modeled "
    "estimates, not actual policy limits or total "
    "insured values. An insurer would securely join "
    "its authorized policy, claims, inspection, "
    "construction, vegetation, and perimeter data."
)
