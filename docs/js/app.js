/* RedRoot website: static, data from data/*.json (exported by src/s05_export_site.py) */
"use strict";

const CAT = { CR: "#8E2A1C", EN: "#B4432E", VU: "#D9874A", NT: "#B9C59A", LC: "#5F7F5B", DD: "#A9AFA9", NE: "#D6D0C2", EW: "#3B1A14", EX: "#111" };
const CAT_NAME = { CR: "Critically Endangered", EN: "Endangered", VU: "Vulnerable", NT: "Near Threatened", LC: "Least Concern", DD: "Data Deficient", NE: "Not Evaluated", EW: "Extinct in the Wild", EX: "Extinct" };
const LIGHT_BADGE = new Set(["NT", "DD", "NE"]);
const THREAT = new Set(["CR", "EN", "VU"]);
const TILE_URL = "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}";
const TILE_ATTR = "Tiles &copy; Esri &mdash; Esri, HERE, Garmin, &copy; OpenStreetMap contributors";

const $ = (s) => document.querySelector(s);
const fmtInt = d3.format(",.0f");
const fmtP = d3.format(".2f");
const fmtPct = d3.format(".0%");
const params = new URLSearchParams(location.search);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

let S = [], M = {}, IMP = [], HS = [], T = 0.3, byName = new Map();

const badge = (code) => `<span class="badge${LIGHT_BADGE.has(code) ? " light" : ""}" style="background:${CAT[code] || "#ccc"}" title="${CAT_NAME[code] || code}">${code}</span>`;
const spName = (s) => `<span class="sp-name">${esc(s.n)}</span><span class="sp-fam">${esc(s.f || "")}</span>`;
const pCell = (s) => s.p == null ? '<span class="note">n/a</span>' :
  `<span class="pval">${fmtP(s.p)}</span><div class="pbar"><div class="rng" style="left:${s.plo * 100}%;width:${Math.max(1, (s.phi - s.plo) * 100)}%"></div><div class="dot" style="left:${s.p * 100}%"></div></div>`;

function tileLayer() { return L.tileLayer(TILE_URL, { attribution: TILE_ATTR, maxZoom: 16 }); }

/* ------------------------------------------------------------------ boot */
Promise.all(["species", "metrics", "importance", "hotspots"].map((f) => fetch(`data/${f}.json`).then((r) => r.json())))
  .then(([s, m, imp, hs]) => {
    S = s; M = m; IMP = imp; HS = hs; T = m.screening_threshold;
    S.forEach((d) => byName.set(d.n, d));
    const shot = params.get("shot");
    if (shot) { document.body.classList.add("shot"); const el = document.getElementById(shot); if (el) el.classList.add("on"); }
    if (params.get("only") === "chart") document.body.classList.add("only-chart");
    renderStats(); renderFindings(); renderScatter(); renderHotspots(); setupPriority(); renderWatchlist();
    setupExplorer(); renderValidation(); renderMethods();
    if (shot) window.scrollTo(0, 0);
    document.body.dataset.ready = "1";
  });

/* ------------------------------------------------------------------ hero stats */
function renderStats() {
  const g = M.gap;
  const tiles = [
    [fmtInt(g.n_species), "medicinal plants with recorded uses in South Asia", ""],
    [fmtPct(g.frac_not_assessed_or_dd), "have no usable IUCN Red List assessment", "red"],
    [g.n_gap_screen_positive, "unassessed species screened as likely threatened", "red"],
    [g.n_harvest_watchlist, "species on the harvest watchlist, where range-based screening is blind", ""],
  ];
  $("#stats").innerHTML = tiles.map(([n, l, c]) => `<div class="stat"><div class="num ${c}">${n}</div><div class="lbl">${l}</div></div>`).join("");
}

/* ------------------------------------------------------------------ findings */
function renderFindings() {
  const g = M.gap, b = M.blind_spot;
  const rec = S.filter((d) => d.src), recThr = rec.filter((d) => THREAT.has(d.iu));
  $("#f1-figs").innerHTML = [
    [g.n_recovered_via_synonyms, "IUCN assessments recovered from behind synonyms"],
    [recThr.length, "of them threatened, incl. kuth (CR) and agarwood (CR)"],
    [M.n_rejected_synonyms ?? 22, "heterotypic matches rejected and logged"],
  ].map(([n, l]) => `<div class="fig"><div class="big">${n}</div><div class="small">${l}</div></div>`).join("");
  $("#f2-text").innerHTML = `Of the <b>${b.n_threatened_medicinal}</b> officially threatened medicinal species, the model catches ${b.n_caught}. Most are narrow-range endemics. It misses ${b.n_missed}: jatamansi, kuth, sandalwood, guggul and red sanders. These plants are declining from <b>harvest</b> across large ranges (IUCN criterion A), which occurrence data cannot see.`;
  $("#f2-figs").innerHTML = [
    [b.median_use_caught, `median recorded uses of the ${b.n_caught} caught`],
    [b.median_use_missed, `median recorded uses of the ${b.n_missed} missed`],
  ].map(([n, l]) => `<div class="fig"><div class="big">${n}</div><div class="small">${l}</div></div>`).join("");
  const ci = b.auc_use_among_range_safe_ci;
  $("#f2-note").innerHTML = `Mann-Whitney p = ${fmtP(b.mannwhitney_p)}. Use counts alone cannot fix it: among range-safe species they barely separate threatened from non-threatened (AUC ${fmtP(b.auc_use_among_range_safe)}, 95% CI ${fmtP(ci[0])}–${fmtP(ci[1])}). That is why harvest risk gets its own watchlist.`;
}

