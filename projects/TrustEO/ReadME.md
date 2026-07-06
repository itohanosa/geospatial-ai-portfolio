# TrustEO

**TrustEO** is an open research project for benchmarking trustworthy Earth observation foundation models for climate and disaster-risk mapping.

## Project Objective

The objective of this project is to improve the reliability of artificial intelligence models that analyze satellite images so they can produce trustworthy maps for climate and disaster decision-making.

## Core Research Question

Can Earth observation foundation models be trusted when they are applied to new regions, new hazards, and real-world decision-support problems?

## Initial Focus

This project will evaluate Earth observation artificial intelligence models for:

1. Flood mapping
2. Land-cover change mapping
3. Burn scar mapping
4. Climate and disaster-risk screening

## What TrustEO Measures

Unlike standard benchmarks that only report accuracy, TrustEO evaluates:

- Spatial generalization
- Uncertainty calibration
- Explainability
- Robustness
- Computational efficiency
- Decision-support usefulness

## Planned Models

- Prithvi-EO
- Prithvi-EO-2.0
- DINOv2
- Segment Anything Model
- U-Net
- DeepLabV3+

## Planned Datasets

- Sen1Floods11
- Landsat
- Sentinel-1
- Sentinel-2
- Dynamic World
- Monitoring Trends in Burn Severity

## Repository Structure

```text
TrustEO/
├── README.md
├── paper/
├── data/
├── notebooks/
├── src/
├── configs/
├── results/
├── figures/
├── docs/
├── requirements.txt
└── LICENSE
