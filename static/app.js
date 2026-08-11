const PALETTE = [
  "#5b9bd5", "#ed7d31", "#a5a5a5", "#70ad47", "#ffc000", "#4472c4",
  "#ff6f91", "#00c2a8", "#9d6bd7", "#e2708a", "#4fbc9f", "#f6c244",
];

function colorFor(name) {
  let h = 0;
  for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) >>> 0;
  return PALETTE[h % PALETTE.length];
}

function itemLine(template, index) {
  const line = document.createElement("div");
  line.className = "item-line";
  line.innerHTML = `
    <input class="name" placeholder="Nombre" value="${template.name}">
    <input class="w" type="number" placeholder="Ancho" value="${template.width}">
    <input class="h" type="number" placeholder="Alto" value="${template.height}">
    <input class="qty" type="number" placeholder="Cant." value="${template.quantity}" min="1">
    <button class="del" title="Quitar">&times;</button>`;
  line.querySelector(".del").addEventListener("click", () => line.remove());
  return line;
}

function defaultPieces() {
  return [
    { name: "Mesa", width: 800, height: 1200, quantity: 1 },
    { name: "Mesita", width: 500, height: 500, quantity: 2 },
    { name: "Mesada", width: 900, height: 600, quantity: 1 },
    { name: "Repisa", width: 300, height: 1500, quantity: 3 },
  ];
}

function defaultSlabs() {
  return [
    { name: "Blanco", width: 3200, height: 1600, quantity: 1 },
    { name: "Gris", width: 2800, height: 1400, quantity: 1 },
  ];
}

function collectRows(container) {
  return [...container.querySelectorAll(".item-line")].map((line) => ({
    name: line.querySelector(".name").value.trim() || "Pieza",
    width: parseFloat(line.querySelector(".w").value) || 0,
    height: parseFloat(line.querySelector(".h").value) || 0,
    quantity: parseInt(line.querySelector(".qty").value, 10) || 1,
  }));
}

function init() {
  const pieceRows = document.getElementById("pieceRows");
  const slabRows = document.getElementById("slabRows");

  defaultPieces().forEach((p, i) => pieceRows.appendChild(itemLine(p, i)));
  defaultSlabs().forEach((s, i) => slabRows.appendChild(itemLine(s, i)));

  document.getElementById("addPiece").addEventListener("click", () =>
    pieceRows.appendChild(itemLine({ name: "Pieza", width: 500, height: 500, quantity: 1 })));
  document.getElementById("addSlab").addEventListener("click", () =>
    slabRows.appendChild(itemLine({ name: "Plancha", width: 3000, height: 1500, quantity: 1 })));

  document.getElementById("optimizeBtn").addEventListener("click", optimize);
}

async function optimize() {
  const pieces = collectRows(document.getElementById("pieceRows"))
    .filter((p) => p.width > 0 && p.height > 0);
  const slabs = collectRows(document.getElementById("slabRows"))
    .filter((s) => s.width > 0 && s.height > 0);

  if (!pieces.length || !slabs.length) {
    alert("Agrega al menos una pieza y una plancha con medidas válidas.");
    return;
  }

  const btn = document.getElementById("optimizeBtn");
  btn.disabled = true;
  btn.textContent = "Optimizando...";

  try {
    const res = await fetch("/api/optimize", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        pieces,
        slabs,
        kerf: parseFloat(document.getElementById("kerf").value) || 0,
        allow_rotation: document.getElementById("allowRotation").checked,
      }),
    });
    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();
    renderResults(data);
  } catch (err) {
    alert("Error: " + err.message);
  } finally {
    btn.disabled = false;
    btn.textContent = "Optimizar corte";
  }
}

function fmt(n) {
  return n % 1 === 0 ? String(n) : String(Math.round(n * 100) / 100);
}