/* ------------------------------------------------------------------ scatter */
function renderScatter() {
  const el = $("#scatter");
  const W = el.clientWidth || 1100, H = el.clientHeight || 460, m = { t: 16, r: 24, b: 52, l: 64 };
  const data = S.filter((d) => d.ok && d.eoo >= 1 && d.u >= 1).map((d) => {
    let g = "other";
    if (THREAT.has(d.iu) && d.poof != null) g = d.poof >= T ? "caught" : "missed";
    else if (d.gap && d.scr && !d.cult) g = "screened";
    return { ...d, g };
  });
  const order = { other: 0, screened: 1, caught: 2, missed: 3 };
  data.sort((a, b) => order[a.g] - order[b.g]);
  const x = d3.scaleLog().domain([1, d3.max(data, (d) => d.eoo) * 1.2]).range([m.l, W - m.r]).nice();
  const y = d3.scaleLog().domain([1, d3.max(data, (d) => d.u) * 1.2]).range([H - m.b, m.t]).nice();
  const svg = d3.select(el).append("svg").attr("viewBox", `0 0 ${W} ${H}`);
  svg.append("g").attr("class", "grid").attr("transform", `translate(0,${H - m.b})`)
    .call(d3.axisBottom(x).ticks(6, "~s").tickSize(-(H - m.t - m.b)).tickFormat("")).call((g) => g.select(".domain").remove());
  svg.append("g").attr("class", "axis").attr("transform", `translate(0,${H - m.b})`).call(d3.axisBottom(x).ticks(6, "~s"));
  svg.append("g").attr("class", "axis").attr("transform", `translate(${m.l},0)`).call(d3.axisLeft(y).ticks(5, "~s"));
  svg.append("text").attr("class", "axis-label").attr("x", W - m.r).attr("y", H - 10).attr("text-anchor", "end").text("Extent of occurrence, km² (log scale) →");
  svg.append("text").attr("class", "axis-label").attr("transform", "rotate(-90)").attr("x", -m.t).attr("y", 16).attr("text-anchor", "end").text("Recorded medicinal uses (log) →");
  const style = {
    other: { r: 3, fill: "#CFC8B8", stroke: "none", op: .7 },
    screened: { r: 4.5, fill: "#D9874A", stroke: "none", op: .85 },
    caught: { r: 6, fill: "#B4432E", stroke: "#fff", op: 1 },
    missed: { r: 6, fill: "#FBF9F4", stroke: "#B4432E", op: 1 },
  };
  const tip = $("#tooltip");
  svg.append("g").selectAll("circle").data(data).join("circle")
    .attr("cx", (d) => x(d.eoo)).attr("cy", (d) => y(d.u)).attr("r", (d) => style[d.g].r)
    .attr("fill", (d) => style[d.g].fill).attr("stroke", (d) => style[d.g].stroke).attr("stroke-width", (d) => d.g === "missed" ? 2.2 : 1)
    .attr("opacity", (d) => style[d.g].op).style("cursor", "pointer")
    .on("mousemove", (e, d) => { tip.hidden = false; tip.style.left = e.clientX + 14 + "px"; tip.style.top = e.clientY + 14 + "px";
      tip.innerHTML = `<i>${esc(d.n)}</i><br>IUCN ${d.iu} · ${fmtInt(d.u)} uses · EOO ${fmtInt(d.eoo)} km²`; })
    .on("mouseleave", () => { tip.hidden = true; })
    .on("click", (e, d) => selectSpecies(d.n, true));
  const annotate = ["Nardostachys jatamansi", "Dolomiaea costus", "Santalum album", "Commiphora wightii", "Pterocarpus santalinus"];
  // labels stacked to the upper right with leader lines, so they never overlap
  const ann = data.filter((d) => annotate.includes(d.n)).sort((a, b) => y(a.u) - y(b.u));
  const lx = d3.max(ann, (d) => x(d.eoo)) + 70;
  let ly = Math.max(m.t + 12, d3.min(ann, (d) => y(d.u)) - 40);
  ann.forEach((d) => {
    svg.append("line").attr("x1", x(d.eoo)).attr("y1", y(d.u)).attr("x2", lx - 4).attr("y2", ly - 4)
      .attr("stroke", "#8E2A1C").attr("stroke-width", 0.8).attr("opacity", .7);
    svg.append("text").attr("class", "anno").attr("x", lx).attr("y", ly).text(d.n);
    ly += 20;
  });
  $("#scatter-legend").innerHTML = [
    ["#B4432E", "#fff", "Threatened, caught by the model"], ["#FBF9F4", "#B4432E", "Threatened, missed (the blind spot)"],
    ["#D9874A", "none", "Unassessed, screened likely threatened"], ["#CFC8B8", "none", "Other species"],
  ].map(([f, s, l]) => `<span><i class="sw" style="background:${f};border:2px solid ${s === "none" ? f : s}"></i>${l}</span>`).join("");
}

