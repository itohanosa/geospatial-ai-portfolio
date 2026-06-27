from __future__ import annotations

import io
import os
from math import cos, radians

import numpy as np
import pandas as pd
import pydeck as pdk
import requests
import streamlit as st


st.set_page_config(
    page_title="Wildfire Portfolio Risk",
    page_icon="🔥",
    layout="wide",
)

REQUIRED = {
    "property_id",
    "latitude",
    "longitude",
    "insured_value",
}

COLORS = {
    "Low": [46, 204, 113, 190],
    "Moderate": [241, 196, 15, 205],
    "High": [230, 126, 34, 220],
    "Critical": [192, 57, 43, 235],
}

SAMPLE_PORTFOLIO = pd.DataFrame(
    [
        [
            "CA-001",
            "Sacramento, CA",
            38.5816,
            -121.4944,
            850000,
            "Commercial",
        ],
        [
            "CA-002",
            "Santa Rosa, CA",
            38.4405,
            -122.7144,
            675000,
            "Residential",
        ],
        [
            "CA-003",
            "Redding, CA",
            40.5865,
            -122.3917,
            525000,
            "Residential",
        ],
        [
            "CA-004",
            "Fresno, CA",
            36.7378,
            -119.7871,
            1100000,
            "Commercial",
        ],
        [
            "CA-005",
            "San Bernardino, CA",
            34.1083,
            -117.2898,
            940000,
            "Residential",
        ],
        [
            "CA-006",
            "San Diego, CA",
            32.7157,
            -117.1611,
            1250000,
            "Commercial",
        ],
    ],
    columns=[
        "property_id",
        "address",
        "latitude",
        "longitude",
        "insured_value",
        "property_type",
    ],
)

SAMPLE_FIRES = pd.DataFrame(
    [
        [38.72, -122.82, 18.4, "nominal"],
        [40.73, -122.49, 34.2, "high"],
        [34.28, -117.51, 15.1, "nominal"],
        [36.95, -119.35, 29.7, "high"],
    ],
    columns=[
        "latitude",
        "longitude",
        "frp",
        "confidence",
    ],
)


def get_saved_key() -> str:
    """Read the NASA key from Streamlit Secrets or an environment variable."""

    try:
        return str(st.secrets.get("FIRMS_MAP_KEY", "")).strip()
    except Exception:
        return os.getenv("FIRMS_MAP_KEY", "").strip()


def validate_portfolio(df: pd.DataFrame) -> pd.DataFrame:
    """Validate and clean the uploaded insurance portfolio."""

    df = df.copy()
    df.columns = [str(column).strip().lower() for column in df.columns]

    missing = REQUIRED - set(df.columns)

    if missing:
        raise ValueError(
            "Missing columns: " + ", ".join(sorted(missing))
        )

    for column in [
        "latitude",
        "longitude",
        "insured_value",
    ]:
        df[column] = pd.to_numeric(
            df[column],
            errors="coerce",
        )

    df["property_id"] = (
        df["property_id"]
        .astype(str)
        .str.strip()
    )

    bad = (
        df["property_id"].eq("")
        | df["latitude"].isna()
        | df["longitude"].isna()
        | df["insured_value"].isna()
        | ~df["latitude"].between(-90, 90)
        | ~df["longitude"].between(-180, 180)
        | (df["insured_value"] < 0)
    )

    if bad.any():
        rows = ", ".join(
            map(
                str,
                (df.index[bad] + 2).tolist()[:20],
            )
        )

        raise ValueError(
            f"Invalid data in CSV row(s): {rows}"
        )

    if "address" not in df:
        df["address"] = "Not supplied"

    if "property_type" not in df:
        df["property_type"] = "Unspecified"

    return (
        df.drop_duplicates("property_id")
        .reset_index(drop=True)
    )


def load_portfolio(
    upload,
    url: str,
) -> tuple[pd.DataFrame, str]:
    """Load the portfolio from an upload, URL, or sample data."""

    if upload is not None:
        return (
            validate_portfolio(pd.read_csv(upload)),
            "Uploaded CSV",
        )

    if url.strip():
        response = requests.get(
            url.strip(),
            timeout=30,
        )
        response.raise_for_status()

        portfolio = pd.read_csv(
            io.StringIO(response.text)
        )

        return (
            validate_portfolio(portfolio),
            "Cloud CSV URL",
        )

    return (
        validate_portfolio(SAMPLE_PORTFOLIO),
        "Built-in sample portfolio",
    )


