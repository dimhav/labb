/* =====================================================================
   pgsqlmesh portal - frontend
   Flikar: Oversikt, Versioner & sakerhet, Data, Superset.
   ===================================================================== */

const SEV_ORDER = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "UNKNOWN"];
const $ = (sel) => document.querySelector(sel);

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[c]);
}

/* ------------------------------------------------------------------ */
/*  Flikar                                                            */
/* ------------------------------------------------------------------ */
function initTabs() {
  document.querySelectorAll(".tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
      document.querySelectorAll(".tab-panel").forEach((p) => p.classList.remove("active"));
      tab.classList.add("active");
      $(`#tab-${tab.dataset.tab}`).classList.add("active");
      if (tab.dataset.tab === "data") loadTables();
      if (tab.dataset.tab === "overview") loadOverview();
      if (tab.dataset.tab === "superset") loadSupersetInfo();
    });
  });
}

/* ------------------------------------------------------------------ */
/*  Oversikt                                                          */
/* ------------------------------------------------------------------ */
async function loadOverview() {
  try {
    const res = await fetch("/api/overview");
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const d = await res.json();
    renderServices(d.services, d.running_versions, d.versions);
    renderWarehouse(d.warehouse);
  } catch (err) {
    $("#services").innerHTML = `<div class="card-error">${esc(err.message)}</div>`;
  }
}

function renderServices(services, running, declared) {
  const wrap = $("#services");
  if (!services || !services.length) {
    wrap.innerHTML = '<div class="card-error">Inga tjänster hittades.</div>';
    return;
  }
  running = running || {};
  wrap.innerHTML = services
    .map((s) => {
      const health = s.health || (s.state === "running" ? "running" : "");
      const dot = health === "healthy" ? "ok"
        : s.state === "running" ? "warn" : "err";
      const ver = running[s.service];
      return `
        <article class="service-card">
          <div class="service-top">
            <span class="dot ${dot}"></span>
            <strong>${esc(s.service)}</strong>
            ${ver ? `<span class="service-ver">${esc(ver)}</span>` : ""}
          </div>
          <p class="service-image">${esc(s.image || "?")}</p>
          <p class="service-state">${esc(s.state || "?")}${health ? " · " + esc(health) : ""}</p>
        </article>`;
    })
    .join("");
}

function renderWarehouse(w) {
  const wrap = $("#warehouse");
  if (!w || w.error) {
    wrap.innerHTML = `<div class="card-error">Kunde inte läsa datalagret: ${esc(w?.error || "okänt fel")}</div>`;
    return;
  }
  const counts = w.table_counts || {};
  const rows = w.rows_by_schema || {};
  wrap.innerHTML = `
    <div class="stat"><span class="stat-num">${esc(w.server_version || "?")}</span><span class="stat-lbl">Postgres-version</span></div>
    <div class="stat"><span class="stat-num">${esc(counts.raw ?? 0)}</span><span class="stat-lbl">tabeller i raw</span></div>
    <div class="stat"><span class="stat-num">${esc((rows.raw ?? 0).toLocaleString("sv-SE"))}</span><span class="stat-lbl">rader i raw</span></div>
    <div class="stat"><span class="stat-num">${esc(counts.analytics ?? 0)}</span><span class="stat-lbl">vyer i analytics</span></div>
    <div class="stat"><span class="stat-num">${esc((rows.analytics ?? 0).toLocaleString("sv-SE"))}</span><span class="stat-lbl">rader i analytics</span></div>`;
}