/* ------------------------------------------------------------------ hotspot map */
function renderHotspots() {
  $("#hs-n").textContent = M.gap.n_gap_screen_positive;
  const map = L.map("hotmap", { scrollWheelZoom: false }).setView([22, 86], 5);
  tileLayer().addTo(map);
  HS.sort((a, b) => a[2].length - b[2].length).forEach(([lat, lon, names]) => {
    const n = names.length;
    L.circleMarker([lat, lon], { radius: 3 + Math.sqrt(n) * 3.2, color: "#8E2A1C", weight: 1, fillColor: "#B4432E", fillOpacity: Math.min(.85, .35 + n * .05) })
      .bindPopup(`<b>${n} species</b><br>${names.slice(0, 14).map((s) => `<i>${esc(s)}</i>`).join("<br>")}${n > 14 ? `<br>…and ${n - 14} more` : ""}`)
      .addTo(map);
  });
}

/* ------------------------------------------------------------------ tables */
function makeTable(el, cols, rows, limit, onRow) {
  el.innerHTML = `<thead><tr>${cols.map((c) => `<th class="${c.num ? "num" : ""}">${c.h}</th>`).join("")}</tr></thead>
    <tbody>${rows.slice(0, limit).map((r, i) => `<tr data-n="${esc(r.n)}">${cols.map((c) => `<td class="${c.num ? "num" : ""}${c.cls ? " " + c.cls : ""}">${c.v(r, i)}</td>`).join("")}</tr>`).join("")}</tbody>`;
  el.querySelectorAll("tbody tr").forEach((tr) => tr.addEventListener("click", () => onRow(tr.dataset.n)));
}
function downloadCSV(rows, cols, name) {
  const q = (v) => `"${String(v ?? "").replace(/"/g, '""')}"`;
  const csv = [cols.map((c) => q(c[0])).join(","), ...rows.map((r) => cols.map((c) => q(c[1](r))).join(","))].join("\n");
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([csv], { type: "text/csv" })); a.download = name; a.click();
}
const CSV_COLS = [["species", (r) => r.n], ["family", (r) => r.f], ["iucn", (r) => r.iu], ["p_threatened", (r) => r.p], ["p10", (r) => r.plo], ["p90", (r) => r.phi],
  ["criterion_b_prelim", (r) => r.cb], ["eoo_km2", (r) => r.eoo], ["aoo_km2_lower_bound", (r) => r.aoo], ["use_records", (r) => r.u], ["top_uses_literature", (r) => r.tu]];
const goTo = (n) => selectSpecies(n, true);

/* ------------------------------------------------------------------ priority list */
function setupPriority() {
  const minp = $("#f-minp"); minp.step = "0.01"; minp.value = (Math.round(T * 100) / 100).toFixed(2);
  const fams = [...new Set(S.filter((d) => d.gap && d.p != null).map((d) => d.f).filter(Boolean))].sort();
  $("#f-family").insertAdjacentHTML("beforeend", fams.map((f) => `<option>${esc(f)}</option>`).join(""));
  let limit = 25, rows = [];
  const cols = [
    { h: "#", num: true, v: (r, i) => i + 1 },
    { h: "Species", v: spName },
    { h: "IUCN", v: (r) => badge(r.iu) },
    { h: "P(threatened)", v: pCell },
    { h: "Criterion B (prelim.)", v: (r) => esc(r.cb) },
    { h: "EOO km²", num: true, v: (r) => fmtInt(r.eoo) },
    { h: "Uses", num: true, v: (r) => fmtInt(r.u) },
    { h: "Most-recorded uses (literature)", cls: "uses", v: (r) => esc(r.tu || "") },
  ];
  const update = () => {
    const mp = +minp.value, w = +$("#f-w").value, reg = $("#f-region").value, fam = $("#f-family").value;
    $("#f-minp-out").textContent = fmtP(mp); $("#f-w-out").textContent = w.toFixed(1);
    rows = S.filter((d) => d.gap && d.p != null && d.p >= mp
      && (reg === "any" || (reg === "nsc" ? d.nsc : d.end))
      && !($("#f-cult").checked && d.cult) && !($("#f-unk").checked && d.unk) && (!fam || d.f === fam))
      .map((d) => ({ ...d, pr: d.p * ((1 - w) + w * d.up) })).sort((a, b) => b.pr - a.pr);
    $("#prio-count").textContent = `${rows.length} species, ranked by priority`;
    makeTable($("#prio-table"), cols, rows, limit, goTo);
    $("#prio-more").hidden = rows.length <= limit;
  };
  ["#f-minp", "#f-w", "#f-region", "#f-family", "#f-cult", "#f-unk"].forEach((s) => $(s).addEventListener("input", () => { limit = 25; update(); }));
  $("#prio-more").addEventListener("click", () => { limit += 25; update(); });
  $("#prio-csv").addEventListener("click", () => downloadCSV(rows, [["priority", (r) => r.pr.toFixed(3)], ...CSV_COLS], "redroot_priority_list.csv"));
  update();
}

