const PALETTE = [
  "#5b9bd5", "#ed7d31", "#a5a5a5", "#70ad47", "#ffc000", "#4472c4",
  "#ff6f91", "#00c2a8", "#9d6bd7", "#e2708a", "#4fbc9f", "#f6c244",
];

const nameColorMap = {};
let paletteIndex = 0;
let layerColors = {};

const ACI_COLORS = {
  1: "#ff0000", 2: "#ffff00", 3: "#00ff00", 4: "#00ffff", 5: "#0000ff",
  6: "#ff00ff", 7: "#000000", 8: "#808080", 9: "#c0c0c0", 10: "#ff0000",
  30: "#ff8000", 40: "#ff8000", 50: "#ff0080", 60: "#0080ff", 90: "#00ff80",
  130: "#8000ff", 210: "#ff0080", 250: "#202020", 251: "#404040",
  252: "#606060", 253: "#808080", 254: "#a0a0a0", 255: "#ffffff",
};

function aciToHex(color) {
  return ACI_COLORS[color] || "#5b9bd5";
}

function colorFor(name) {
  if (!nameColorMap[name]) {
    nameColorMap[name] = PALETTE[paletteIndex % PALETTE.length];
    paletteIndex++;
  }
  return nameColorMap[name];
}

let lastResult = null;
let currentJobId = null;
let units = "mm";

function fmt(n) {
  return n % 1 === 0 ? String(n) : String(Math.round(n * 100) / 100);
}

function escapeHtml(value) {
  return String(value).replace(/[&<>'"]/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    "'": "&#39;",
    '"': "&quot;",
  }[char]));
}

function renderEdgeDistances(pieces, savedDistances) {
  const container = document.getElementById("edgeDistanceRows");
  const hint = document.getElementById("edgeDistanceHint");
  const layerSet = new Set();
  (pieces || []).forEach((p) => (p.lines || []).forEach((s) => layerSet.add(s[0])));
  const kerf = parseFloat(document.getElementById("kerf").value) || 0;
  container.innerHTML = "";
  if (!layerSet.size) {
    hint.hidden = false;
    return;
  }
  hint.hidden = true;
  layerSet.forEach((layer) => {
    const row = document.createElement("label");
    row.className = "edge-row";
    row.dataset.layer = layer;
    const color = layerColors[layer] !== undefined
      ? aciToHex(layerColors[layer])
      : "#888888";
    const value = savedDistances && savedDistances[layer] !== undefined
      ? savedDistances[layer]
      : kerf;
    row.innerHTML = `<span><span class="color-dot" style="background:${color}"></span> ${escapeHtml(layer)}</span>
      <input type="number" min="0" step="0.5" value="${value}">`;
    container.appendChild(row);
  });
}

function collectEdgeDistances() {
  const out = {};
  document.querySelectorAll("#edgeDistanceRows .edge-row").forEach((row) => {
    const layer = row.dataset.layer;
    const value = parseFloat(row.querySelector("input").value);
    if (layer && value >= 0) out[layer] = value;
  });
  return out;
}

function renumberPriorities() {
  ["#pieceRows", "#slabRows"].forEach((selector) => {
    const rows = [...document.querySelectorAll(`${selector} .item-line`)];
    rows.forEach((row, index) => {
      const prio = row.querySelector(".prio");
      if (prio) prio.value = index + 1;
    });
  });
}

