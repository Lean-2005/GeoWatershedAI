# GeoWatershed AI — Working Prototype

**SIH 2026 · Problem Statement 26015** — *Application of Geospatial Techniques
for visualization and analysis to interpret Geo-Coded Images to enhance
Watershed Development Outcomes.*

This is a runnable implementation of the architecture in the pitch deck:
a FastAPI + GDAL/Rasterio geospatial backend, and a Leaflet-based GIS
dashboard frontend, covering the full pipeline —

```
Geo-coded evidence → Validated layers → Spatial indicators → Thematic maps → Decision report
```

## What's implemented

| Deck module | Implementation |
|---|---|
| Data sources | Synthetic Sentinel-2-style 4-band (R/G/B/NIR) scene generator over a demo watershed AOI (swap for a real GeoTIFF reader to go live) |
| Pre-processing | Coordinate/bounds/type validation on every uploaded field photo |
| Geospatial engine | NDVI & NDWI computation with `rasterio` + `numpy`, land/water/vegetation classification |
| Analysis | Before/after change detection, connected-component hotspot clustering (`scipy.ndimage`) ranked by priority score |
| Dashboard | Interactive Leaflet map: watershed boundary, drainage network, land-use zones, waterbodies, thematic overlay, change-detection overlay, hotspot markers, field-evidence photo pins |
| Image & Metadata Validation | `/api/evidence/upload` — rejects out-of-AOI coordinates / bad file types, stores to SQLite + local disk |
| GIS Layer Management | `/api/watershed/*` — boundary + drainage + land-use + waterbody GeoJSON layers |
| Spatial Analysis & Hotspots | `/api/analysis/hotspots` |
| Change Detection | `/api/analysis/change-detection` |
| Report Generation | `/api/report/generate` — downloadable PDF decision report (ReportLab) |

The demo ships **synthetic imagery** so it runs immediately with zero API
keys / data downloads / PostGIS server setup. `backend/app/geospatial.py`
is written so `generate_synthetic_scene()` is the *only* place that needs
replacing with a real Sentinel-2/Landsat GeoTIFF reader (`rasterio.open(...)`)
to go from demo to production — every function downstream only depends on
the (red, green, blue, nir, transform) it receives.

## Requirements

- Python 3.9+
- A modern web browser (Chrome/Firefox/Edge)
- No database server, no API keys, no internet access required after the
  one-time `pip install` (the frontend map tiles need internet; the API
  and analysis work fully offline)

## Quick start

### 1. Start the backend

**Linux/macOS:**
```bash
./run_backend.sh
```

**Windows:**
```bat
run_backend.bat
```

This creates a virtual environment, installs `backend/requirements.txt`,
and starts the API at `http://127.0.0.1:8000` (interactive docs at
`http://127.0.0.1:8000/docs`).

If you'd rather do it manually:
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### 2. Open the frontend

Just open `frontend/index.html` directly in your browser (double-click it,
or `open frontend/index.html` / `start frontend/index.html`). It talks to
the backend at `http://127.0.0.1:8000` — edit `frontend/config.js` if you
run the API on a different host/port.

(No `npm install` / build step needed — it's plain HTML/CSS/JS using
Leaflet from a CDN, so it works even if Node.js isn't installed.)

### 3. Walk through the pipeline in the UI

1. **Generate satellite scenes** — creates the synthetic before/after AOI raster.
2. **Analyze "before" / "after"** — computes NDVI/NDWI, shows class
   composition, overlays a thematic classification map on the Leaflet map.
3. **Run change detection** — overlays a red/green gain-loss difference map
   and shows summary change stats.
4. **Find intervention hotspots** — clusters the most degraded zones and
   drops ranked priority markers on the map.
5. **Upload field evidence** — pick a photo, enter lat/lon (try a point
   inside the AOI, e.g. `19.96, 73.79`, and one clearly outside it to see
   validation reject it), see it pinned on the map.
6. **Generate PDF report** — downloads a decision report combining all of
   the above.

## Project layout

```
GeoWatershedAI/
├── backend/
│   ├── app/
│   │   ├── main.py         FastAPI routes
│   │   ├── geospatial.py   NDVI/NDWI, classification, change detection, hotspots
│   │   ├── data.py         Sample watershed boundary / drainage / land-use layers
│   │   ├── storage.py      SQLite-backed evidence image store
│   │   └── report.py       PDF report builder (ReportLab)
│   ├── generated/          Runtime output (rasters, uploaded images, reports, db) — gitignored
│   └── requirements.txt
├── frontend/
│   ├── index.html
│   ├── app.js              Leaflet map + API wiring
│   ├── style.css
│   └── config.js           API base URL
├── run_backend.sh
├── run_backend.bat
└── README.md
```

## Moving from prototype to production

- Swap `storage.py`'s SQLite calls for PostgreSQL/PostGIS (`psycopg2` /
  `SQLAlchemy` + `GeoAlchemy2`), and image files for S3/object storage —
  the function signatures are already the seam to do this behind.
- Swap `geospatial.generate_synthetic_scene()` for a real ingestion step:
  download/read a Sentinel-2 (via `sentinelsat` / Copernicus Data Space)
  or Landsat (`USGS EarthExplorer`) scene clipped to the AOI with
  `rasterio`/`rioxarray`.
- Add authentication (e.g. `fastapi-users`) in front of the upload/report
  endpoints for a multi-district deployment.
- Replace the connected-component hotspot heuristic with the
  `scikit-learn` clustering already in `requirements.txt` (e.g. DBSCAN
  over degraded-pixel coordinates) if you need density-based clustering
  instead of raster connectivity.