/* ------------------------------------------------------------------ watchlist */
function renderWatchlist() {
  const wc = M.watchlist_check;
  $("#wl-lead").innerHTML = `Unassessed species whose range looks safe but whose profile matches harvest-threatened plants: used more than the median species, native to the Indian subcontinent, not an annual, native to 15 or fewer botanical countries, and mostly recorded in the wild. <b>This list is not a prediction.</b> For these plants, trade, market and harvest monitoring is the way to detect decline. Exploratory check on assessed species: ${fmtPct(wc.rate_in_profile)} of range-safe species with this profile are officially threatened, against ${fmtPct(wc.rate_other_range_safe)} of other range-safe species (odds ratio ${wc.odds_ratio.toFixed(1)}). The profile was chosen among ${wc.variants_tested} variants, so treat that as supporting evidence, not proof.`;
  const rows = S.filter((d) => d.wl).sort((a, b) => b.u - a.u);
  let limit = 20;
  const cols = [
    { h: "Species", v: spName }, { h: "IUCN", v: (r) => badge(r.iu) },
    { h: "Life form", v: (r) => esc(r.lf || "") }, { h: "Uses", num: true, v: (r) => fmtInt(r.u) },
    { h: "P(threatened) by range", v: pCell }, { h: "Most-recorded uses (literature)", cls: "uses", v: (r) => esc(r.tu || "") },
  ];
  const draw = () => { makeTable($("#wl-table"), cols, rows, limit, goTo); $("#wl-more").hidden = rows.length <= limit; };
  $("#wl-count").textContent = `${rows.length} species, most-used first`;
  $("#wl-more").addEventListener("click", () => { limit += 20; draw(); });
  $("#wl-csv").addEventListener("click", () => downloadCSV(rows, CSV_COLS, "redroot_harvest_watchlist.csv"));
  draw();
}

/* ------------------------------------------------------------------ explorer */
let spMap, spLayer;
function setupExplorer() {
  spMap = L.map("spmap", { scrollWheelZoom: false }).setView([24, 82], 4);
  tileLayer().addTo(spMap);
  spLayer = L.layerGroup().addTo(spMap);
  setupCombobox();
  $("#sp-print").addEventListener("click", () => { spMap.invalidateSize(); window.print(); });
  selectSpecies(params.get("species") || "Dolomiaea costus");
}

