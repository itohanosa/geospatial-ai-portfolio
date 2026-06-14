# Baltimore Urban Heat Insurance Risk Intelligence


This project uses **Google Earth Engine, Landsat satellite imagery, vegetation indices, impervious surface data, population exposure, and water-body masking** to identify land areas with elevated urban heat risk. The final outputs include water-masked risk maps, census-tract priority rankings, insurance screening tiers, and portfolio-ready CSV deliverables.

---

## Project snapshot

| Item | Description |
|---|---|
| Project type | Climate-risk analytics, remote sensing, geospatial AI |
| Study area | Baltimore City, Maryland |
| Period analyzed | Summer months, 2020–2024 |
| Main tool | Google Earth Engine |
| Main output | Water-masked urban heat-risk index |
| Business use case | Insurance portfolio screening and resilience planning |
| Reporting unit | Census tracts |
| Final deliverables | GeoTIFFs, CSVs, maps, tract rankings, portfolio template |

---

## Why this project matters

Urban heat is becoming an important climate-risk issue for cities, insurers, property owners, and public agencies. High heat exposure can affect building performance, energy demand, infrastructure stress, health risk, and neighborhood resilience.

This project demonstrates how satellite data can be transformed into a practical decision-support product that helps answer:

- Which parts of Baltimore have the highest land-based heat exposure?
- Which census tracts combine high surface temperature, low vegetation, high imperviousness, and high population exposure?
- Which tracts should be prioritized for resilience review?
- How can insurers screen property portfolios for heat-related exposure?
- How can remote-sensing outputs be translated into business-ready risk tables?

---

## What I built

I built an end-to-end workflow that:

1. Extracts the Baltimore City boundary and census tracts.
2. Processes Landsat 8 and Landsat 9 summer imagery from 2020–2024.
3. Computes land surface temperature, NDVI, NDBI, impervious surface, and population exposure.
4. Fully masks out water bodies so rivers, reservoirs, and Baltimore Harbor appear blank or NoData.
5. Creates a continuous 0–1 urban heat-risk index.
6. Classifies the city into five heat-risk classes.
7. Ranks census tracts by heat-risk priority.
8. Converts tract rankings into insurance-facing screening tiers.
9. Produces CSV outputs that can support portfolio screening and resilience planning.

---

## Skills demonstrated

This project demonstrates practical skills in:

- Remote sensing
- Google Earth Engine
- Climate-risk analytics
- Geospatial data processing
- Raster analysis
- Census-tract aggregation
- Environmental risk modeling
- Insurance risk screening
- Data product design
- GIS-ready deliverable preparation
- Recruiter/client-facing technical communication

---

## Technical stack

| Tool or dataset | Purpose |
|---|---|
| Google Earth Engine | Satellite processing and geospatial analysis |
| Landsat 8/9 Collection 2 Level 2 | Land surface temperature, NDVI, and NDBI |
| JRC Global Surface Water | Water-body masking |
| National Land Cover Database | Impervious surface and open-water validation |
| GPW population data | Population exposure |
| Census tract boundaries | Tract-level reporting |
| QGIS or GIS software | Final map styling |
| CSV outputs | Insurance-ready tables and portfolio screening |

---

## Study area

**Baltimore City, Maryland, USA**

Baltimore is a strong case study because it contains dense urban surfaces, variable vegetation cover, industrial and residential zones, and major water bodies such as Baltimore Harbor. Because water can appear artificially cool in satellite-derived heat maps, water bodies were fully masked out to ensure the analysis reflects land-based exposure.

---

## Analysis period

**June to September, 2020–2024**

The workflow uses a multi-year summer composite instead of a single image. This helps capture persistent warm-season heat patterns and reduces the influence of one unusually hot or cloudy day.

---

## Methodology summary

### 1. Satellite processing

Landsat 8 and Landsat 9 imagery were filtered to summer months from 2020 to 2024. Cloud, cirrus, cloud-shadow, and dilated-cloud pixels were removed using the Landsat quality-assurance band.

### 2. Predictor generation

The model uses five main predictors:

| Predictor | Meaning |
|---|---|
| Land surface temperature | Measures surface heat intensity |
| NDVI | Measures vegetation greenness and cooling potential |
| NDBI | Measures built-up intensity |
| Impervious surface | Measures hard urban surfaces |
| Population exposure | Represents exposed population |

### 3. Water masking