function itemLine(template, polygon, holes) {
  const line = document.createElement("div");
  line.className = "item-line with-prio";
  line.innerHTML = `
    <input class="name" placeholder="Nombre" value="${escapeHtml(template.name)}">
    <input class="w" type="number" placeholder="Ancho" value="${template.width}">
    <input class="h" type="number" placeholder="Alto" value="${template.height}">
    <input class="qty" type="number" placeholder="Cant." value="${template.quantity}" min="1">
    <input class="prio" type="number" placeholder="Prio" value="${template.priority || ""}" min="0" title="Prioridad: 1 primero">
    <span class="arrows"><button class="up" title="Subir">&uarr;</button><button class="down" title="Bajar">&darr;</button></span>
    <button class="del" title="Quitar">&times;</button>
    <button class="dup" title="Duplicar">&plus;</button>`;
  const up = line.querySelector(".up");
  const down = line.querySelector(".down");
  up.addEventListener("click", () => {
    const prev = line.previousElementSibling;
    if (prev) {
      line.parentElement.insertBefore(line, prev);
      renumberPriorities();
    }
  });
  down.addEventListener("click", () => {
    const next = line.nextElementSibling;
    if (next) {
      line.parentElement.insertBefore(next, line);
      renumberPriorities();
    }
  });
  if (polygon) {
    line.dataset.polygon = JSON.stringify(polygon);
    line.dataset.holes = JSON.stringify(holes || []);
    line.classList.add("shape");
    line.title = "Pieza de forma libre cargada de DXF";
  }
  if (template.obstacles) {
    line.dataset.obstacles = JSON.stringify(template.obstacles);
    line.classList.add("shape");
    line.title = "Chapa con perforaciones internas";
  }
  if (template.lines) {
    line.dataset.lines = JSON.stringify(template.lines);
  }
  line.querySelector(".del").addEventListener("click", () => line.remove());
  line.querySelector(".dup").addEventListener("click", () => {
    const parent = line.parentElement;
    const clone = itemLine(
      { name: template.name, width: template.width, height: template.height, quantity: 1, priority: template.priority },
      polygon,
      holes
    );
    parent.insertBefore(clone, line.nextSibling);
    renumberPriorities();
  });
  return line;
}

function defaultPieces() {
  return [];
}

function defaultSlabs() {
  return [];
}

function collectRows(container) {
  return [...container.querySelectorAll(".item-line")].map((line) => {
    const row = {
      name: line.querySelector(".name").value.trim() || "Pieza",
      width: parseFloat(line.querySelector(".w").value) || 0,
      height: parseFloat(line.querySelector(".h").value) || 0,
      quantity: parseInt(line.querySelector(".qty").value, 10) || 1,
      priority: parseInt(line.querySelector(".prio")?.value, 10) || 0,
    };
    if (line.dataset.polygon) {
      row.polygon = JSON.parse(line.dataset.polygon);
      if (line.dataset.holes) row.holes = JSON.parse(line.dataset.holes);
    }
    if (line.dataset.obstacles) row.holes = JSON.parse(line.dataset.obstacles);
    if (line.dataset.lines) row.lines = JSON.parse(line.dataset.lines);
    return row;
  });
}

async function checkLicense() {
  const overlay = document.getElementById("licenseOverlay");
  const badge = document.getElementById("licenseBadge");
  const openBtn = document.getElementById("licenseOpenBtn");
  try {
    const res = await fetch("/api/license/status");
    if (!res.ok) return;
    const estado = await res.json();
    if (estado.status === "licensed") {
      overlay.hidden = true;
      badge.hidden = false;
      badge.textContent = `Licencia: ${estado.licensed_to}`;
      badge.className = "license-badge ok";
      openBtn.hidden = true;
    } else if (estado.status === "trial") {
      overlay.hidden = true;
      badge.hidden = false;
      badge.textContent = `Prueba: ${estado.days_left} día(s) restante(s)`;
      badge.className = "license-badge trial";
      openBtn.hidden = false;
    } else {
      badge.hidden = true;
      openBtn.hidden = true;
      showLicenseModal(
        "Licencia vencida",
        estado.reason || "El período de prueba terminó. Ingresá tu clave de activación para seguir usando la aplicación.",
        false
      );
    }
  } catch (_) {
    // Si no responde el estado, se deja pasar (modo local).
  }
}

function showLicenseModal(title, message, cancellable) {
  document.getElementById("licenseTitle").textContent = title;
  document.getElementById("licenseMessage").textContent = message;
  document.getElementById("licenseError").hidden = true;
  document.getElementById("licenseKey").value = "";
  document.getElementById("licenseCancelBtn").hidden = !cancellable;
  document.getElementById("licenseOverlay").hidden = false;
  document.getElementById("licenseKey").focus();
}