/* searchable species dropdown (replaces the native datalist, whose arrow did nothing in some browsers) */
function setupCombobox() {
  const input = $("#sp-input"), list = $("#sp-list"), toggle = $("#sp-toggle");
  const all = [...byName.values()].sort((a, b) => a.n.localeCompare(b.n));
  let items = [], active = -1, current = "";

  const open = () => { list.hidden = false; input.setAttribute("aria-expanded", "true"); };
  const close = () => { list.hidden = true; input.setAttribute("aria-expanded", "false"); active = -1; input.removeAttribute("aria-activedescendant"); };

  function render(q) {
    q = (q || "").trim().toLowerCase();
    if (!q) items = all;
    else {
      const starts = [], genus = [], other = [];
      for (const s of all) {
        const n = s.n.toLowerCase();
        if (n.startsWith(q)) starts.push(s);
        else if (n.includes(" " + q) || (s.f || "").toLowerCase().startsWith(q)) genus.push(s);
        else if (n.includes(q)) other.push(s);
      }
      items = starts.concat(genus, other);
    }
    active = -1;
    if (!items.length) { list.innerHTML = `<li class="sp-empty">No matching species</li>`; open(); return; }
    list.innerHTML = items.map((s, i) =>
      `<li role="option" id="sp-opt-${i}" data-i="${i}" aria-selected="false"${s.n === current ? ' class="current"' : ""}>` +
      `<span class="sp-name">${esc(s.n)}</span><span class="sp-fam">${esc(s.f || "")}</span>` +
      (s.iu ? badge(s.iu) : "") + `</li>`).join("");
    open();
  }
  function setActive(i) {
    const opts = list.querySelectorAll('[role="option"]');
    if (!opts.length) return;
    if (active >= 0 && opts[active]) { opts[active].classList.remove("active"); opts[active].setAttribute("aria-selected", "false"); }
    active = (i + opts.length) % opts.length;
    const el = opts[active];
    el.classList.add("active"); el.setAttribute("aria-selected", "true");
    input.setAttribute("aria-activedescendant", el.id);
    el.scrollIntoView({ block: "nearest" });
  }
  function choose(i) {
    const s = items[i]; if (!s) return;
    current = s.n; close(); selectSpecies(s.n); input.blur();
  }

  input.addEventListener("input", () => render(input.value));
  input.addEventListener("focus", () => { input.select(); render(input.value === current ? "" : input.value); });
  input.addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown") { e.preventDefault(); if (list.hidden) render(input.value === current ? "" : input.value); setActive(active + 1); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setActive(active - 1); }
    else if (e.key === "Enter") { e.preventDefault(); if (!list.hidden) choose(active >= 0 ? active : 0); }
    else if (e.key === "Escape") { close(); input.value = current; }
  });
  toggle.addEventListener("mousedown", (e) => e.preventDefault());
  toggle.addEventListener("click", () => {
    if (!list.hidden) { close(); return; }
    if (document.activeElement === input) render(input.value === current ? "" : input.value);
    else input.focus();
  });
  list.addEventListener("mousedown", (e) => e.preventDefault());
  list.addEventListener("click", (e) => { const li = e.target.closest('[role="option"]'); if (li) choose(+li.dataset.i); });
  list.addEventListener("mousemove", (e) => { const li = e.target.closest('[role="option"]'); if (li && +li.dataset.i !== active) setActive(+li.dataset.i); });
  input.addEventListener("blur", () => { close(); if (!byName.has(input.value)) input.value = current; });
  document.addEventListener("speciesselected", (e) => { current = e.detail; });
}