function renderResults(data) {
  const results = document.getElementById("results");
  results.hidden = false;

  document.getElementById("summary").innerHTML = [
    ["Piezas colocadas", `${data.pieces_placed}/${data.total_pieces}`],
    ["Utilización", `${data.global_utilization}%`],
    ["Planchas usadas", String(data.slabs_used.length)],
    ["Área colocada", `${(data.placed_area / 1e6).toFixed(3)} m²`],
    ["Desperdicio", `${(data.total_waste / 1e6).toFixed(3)} m²`],
  ].map(([label, value]) => `<div class="stat"><div class="value">${value}</div><div class="label">${label}</div></div>`).join("");

  const slabsEl = document.getElementById("slabs");
  slabsEl.innerHTML = "";

  data.slabs_used.forEach((slab) => {
    const maxDim = Math.max(slab.width, slab.height);
    const pxPerUnit = 560 / maxDim;

    const card = document.createElement("div");
    card.className = "slab-card";

    const head = document.createElement("div");
    head.className = "slab-head";
    head.innerHTML = `<span><strong>${slab.name}</strong> &middot; ${fmt(slab.width)} × ${fmt(slab.height)} mm &middot; ${slab.pieces.length} piezas</span>
      <span class="util">Utilización: ${slab.utilization}% &middot; Desperdicio: ${fmt(slab.waste_area)} mm²</span>`;
    card.appendChild(head);

    const wrap = document.createElement("div");
    wrap.className = "svg-wrap";

    const svgW = slab.width * pxPerUnit;
    const svgH = slab.height * pxPerUnit;
    const ns = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(ns, "svg");
    svg.setAttribute("width", Math.ceil(svgW));
    svg.setAttribute("height", Math.ceil(svgH));
    svg.setAttribute("viewBox", `0 0 ${slab.width} ${slab.height}`);
    svg.style.maxWidth = "100%";
    svg.style.height = "auto";

    const bg = document.createElementNS(ns, "rect");
    bg.setAttribute("x", 0); bg.setAttribute("y", 0);
    bg.setAttribute("width", slab.width); bg.setAttribute("height", slab.height);
    bg.setAttribute("fill", "#fafafa");
    bg.setAttribute("stroke", "#333"); bg.setAttribute("stroke-width", 2);
    svg.appendChild(bg);

    slab.pieces.forEach((p) => {
      const y = slab.height - p.y - p.height; // invertir eje Y
      const fill = colorFor(p.name);
      const rect = document.createElementNS(ns, "rect");
      rect.setAttribute("x", p.x); rect.setAttribute("y", y);
      rect.setAttribute("width", p.width); rect.setAttribute("height", p.height);
      rect.setAttribute("fill", fill);
      rect.setAttribute("fill-opacity", 0.35);
      rect.setAttribute("stroke", fill); rect.setAttribute("stroke-width", 3);
      svg.appendChild(rect);

      const labelW = p.width / 2, labelH = p.height / 2;
      if (labelW > 30 && labelH > 20) {
        const t1 = document.createElementNS(ns, "text");
        t1.setAttribute("x", p.x + p.width / 2); t1.setAttribute("y", y + p.height / 2 - 2);
        t1.setAttribute("text-anchor", "middle"); t1.setAttribute("font-size", 10);
        t1.textContent = p.name;
        const t2 = document.createElementNS(ns, "text");
        t2.setAttribute("x", p.x + p.width / 2); t2.setAttribute("y", y + p.height / 2 + 11);
        t2.setAttribute("text-anchor", "middle"); t2.setAttribute("font-size", 9);
        t2.textContent = `${fmt(p.width)}×${fmt(p.height)}${p.rotated ? " ↻" : ""}`;
        svg.appendChild(t1); svg.appendChild(t2);
      }
    });

    wrap.appendChild(svg);
    card.appendChild(wrap);
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
      .map(([k, n]) => `<div>${n} × ${k} mm</div>`).join("");
  } else {
    unplaced.hidden = true;
  }
}

init();