async function activateLicense() {
  const key = document.getElementById("licenseKey").value.trim();
  const error = document.getElementById("licenseError");
  if (!key) {
    error.hidden = false;
    error.textContent = "Ingresá la clave de licencia.";
    return;
  }
  try {
    const res = await fetch("/api/license/activate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ key }),
    });
    const data = await res.json();
    if (data.ok) {
      error.hidden = true;
      document.getElementById("licenseOverlay").hidden = true;
      checkLicense();
      alert(data.message);
    } else {
      error.hidden = false;
      error.textContent = data.message;
    }
  } catch (err) {
    error.hidden = false;
    error.textContent = "Error: " + err.message;
  }
}

function init() {
  const pieceRows = document.getElementById("pieceRows");
  const slabRows = document.getElementById("slabRows");

  defaultPieces().forEach((p) => pieceRows.appendChild(itemLine(p)));
  defaultSlabs().forEach((s) => slabRows.appendChild(itemLine(s)));

  document.getElementById("addPiece").addEventListener("click", () =>
    pieceRows.appendChild(itemLine({ name: "Pieza", width: 500, height: 500, quantity: 1 })));
  document.getElementById("addSlab").addEventListener("click", () =>
    slabRows.appendChild(itemLine({ name: "Plancha", width: 3000, height: 1500, quantity: 1 })));

  document.getElementById("optimizeBtn").addEventListener("click", optimize);
  document.getElementById("exportBtn").addEventListener("click", exportDxf);
  document.getElementById("licenseActivateBtn").addEventListener("click", activateLicense);
  document.getElementById("licenseKey").addEventListener("keydown", (event) => {
    if (event.key === "Enter") activateLicense();
  });
  document.getElementById("licenseOpenBtn").addEventListener("click", () => {
    showLicenseModal(
      "Activar licencia",
      "Tu licencia de prueba sigue activa. Si ya tenés la clave, podés activar la licencia permanente ahora.",
      true
    );
  });
  document.getElementById("licenseCancelBtn").addEventListener("click", () => {
    document.getElementById("licenseOverlay").hidden = true;
  });
  document.getElementById("units").addEventListener("change", (event) => {
    units = event.target.value;
    if (lastResult) renderResults(lastResult);
  });
  document.getElementById("dxfFile").addEventListener("change", loadDxf);
  document.getElementById("slabDxfFile").addEventListener("change", loadSlabDxf);
  document.getElementById("saveJobBtn").addEventListener("click", saveJob);
  document.getElementById("jobSelect").addEventListener("change", (event) => {
    if (event.target.value) loadJob(Number(event.target.value));
  });
  document.getElementById("clearDxf").addEventListener("click", () => {
    document.getElementById("pieceRows").innerHTML = "";
    defaultPieces().forEach((p) => pieceRows.appendChild(itemLine(p)));
    document.getElementById("dxfInfo").hidden = true;
    document.getElementById("dxfFile").value = "";
  });
  document.getElementById("clearPieces").addEventListener("click", () => {
    document.getElementById("pieceRows").innerHTML = "";
  });
  document.getElementById("clearSlabs").addEventListener("click", () => {
    document.getElementById("slabRows").innerHTML = "";
  });
  document.getElementById("resetDefaults").addEventListener("click", () => {
    document.getElementById("pieceRows").innerHTML = "";
    document.getElementById("slabRows").innerHTML = "";
    defaultPieces().forEach((p) => pieceRows.appendChild(itemLine(p)));
    defaultSlabs().forEach((s) => slabRows.appendChild(itemLine(s)));
    document.getElementById("dxfInfo").hidden = true;
    document.getElementById("dxfFile").value = "";
    layerColors = {};
    renderEdgeDistances([]);
  });

  refreshJobs();
  checkLicense();
}

function currentPayload() {
  return {
    pieces: collectRows(document.getElementById("pieceRows")),
    slabs: collectRows(document.getElementById("slabRows")),
    kerf: parseFloat(document.getElementById("kerf").value) || 0,
    allow_rotation: document.getElementById("allowRotation").checked,
    intensive: document.getElementById("intensive").checked,
    layers_colors: layerColors,
    edge_distances: collectEdgeDistances(),
    units,
  };
}