/* ------------------------------------------------------------------ */
/*  Versioner & sakerhet                                              */
/* ------------------------------------------------------------------ */
async function runCheck() {
  const btn = $("#check-btn");
  btn.disabled = true;
  btn.classList.add("spinning");
  $("#empty").classList.add("hidden");
  $("#summary").classList.add("hidden");
  $("#cards").innerHTML =
    '<div class="empty"><span class="spinner-inline"></span> ' +
    "Hämtar senaste versioner och skannar efter CVE:er ...</div>";

  let first = true;
  try {
    const res = await fetch("/api/check", { method: "POST" });
    if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`);

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const parts = buffer.split("\n\n");
      buffer = parts.pop();
      for (const part of parts) {
        const line = part.replace(/^data: /, "").trim();
        if (!line) continue;
        let evt;
        try { evt = JSON.parse(line); } catch { continue; }

        if (evt.type === "component") {
          if (first) { $("#cards").innerHTML = ""; first = false; }
          $("#cards").appendChild(buildCard(evt.component));
        } else if (evt.type === "done") {
          renderSummary(evt);
        }
      }
    }
  } catch (err) {
    $("#cards").innerHTML =
      `<div class="card-error">Kontrollen misslyckades: ${esc(err.message)}</div>`;
  } finally {
    btn.disabled = false;
    btn.classList.remove("spinning");
  }
}

function renderSummary(data) {
  const el = $("#summary");
  const totals = data.totals || {};
  const chips = SEV_ORDER.filter((s) => (totals[s] || 0) > 0)
    .map((s) => `<span class="chip ${s}">${totals[s]} ${s}</span>`)
    .join("");
  const zero = Object.values(totals).every((n) => !n)
    ? '<span class="chip zero">0 sårbarheter</span>'
    : "";
  el.innerHTML = `
    <p>${esc(data.summary)}</p>
    <div class="sev-chips">${chips}${zero}</div>`;
  el.classList.remove("hidden");
}

function buildCard(c) {
  const card = document.createElement("article");
  card.className = "card";

  const hasUpdate = c.upgrade_available && c.recommended;
  const totalFindings = Object.values(c.severity_counts || {}).reduce((a, b) => a + b, 0);

  const badge = c.error
    ? '<span class="badge err">fel</span>'
    : c.drift
    ? '<span class="badge warn">avvikelse</span>'
    : hasUpdate
    ? '<span class="badge update">uppdatering finns</span>'
    : '<span class="badge ok">uppdaterad</span>';

  const verLine = hasUpdate
    ? `<span class="ver">${esc(c.current)}</span>
       <span class="arrow">→</span>
       <span class="ver new">${esc(c.recommended)}</span>`
    : `<span class="ver">${esc(c.current || "?")}</span>`;

  const head = `
    <div class="card-head">
      <div class="card-title">
        <div>
          <h2>${esc(c.name)} ${badge}</h2>
          <p class="card-role">${esc(c.role)}</p>
        </div>
      </div>
      <div class="ver-line">
        ${verLine}
        ${c.latest && c.latest !== c.current ? `<small class="muted">senaste: ${esc(c.latest)}</small>` : ""}
      </div>
    </div>
    ${c.drift ? `<div class="card-error">⚠ Avvikelse: .env anger ${esc(c.declared)} men tjänsten kör ${esc(c.current)}. Starta om tjänsten eller uppdatera igen.</div>` : ""}`;

  let findingsHtml;
  if (c.error) {
    findingsHtml = `<div class="card-error">${esc(c.error)}</div>`;
  } else if (totalFindings === 0) {
    findingsHtml =
      '<div class="no-findings">✓ Inga kända sårbarheter för denna version.</div>';
  } else {
    findingsHtml =
      `<ul class="findings">${(c.findings || []).map(findingRow).join("")}</ul>`;
  }

  let residualNote = "";
  if (hasUpdate && c.residual) {
    const r = c.residual.severity_counts || {};
    const rTotal = c.residual.total || 0;
    residualNote = `<p class="residual-note">Efter uppdatering till ${esc(
      c.residual.version
    )}: ${rTotal} kvarvarande fynd` +
      (rTotal
        ? ` (${["CRITICAL", "HIGH", "MEDIUM", "LOW"]
            .filter((s) => r[s])
            .map((s) => `${r[s]} ${s}`)
            .join(", ")})`
        : " - rent") +
      `.</p>`;
  }

  const actionsHtml = (c.actions || [])
    .map((a) => {
      const isUpgrade = a.type === "upgrade";
      const cls = ["action", a.priority].filter(Boolean).join(" ");
      const cta = isUpgrade
        ? `<div class="action-cta">
             <button class="btn btn-upgrade ${a.priority === "critical" ? "danger" : ""}"
                     data-upgrade="${esc(c.key)}" data-target="${esc(a.target)}">
               Uppdatera till ${esc(a.target)}
             </button>
           </div>`
        : "";
      return `
        <li class="${cls}">
          <div class="action-title">${esc(a.title)}</div>
          <p class="action-detail">${esc(a.detail)}</p>
          ${cta}
        </li>`;
    })
    .join("");

  const body = `
    <div class="card-body">
      <div>
        <p class="section-label">Säkerhetsrisker (${totalFindings})</p>
        ${findingsHtml}
      </div>
      <div>
        <p class="section-label">Åtgärdsförslag</p>
        ${residualNote}
        <ul class="actions">${actionsHtml}</ul>
      </div>
    </div>`;

  card.innerHTML = head + body;
  card.querySelectorAll("[data-upgrade]").forEach((btn) => {
    btn.addEventListener("click", () =>
      startUpgrade(btn.dataset.upgrade, btn.dataset.target)
    );
  });
  return card;
}

function findingRow(f) {
  const url = (f.references || [])[0] || `https://nvd.nist.gov/vuln/detail/${f.id}`;
  const score = f.score != null ? `CVSS ${f.score}` : "";
  const fix = f.fixed_in
    ? `<p class="finding-fix">Rätas i version ${esc(f.fixed_in)}</p>`
    : "";
  return `
    <li class="finding ${esc(f.severity)}">
      <div class="finding-top">
        <span class="finding-id"><a href="${esc(url)}" target="_blank" rel="noopener">${esc(f.id)}</a></span>
        <span class="sev ${esc(f.severity)}">${esc(f.severity)}</span>
        <span class="score">${esc(score)}</span>
      </div>
      <p class="finding-summary">${esc(f.summary)}</p>
      ${fix}
    </li>`;
}

/* ------------------------------------------------------------------ */
/*  Data                                                              */
/* ------------------------------------------------------------------ */
async function loadTables() {
  const wrap = $("#data-tables");
  wrap.innerHTML = '<div class="empty"><span class="spinner-inline"></span> Läser tabeller ...</div>';
  try {
    const res = await fetch("/api/data/tables");
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const d = await res.json();
    renderTables(d.tables || []);
  } catch (err) {
    wrap.innerHTML = `<div class="card-error">${esc(err.message)}</div>`;
  }
}

function renderTables(tables) {
  const wrap = $("#data-tables");
  if (!tables.length) {
    wrap.innerHTML = '<div class="empty">Inga tabeller hittades.</div>';
    return;
  }
  const bySchema = {};
  tables.forEach((t) => {
    (bySchema[t.table_schema] ||= []).push(t);
  });
  wrap.innerHTML = Object.entries(bySchema)
    .map(
      ([schema, rows]) => `
      <div class="schema-block">
        <h3>${esc(schema)}</h3>
        <ul class="table-list">
          ${rows
            .map(
              (t) => `
            <li class="table-item" data-schema="${esc(t.table_schema)}" data-table="${esc(t.table_name)}">
              <span class="table-name">${esc(t.table_name)}</span>
              <span class="table-rows">${t.rows != null ? t.rows.toLocaleString("sv-SE") + " rader" : ""}</span>
            </li>`
            )
            .join("")}
        </ul>
      </div>`
    )
    .join("");

  wrap.querySelectorAll(".table-item").forEach((el) => {
    el.addEventListener("click", () => openTable(el.dataset.schema, el.dataset.table));
  });
}

async function openTable(schema, table) {
  const dialog = $("#table-dialog");
  $("#table-title").textContent = `${schema}.${table}`;
  $("#table-meta").textContent = "";
  $("#table-wrap").innerHTML = '<div class="empty"><span class="spinner-inline"></span> Hämtar rader ...</div>';
  dialog.showModal();
  try {
    const res = await fetch(`/api/data/${encodeURIComponent(schema)}/${encodeURIComponent(table)}?limit=25`);
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    const d = await res.json();
    renderPreview(d);
  } catch (err) {
    $("#table-wrap").innerHTML = `<div class="card-error">${esc(err.message)}</div>`;
  }
}

function renderPreview(d) {
  $("#table-meta").textContent =
    `${d.columns.length} kolumner · visar ${d.rows.length} rader`;
  if (!d.rows.length) {
    $("#table-wrap").innerHTML = '<div class="empty">Tabellen är tom.</div>';
    return;
  }
  const head = d.columns.map((c) =>
    `<th title="${esc(d.column_types[c] || "")}">${esc(c)}</th>`).join("");
  const body = d.rows
    .map(
      (r) =>
        `<tr>${d.columns
          .map((c) => `<td>${r[c] === null ? '<span class="null">NULL</span>' : esc(r[c])}</td>`)
          .join("")}</tr>`
    )
    .join("");
  $("#table-wrap").innerHTML =
    `<table class="data-table"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
}

/* ------------------------------------------------------------------ */
/*  Superset                                                          */
/* ------------------------------------------------------------------ */
function loadSupersetInfo() {
  const { protocol, hostname, port } = window.location;
  let url;
  if (port === "12000") {
    // Lokalt: Superset lyssnar pa port 12001 pa samma vard.
    url = `${protocol}//${hostname}:12001/`;
  } else if (hostname.includes("work-1-")) {
    // Fjarrmiljo: work-2-varden motsvarar port 12001.
    url = `${protocol}//${hostname.replace("work-1-", "work-2-")}/`;
  } else {
    url = "/superset/";
  }
  const link = $("#superset-open");
  link.href = url;
  link.title = url;
}

