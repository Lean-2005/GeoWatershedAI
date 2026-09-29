const map = L.map("map").setView([19.96, 73.79], 13);
L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  attribution: "&copy; OpenStreetMap contributors",
  maxZoom: 18,
}).addTo(map);

const layers = {
  boundary: L.geoJSON(null, { style: { color: "#12406b", weight: 3, fillOpacity: 0.03 } }),
  drainage: L.geoJSON(null, { style: (f) => ({ color: "#2b6cb0", weight: f.properties.stream_order + 1 }) }),
  landuse: L.geoJSON(null, {
    style: (f) => {
      const colors = { agriculture: "#a3d977", forest: "#1e7d32", settlement: "#c9622a", barren: "#c9a06a" };
      return { color: colors[f.properties.class] || "#999", weight: 1, fillOpacity: 0.25 };
    },
  }),
  waterbodies: L.geoJSON(null, { style: { color: "#2b6cb0", fillColor: "#2b6cb0", fillOpacity: 0.5 } }),
  thematic: null, // ImageOverlay, created on demand
  change: null,   // ImageOverlay, created on demand
  hotspots: L.layerGroup(),
  evidence: L.layerGroup(),
};

for (const key of ["boundary", "drainage", "landuse", "waterbodies", "hotspots", "evidence"]) {
  layers[key].addTo(map);
}

function setStatus(ok, msg) {
  const el = document.getElementById("apiStatus");
  el.textContent = msg;
  el.className = "api-status " + (ok ? "ok" : "bad");
}

async function api(path, opts) {
  const res = await fetch(API_BASE + path, opts);
  if (!res.ok) throw new Error(`${path} -> ${res.status}`);
  return res;
}

async function loadStaticLayers() {
  try {
    const boundary = await (await api("/api/watershed/boundary")).json();
    layers.boundary.addData(boundary);
    map.fitBounds(layers.boundary.getBounds(), { padding: [20, 20] });

    const gis = await (await api("/api/watershed/layers")).json();
    layers.drainage.addData(gis.drainage);
    layers.landuse.addData(gis.landuse);
    layers.waterbodies.addData(gis.waterbodies);

    setStatus(true, "backend connected");
  } catch (e) {
    setStatus(false, "backend not reachable — start the FastAPI server");
    console.error(e);
  }
}
loadStaticLayers();
refreshEvidence();

// ---- layer toggles ----------------------------------------------------
const toggleMap = {
  layerBoundary: "boundary",
  layerDrainage: "drainage",
  layerLanduse: "landuse",
  layerWater: "waterbodies",
  layerHotspots: "hotspots",
  layerEvidence: "evidence",
};
for (const [id, key] of Object.entries(toggleMap)) {
  document.getElementById(id).addEventListener("change", (e) => {
    if (e.target.checked) layers[key].addTo(map);
    else map.removeLayer(layers[key]);
  });
}
document.getElementById("layerThematic").addEventListener("change", (e) => {
  if (!e.target.checked && layers.thematic) map.removeLayer(layers.thematic);
  else if (layers.thematic) layers.thematic.addTo(map);
});
document.getElementById("layerChange").addEventListener("change", (e) => {
  if (!e.target.checked && layers.change) map.removeLayer(layers.change);
  else if (layers.change) layers.change.addTo(map);
});

// ---- 1. generate scenes -------------------------------------------------
document.getElementById("btnGenerate").addEventListener("click", async () => {
  const btn = document.getElementById("btnGenerate");
  btn.textContent = "Generating…";
  try {
    await api("/api/scenes/generate", { method: "POST" });
    btn.textContent = "Scenes generated ✓";
  } catch (e) {
    btn.textContent = "Failed — is backend running?";
  }
  setTimeout(() => (btn.textContent = "Generate satellite scenes"), 1800);
});

// ---- 2. spectral index analysis -----------------------------------------
function renderStats(containerId, obj) {
  const rows = Object.entries(obj).map(([k, v]) => `<tr><td>${k}</td><td style="text-align:right">${v}</td></tr>`).join("");
  document.getElementById(containerId).innerHTML = `<table>${rows}</table>`;
}