function selectSpecies(name, scroll) {
  const s = byName.get(name); if (!s) return;
  $("#sp-input").value = s.n;
  document.dispatchEvent(new CustomEvent("speciesselected", { detail: s.n }));
  const thrMissed = THREAT.has(s.iu) && s.poof != null && s.poof < T;
  const pShow = s.poof ?? s.p;
  let gauge = '<p class="note">Not scored: fewer than 3 occupied native-range cells.</p>';
  if (pShow != null) {
    gauge = `<div class="gauge"><div class="thr" style="left:${T * 100}%"><span>threshold ${fmtP(T)}</span></div>
      ${s.plo != null ? `<div class="rng" style="left:${s.plo * 100}%;width:${Math.max(1, (s.phi - s.plo) * 100)}%"></div>` : ""}
      <div class="dot" style="left:${pShow * 100}%"></div></div>
      <p class="note">Model P(threatened) = <b>${fmtP(pShow)}</b>${s.poof != null ? " (out-of-fold: this species’ plant family was held out of training)" : `, ensemble 10–90% range ${fmtP(s.plo)}–${fmtP(s.phi)}`}.</p>`;
    const pc = s.poof != null ? s.pco : s.pc;
    const share = pc == null ? null : pc >= 0.95 ? "over 95%" : pc <= 0.05 ? "under 5%" : "about " + fmtPct(pc);
    if (share) gauge += `<p class="note">Among assessed species with a similar score, <b>${share}</b> are officially threatened.</p>`;
  }
  let drivers = "";
  if (s.dr && s.dr.length) {
    const mx = d3.max(s.dr, (d) => Math.abs(d[2])) || 1;
    drivers = `<div class="drivers"><h4>Why this score</h4>${s.dr.map(([l, v, c]) =>
      `<div class="drv ${c > 0 ? "up" : "down"}"><span>${esc(l)} <span class="val">· ${esc(v)}</span></span><span class="eff">${c > 0 ? "▲ raises risk" : "▼ lowers risk"}</span><div class="track"><div class="fill" style="width:${Math.max(4, 100 * Math.abs(c) / mx)}%"></div></div></div>`).join("")}
      <p class="note">Largest SHAP contributions to the score${s.poof != null ? ", from the models that never saw this species’ family" : ", averaged over the 25-model ensemble"}.</p></div>`;
  }
  $("#print-head").textContent = `RedRoot assessor sheet · ${s.n} · preliminary screening, not an official Red List assessment · printed ${new Date().toISOString().slice(0, 10)} · dukenukem1611.github.io/redroot/?species=${encodeURIComponent(s.n)}`;
  const flags = [];
  if (s.src) flags.push(["info", `Assessed by IUCN under <i>${esc(s.src.split(" (")[0].replace(/\.$/, ""))}</i>. GBIF’s accepted name returns “Not Evaluated”, so this status was recovered by taxonomic reconciliation.`]);
  if (thrMissed) flags.push(["", "Officially threatened but missed by range-based screening. Its decline is likely driven by harvest, not range size (the blind spot)."]);
  if (s.wl) flags.push(["", "On the harvest watchlist: heavily used, with a range that looks safe."]);
  if (s.cult) flags.push(["info", "Widely cultivated or naturalised: most GBIF records lie outside its native range."]);
  if (s.unk) flags.push(["info", "Native range not found in Kew’s WCVP, so all records were used."]);
  $("#sp-card").innerHTML = `
    <h3>${esc(s.n)}</h3>
    <p class="meta">${esc(s.f || "")}${s.lf ? " · " + esc(s.lf) : ""}${s.cl ? " · " + esc(s.cl) : ""}</p>
    <p>${badge(s.iu)} <b>${CAT_NAME[s.iu] || s.iu}</b> <span class="note">official IUCN status</span></p>
    ${gauge}
    ${flags.map(([c, t]) => `<p class="flag ${c}">${t}</p>`).join("")}
    ${drivers}
    <dl>
      <dt>Criterion B (prelim.)</dt><dd>${esc(s.cb)}</dd>
      <dt>Range</dt><dd>EOO ${fmtInt(s.eoo)} km² · AOO ≥ ${fmtInt(s.aoo)} km²</dd>
      <dt>Records</dt><dd>${fmtInt(s.nn || 0)} in native range (${fmtPct(s.fn || 0)} of ${fmtInt(s.gc || 0)} GBIF records)</dd>
      <dt>Native to</dt><dd>${s.l3 ? s.l3.split(" ").length + " botanical countries" : "unknown"}${s.end ? " · endemic to the Indian subcontinent" : ""}</dd>
      <dt>Recorded uses</dt><dd>${fmtInt(s.u)} records · ${fmtInt(s.ua || 0)} distinct uses in South Asia</dd>
      ${s.tu ? `<dt>Most recorded</dt><dd>${esc(s.tu)} <span class="note">(as documented in literature, not verified efficacy)</span></dd>` : ""}
      ${s.sc ? `<dt>Recorded from</dt><dd>${esc(s.sc)}</dd>` : ""}
    </dl>`;
  spLayer.clearLayers();
  $("#spmap-note").textContent = "Loading records…";
  fetch(`data/points/${s.k}.json`).then((r) => (r.ok ? r.json() : [])).then((pts) => {
    if (!pts.length) { $("#spmap-note").textContent = "No native-range georeferenced records."; return; }
    const col = d3.scaleSequential(d3.interpolateViridis).domain([1900, 2025]).clamp(true);
    pts.forEach(([la, lo, n, y]) => L.circleMarker([la, lo], { radius: 4, weight: 0.6, color: "#17251D", fillColor: y ? col(y) : "#999", fillOpacity: .85 })
      .bindTooltip(`${n} record${n > 1 ? "s" : ""}${y ? ", latest " + y : ""}`).addTo(spLayer));
    spMap.invalidateSize();
    spMap.fitBounds(L.latLngBounds(pts.map((p) => [p[0], p[1]])).pad(0.15), { maxZoom: 7 });
    $("#spmap-note").textContent = `${fmtInt(pts.length)} native-range grid cells (~2.4 km) with GBIF records · colour = year of latest record (purple = old, yellow = recent)`;
  });
  if (scroll) document.getElementById("explorer").scrollIntoView({ behavior: "smooth" });
}

