from __future__ import annotations

import shutil
import uuid
from pathlib import Path

import numpy as np
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import data, geospatial as geo, storage, report as report_mod

GENERATED_DIR = Path(__file__).resolve().parent.parent / "generated"
GENERATED_DIR.mkdir(exist_ok=True)

app = FastAPI(title="GeoWatershed AI API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

storage.init_db()

# In-memory cache of the last generated before/after scenes so repeated
# analysis/hotspot/report calls in a session are consistent and fast.
_STATE = {"before": None, "after": None}


def _ensure_scenes():
    if _STATE["before"] is None:
        _STATE["before"] = geo.generate_synthetic_scene(seed=1, degrade_region=False)
    if _STATE["after"] is None:
        _STATE["after"] = geo.generate_synthetic_scene(seed=1, degrade_region=True)
    return _STATE["before"], _STATE["after"]


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "GeoWatershed AI"}


# ---------------------------------------------------------------- GIS layers
@app.get("/api/watershed/boundary")
def get_boundary():
    return data.watershed_boundary_geojson()


@app.get("/api/watershed/layers")
def get_layers():
    return {
        "drainage": data.drainage_network_geojson(),
        "landuse": data.landuse_geojson(),
        "waterbodies": data.waterbodies_geojson(),
        "bbox": list(geo.WATERSHED_BBOX),
    }


# ------------------------------------------------------ evidence image upload
ALLOWED_EXT = {".jpg", ".jpeg", ".png"}


@app.post("/api/evidence/upload")
async def upload_evidence(
    file: UploadFile = File(...),
    lat: float = Form(...),
    lon: float = Form(...),
    captured_on: str = Form(""),
    notes: str = Form(""),
):
    ext = Path(file.filename).suffix.lower()
    valid = True
    messages = []

    if ext not in ALLOWED_EXT:
        valid = False
        messages.append(f"Unsupported file type '{ext}'")

    minx, miny, maxx, maxy = geo.WATERSHED_BBOX
    if not (minx - 0.05 <= lon <= maxx + 0.05 and miny - 0.05 <= lat <= maxy + 0.05):
        valid = False
        messages.append("Coordinates fall well outside the watershed AOI")

    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        valid = False
        messages.append("Coordinates are not valid lat/lon values")

    stored_name = f"{uuid.uuid4().hex}{ext if ext in ALLOWED_EXT else '.bin'}"
    stored_path = storage.IMAGES_DIR / stored_name
    with stored_path.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    msg = "OK" if valid else "; ".join(messages)
    image_id = storage.insert_image(
        filename=file.filename, stored_path=str(stored_path), lat=lat, lon=lon,
        captured_on=captured_on, notes=notes, valid=valid, validation_message=msg,
    )
    return {"id": image_id, "valid": valid, "message": msg}


@app.get("/api/evidence")
def list_evidence():
    rows = storage.list_images()
    for r in rows:
        r["url"] = f"/generated/images/{Path(r['stored_path']).name}"
    return {"images": rows, "counts": storage.counts()}


# ------------------------------------------------------------- raster analysis
@app.post("/api/scenes/generate")
def generate_scenes():
    """(Re)generate the before/after synthetic satellite scenes for this AAO."""
    _STATE["before"] = geo.generate_synthetic_scene(seed=1, degrade_region=False)
    _STATE["after"] = geo.generate_synthetic_scene(seed=1, degrade_region=True)
    geo.write_scene_geotiff(_STATE["before"], str(GENERATED_DIR / "scene_before.tif"))
    geo.write_scene_geotiff(_STATE["after"], str(GENERATED_DIR / "scene_after.tif"))
    return {"status": "generated", "files": ["scene_before.tif", "scene_after.tif"]}


@app.get("/api/analysis/indices")
def analysis_indices(period: str = "after"):
    before, after = _ensure_scenes()
    scene = before if period == "before" else after
    ndvi, ndwi = geo.compute_indices(scene)
    cls = geo.classify(ndvi, ndwi)
    return {
        "period": period,
        "class_stats": geo.class_stats(cls),
        "mean_ndvi": round(float(ndvi.mean()), 4),
        "mean_ndwi": round(float(ndwi.mean()), 4),
        "thematic_map_png_base64": geo.classification_png(cls),
        "bounds": geo.bounds_latlng(),
    }


@app.get("/api/analysis/change-detection")
def change_detection():
    before, after = _ensure_scenes()
    ndvi_b, ndwi_b = geo.compute_indices(before)
    ndvi_a, ndwi_a = geo.compute_indices(after)

    delta_ndvi = ndvi_a - ndvi_b
    delta_ndwi = ndwi_a - ndwi_b

    veg_before = float((ndvi_b > 0.3).sum())
    veg_after = float((ndvi_a > 0.3).sum())
    water_before = float((ndwi_b > 0.15).sum())
    water_after = float((ndwi_a > 0.15).sum())
    total = ndvi_b.size
    degraded_pct = round(100.0 * float((delta_ndvi < -0.12).sum()) / total, 2)

    stats = {
        "veg_change_pct": round(100.0 * (veg_after - veg_before) / total, 2),
        "water_change_pct": round(100.0 * (water_after - water_before) / total, 2),
        "degraded_pct": degraded_pct,
    }
    return {
        "stats": stats,
        "diff_map_png_base64": geo.diff_png(delta_ndvi),
        "bounds": geo.bounds_latlng(),
    }


@app.get("/api/analysis/hotspots")
def hotspots(top_n: int = 6):
    before, after = _ensure_scenes()
    ndvi_b, _ = geo.compute_indices(before)
    ndvi_a, _ = geo.compute_indices(after)
    spots = geo.find_hotspots(ndvi_b, ndvi_a, after.transform, top_n=top_n)
    return {"hotspots": spots}


# ------------------------------------------------------------------- report
@app.get("/api/report/generate")
def generate_report():
    before, after = _ensure_scenes()
    ndvi_a, ndwi_a = geo.compute_indices(after)
    cls = geo.classify(ndvi_a, ndwi_a)
    cstats = geo.class_stats(cls)

    ndvi_b, ndwi_b = geo.compute_indices(before)
    delta_ndvi = ndvi_a - ndvi_b
    total = ndvi_a.size
    change_stats = {
        "veg_change_pct": round(100.0 * ((ndvi_a > 0.3).sum() - (ndvi_b > 0.3).sum()) / total, 2),
        "water_change_pct": round(100.0 * ((ndwi_a > 0.15).sum() - (ndwi_b > 0.15).sum()) / total, 2),
        "degraded_pct": round(100.0 * float((delta_ndvi < -0.12).sum()) / total, 2),
    }
    spots = geo.find_hotspots(ndvi_b, ndvi_a, after.transform, top_n=6)
    ev_counts = storage.counts()

    out_path = GENERATED_DIR / "watershed_decision_report.pdf"
    report_mod.build_report(str(out_path), cstats, change_stats, spots, ev_counts)
    return FileResponse(str(out_path), filename="GeoWatershedAI_Decision_Report.pdf", media_type="application/pdf")


# Serve uploaded evidence images
app.mount("/generated/images", StaticFiles(directory=str(storage.IMAGES_DIR)), name="evidence-images")