async function refreshJobs() {
  try {
    const res = await fetch("/api/jobs");
    if (!res.ok) return;
    const jobs = await res.json();
    const select = document.getElementById("jobSelect");
    select.innerHTML = '<option value="">Cargar trabajo...</option>';
    jobs.forEach((job) => {
      const option = document.createElement("option");
      option.value = job.id;
      option.textContent = `${job.name} (#${job.id})`;
      select.appendChild(option);
    });
  } catch (_) {
  }
}

async function saveJob() {
  const name = document.getElementById("jobName").value.trim();
  if (!name) {
    alert("Ingres\u00e1 un nombre para el trabajo.");
    return;
  }
  try {
    const res = await fetch("/api/jobs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, payload: currentPayload(), job_id: currentJobId }),
    });
    if (!res.ok) throw new Error(await res.text());
    const job = await res.json();
    currentJobId = job.id;
    document.getElementById("jobName").value = job.name;
    await refreshJobs();
    alert("Trabajo guardado.");
  } catch (err) {
    alert("Error al guardar: " + err.message);
  }
}

async function loadJob(jobId) {
  try {
    const res = await fetch(`/api/jobs/${jobId}`);
    if (!res.ok) throw new Error(await res.text());
    const job = await res.json();
    const payload = job.payload;
    const pieceRows = document.getElementById("pieceRows");
    const slabRows = document.getElementById("slabRows");
    pieceRows.innerHTML = "";
    slabRows.innerHTML = "";
    payload.pieces.forEach((piece) => pieceRows.appendChild(itemLine(piece, piece.polygon, piece.holes)));
    payload.slabs.forEach((slab) => slabRows.appendChild(itemLine(slab)));
    document.getElementById("kerf").value = payload.kerf ?? 0;
    document.getElementById("allowRotation").checked = payload.allow_rotation !== false;
    document.getElementById("intensive").checked = payload.intensive === true;
    layerColors = payload.layers_colors || {};
    renderEdgeDistances(payload.pieces, payload.edge_distances);
    document.getElementById("jobName").value = job.name;
    currentJobId = job.id;
    document.getElementById("jobSelect").value = String(job.id);
  } catch (err) {
    alert("Error al cargar: " + err.message);
  }
}

async function loadDxf(event) {
  const files = [...event.target.files];
  if (!files.length) return;
  const status = document.getElementById("dxfInfo");
  status.hidden = false;
  status.className = "dxf-info";
  const pieceRows = document.getElementById("pieceRows");
  let filesOk = 0;
  let totalPieces = 0;
  let totalArea = 0;
  const errors = [];
  for (const file of files) {
    status.textContent = `Leyendo ${file.name}...`;
    try {
      const fd = new FormData();
      fd.append("file", file);
      const res = await fetch("/api/dxf-parse", { method: "POST", body: fd });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      if (!data.pieces.length) {
        errors.push(`${file.name}: no se encontraron piezas cerradas`);
        continue;
      }
      data.pieces.forEach((p) =>
        pieceRows.appendChild(itemLine(
          { name: p.name, width: p.width, height: p.height, quantity: p.quantity || 1, lines: p.lines },
          p.polygon, p.holes)));
      Object.assign(layerColors, data.stats.layers_colors || {});
      filesOk += 1;
      totalPieces += data.pieces.length;
      totalArea += data.stats.total_area || 0;
    } catch (err) {
      errors.push(`${file.name}: ${err.message}`);
    }
  }
  event.target.value = "";
  renderEdgeDistances(collectRows(pieceRows));
  const m2 = (totalArea / 1e6).toFixed(3);
  let message = `${filesOk} archivo(s) leído(s), ${totalPieces} piezas agregadas (${m2} m\u00b2 total).`;
  if (errors.length) message += " Errores: " + errors.join(" | ");
  status.className = errors.length && !filesOk ? "dxf-info error" : "dxf-info ok";
  status.textContent = message;
}

