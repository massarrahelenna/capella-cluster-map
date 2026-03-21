# 🛰️ capella-cluster-map

Geospatial visualization and temporal analysis of Capella Space SAR satellite imagery metadata, with interactive map rendering and AI-powered storytelling using Amazon Bedrock.

---

## 📌 Overview

This project processes a dataset of SAR (Synthetic Aperture Radar) satellite images from Capella Space, clusters them using K-Means, visualizes their geographic distribution, and uses Claude (via Amazon Bedrock) to generate narrative analyses of temporal series — telling the "story" of each monitored location over time.

---

## 🗂️ Project Structure

```
capella-cluster-map/
├── main.py                  # Interactive map generation (Leaflet.js)
├── agent.py                 # AI agent for temporal series analysis
├── resultados_editado.xlsx  # Input dataset with SAR metadata and clusters
├── pesquisas/               # PDF research papers for context
│   └── *.pdf
└── output/
    ├── meu_globo_3d.html    # Interactive distribution map
    └── historias.md         # AI-generated temporal narratives
```

---

## 🚀 Features

- **Interactive Map** — Visualizes 1,582 SAR images across 61 unique locations worldwide, with circle size proportional to the number of images per location (time series depth)
- **K-Means Clustering** — Groups images by technical acquisition parameters (incidence angle, resolution, image size)
- **AI Temporal Analysis** — Uses Claude via Amazon Bedrock to analyze metadata sequences and generate chronological narratives for each monitored location
- **PDF Context Integration** — Feeds academic research papers as context to enrich the AI analysis
- **Regional Correlation** — Cross-analyzes multiple locations to identify global monitoring patterns

---

## 🛠️ Requirements

```bash
pip install pandas openpyxl boto3 pypdf
```

AWS credentials configured:
```bash
aws configure
```

---

## ⚙️ Configuration

In `agent.py`, adjust these variables:

```python
MAX_LOCAIS = 3       # Number of locations to analyze
MIN_IMAGENS = 5      # Minimum images per location to be included
```

---

## 🗺️ Running the Map

```bash
python3 main.py
```

Opens `output/meu_globo_3d.html` in the browser — an interactive dark-theme map showing all locations with:
- Circle size = number of images (time series)
- Color = K-Means cluster
- Click on any point to see platforms and cluster details
- Toggle clusters on/off via the top buttons

---

## 🤖 Running the AI Agent

```bash
python3 agent.py
```

The agent will:
1. Load the Excel dataset and group images by geographic location
2. Read all PDFs in `pesquisas/` as scientific context
3. Send metadata sequences to Claude via Amazon Bedrock
4. Generate a Markdown report at `output/historias.md`

---

## 📊 Dataset

The input file `resultados_editado.xlsx` contains SAR metadata from Capella Space with the following key columns:

| Column | Description |
|--------|-------------|
| `stac_id` | Unique image identifier |
| `platform` | Satellite (capella-5 through capella-14) |
| `datetime` | Acquisition timestamp |
| `center_lat/lon` | Geographic coordinates |
| `instrument_mode` | Capture mode (spotlight) |
| `incidence_angle` | Radar look angle |
| `KMeans_Cluster` | Assigned cluster (Grupo 0–2) |
| `DBSCAN_Cluster` | Secondary clustering result |

---

## 🔍 Cluster Interpretation

| Cluster | Characteristics | Interpretation |
|---------|----------------|----------------|
| **Grupo 0** | High angle (~44°), wide images, capella-13 | Lateral panoramic — good for coastal/urban |
| **Grupo 1** | Low angle (~36°), largest images, older satellites | Wide-area coverage — agriculture/mining |
| **Grupo 2** | Medium angle (~39°), smaller/square images | Focused target — ports, facilities |

---

## 🌍 Key Monitored Locations

| Location | Images | Coordinates |
|----------|--------|-------------|
| Hawaii | 376 | 19.42, -155.29 |
| California (Los Angeles) | 214 | 34.83, -118.07 |
| Australia (Pilbara) | 200 | -23.18, 118.77 |
| San Jose, CA | 176 | 37.32, -121.87 |

---

## ☁️ AWS Setup

This project uses **Amazon Bedrock** with Claude Sonnet 4:

```python
modelId = "us.anthropic.claude-sonnet-4-20250514-v1:0"
```

Make sure your IAM user has `bedrock:InvokeModel` permissions for `us-east-1`.

---

## 📄 License

MIT
