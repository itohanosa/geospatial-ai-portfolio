# 🔥 Wildfire Portfolio Risk Intelligence

A cloud-connected geospatial risk application for insurance underwriting, catastrophe monitoring, portfolio exposure analysis, and client risk advisory.

## Live Application


**Application:** `https://itohanosa.github.io/geospatial-ai-portfolio/projects/wildfire-insurance-risk-intelligence/`

---

## Business Problem

Insurance companies, brokers, risk managers, and property owners need a rapid way to answer questions such as:

- Which insured properties are closest to recent wildfire detections?
- How much total insured value is exposed to elevated wildfire conditions?
- Which properties should be prioritized for underwriting review?
- Where are wildfire risks geographically concentrated?
- Are low humidity, high temperature, strong wind, and wind gusts increasing current risk?
- Which properties should be reviewed by catastrophe-response teams?

This project converts live environmental data into an explainable property-level review queue.

---

## Main Features

- Upload an insurance portfolio CSV.
- Read a portfolio from a public or pre-signed cloud CSV URL.
- Retrieve near-real-time active-fire detections from NASA FIRMS.
- Retrieve current weather from Open-Meteo.
- Calculate distance from every insured property to the nearest fire detection.
- Count recent fire detections within 25 miles.
- Calculate an explainable 0–100 wildfire screening score.
- Categorize properties as Low, Moderate, High, or Critical.
- Calculate total insured value within elevated-risk categories.
- Display properties and fire detections on an interactive map.
- Produce an underwriting and catastrophe-review queue.
- Download a scored CSV.
- Download a client-ready Excel report.

---

## Data Sources

### NASA FIRMS

NASA Fire Information for Resource Management System provides satellite-derived active-fire and thermal-anomaly detections.

A free NASA FIRMS `MAP_KEY` is required for live fire detections.

Official website:

https://firms.modaps.eosdis.nasa.gov/api/map_key/

### Open-Meteo

Open-Meteo provides current and forecast weather information used in the fire-weather component.

Variables include:

- Temperature
- Relative humidity
- Precipitation
- Wind speed
- Wind gusts

Official website:

https://open-meteo.com/en/docs

---