Water bodies were fully removed from the analysis and exported rasters. This means water pixels appear blank or transparent in final maps.

The water mask combines:

- JRC Global Surface Water occurrence
- National Land Cover Database open-water class

This prevents water pixels from lowering land-based heat-risk values.

### 4. Urban heat-risk index

The final heat-risk index combines heat intensity, vegetation deficit, built-up intensity, imperviousness, and population exposure.

```text
Urban Heat Risk =
0.40 × normalized land surface temperature
+ 0.20 × low vegetation
+ 0.15 × normalized built-up index
+ 0.15 × normalized imperviousness
+ 0.10 × normalized population exposure
```

### 5. Tract priority score

Census tracts were ranked using a tract-level priority score.

```text
Priority Score =
0.35 × land-surface-temperature score
+ 0.20 × low-vegetation score
+ 0.15 × imperviousness score
+ 0.15 × population-exposure score
+ 0.15 × high-risk-land-area score
```

---

## Headline results

The water-masked analysis produced the following citywide summary:

| Metric | Value |
|---|---:|
| Mean land surface temperature | 38.63 °C |
| Mean normalized urban heat-risk score | 0.511 |
| Mean impervious surface | 51.09% |
| Mean NDVI | 0.474 |
| Census tracts ranked | 247 |
| Water-body treatment | Fully masked out / NoData |

The highest-ranked tract in the insurance-ready table is **Census Tract 2805**.

| Metric | Value |
|---|---:|
| Priority score | 0.8935 |
| Mean land surface temperature | 43.40 °C |
| Mean impervious surface | 87.27% |
| High-risk land area | 99.41% |
| Insurance heat tier | Severe |

---

## Four main figures

This project uses only four figures to keep the repository clean and easy to review.

### Figure 1. Continuous water-masked heat-risk map

**File:** `figures/baltimore_heat_risk_map.png`

Continuous water-masked urban heat-risk index.

![Continuous water-masked urban heat-risk index for Baltimore](figures/baltimore_heat_risk_map.png)

---

### Figure 2. Five-class heat-risk map

**File:** `figures/baltimore_risk_classes_map.png`

Five-class heat-risk map with water bodies blank or transparent.

![Five-class water-masked heat-risk map for Baltimore](figures/baltimore_risk_classes_map.png)

---

### Figure 3. Top 20 insurance-priority tracts

**File:** `figures/baltimore_top20_tracts.png`

Bar chart of the top 20 tracts by insurance priority score.

![Top 20 Baltimore census tracts by insurance priority score](figures/baltimore_top20_tracts.png)

---

### Figure 4. Insurance workflow diagram

**File:** `figures/baltimore_insurance_workflow.png`

Workflow diagram showing the path from satellite data to tract scores to insurance deliverables.

![Workflow from satellite data to tract scores to insurance deliverables](figures/baltimore_insurance_workflow.png)

---

## Insurance-facing deliverables

The project translates geospatial outputs into files that can be used for insurance and climate-risk screening.

| File | Purpose |
|---|---|
| `Baltimore_Insurance_Ready_Tract_Heat_Risk_Table.csv` | Main insurance-ready tract table |
| `Baltimore_Insurance_Top20_Heat_Risk_Tracts.csv` | Shortlist of highest-priority tracts |
| `Baltimore_Insurance_Executive_Summary.csv` | Summary of citywide heat-risk metrics |
| `Baltimore_Portfolio_Scoring_Template.csv` | Template for property-level portfolio scoring |
| `Baltimore_Urban_Heat_Risk_Index_2020_2024_WaterFullyMaskedOut.tif` | Continuous heat-risk raster |
| `Baltimore_Urban_Heat_Risk_Classes_2020_2024_WaterFullyMaskedOut.tif` | Classified heat-risk raster |

---

## Insurance screening tiers

The tract-level priority score is converted into five insurance-facing screening tiers.

| Tier code | Insurance heat tier | Suggested use |
|---:|---|---|
| 1 | Low | Standard monitoring |
| 2 | Mild | Low concern; monitor over time |
| 3 | Moderate | Review vegetation, imperviousness, and exposure context |
| 4 | High | Flag for underwriting and resilience review |
| 5 | Severe | Priority review; test claims concentration and mitigation needs |

These tiers are designed for screening and resilience planning. They are not direct premium categories.

---

## Business use cases

### 1. Insurance portfolio screening

Insurers can join property locations to the tract-level heat-risk table and identify how many assets fall in high or severe heat-risk areas.