async function loadSlabDxf(event) {
  const files = [...event.target.files];
  if (!files.length) return;
  const status = document.getElementById("slabDxfInfo");
  status.hidden = false;
  status.className = "dxf-info";
  const slabRows = document.getElementById("slabRows");
  let ok = 0;
  const errors = [];
  for (const file of files) {
    status.textContent = `Leyendo chapa ${file.name}...`;
    try {
      const fd = new FormData();
      fd.append("file", file);
      const res = await fetch("/api/slab-parse", { method: "POST", body: fd });
      if (!res.ok) throw new Error(await res.text());
      const slab = await res.json();
      if (slab.error) throw new Error(slab.error);
      slabRows.appendChild(itemLine({
        name: slab.name,
        width: slab.width,
        height: slab.height,
        quantity: 1,
        obstacles: slab.holes,
      }));
      ok += 1;
    } catch (err) {
      errors.push(`${file.name}: ${err.message}`);
    }
  }
  event.target.value = "";
  let message = `${ok} chapa(s) agregada(s).`;
  if (errors.length) message += " Errores: " + errors.join(" | ");
  status.className = errors.length && !ok ? "dxf-info error" : "dxf-info ok";
  status.textContent = message;
}

async function optimize() {
  const pieces = collectRows(document.getElementById("pieceRows"))
    .filter((p) => p.width > 0 && p.height > 0);
  const slabs = collectRows(document.getElementById("slabRows"))
    .filter((s) => s.width > 0 && s.height > 0);

  if (!pieces.length || !slabs.length) {
    alert("Agrega al menos una pieza y una plancha con medidas v\u00e1lidas.");
    return;
  }

  const btn = document.getElementById("optimizeBtn");
  const statusEl = document.getElementById("optimizeStatus");
  btn.disabled = true;
  btn.textContent = "Optimizando...";
  statusEl.hidden = false;
  statusEl.textContent = "Enviando cálculo...";
  const startedAt = Date.now();

  try {
    const res = await fetch("/api/optimize-async", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        pieces,
        slabs,
        kerf: parseFloat(document.getElementById("kerf").value) || 0,
        allow_rotation: document.getElementById("allowRotation").checked,
        intensive: document.getElementById("intensive").checked,
        layers_colors: layerColors,
        edge_distances: collectEdgeDistances(),
      }),
    });
    if (!res.ok) throw new Error(await res.text());
    const { job_id } = await res.json();

    let data = null;
    while (true) {
      await new Promise((resolve) => setTimeout(resolve, 3000));
      const seconds = Math.round((Date.now() - startedAt) / 1000);
      statusEl.textContent =
        `Calculando el mejor agrupamiento... ${seconds}s. Piezas grandes pueden tardar varios minutos.`;
      const statusRes = await fetch(`/api/optimize-async/${job_id}`);
      if (!statusRes.ok) throw new Error(await statusRes.text());
      const job = await statusRes.json();
      if (job.status === "done") {
        data = job.result;
        break;
      }
      if (job.status === "error") {
        throw new Error(job.error || "Error en la optimización");
      }
    }

    lastResult = data;
    paletteIndex = 0;
    for (const k of Object.keys(nameColorMap)) delete nameColorMap[k];
    const seconds = ((Date.now() - startedAt) / 1000).toFixed(1);
    statusEl.textContent = `Optimización completada en ${seconds}s.`;
    statusEl.hidden = true;
    renderResults(data);
  } catch (err) {
    alert("Error: " + err.message);
  } finally {
    btn.disabled = false;
    btn.textContent = "Optimizar corte";
  }
}

