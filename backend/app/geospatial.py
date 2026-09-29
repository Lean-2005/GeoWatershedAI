"""
Geospatial engine for GeoWatershed AI.

Implements the "GEOSPATIAL ENGINE" + "ANALYSIS" stages from the system
architecture:
  - synthetic Sentinel-2-like multispectral raster generation
    (stand-in for real satellite ingestion, so the demo needs no
    external data download / API keys)
  - NDVI / NDWI spectral index computation (rasterio + numpy)
  - land/water/vegetation/bare classification
  - before/after change detection
  - hotspot clustering of the highest-priority degraded zones
  - thematic map rendering to PNG for the web map overlay

Swapping `generate_synthetic_scene()` for a real Sentinel-2 / Landsat
GeoTIFF reader (rasterio.open on a real file) plugs this straight into
live data — every downstream function only cares about the (bands, transform,
crs) it receives, not where they came from.
"""
from __future__ import annotations

import io
import base64
from dataclasses import dataclass

import numpy as np
import rasterio
from rasterio.transform import from_bounds
from scipy import ndimage
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from .data import WATERSHED_BBOX

WIDTH, HEIGHT = 220, 200  # raster grid resolution for the demo AOI


@dataclass
class Scene:
    red: np.ndarray
    green: np.ndarray
    blue: np.ndarray
    nir: np.ndarray
    transform: any
    crs: str = "EPSG:4326"


def _smooth_noise(seed: int, scale: float = 18.0) -> np.ndarray:
    """Cheap Perlin-ish smooth noise field without extra dependencies."""
    rng = np.random.default_rng(seed)
    small = rng.random((max(4, int(HEIGHT / scale)), max(4, int(WIDTH / scale))))
    field = ndimage.zoom(small, (HEIGHT / small.shape[0], WIDTH / small.shape[1]), order=3)
    field = ndimage.gaussian_filter(field, sigma=2.0)
    field = (field - field.min()) / (field.max() - field.min() + 1e-9)
    return field


def generate_synthetic_scene(seed: int = 1, degrade_region: bool = False) -> Scene:
    """
    Generate a synthetic 4-band (R, G, B, NIR) scene over the demo watershed
    bounding box. `degrade_region` simulates vegetation loss / drying of a
    sub-area, used to build the "after" scene for change detection so the
    demo has a realistic, reproducible signal to detect.
    """
    veg = _smooth_noise(seed, scale=14)          # vegetation density field
    moisture = _smooth_noise(seed + 1, scale=22)  # soil/water moisture field
    urban = _smooth_noise(seed + 2, scale=30)

    if degrade_region:
        yy, xx = np.mgrid[0:HEIGHT, 0:WIDTH]
        cy, cx = HEIGHT * 0.62, WIDTH * 0.5
        mask = ((yy - cy) ** 2) / (HEIGHT * 0.18) ** 2 + ((xx - cx) ** 2) / (WIDTH * 0.22) ** 2 <= 1
        veg = veg.copy()
        veg[mask] *= 0.35
        moisture = moisture.copy()
        moisture[mask] *= 0.6

    water_mask = moisture > 0.82

    nir = 0.15 + 0.65 * veg + 0.05 * (1 - urban)
    red = 0.30 - 0.18 * veg + 0.10 * urban
    green = 0.20 + 0.10 * veg + 0.05 * moisture
    blue = 0.18 + 0.04 * moisture - 0.05 * veg

    nir[water_mask] = 0.06 + 0.02 * moisture[water_mask]
    red[water_mask] = 0.05
    green[water_mask] = 0.09
    blue[water_mask] = 0.16

    def clip(a):
        return np.clip(a, 0.01, 0.95).astype("float32")

    transform = from_bounds(*WATERSHED_BBOX, WIDTH, HEIGHT)
    return Scene(clip(red), clip(green), clip(blue), clip(nir), transform)


def write_scene_geotiff(scene: Scene, path: str):
    with rasterio.open(
        path, "w", driver="GTiff", height=HEIGHT, width=WIDTH, count=4,
        dtype="float32", crs=scene.crs, transform=scene.transform,
    ) as dst:
        dst.write(scene.red, 1)
        dst.write(scene.green, 2)
        dst.write(scene.blue, 3)
        dst.write(scene.nir, 4)