### 2. Underwriting review

Properties in high-risk tracts can be flagged for additional review of building age, roof condition, cooling systems, energy demand, or previous claims.

### 3. Claims validation

Historical claims can be joined with the heat-risk table to test whether hotter tracts show higher claim frequency or severity.

### 4. Resilience investment

The highest-ranked tracts can be prioritized for tree planting, cool roofs, reflective surfaces, cooling centers, and infrastructure adaptation.

### 5. Public-sector planning

The maps and rankings can support local climate adaptation planning, environmental justice work, and urban resilience strategy.

---

## Portfolio scoring workflow

The portfolio scoring template allows property-level data to be connected to tract-level heat risk.

### Input format

```text
property_id,address,latitude,longitude,insured_value,occupancy_type,building_type,tract_geoid
```

### Expected output fields

```text
property_id
tract_geoid
insured_value
heat_risk_score
insurance_heat_tier
underwriting_review_flag
resilience_investment_flag
recommended_insurance_action
```

### Useful portfolio summaries

- Number of properties in high and severe heat-risk tiers
- Percent of total insured value in high and severe tiers
- Top exposed tracts by insured value
- Top exposed properties
- Average heat-risk score by building type
- Average heat-risk score by occupancy type

---

## Repository structure

```text
baltimore-urban-heat-insurance-risk/
│
├── README.md
│
├── gee/
│   └── baltimore_heat_risk_water_masked.js
│
├── data/
│   ├── Baltimore_Citywide_Heat_Risk_Summary_2020_2024_WaterFullyMaskedOut.csv
│   ├── Baltimore_Census_Tract_Heat_Risk_Priority_Ranking_2020_2024_WaterFullyMaskedOut.csv
│   ├── Baltimore_Insurance_Ready_Tract_Heat_Risk_Table.csv
│   ├── Baltimore_Insurance_Top20_Heat_Risk_Tracts.csv
│   ├── Baltimore_Insurance_Executive_Summary.csv
│   └── Baltimore_Portfolio_Scoring_Template.csv
│
├── rasters/
│   ├── Baltimore_Urban_Heat_Risk_Index_2020_2024_WaterFullyMaskedOut.tif
│   ├── Baltimore_Urban_Heat_Risk_Classes_2020_2024_WaterFullyMaskedOut.tif
│   ├── Baltimore_High_Heat_Risk_Areas_2020_2024_WaterFullyMaskedOut.tif
│   ├── Baltimore_LST_Celsius_2020_2024_WaterFullyMaskedOut.tif
│   ├── Baltimore_NDVI_2020_2024_WaterFullyMaskedOut.tif
│   ├── Baltimore_NDBI_2020_2024_WaterFullyMaskedOut.tif
│   └── Baltimore_Impervious_Surface_NLCD_2021_WaterFullyMaskedOut.tif
│
├── figures/
│   ├── baltimore_heat_risk_map.png
│   ├── baltimore_risk_classes_map.png
│   ├── baltimore_top20_tracts.png
│   └── baltimore_insurance_workflow.png
│
└── docs/
    ├── insurance_use_case_notes.md
    └── figure_captions.md
```

---

## How to reproduce

1. Open the Google Earth Engine script in `gee/baltimore_heat_risk_water_masked.js`.
2. Run the analysis for Baltimore City.
3. Export the GeoTIFF rasters and CSV tables to Google Drive.
4. Save exported CSV files in the `data/` folder.
5. Save exported GeoTIFF files in the `rasters/` folder.
6. Create the four figures and save them in the `figures/` folder.
7. Use the insurance-ready CSV outputs for portfolio screening and reporting.

---

## Limitations

This is a screening model, not a deterministic loss model.

Important limitations:

- Land surface temperature is not the same as air temperature.
- Outdoor surface heat does not directly measure indoor heat exposure.
- Tract-level scores do not replace building-level inspection.
- Population exposure is a proxy and not a direct measure of insured value.
- The model does not include building age, roof type, air-conditioning access, energy burden, or historical claims unless added separately.
- The model does not directly estimate premiums, claims, policy losses, or expected annual loss.
- Results are calibrated to Baltimore City and should be recalibrated before transfer to another city.

---

## Disclaimer

This project is for research, portfolio demonstration, and climate-risk screening. It is not an approved actuarial model and should not be used for premium setting, policy cancellation, or binding underwriting decisions without claims validation, regulatory review, and actuarial governance.