async function exportDxf() {
  if (!lastResult) {
    alert("Primero ejecut\u00e1 la optimizaci\u00f3n.");
    return;
  }
  const isDesktop = typeof window.pywebview !== "undefined";
  try {
    const res = await fetch(isDesktop ? "/api/export-dxf-save" : "/api/export-dxf", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        slabs_used: lastResult.slabs_used,
        kerf: lastResult.kerf,
        layers_colors: lastResult.layers_colors || layerColors,
      }),
    });
    if (!res.ok) throw new Error(await res.text());
    if (isDesktop) {
      const data = await res.json();
      alert("DXF guardado en:\n" + data.files.join("\n"));
      return;
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = res.headers.get("Content-Type")?.includes("zip")
      ? "cortes_optimizado.zip"
      : "corte_optimizado.dxf";
    a.click();
    URL.revokeObjectURL(url);
  } catch (err) {
    alert("Error al exportar: " + err.message);
  }
}

function fmt(n) {
  return n % 1 === 0 ? String(n) : String(Math.round(n * 100) / 100);
}

function renderResults(data) {
  const results = document.getElementById("results");
  results.hidden = false;

  const validation = document.getElementById("validation");
  if (data.validation && !data.validation.valid) {
    validation.hidden = false;
    validation.className = "validation error";
    validation.textContent = "Revisar resultado: " + data.validation.errors.join("; ");
  } else {
    validation.hidden = false;
    validation.className = "validation ok";
    validation.textContent = "Geometr\u00eda validada: sin solapamientos ni piezas fuera de plancha.";
  }

  const unplacedAlert = document.getElementById("unplacedAlert");
  if (data.pieces_unplaced) {
    const grouped = {};
    data.unplaced.forEach((p) => {
      const key = `${p.name} ${p.width}x${p.height}`;
      grouped[key] = (grouped[key] || 0) + 1;
    });
    const items = Object.entries(grouped)
      .map(([k, n]) => `<div>${n} \u00d7 ${escapeHtml(k)} mm</div>`)
      .join("");
    unplacedAlert.hidden = false;
    unplacedAlert.innerHTML =
      `<div class="alert-title">\u26a0 ${data.pieces_unplaced} pieza(s) NO se pudieron colocar por falta de espacio</div>` +
      `<div class="alert-list">${items}</div>` +
      `<div style="margin-top:6px;opacity:0.9">Verific\u00e1 que las piezas entren en alguna plancha o aument\u00e1 la cantidad/tama\u00f1o de planchas disponibles.</div>`;
  } else {
    unplacedAlert.hidden = true;
  }

  const kerfInfo = data.kerf > 0
    ? (data.kerf % 1 === 0 ? `${data.kerf} mm hoja` : `${data.kerf} mm hoja`)
    : "sin hoja";

  document.getElementById("summary").innerHTML = [
    ["Piezas colocadas", `${data.pieces_placed}/${data.total_pieces}`],
    ["Utilizaci\u00f3n", `${data.global_utilization}%`],
    ["Planchas usadas", `${data.slabs_used.length}`],
    ["\u00c1rea colocada", `${(data.placed_area / 1e6).toFixed(3)} m\u00b2`],
    ["Desperdicio total", `${(data.total_waste / 1e6).toFixed(3)} m\u00b2`],
    ["Corte (kerf)", kerfInfo],
  ].map(([label, value]) => `<div class="stat"><div class="value">${value}</div><div class="label">${label}</div></div>`).join("");

  const slabsEl = document.getElementById("slabs");
  slabsEl.innerHTML = "";

  data.slabs_used.forEach((slab) => {
    const maxDim = Math.max(slab.width, slab.height);
    const card = document.createElement("div");
    card.className = "slab-card";

    const head = document.createElement("div");
    head.className = "slab-head";
    head.innerHTML = `<span><strong>${escapeHtml(slab.name)}</strong> &middot; ${fmt(slab.width)} \u00d7 ${fmt(slab.height)} mm &middot; ${slab.pieces.length} piezas</span>
      <span class="util">Utilizaci\u00f3n: ${slab.utilization}% &middot; Desperdicio: ${(slab.waste_area / 1e6).toFixed(3)} m\u00b2</span>`;
    card.appendChild(head);

    const wrap = document.createElement("div");
    wrap.className = "svg-wrap";

    const svgW = slab.width * 0.2;
    const svgH = slab.height * 0.2;
    const ns = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(ns, "svg");
    svg.setAttribute("width", Math.ceil(svgW));
    svg.setAttribute("height", Math.ceil(svgH));
    svg.setAttribute("viewBox", `0 0 ${slab.width} ${slab.height}`);
    svg.style.maxWidth = "100%";
    svg.style.height = "auto";
    svg.setAttribute("preserveAspectRatio", "xMidYMid meet");

    let scale = 1, panX = 0, panY = 0;
    const viewGroup = document.createElementNS(ns, "g");
    viewGroup.setAttribute("transform", `translate(${panX} ${panY}) scale(${scale})`);
    svg.appendChild(viewGroup);

    const bg = document.createElementNS(ns, "rect");
    bg.setAttribute("x", -10); bg.setAttribute("y", -10);
    bg.setAttribute("width", slab.width + 20); bg.setAttribute("height", slab.height + 20);
    bg.setAttribute("fill", "#fafafa");
    bg.setAttribute("stroke", "#333"); bg.setAttribute("stroke-width", 3);
    viewGroup.appendChild(bg);

    const flip = document.createElementNS(ns, "g");
    flip.setAttribute("transform", `scale(1 -1) translate(0 -${slab.height})`);
    viewGroup.appendChild(flip);

    slab.pieces.forEach((p) => {
      const fill = colorFor(p.name);
      const g = document.createElementNS(ns, "g");
      g.setAttribute("transform", `translate(${p.x} ${p.y})`);
      if (p.polygon) {
        const d = ringPath(p.polygon) + (p.holes || []).map(ringPath).join("");
        const path = document.createElementNS(ns, "path");
        path.setAttribute("d", d);
        path.setAttribute("fill", fill);
        path.setAttribute("fill-opacity", 0.4);
        path.setAttribute("fill-rule", "evenodd");
        path.setAttribute("stroke", fill);
        path.setAttribute("stroke-width", 3);
        g.appendChild(path);
      } else {
        const rect = document.createElementNS(ns, "rect");
        rect.setAttribute("x", 0); rect.setAttribute("y", 0);
        rect.setAttribute("width", p.width); rect.setAttribute("height", p.height);
        rect.setAttribute("fill", fill);
        rect.setAttribute("fill-opacity", 0.35);
        rect.setAttribute("stroke", fill); rect.setAttribute("stroke-width", 3);
        g.appendChild(rect);
      }
      (p.lines || []).forEach((segment) => {
        const lineLayer = segment[0];
        const x1 = segment[1], y1 = segment[2], x2 = segment[3], y2 = segment[4];
        const stroke = layerColors[lineLayer] !== undefined
          ? aciToHex(layerColors[lineLayer])
          : fill;
        const l = document.createElementNS(ns, "line");
        l.setAttribute("x1", x1); l.setAttribute("y1", y1);
        l.setAttribute("x2", x2); l.setAttribute("y2", y2);
        l.setAttribute("stroke", stroke);
        l.setAttribute("stroke-width", 4);
        g.appendChild(l);
      });
      flip.appendChild(g);

      const cy = slab.height - (p.y + p.height / 2);
      const cx = p.x + p.width / 2;
      if (p.width > 60 || p.height > 40) {
        const t1 = document.createElementNS(ns, "text");
        t1.setAttribute("x", cx); t1.setAttribute("y", cy - 2);
        t1.setAttribute("text-anchor", "middle"); t1.setAttribute("font-size", 14);
        t1.textContent = p.name;
        const t2 = document.createElementNS(ns, "text");
        t2.setAttribute("x", cx); t2.setAttribute("y", cy + 14);
        t2.setAttribute("text-anchor", "middle"); t2.setAttribute("font-size", 12);
        t2.textContent = `${fmt(p.width)}\u00d7${fmt(p.height)}${p.rotated ? " \u21bb" : ""}`;
        viewGroup.appendChild(t1); viewGroup.appendChild(t2);
      }
    });

    let isDragging = false;
    let lastX = 0, lastY = 0;

    function updateTransform() {
      viewGroup.setAttribute("transform", `translate(${panX} ${panY}) scale(${scale})`);
    }

    svg.addEventListener("wheel", (e) => {
      e.preventDefault();
      const factor = e.deltaY < 0 ? 1.1 : 0.9;
      const newScale = Math.min(5, Math.max(0.1, scale * factor));
      const rect = svg.getBoundingClientRect();
      const mx = e.clientX - rect.left;
      const my = e.clientY - rect.top;
      panX = mx - (mx - panX) * (newScale / scale);
      panY = my - (my - panY) * (newScale / scale);
      scale = newScale;
      updateTransform();
    });

    svg.addEventListener("mousedown", (e) => {
      if (e.button !== 0) return;
      isDragging = true;
      lastX = e.clientX;
      lastY = e.clientY;
      svg.style.cursor = "grabbing";
    });

    window.addEventListener("mousemove", (e) => {
      if (!isDragging || !svg.contains(e.target)) return;
      panX += e.clientX - lastX;
      panY += e.clientY - lastY;
      lastX = e.clientX;
      lastY = e.clientY;
      updateTransform();
    });

    window.addEventListener("mouseup", () => {
      if (isDragging) {
        isDragging = false;
        svg.style.cursor = "default";
      }
    });

    svg.style.cursor = "grab";

    wrap.appendChild(svg);
    card.appendChild(wrap);
    const detail = document.createElement("div");
    detail.className = "slab-detail";

    const groups = {};
    slab.pieces.forEach((p, i) => {
      const key = `${p.name}|${p.width}|${p.height}`;
      if (!groups[key]) groups[key] = { name: p.name, width: p.width, height: p.height, rotated: p.rotated, count: 0, positions: [] };
      groups[key].count++;
      groups[key].positions.push(`(${p.x}, ${p.y})${p.rotated ? " \u21bb" : ""}`);
    });

    detail.innerHTML =
      `<table><thead><tr><th>Pieza</th><th>Dimensiones</th><th>Cant.</th><th>Posiciones</th></tr></thead><tbody>${
        Object.values(groups).map(g =>
          `<tr><td><span class="color-dot" style="background:${colorFor(g.name)}"></span> ${escapeHtml(g.name)}</td><td>${fmt(g.width)} \u00d7 ${fmt(g.height)}</td><td>${g.count}</td><td style="font-size:10px;word-break:break-all">${g.positions.join(", ")}</td></tr>`
        ).join("")
      }</tbody></table>`;
    card.appendChild(detail);
    slabsEl.appendChild(card);
  });

  const unplaced = document.getElementById("unplaced");
  if (data.pieces_unplaced) {
    unplaced.hidden = false;
    unplaced.innerHTML = `<h3>No se colocaron ${data.pieces_unplaced} pieza(s):</h3>`;
    const list = {};
    data.unplaced.forEach((p) => {
      const k = `${p.name} ${p.width}x${p.height}`;
      list[k] = (list[k] || 0) + 1;
    });
    unplaced.innerHTML += Object.entries(list)
      .map(([k, n]) => `<div>${n} \u00d7 ${escapeHtml(k)} mm</div>`).join("");
  } else {
    unplaced.hidden = true;
  }

  const scraps = document.getElementById("scraps");
  scraps.innerHTML = "";
  const allPlacedTotalArea = data.placed_area || 0;

  data.slabs_used.forEach((slab, idx) => {
    const scrapArea = slab.waste_area || 0;
    if (scrapArea > 1) {
      scraps.innerHTML +=
        `<div>Plancha ${idx + 1} (${escapeHtml(slab.name)}): ${(scrapArea / 1e6).toFixed(3)} m\u00b2 de retazos</div>`;
    }
  });
  if (scraps.innerHTML) {
    scraps.hidden = false;
    const header = document.createElement("h3");
    header.textContent = "Retazos / Scraps disponibles:";
    scraps.insertBefore(header, scraps.firstChild);
  } else {
    scraps.hidden = true;
  }

  results.scrollIntoView({ behavior: "smooth" });
}

function ringPath(ring) {
  return ring.map((pt, i) =>
    (i === 0 ? "M" : "L") + pt[0] + " " + pt[1]).join(" ") + " Z";
}

init();