async function runAnalysis(period) {
  const res = await (await api(`/api/analysis/indices?period=${period}`)).json();
  renderStats("indexStats", {
    period,
    "mean NDVI": res.mean_ndvi,
    "mean NDWI": res.mean_ndwi,
    ...res.class_stats,
  });
  if (layers.thematic) map.removeLayer(layers.thematic);
  layers.thematic = L.imageOverlay(`data:image/png;base64,${res.thematic_map_png_base64}`, res.bounds, { opacity: 0.75 });
  if (document.getElementById("layerThematic").checked) layers.thematic.addTo(map);
}
document.getElementById("btnAnalyzeBefore").addEventListener("click", () => runAnalysis("before"));
document.getElementById("btnAnalyzeAfter").addEventListener("click", () => runAnalysis("after"));

// ---- 3. change detection --------------------------------------------------
document.getElementById("btnChange").addEventListener("click", async () => {
  const res = await (await api("/api/analysis/change-detection")).json();
  renderStats("changeStats", res.stats);
  if (layers.change) map.removeLayer(layers.change);
  layers.change = L.imageOverlay(`data:image/png;base64,${res.diff_map_png_base64}`, res.bounds, { opacity: 0.8 });
  document.getElementById("layerChange").checked = true;
  layers.change.addTo(map);
});

// ---- 4. hotspots ------------------------------------------------------
document.getElementById("btnHotspots").addEventListener("click", async () => {
  const res = await (await api("/api/analysis/hotspots")).json();
  layers.hotspots.clearLayers();
  const list = document.getElementById("hotspotList");
  list.innerHTML = "";
  res.hotspots.forEach((h) => {
    const marker = L.circleMarker([h.lat, h.lon], {
      radius: 8 + h.rank * -0.5,
      color: "#c9622a",
      fillColor: "#c9622a",
      fillOpacity: 0.7,
    }).bindPopup(
      `<b>Priority zone #${h.rank}</b><br/>Severity: ${h.severity}<br/>Priority score: ${h.priority_score}<br/>${h.recommended_action}`
    );
    layers.hotspots.addLayer(marker);
    const li = document.createElement("li");
    li.textContent = `#${h.rank} — severity ${h.severity}, score ${h.priority_score} — ${h.recommended_action}`;
    list.appendChild(li);
  });
});

// ---- 5. evidence upload -------------------------------------------------
document.getElementById("evidenceForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const fd = new FormData();
  fd.append("file", document.getElementById("evFile").files[0]);
  fd.append("lat", document.getElementById("evLat").value);
  fd.append("lon", document.getElementById("evLon").value);
  fd.append("captured_on", document.getElementById("evDate").value);
  fd.append("notes", document.getElementById("evNotes").value);
  try {
    const res = await (await api("/api/evidence/upload", { method: "POST", body: fd })).json();
    document.getElementById("evidenceResult").innerHTML = res.valid
      ? `<span style="color:#1e7d32">✓ Validated and stored (id ${res.id})</span>`
      : `<span style="color:#b91c1c">✗ ${res.message}</span>`;
    refreshEvidence();
  } catch (err) {
    document.getElementById("evidenceResult").textContent = "Upload failed — is the backend running?";
  }
});

async function refreshEvidence() {
  try {
    const res = await (await api("/api/evidence")).json();
    layers.evidence.clearLayers();
    res.images.forEach((img) => {
      const marker = L.marker([img.lat, img.lon]).bindPopup(
        `<b>${img.filename}</b><br/>${img.captured_on || ""}<br/>${img.notes || ""}<br/>
         Status: ${img.valid ? "✓ valid" : "✗ " + img.validation_message}<br/>
         <img src="${API_BASE}${img.url}" style="max-width:180px;margin-top:4px;border-radius:4px" />`
      );
      layers.evidence.addLayer(marker);
    });
    document.getElementById("evidenceCounts").textContent =
      `${res.counts.total} uploaded · ${res.counts.valid} valid · ${res.counts.invalid} flagged`;
  } catch (e) {
    /* backend not up yet — ignore */
  }
}

// ---- 6. report ---------------------------------------------------------
document.getElementById("btnReport").addEventListener("click", async () => {
  const btn = document.getElementById("btnReport");
  btn.textContent = "Generating report…";
  try {
    const res = await api("/api/report/generate");
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "GeoWatershedAI_Decision_Report.pdf";
    a.click();
    btn.textContent = "Report downloaded ✓";
  } catch (e) {
    btn.textContent = "Failed — is backend running?";
  }
  setTimeout(() => (btn.textContent = "Generate PDF report"), 1800);
});