def read_scene_geotiff(path: str) -> Scene:
    with rasterio.open(path) as src:
        red, green, blue, nir = src.read(1), src.read(2), src.read(3), src.read(4)
        return Scene(red, green, blue, nir, src.transform, str(src.crs))


def compute_indices(scene: Scene):
    ndvi = (scene.nir - scene.red) / (scene.nir + scene.red + 1e-6)
    ndwi = (scene.green - scene.nir) / (scene.green + scene.nir + 1e-6)
    return ndvi.astype("float32"), ndwi.astype("float32")


def classify(ndvi: np.ndarray, ndwi: np.ndarray) -> np.ndarray:
    """
    0 = water, 1 = dense vegetation, 2 = sparse vegetation/agriculture,
    3 = barren/urban
    """
    cls = np.full(ndvi.shape, 3, dtype="uint8")
    cls[ndvi > 0.15] = 2
    cls[ndvi > 0.45] = 1
    cls[ndwi > 0.15] = 0
    return cls


CLASS_NAMES = {0: "Water body", 1: "Dense vegetation", 2: "Sparse vegetation / cropland", 3: "Barren / built-up"}
CLASS_COLORS = {0: "#2b6cb0", 1: "#1e7d32", 2: "#a3d977", 3: "#c9a06a"}


def class_stats(cls: np.ndarray) -> dict:
    total = cls.size
    return {
        CLASS_NAMES[k]: round(100.0 * float((cls == k).sum()) / total, 2)
        for k in CLASS_NAMES
    }


def _array_to_png_b64(rgba: np.ndarray) -> str:
    from PIL import Image

    img = Image.fromarray(rgba, mode="RGBA")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def classification_png(cls: np.ndarray) -> str:
    rgba = np.zeros((*cls.shape, 4), dtype="uint8")
    for k, hexcolor in CLASS_COLORS.items():
        r = int(hexcolor[1:3], 16)
        g = int(hexcolor[3:5], 16)
        b = int(hexcolor[5:7], 16)
        rgba[cls == k] = [r, g, b, 200]
    return _array_to_png_b64(rgba)


def diff_png(delta: np.ndarray, vmin=-0.5, vmax=0.5) -> str:
    """Red = loss (e.g. vegetation loss / drying), green = gain."""
    norm = np.clip((delta - vmin) / (vmax - vmin), 0, 1)
    cmap = plt.get_cmap("RdYlGn")
    rgba = (cmap(norm) * 255).astype("uint8")
    # make near-zero change transparent so the base map shows through
    alpha = (np.abs(delta) > 0.05) * 200
    rgba[..., 3] = alpha.astype("uint8")
    return _array_to_png_b64(rgba)


def bounds_latlng() -> list:
    minx, miny, maxx, maxy = WATERSHED_BBOX
    # Leaflet ImageOverlay bounds: [[south, west], [north, east]]
    return [[miny, minx], [maxy, maxx]]


def pixel_to_lonlat(row: int, col: int, transform) -> tuple:
    lon, lat = rasterio.transform.xy(transform, row, col)
    return lon, lat


def find_hotspots(ndvi_before: np.ndarray, ndvi_after: np.ndarray, transform, top_n=6) -> list:
    """
    Connected-component clustering of pixels with significant vegetation
    loss between two dates -> ranked list of intervention-priority zones.
    """
    delta = ndvi_after - ndvi_before
    degraded = delta < -0.12
    labeled, n = ndimage.label(degraded)
    hotspots = []
    for label_id in range(1, n + 1):
        ys, xs = np.where(labeled == label_id)
        if len(ys) < 8:  # ignore noise-sized specks
            continue
        severity = float(-delta[ys, xs].mean())
        area_px = len(ys)
        cy, cx = ys.mean(), xs.mean()
        lon, lat = pixel_to_lonlat(cy, cx, transform)
        hotspots.append(
            {
                "lat": round(float(lat), 5),
                "lon": round(float(lon), 5),
                "severity": round(severity, 3),
                "area_px": int(area_px),
                "priority_score": round(severity * np.sqrt(area_px), 3),
            }
        )
    hotspots.sort(key=lambda h: h["priority_score"], reverse=True)
    for i, h in enumerate(hotspots[:top_n], start=1):
        h["rank"] = i
        h["recommended_action"] = (
            "Check-dam / afforestation intervention recommended"
            if h["severity"] > 0.2
            else "Field verification recommended"
        )
    return hotspots[:top_n]