/* ------------------------------------------------------------------ */
/*  Uppdatering (SSE)                                                 */
/* ------------------------------------------------------------------ */
function startUpgrade(key, target) {
  const dialog = $("#upgrade-dialog");
  const log = $("#dialog-log");
  const closeBtn = $("#dialog-close");
  $("#dialog-title").textContent = `Uppdaterar ${key} till ${target} ...`;
  log.innerHTML = "";
  closeBtn.disabled = true;
  dialog.showModal();

  fetch("/api/upgrade", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ key, target }),
  })
    .then((res) => {
      if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`);
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      const pump = () =>
        reader.read().then(({ value, done }) => {
          if (done) return;
          buffer += decoder.decode(value, { stream: true });
          const parts = buffer.split("\n\n");
          buffer = parts.pop();
          parts.forEach((part) => {
            const line = part.replace(/^data: /, "").trim();
            if (!line) return;
            try {
              handleEvent(JSON.parse(line), log, closeBtn);
            } catch { /* ignorera ofullstandig rad */ }
          });
          return pump();
        });
      return pump();
    })
    .catch((err) => {
      appendLog(log, `Fel: ${err.message}`, "err");
      closeBtn.disabled = false;
    });

  closeBtn.onclick = () => {
    dialog.close();
    runCheck();
    loadOverview();
  };
}

function handleEvent(evt, log, closeBtn) {
  if (evt.type === "log") {
    const cls = evt.line.startsWith("$") ? "cmd"
      : /\[(varning|info)\]/.test(evt.line) ? "warn"
      : /slutkod [1-9]/.test(evt.line) ? "err"
      : /(healthy|klart|nu pa|rätar|uppe|verifierat)/.test(evt.line) ? "ok" : "";
    appendLog(log, evt.line, cls);
  } else if (evt.type === "done") {
    if (evt.ok) {
      appendLog(log, "\n=== Uppdatering klar ===", "ok");
    } else {
      appendLog(log, `\n=== Misslyckades: ${evt.error} ===`, "err");
    }
    closeBtn.disabled = false;
  }
}

function appendLog(log, text, cls) {
  const span = document.createElement("span");
  span.className = cls || "";
  span.textContent = text + "\n";
  log.appendChild(span);
  log.scrollTop = log.scrollHeight;
}

/* ------------------------------------------------------------------ */
/*  Driftstatus i topbaren                                            */
/* ------------------------------------------------------------------ */
async function loadStatus() {
  try {
    const res = await fetch("/api/status");
    if (!res.ok) return;
    const d = await res.json();
    const bad = d.services.filter((s) => s.state !== "running");
    const el = $("#stack-status");
    if (bad.length) {
      el.className = "stack-status err";
      el.textContent = `${bad.length} tjänst(er) nere`;
    } else {
      el.className = "stack-status ok";
      el.textContent = `● ${d.services.length} tjänster uppe`;
    }
  } catch { /* tyst */ }
}

/* ------------------------------------------------------------------ */
/*  Init                                                              */
/* ------------------------------------------------------------------ */
initTabs();
$("#check-btn").addEventListener("click", runCheck);
$("#refresh-btn").addEventListener("click", loadOverview);
$("#data-refresh").addEventListener("click", loadTables);
$("#table-close").addEventListener("click", () => $("#table-dialog").close());

loadStatus();
loadOverview();
loadSupersetInfo();
setInterval(loadStatus, 15000);
