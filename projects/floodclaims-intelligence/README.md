# FloodClaims Intelligence

A geospatial flood exposure and satellite damage-assessment platform for insurance underwriting, catastrophe response, claims triage, and resilience consulting.

## What It Does

- Searches for a United States address or location
- Displays flood zones and floodways
- Retrieves nearby public structure records
- Estimates exposed structure and contents value
- Shows elevation, terrain, and nearby water features
- Retrieves current weather, flood alerts, and stream-gauge conditions
- Uses Sentinel-1 radar imagery to detect probable flooding
- Identifies structures near detected floodwater
- Ranks properties for insurance inspection and claims review
- Exports property and neighborhood results

## Data Sources

- Federal Emergency Management Agency National Flood Hazard Layer
- United States Army Corps of Engineers National Structure Inventory
- United States Geological Survey stream gauges and elevation data
- National Weather Service forecasts and flood alerts
- Sentinel-1, Sentinel-2, and Landsat satellite imagery
- United States Census Bureau American Community Survey
- OpenFEMA
- OpenStreetMap

## Claims-Triage Categories

- Immediate inspection
- Priority remote review
- Desk review
- No visible flood signal
- Insufficient evidence

## Technology

- Python
- Streamlit
- Folium
- GeoPandas
- Rasterio
- Google Earth Engine
- PostgreSQL/PostGIS
- FastAPI
- Docker

## Run the Application

Install the required packages:

```bash
pip install -r requirements.txt

Run the application:

streamlit run app.py

Professional Use Cases

- Flood underwriting support
- Catastrophe monitoring
- Claims inspection prioritization
- Property exposure analysis
- Portfolio risk concentration
- Satellite damage assessment
- Climate-risk and resilience consulting

Author

Itohan-Osa Abu

Remote Sensing, Geographic Information Systems, Geospatial Artificial Intelligence, Climate Risk, and Insurance Analytics

Portfolio:
https://itohanosa.github.io/geospatial-ai-portfolio/

Disclaimer

This application is a decision-support and portfolio demonstration tool. It is not a flood guarantee, insurance quote, claim decision, property appraisal, or substitute for official emergency guidance and field inspection.

Public structure values are modeled estimates and are not actual insurance policy limits.