@st.cache_data(
    ttl=900,
    show_spinner=False,
)
def get_fires(
    key: str,
    source: str,
    box: str,
    days: int,
) -> pd.DataFrame:
    """Retrieve near-real-time fire detections from NASA FIRMS."""

    url = (
        "https://firms.modaps.eosdis.nasa.gov/"
        f"api/area/csv/{key}/{source}/{box}/{days}"
    )

    response = requests.get(
        url,
        timeout=60,
    )
    response.raise_for_status()

    if response.text.lower().startswith("invalid"):
        raise ValueError(response.text.strip())

    df = pd.read_csv(
        io.StringIO(response.text)
    )

    if df.empty:
        return pd.DataFrame(
            columns=[
                "latitude",
                "longitude",
                "frp",
                "confidence",
            ]
        )

    for column in [
        "latitude",
        "longitude",
        "frp",
    ]:
        if column not in df:
            df[column] = np.nan

        df[column] = pd.to_numeric(
            df[column],
            errors="coerce",
        )

    if "confidence" not in df:
        df["confidence"] = "unknown"

    return (
        df.dropna(
            subset=[
                "latitude",
                "longitude",
            ]
        )
        .sort_values(
            "frp",
            ascending=False,
        )
        .head(10000)
    )


@st.cache_data(
    ttl=900,
    show_spinner=False,
)
def get_weather(
    latitudes: tuple[float, ...],
    longitudes: tuple[float, ...],
) -> pd.DataFrame:
    """Retrieve current weather from Open-Meteo."""

    rows = []

    for start in range(
        0,
        len(latitudes),
        50,
    ):
        latitude_batch = latitudes[
            start : start + 50
        ]

        longitude_batch = longitudes[
            start : start + 50
        ]

        params = {
            "latitude": ",".join(
                map(str, latitude_batch)
            ),
            "longitude": ",".join(
                map(str, longitude_batch)
            ),
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
        }

        response = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params=params,
            timeout=60,
        )
        response.raise_for_status()

        payload = response.json()

        locations = (
            payload
            if isinstance(payload, list)
            else [payload]
        )

        for item in locations:
            current = item.get(
                "current",
                {},
            )

            rows.append(
                {
                    "temperature_f": current.get(
                        "temperature_2m"
                    ),
                    "humidity_pct": current.get(
                        "relative_humidity_2m"
                    ),
                    "precipitation_in": current.get(
                        "precipitation"
                    ),
                    "wind_mph": current.get(
                        "wind_speed_10m"
                    ),
                    "gust_mph": current.get(
                        "wind_gusts_10m"
                    ),
                    "weather_time": current.get(
                        "time"
                    ),
                }
            )

    return pd.DataFrame(rows)


def distances_miles(
    latitude: float,
    longitude: float,
    fire_latitudes: np.ndarray,
    fire_longitudes: np.ndarray,
) -> np.ndarray:
    """Calculate great-circle distance from one property to many fires."""

    earth_radius_miles = 3958.7613

    latitude_1 = radians(latitude)
    longitude_1 = radians(longitude)

    latitude_2 = np.radians(
        fire_latitudes
    )
    longitude_2 = np.radians(
        fire_longitudes
    )

    latitude_difference = (
        latitude_2 - latitude_1
    )
    longitude_difference = (
        longitude_2 - longitude_1
    )

    haversine_value = (
        np.sin(
            latitude_difference / 2
        )
        ** 2
        + cos(latitude_1)
        * np.cos(latitude_2)
        * np.sin(
            longitude_difference / 2
        )
        ** 2
    )

    return (
        2
        * earth_radius_miles
        * np.arctan2(
            np.sqrt(haversine_value),
            np.sqrt(
                1 - haversine_value
            ),
        )
    )


def fire_score(
    distance: float,
) -> float:
    """Convert nearest-fire distance into a 0–100 score."""

    if not np.isfinite(distance):
        return 0

    if distance <= 1:
        return 100

    if distance <= 5:
        return 90

    if distance <= 10:
        return 75

    if distance <= 25:
        return 55

    if distance <= 50:
        return 30

    if distance <= 100:
        return 10

    return 0