/* ------------------------------------------------------------------ validation */
function renderValidation() {
  $("#val-lead").innerHTML = `Trained and tested on <b>${fmtInt(M.n_train)}</b> vascular plants with an official IUCN category (${fmtInt(M.n_train_threatened)} threatened), from ${M.n_families} families: the assessed flora native to the Indian subcontinent plus every assessed medicinal species. Cross-validation is grouped by plant family, so no family is in both train and test, and it is repeated over 5 seeds. Medicinal-use data is <b>not</b> a model input.`;
  const b = M.baseline_all, ml = M.ml_all, sd = M.ml_all_sd, at = M.at_threshold.all;
  const rows = [
    ["ROC-AUC", b.roc_auc, ml.roc_auc, `±${sd.roc_auc.toFixed(3)}`, 3],
    ["Sensitivity", b.sensitivity, at.sensitivity, "", 2],
    ["Specificity", b.specificity, at.specificity, "", 2],
    ["Balanced accuracy", b.balanced_accuracy, at.balanced_accuracy, "", 2],
    ["ROC-AUC, medicinal only", M.baseline_medicinal.roc_auc, M.ml_medicinal.roc_auc, `±${M.ml_medicinal_sd.roc_auc.toFixed(3)}`, 3],
  ];
  $("#val-table").innerHTML = `<tr><th>Metric</th><th>Criterion-B rule</th><th>RedRoot</th></tr>` +
    rows.map(([l, a, c, e, dp]) => `<tr><td>${l}</td><td>${a.toFixed(dp)}</td><td class="${c > a ? "win" : ""}">${c.toFixed(dp)}${e ? `<br><span class="sd">${e}</span>` : ""}</td></tr>`).join("");
  $("#val-note").innerHTML = `Sensitivity, specificity and balanced accuracy are at the screening threshold of ${fmtP(T)}, chosen on out-of-fold predictions. Range-size features alone reach AUC ${M.range_only_auc_mean.toFixed(3)}.`;
  const cm = (title, mtx) => {
    const max = d3.max(mtx.flat()), sh = (v) => `rgba(180,67,46,${0.12 + 0.75 * v / max})`;
    return `<div class="cm"><h4>${title}</h4><div class="cm-grid">
      <div class="h"></div><div class="h">pred. not thr.</div><div class="h">pred. threatened</div>
      <div class="h">IUCN not thr.</div><div class="c" style="background:${sh(mtx[0][0])}">${fmtInt(mtx[0][0])}</div><div class="c" style="background:${sh(mtx[0][1])}">${fmtInt(mtx[0][1])}</div>
      <div class="h">IUCN threatened</div><div class="c" style="background:${sh(mtx[1][0])}">${fmtInt(mtx[1][0])}</div><div class="c" style="background:${sh(mtx[1][1])}">${fmtInt(mtx[1][1])}</div>
    </div></div>`;
  };
  $("#cms").innerHTML = cm("Criterion-B rule", M.confusion_baseline_all) + cm("RedRoot (cut-off 0.5)", M.confusion_ml_all);
  const mx = d3.max(IMP, (d) => d.importance);
  $("#imp").innerHTML = IMP.slice(0, 10).map((d) => `<div class="bar"><span>${esc(d.label.replace(/^life /, "Life form: ").replace(/^climate /, "Climate: "))}</span><div class="track"><div class="fill" style="width:${Math.max(2, 100 * d.importance / mx)}%"></div></div></div>`).join("");
  if (M.assessment_yield) setupYield();
  if (M.calibration) renderCalibration();
}

/* decision value: threatened species found when assessors work down a ranking (out-of-fold) */
function setupYield() {
  const seg = $("#yield-seg");
  const draw = (key) => {
    seg.querySelectorAll("button").forEach((b) => b.classList.toggle("on", b.dataset.k === key));
    renderYield(M.assessment_yield[key], key);
  };
  seg.addEventListener("click", (e) => { const b = e.target.closest("button"); if (b) draw(b.dataset.k); });
  draw("all");
}
function renderYield(Y, key) {
  const el = $("#yield"); el.innerHTML = "";
  const W = el.clientWidth || 560, H = el.clientHeight || 320, m = { t: 12, r: 16, b: 44, l: 52 };
  const pts = Y.k.map((k, i) => ({ k, r: Y.redroot[i], b: Y.range_rule[i], n: Y.random[i] }));
  const x = d3.scaleLinear().domain([0, Y.n]).range([m.l, W - m.r]);
  const y = d3.scaleLinear().domain([0, Y.n_threatened]).range([H - m.b, m.t]).nice();
  const svg = d3.select(el).append("svg").attr("viewBox", `0 0 ${W} ${H}`);
  svg.append("g").attr("class", "grid").attr("transform", `translate(${m.l},0)`)
    .call(d3.axisLeft(y).ticks(5).tickSize(-(W - m.l - m.r)).tickFormat("")).call((g) => g.select(".domain").remove());
  svg.append("g").attr("class", "axis").attr("transform", `translate(0,${H - m.b})`).call(d3.axisBottom(x).ticks(6));
  svg.append("g").attr("class", "axis").attr("transform", `translate(${m.l},0)`).call(d3.axisLeft(y).ticks(5));
  svg.append("text").attr("class", "axis-label").attr("x", W - m.r).attr("y", H - 8).attr("text-anchor", "end").text("Species assessed, in ranked order →");
  svg.append("text").attr("class", "axis-label").attr("transform", "rotate(-90)").attr("x", -m.t).attr("y", 14).attr("text-anchor", "end").text("Threatened species found →");
  const lines = [["n", "#A9AFA9", "3 4", 2], ["b", "#17251D", "", 2], ["r", "#B4432E", "", 3]];
  lines.forEach(([f, c, dash, w]) => svg.append("path").datum(pts).attr("fill", "none").attr("stroke", c).attr("stroke-width", w)
    .attr("stroke-dasharray", dash).attr("d", d3.line().x((d) => x(d.k)).y((d) => y(d[f]))));
  const at = Y.at["100"];
  $("#yield-legend").innerHTML = [["#B4432E", "RedRoot ranking"], ["#17251D", "Range-size rule (smallest AOO first)"], ["#A9AFA9", "Random order"]]
    .map(([c, l]) => `<span><i class="sw" style="background:${c}"></i>${l}</span>`).join("");
  $("#yield-note").innerHTML = `${key === "all" ? `All ${fmtInt(Y.n)} assessed species` : `The ${fmtInt(Y.n)} assessed medicinal species`}, ranked out-of-fold. Assessing the top 100 finds <b>${at.redroot}</b> threatened species with RedRoot, ${at.range_rule} with the range rule and about ${Math.round(at.random)} at random. Finding half of the ${Y.n_threatened} threatened species takes <b>${Y.k_half_redroot}</b> assessments with RedRoot, against ${Y.k_half_range_rule} and ${fmtInt(Y.k_half_random)}.`;
}

