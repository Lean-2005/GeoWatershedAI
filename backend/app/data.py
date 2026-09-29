"""
Sample GIS layers for the GeoWatershed AI demo.

In production these would come from PostGIS / uploaded shapefiles / WFS
services. For this runnable prototype we ship a realistic synthetic
watershed (loosely modelled on a small watershed in the Deccan plateau,
Maharashtra) so the whole pipeline works end-to-end without needing any
external data downloads or a spatial database server.
"""

# Bounding box of the demo watershed: (min_lon, min_lat, max_lon, max_lat)
WATERSHED_BBOX = (73.72, 19.90, 73.86, 20.02)

WATERSHED_NAME = "Devnadi Micro-Watershed (Demo AOI)"
WATERSHED_DISTRICT = "Nashik, Maharashtra"


def watershed_boundary_geojson():
    minx, miny, maxx, maxy = WATERSHED_BBOX
    # A slightly irregular polygon (not a perfect rectangle) so it reads as
    # a real catchment boundary rather than a bounding box.
    coords = [
        [minx + 0.01, miny],
        [maxx - 0.02, miny + 0.005],
        [maxx, miny + 0.05],
        [maxx - 0.01, maxy - 0.01],
        [maxx - 0.05, maxy],
        [minx + 0.03, maxy - 0.005],
        [minx, maxy - 0.06],
        [minx + 0.005, miny + 0.03],
        [minx + 0.01, miny],
    ]
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "name": WATERSHED_NAME,
                    "district": WATERSHED_DISTRICT,
                    "area_sq_km": 118.4,
                },
                "geometry": {"type": "Polygon", "coordinates": [coords]},
            }
        ],
    }


def drainage_network_geojson():
    """A simple dendritic drainage network (main stream + tributaries)."""
    minx, miny, maxx, maxy = WATERSHED_BBOX
    cx = (minx + maxx) / 2
    main_stream = [
        [minx + 0.005, miny + 0.03],
        [cx - 0.02, miny + 0.10],
        [cx, (miny + maxy) / 2],
        [cx + 0.015, maxy - 0.08],
        [maxx - 0.02, maxy - 0.02],
    ]
    trib1 = [[minx + 0.06, miny + 0.005], [cx - 0.02, miny + 0.10]]
    trib2 = [[maxx - 0.005, miny + 0.09], [cx, (miny + maxy) / 2]]
    trib3 = [[minx + 0.02, maxy - 0.02], [cx + 0.015, maxy - 0.08]]
    features = []
    for name, order, coords in [
        ("Main Stream", 3, main_stream),
        ("Tributary A", 1, trib1),
        ("Tributary B", 1, trib2),
        ("Tributary C", 2, trib3),
    ]:
        features.append(
            {
                "type": "Feature",
                "properties": {"name": name, "stream_order": order},
                "geometry": {"type": "LineString", "coordinates": coords},
            }
        )
    return {"type": "FeatureCollection", "features": features}


def landuse_geojson():
    """Coarse land-use zones used for context layers on the map."""
    minx, miny, maxx, maxy = WATERSHED_BBOX
    dx, dy = (maxx - minx), (maxy - miny)

    def box(fx0, fy0, fx1, fy1):
        return [
            [minx + fx0 * dx, miny + fy0 * dy],
            [minx + fx1 * dx, miny + fy0 * dy],
            [minx + fx1 * dx, miny + fy1 * dy],
            [minx + fx0 * dx, miny + fy1 * dy],
            [minx + fx0 * dx, miny + fy0 * dy],
        ]

    zones = [
        ("Agricultural land", "agriculture", box(0.05, 0.05, 0.55, 0.45)),
        ("Forest / scrub", "forest", box(0.55, 0.45, 0.95, 0.90)),
        ("Settlement", "settlement", box(0.10, 0.55, 0.35, 0.80)),
        ("Barren / degraded land", "barren", box(0.40, 0.55, 0.65, 0.75)),
    ]
    features = [
        {
            "type": "Feature",
            "properties": {"name": n, "class": c},
            "geometry": {"type": "Polygon", "coordinates": [coords]},
        }
        for n, c, coords in zones
    ]
    return {"type": "FeatureCollection", "features": features}


def waterbodies_geojson():
    minx, miny, maxx, maxy = WATERSHED_BBOX
    dx, dy = (maxx - minx), (maxy - miny)
    cx, cy = minx + 0.72 * dx, miny + 0.18 * dy
    r = 0.012
    import math

    ring = [
        [cx + r * math.cos(t), cy + r * 0.6 * math.sin(t)]
        for t in [i * 2 * math.pi / 24 for i in range(25)]
    ]
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"name": "Percolation Tank", "type": "reservoir"},
                "geometry": {"type": "Polygon", "coordinates": [ring]},
            }
        ],
    }