def weather_score(
    row: pd.Series,
) -> float:
    """Calculate a transparent current fire-weather score."""

    def number(
        name: str,
        fallback: float,
    ) -> float:
        value = pd.to_numeric(
            row.get(name),
            errors="coerce",
        )

        if pd.isna(value):
            return fallback

        return float(value)

    humidity = number(
        "humidity_pct",
        50,
    )

    wind = number(
        "wind_mph",
        0,
    )

    gust = number(
        "gust_mph",
        0,
    )

    temperature = number(
        "temperature_f",
        70,
    )

    precipitation = number(
        "precipitation_in",
        0,
    )

    score = (
        np.clip(
            (100 - humidity) / 100,
            0,
            1,
        )
        * 35
        + np.clip(
            wind / 35,
            0,
            1,
        )
        * 25
        + np.clip(
            gust / 55,
            0,
            1,
        )
        * 20
        + np.clip(
            (temperature - 60) / 45,
            0,
            1,
        )
        * 20
        - np.clip(
            precipitation / 0.20,
            0,
            1,
        )
        * 20
    )

    return float(
        np.clip(
            score,
            0,
            100,
        )
    )


def score_portfolio(
    portfolio: pd.DataFrame,
    fires: pd.DataFrame,
) -> pd.DataFrame:
    """Calculate property-level wildfire screening scores."""

    scored = (
        portfolio.copy()
        .reset_index(drop=True)
    )

    weather = get_weather(
        tuple(
            scored["latitude"].round(5)
        ),
        tuple(
            scored["longitude"].round(5)
        ),
    )

    if len(weather) != len(scored):
        raise RuntimeError(
            "Weather API returned an unexpected number of locations."
        )

    scored = pd.concat(
        [
            scored,
            weather,
        ],
        axis=1,
    )

    nearest = []
    nearby = []

    if fires.empty:
        nearest = [
            np.nan
        ] * len(scored)

        nearby = [
            0
        ] * len(scored)

    else:
        fire_latitudes = (
            fires["latitude"]
            .to_numpy(float)
        )

        fire_longitudes = (
            fires["longitude"]
            .to_numpy(float)
        )

        for row in scored.itertuples():
            distance = distances_miles(
                row.latitude,
                row.longitude,
                fire_latitudes,
                fire_longitudes,
            )

            nearest.append(
                float(distance.min())
            )

            nearby.append(
                int(
                    (
                        distance <= 25
                    ).sum()
                )
            )

    scored[
        "nearest_fire_miles"
    ] = nearest

    scored[
        "fires_within_25_miles"
    ] = nearby

    scored[
        "fire_proximity_score"
    ] = scored[
        "nearest_fire_miles"
    ].apply(fire_score)

    scored[
        "fire_weather_score"
    ] = scored.apply(
        weather_score,
        axis=1,
    )

    scored[
        "risk_score"
    ] = (
        scored[
            "fire_proximity_score"
        ]
        * 0.65
        + scored[
            "fire_weather_score"
        ]
        * 0.35
        + np.clip(
            scored[
                "fires_within_25_miles"
            ]
            * 2.5,
            0,
            10,
        )
    ).clip(
        0,
        100,
    ).round(1)

    scored[
        "risk_level"
    ] = pd.cut(
        scored[
            "risk_score"
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
    ).astype(str)

    scored[
        "map_color"
    ] = scored[
        "risk_level"
    ].map(COLORS)

    return (
        scored.sort_values(
            "risk_score",
            ascending=False,
        )
        .reset_index(drop=True)
    )


def excel_report(
    scored: pd.DataFrame,
    fires: pd.DataFrame,
    source: str,
) -> bytes:
    """Create an Excel insurance-risk report."""

    output = io.BytesIO()

    elevated = scored[
        "risk_level"
    ].isin(
        [
            "High",
            "Critical",
        ]
    )

    summary = pd.DataFrame(
        {
            "Metric": [
                "Properties",
                "Total insured value",
                "High/critical properties",
                "High/critical insured value",
                "Fire detections",
                "Fire source",
            ],
            "Value": [
                len(scored),
                scored[
                    "insured_value"
                ].sum(),
                elevated.sum(),
                scored.loc[
                    elevated,
                    "insured_value",
                ].sum(),
                len(fires),
                source,
            ],
        }
    )

    with pd.ExcelWriter(
        output,
        engine="openpyxl",
    ) as writer:
        summary.to_excel(
            writer,
            index=False,
            sheet_name="Executive Summary",
        )

        scored.drop(
            columns="map_color"
        ).to_excel(
            writer,
            index=False,
            sheet_name="Risk Queue",
        )

        fires.to_excel(
            writer,
            index=False,
            sheet_name="Fire Detections",
        )

    return output.getvalue()


def money(
    value: float,
) -> str:
    """Format monetary portfolio values."""

    if value >= 1_000_000_000:
        return (
            f"${value / 1_000_000_000:.2f}B"
        )

    if value >= 1_000_000:
        return (
            f"${value / 1_000_000:.2f}M"
        )

    return f"${value:,.0f}"


st.title(
    "🔥 Wildfire Portfolio Risk Intelligence"
)

st.caption(
    "Insurance exposure triage, underwriting review, "
    "catastrophe monitoring, and client risk advisory."
)

with st.sidebar:
    st.header(
        "Portfolio"
    )

    upload = st.file_uploader(
        "Upload portfolio CSV",
        type="csv",
    )

    csv_url = st.text_input(
        "Or paste a public/pre-signed CSV URL"
    )

    st.header(
        "Live fire data"
    )

    api_key = st.text_input(
        "NASA FIRMS MAP_KEY",
        value=get_saved_key(),
        type="password",
    )

    demo_fires = st.checkbox(
        "Use labelled demonstration fires without a key",
        True,
    )

    days = st.slider(
        "Recent detection window",
        1,
        5,
        2,
    )

    sensor = st.selectbox(
        "Satellite product",
        [
            "VIIRS_SNPP_NRT",
            "VIIRS_NOAA20_NRT",
            "MODIS_NRT",
        ],
    )

    run = st.button(
        "Run portfolio analysis",
        type="primary",
        use_container_width=True,
    )


with st.expander(
    "CSV format"
):
    st.code(
        "property_id,address,latitude,longitude,"
        "insured_value,property_type\n"
        "CA-001,Sacramento CA,38.5816,-121.4944,"
        "850000,Commercial"
    )


if not run:
    st.info(
        "Upload a CSV or use the sample portfolio, "
        "then tap **Run portfolio analysis**."
    )
    st.stop()


try:
    portfolio, portfolio_source = (
        load_portfolio(
            upload,
            csv_url,
        )
    )

except Exception as error:
    st.error(
        f"Portfolio error: {error}"
    )
    st.stop()


if len(portfolio) > 500:
    st.warning(
        "The public demonstration processes the first "
        "500 properties to control API use."
    )

    portfolio = portfolio.head(
        500
    )


padding = 0.75

box = ",".join(
    map(
        str,
        [
            max(
                -180,
                portfolio[
                    "longitude"
                ].min()
                - padding,
            ),
            max(
                -90,
                portfolio[
                    "latitude"
                ].min()
                - padding,
            ),
            min(
                180,
                portfolio[
                    "longitude"
                ].max()
                + padding,
            ),
            min(
                90,
                portfolio[
                    "latitude"
                ].max()
                + padding,
            ),
        ],
    )
)


fires = pd.DataFrame()

fire_source = (
    "No active-fire data"
)


if api_key:
    try:
        with st.spinner(
            "Downloading NASA FIRMS fire detections..."
        ):
            fires = get_fires(
                api_key,
                sensor,
                box,
                days,
            )

        fire_source = (
            f"NASA FIRMS {sensor}, "
            f"latest {days} day(s)"
        )

    except Exception as error:
        st.warning(
            "NASA FIRMS request failed: "
            f"{error}"
        )

        if demo_fires:
            fires = (
                SAMPLE_FIRES.copy()
            )

            fire_source = (
                "Synthetic demo fire points "
                "after API failure"
            )

elif demo_fires:
    fires = (
        SAMPLE_FIRES.copy()
    )

    fire_source = (
        "Synthetic demonstration fire points "
        "— not operational data"
    )


try:
    with st.spinner(
        "Retrieving weather and scoring the portfolio..."
    ):
        scored = score_portfolio(
            portfolio,
            fires,
        )

except Exception as error:
    st.error(
        f"Analysis error: {error}"
    )
    st.stop()


high = scored[
    "risk_level"
].isin(
    [
        "High",
        "Critical",
    ]
)


metrics = st.columns(4)

metrics[0].metric(
    "Properties",
    f"{len(scored):,}",
)

metrics[1].metric(
    "Total insured value",
    money(
        scored[
            "insured_value"
        ].sum()
    ),
)

metrics[2].metric(
    "High/critical properties",
    f"{high.sum():,}",
)

metrics[3].metric(
    "High/critical insured value",
    money(
        scored.loc[
            high,
            "insured_value",
        ].sum()
    ),
)


st.info(
    f"**Portfolio:** {portfolio_source}  |  "
    f"**Fire data:** {fire_source}  |  "
    "**Weather:** Open-Meteo"
)


portfolio_layer = pdk.Layer(
    "ScatterplotLayer",
    scored,
    get_position="[longitude, latitude]",
    get_fill_color="map_color",
    get_radius=4500,
    radius_min_pixels=6,
    radius_max_pixels=18,
    pickable=True,
    stroked=True,
    get_line_color=[
        30,
        30,
        30,
        220,
    ],
    line_width_min_pixels=1,
)


layers = [
    portfolio_layer
]


if not fires.empty:
    fire_layer = pdk.Layer(
        "ScatterplotLayer",
        fires,
        get_position="[longitude, latitude]",
        get_fill_color=[
            255,
            45,
            0,
            230,
        ],
        get_radius=3000,
        radius_min_pixels=4,
        radius_max_pixels=12,
        pickable=True,
    )

    layers.append(
        fire_layer
    )


deck = pdk.Deck(
    layers=layers,
    initial_view_state=pdk.ViewState(
        latitude=scored[
            "latitude"
        ].mean(),
        longitude=scored[
            "longitude"
        ].mean(),
        zoom=5,
    ),
    tooltip={
        "html": (
            "<b>{property_id}</b><br/>"
            "Risk: {risk_level} ({risk_score})<br/>"
            "Nearest fire: {nearest_fire_miles} mi"
        )
    },
)


st.pydeck_chart(
    deck,
    use_container_width=True,
)


left_column, right_column = (
    st.columns(2)
)

level_order = [
    "Critical",
    "High",
    "Moderate",
    "Low",
]


with left_column:
    st.subheader(
        "Property count by risk level"
    )

    property_counts = (
        scored[
            "risk_level"
        ]
        .value_counts()
        .reindex(
            level_order,
            fill_value=0,
        )
    )

    st.bar_chart(
        property_counts
    )


with right_column:
    st.subheader(
        "Insured value by risk level"
    )

    insured_value = (
        scored.groupby(
            "risk_level",
            observed=False,
        )[
            "insured_value"
        ]
        .sum()
        .reindex(
            level_order,
            fill_value=0,
        )
    )

    st.bar_chart(
        insured_value
    )


st.subheader(
    "Underwriting and catastrophe-review queue"
)


shown_columns = [
    "property_id",
    "address",
    "property_type",
    "insured_value",
    "risk_level",
    "risk_score",
    "nearest_fire_miles",
    "fires_within_25_miles",
    "temperature_f",
    "humidity_pct",
    "wind_mph",
    "gust_mph",
]


st.dataframe(
    scored[
        shown_columns
    ],
    use_container_width=True,
    hide_index=True,
    column_config={
        "insured_value": (
            st.column_config.NumberColumn(
                "Insured value",
                format="$%.0f",
            )
        ),
        "risk_score": (
            st.column_config.ProgressColumn(
                "Risk score",
                min_value=0,
                max_value=100,
                format="%.1f",
            )
        ),
        "nearest_fire_miles": (
            st.column_config.NumberColumn(
                "Nearest fire (mi)",
                format="%.1f",
            )
        ),
    },
)


csv_data = (
    scored.drop(
        columns="map_color"
    )
    .to_csv(
        index=False
    )
    .encode()
)


excel_data = excel_report(
    scored,
    fires,
    fire_source,
)


download_csv, download_excel = (
    st.columns(2)
)


download_csv.download_button(
    "Download scored CSV",
    csv_data,
    "wildfire_scored_portfolio.csv",
    "text/csv",
    use_container_width=True,
)


download_excel.download_button(
    "Download Excel client report",
    excel_data,
    "wildfire_insurance_report.xlsx",
    (
        "application/vnd.openxmlformats-officedocument."
        "spreadsheetml.sheet"
    ),
    use_container_width=True,
)


st.warning(
    "Decision-support only. This transparent screening "
    "score is not a filed rating model, claim probability, "
    "evacuation tool, or substitute for verified perimeters, "
    "defensible-space inspections, construction data, claims "
    "history, local emergency guidance, and insurer governance."
)


with st.expander(
    "How the score works"
):
    st.markdown(
        """
- **65% fire proximity** to the nearest satellite detection.
- **35% current fire weather** using humidity, heat, wind, gusts, and precipitation.
- A small adjustment for multiple detections within 25 miles.
- The 0–100 result prioritizes human review; it does not predict losses.
        """
      )