/* calibration: reliability diagram of raw scores and of the calibrated share */
function renderCalibration() {
  const C = M.calibration, el = $("#calib"); el.innerHTML = "";
  const W = el.clientWidth || 560, H = el.clientHeight || 320, m = { t: 12, r: 16, b: 44, l: 64 };
  const x = d3.scaleLinear().domain([0, 1]).range([m.l, W - m.r]), y = d3.scaleLinear().domain([0, 1]).range([H - m.b, m.t]);
  const svg = d3.select(el).append("svg").attr("viewBox", `0 0 ${W} ${H}`);
  svg.append("g").attr("class", "grid").attr("transform", `translate(${m.l},0)`)
    .call(d3.axisLeft(y).ticks(5).tickSize(-(W - m.l - m.r)).tickFormat("")).call((g) => g.select(".domain").remove());
  svg.append("g").attr("class", "axis").attr("transform", `translate(0,${H - m.b})`).call(d3.axisBottom(x).ticks(5));
  svg.append("g").attr("class", "axis").attr("transform", `translate(${m.l},0)`).call(d3.axisLeft(y).ticks(5, ".0%"));
  svg.append("text").attr("class", "axis-label").attr("x", W - m.r).attr("y", H - 8).attr("text-anchor", "end").text("Predicted, mean per bin →");
  svg.append("text").attr("class", "axis-label").attr("transform", "rotate(-90)").attr("x", -m.t).attr("y", 14).attr("text-anchor", "end").text("Observed share threatened →");
  svg.append("line").attr("x1", x(0)).attr("y1", y(0)).attr("x2", x(1)).attr("y2", y(1)).attr("stroke", "#A9AFA9").attr("stroke-dasharray", "3 4");
  const r = d3.scaleSqrt().domain([0, d3.max(C.bins_raw.concat(C.bins_calibrated), (d) => d.n)]).range([3, 13]);
  const series = [[C.bins_raw, "#FBF9F4", "#B4432E"], [C.bins_calibrated, "#17251D", "#17251D"]];
  series.forEach(([bins, fill, stroke]) => {
    svg.append("path").datum(bins).attr("fill", "none").attr("stroke", stroke).attr("stroke-width", 1.2).attr("opacity", .6)
      .attr("d", d3.line().x((d) => x(d.mean_p)).y((d) => y(d.observed)));
    svg.append("g").selectAll("circle").data(bins).join("circle").attr("cx", (d) => x(d.mean_p)).attr("cy", (d) => y(d.observed))
      .attr("r", (d) => r(d.n)).attr("fill", fill).attr("stroke", stroke).attr("stroke-width", 2)
      .append("title").text((d) => `${d.n} species · predicted ${fmtP(d.mean_p)} · observed ${fmtP(d.observed)}`);
  });
  $("#calib-legend").innerHTML = `<span><i class="sw" style="background:#FBF9F4;border:2px solid #B4432E"></i>Raw score (ECE ${C.ece_raw.toFixed(3)})</span><span><i class="sw" style="background:#17251D"></i>Calibrated share (ECE ${C.ece_calibrated.toFixed(3)})</span>`;
  $("#calib-note").innerHTML = `Circle size = species per bin; the dashed line is perfect calibration. The model is trained with balanced class weights, so raw scores are a ranking, inflated at the top. An isotonic map, checked by family-grouped cross-fitting, turns a score into the share of similar assessed species that are threatened; the species cards report that share. At the screening threshold it is about ${fmtPct(C.share_threatened_at_threshold)}.`;
}

/* ------------------------------------------------------------------ methods */
function renderMethods() {
  fetch("methods.md").then((r) => r.text()).then((md) => { $("#methods-body").innerHTML = marked.parse(md); });
}
