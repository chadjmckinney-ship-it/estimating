import { Api } from "./api.js";
import { toShown, toStored } from "./units.js";
import {
  day as dayLabel,
  initDaily,
  openReportModal,
  renderCalendar,
  renderDaily,
  renderReportForm,
  shiftDays,
  todayLocal,
} from "./daily.js";

const $ = (sel, el = document) => el.querySelector(sel);
const $$ = (sel, el = document) => [...el.querySelectorAll(sel)];

const state = {
  route: "home",
  // Who is signed in (sql/068): {id, username, full_name, role}, or null.
  user: null,
  projectId: null,
  estimateId: null,
  // The section the estimate page is currently editing (sql/033-034). Set when
  // an estimate opens; the pour and beam modals read it.
  sectionId: null,
  // The daily report being edited on the form page (sql/084); null files a new one.
  reportId: null,
  estimators: [],
  projectTypes: [],
  projectStatuses: [],
  mixes: [],
  // The bar catalog (sql/066), loaded with the mixes; BAR_SIZES is the fallback.
  barSizes: [],
};

function toast(msg, kind = "ok") {
  const el = document.createElement("div");
  el.className = `toast ${kind}`;
  el.textContent = msg;
  document.body.appendChild(el);
  setTimeout(() => el.remove(), 3200);
}

function money(n) {
  if (n == null || n === "") return "—";
  const v = Number(n);
  if (Number.isNaN(v)) return "—";
  return v.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 4 });
}

function usd(n, digits = 0) {
  if (n == null || n === "") return "—";
  const v = Number(n);
  if (Number.isNaN(v)) return "—";
  return v.toLocaleString(undefined, {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

function num(n, digits = 2) {
  if (n == null || n === "") return "—";
  const v = Number(n);
  if (Number.isNaN(v)) return "—";
  return v.toLocaleString(undefined, {
    minimumFractionDigits: 0,
    maximumFractionDigits: digits,
  });
}

// ------------------------------------------- the money on the stat cards ----
// The cards at the top of a section have always shown the takeoff — 2,205 CY,
// 21,945 lb, 158,109 SF of poly — with no price anywhere near it. These three
// helpers put the dollars on them, off /sections/{id}/material-costs.
//
// The rule they all follow: a material with no priced line renders as NOTHING,
// never as $0. A zero is a claim that the thing is free; silence is the honest
// answer to "we could not price this", and the quantity is still on the card.

/** key -> line, so a card can ask for its own dollars by name. */
function matIndex(payload) {
  const by = {};
  for (const ln of (payload && payload.lines) || []) by[ln.key] = ln;
  return by;
}

/** Rates run from $0.04/lb to $155/CY, so the decimals follow the number. */
function rateUsd(v) {
  return usd(v, Math.abs(Number(v)) < 10 ? 4 : 2);
}

/** "$295,496 · $134.00/CY" — the line's own total and the rate behind it. */
function matCost(mat, key) {
  const ln = mat[key];
  if (!ln) return "";
  // A NULL master price is unpriced, not free (sql/047). The dollars on this
  // line are light by an unknown amount, so say that, not "$0".
  if (ln.unpriced && ln.unpriced.length) {
    return `<span class="badge warn">unpriced</span> ${esc(ln.unpriced.join(", "))}`;
  }
  const quoted = String(ln.source || "").startsWith("quote") ? " quoted" : "";
  const rate =
    ln.unit_cost == null ? "" : ` · ${rateUsd(ln.unit_cost)}/${ln.unit}`;
  return `${usd(ln.cost, 0)}${quoted}${rate}`;
}

/**
 * A COMPONENT of a priced line, at that line's rate — slab mat and support
 * steel are both part of one rebar buy, and neither is quoted on its own.
 * Priced here rather than on the server because it is arithmetic on a rate
 * that is already on screen, not a second opinion about what steel costs.
 */
function matAt(mat, key, qty) {
  const ln = mat[key];
  const q = Number(qty);
  if (!ln || ln.unit_cost == null || !q || Number.isNaN(q)) return "";
  return `${usd(Number(ln.unit_cost) * q, 0)} at ${rateUsd(ln.unit_cost)}/${ln.unit}`;
}

/** The money line on a stat card — omitted entirely when there is none. */
function moneyRow(s) {
  return s ? `<div class="money">${s}</div>` : "";
}

/** SF per CY of concrete (includes slab + beams + waste). */
function sfPerCy(sf, cy) {
  const c = Number(cy);
  const s = Number(sf);
  if (!c || Number.isNaN(c) || Number.isNaN(s)) return null;
  return s / c;
}

function statusBadge(status) {
  const map = {
    not_started: "warn",
    in_progress: "info",
    submitted: "accent",
    awarded: "ok",
    draft: "info",
    in_review: "warn",
    final: "ok",
    archived: "",
    lost: "",
    no_bid: "",
  };
  const cls = map[status] || "";
  const label = (status || "").replace(/_/g, " ");
  return `<span class="badge ${cls}">${esc(label)}</span>`;
}

function esc(s) {
  return String(s ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

/**
 * Modals hang off document.body, not #app, so changing page leaves them
 * floating over the new one. Navigation closes them; render() must not, since
 * some modals re-render the page behind themselves while staying open.
 */
function closeAllModals() {
  $$(".modal-backdrop").forEach((el) => el.remove());
}

function setRoute(route, params = {}) {
  closeAllModals();
  state.route = route;
  state.projectId = params.projectId || null;
  state.estimateId = params.estimateId || null;
  state.sectionId = params.sectionId || null;
  state.reportId = params.reportId || null;
  $$(".nav button").forEach((b) => {
    const active =
      b.dataset.route === route ||
      (route === "project" && b.dataset.route === "projects") ||
      (route === "estimate" && b.dataset.route === "projects") ||
      (route === "section" && b.dataset.route === "projects") ||
      (route === "prices" && b.dataset.route === "projects") ||
      (route === "proposal" && b.dataset.route === "projects") ||
      (route === "report" && b.dataset.route === "daily");
    b.classList.toggle("active", active);
  });
  render();
  let hash = `#${route}`;
  if (route === "project" && state.projectId) hash = `#project/${state.projectId}`;
  if (route === "estimate" && state.estimateId) hash = `#estimate/${state.estimateId}`;
  if (route === "section" && state.sectionId) hash = `#section/${state.sectionId}`;
  if (route === "prices" && state.estimateId) hash = `#prices/${state.estimateId}`;
  if (route === "proposal" && state.estimateId) hash = `#proposal/${state.estimateId}`;
  if (route === "report" && state.reportId) hash = `#report/${state.reportId}`;
  if (location.hash !== hash) history.replaceState(null, "", hash);
}

function parseHash() {
  const h = location.hash.replace(/^#/, "") || "home";
  if (h.startsWith("project/")) {
    return { route: "project", projectId: h.slice("project/".length), estimateId: null };
  }
  if (h.startsWith("estimate/")) {
    return { route: "estimate", projectId: null, estimateId: h.slice("estimate/".length) };
  }
  // A section is deep-linkable in its own right — an estimator working paving
  // should be able to bookmark it, not navigate through the job every time.
  if (h.startsWith("section/")) {
    return { route: "section", projectId: null, estimateId: null, sectionId: h.slice("section/".length) };
  }
  if (h.startsWith("prices/")) {
    return { route: "prices", projectId: null, estimateId: h.slice("prices/".length), sectionId: null };
  }
  if (h === "estimators") return { route: "users", projectId: null, estimateId: null, sectionId: null }; // the old bookmark
  if (h.startsWith("report/")) {
    return { route: "report", projectId: null, estimateId: null, sectionId: null, reportId: h.slice("report/".length) };
  }
  return { route: h, projectId: null, estimateId: null, sectionId: null };
}

async function checkHealth() {
  const dot = $("#api-dot");
  const label = $("#api-status");
  try {
    const h = await Api.health();
    dot.classList.add("ok");
    label.textContent = `API online · ${h.db || "ok"}`;
  } catch {
    dot.classList.remove("ok");
    label.textContent = "API offline — start uvicorn on :8001";
  }
}

// ---------- Pages ----------

// The dashboard (2026-09-09, Chad: "now the dashboard..."): four cards that
// change what you do next — bids, projects, today in the field, this month —
// the bids due soon, the latest daily reports, the recent projects, and the
// catalog counts as one muted line at the bottom. Everything here is read
// through the same calls the pages make; nothing is computed on the server for it.
async function renderHome(root) {
  root.innerHTML = `<div class="loading">Loading dashboard…</div>`;
  const today = todayLocal();
  const [bids, projects, estimates, reports, month, mixes, materials, equipment, people] = await Promise.all([
    Api.listBids(),
    Api.listProjects(),
    Api.listEstimates(),
    Api.listDailyReports({ date_from: shiftDays(today, -14), limit: 200 }),
    Api.dailyReportSummary({ date_from: today.slice(0, 7) + "-01" }),
    Api.listMixes({ active_only: true }),
    Api.listMaterials({ active_only: true }),
    Api.listEquipment({ active_only: true }),
    Api.listEstimators({ active_only: true }),
  ]);

  const openBids = bids.filter((b) => BID_OPEN.has(b.status));
  const days = (b) => bidDaysLeft(b);
  const dueWeek = openBids.filter((b) => days(b) !== null && days(b) >= 0 && days(b) <= 7).length;
  const overdue = openBids.filter((b) => days(b) !== null && days(b) < 0).length;
  const soon = openBids
    .filter((b) => b.bid_due)
    .sort((a, b) => `${a.bid_due} ${a.bid_due_time || ""}`.localeCompare(`${b.bid_due} ${b.bid_due_time || ""}`))
    .slice(0, 8);

  const open = projects.filter((p) => !["archived", "awarded", "lost", "no_bid"].includes(p.status));
  const openIds = new Set(open.map((p) => p.id));
  const estimatesOn = estimates.filter((e) => openIds.has(e.project_id)).length;

  // Today in the field — or yesterday's, when nothing has come in yet today.
  let fieldDay = today;
  let filed = reports.filter((r) => r.report_date === today);
  if (!filed.length) {
    const y = shiftDays(today, -1);
    const ys = reports.filter((r) => r.report_date === y);
    if (ys.length) {
      fieldDay = y;
      filed = ys;
    }
  }
  const poursToday = filed.filter((r) => r.concrete_poured);
  const yardsToday = poursToday.reduce((s, r) => s + Number(r.yards_poured || 0), 0);
  const m = month.reduce(
    (t, s) => ({
      reports: t.reports + s.reports,
      pours: t.pours + s.pours,
      yards: t.yards + Number(s.yards || 0),
      man_hours: t.man_hours + Number(s.man_hours || 0),
    }),
    { reports: 0, pours: 0, yards: 0, man_hours: 0 }
  );
  const latest = reports.slice(0, 8); // the list comes newest first
  const clamp =
    "display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;font-size:0.8rem;max-width:26rem";

  root.innerHTML = `
    <div class="page-header">
      <div>
        <h1>Dashboard</h1>
        <p>${esc(new Date().toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric", year: "numeric" }))}</p>
      </div>
    </div>
    <div class="grid stats">
      <div class="card stat clickable" data-go="bids" title="Open the bid list">
        <div class="label">Bids</div><div class="value">${openBids.length}</div>
        <div class="hint">open · <strong>${dueWeek}</strong> due this week${overdue ? ` · <strong style="color:var(--danger)">${overdue}</strong> overdue` : ""}</div>
      </div>
      <div class="card stat clickable" data-go="projects" title="Open the projects">
        <div class="label">Projects</div><div class="value">${open.length}</div>
        <div class="hint">in progress · ${estimatesOn} estimate${estimatesOn === 1 ? "" : "s"} on them</div>
      </div>
      <div class="card stat clickable" data-go="daily" title="Open the daily reports">
        <div class="label">${fieldDay === today ? "Today in the field" : "Yesterday in the field"}</div>
        <div class="value">${filed.length}</div>
        <div class="hint">report${filed.length === 1 ? "" : "s"} · ${poursToday.length} pour${poursToday.length === 1 ? "" : "s"}${poursToday.length ? ` · ${num(yardsToday, 1)} yards` : ""}</div>
      </div>
      <div class="card stat clickable" data-go="calendar" title="Open the calendar">
        <div class="label">This month</div><div class="value">${num(m.yards, 1)}</div>
        <div class="hint">yards · ${m.pours} pour${m.pours === 1 ? "" : "s"} · ${num(m.man_hours, 0)} crew man-hours</div>
      </div>
    </div>
    <div class="grid" style="grid-template-columns:repeat(auto-fit,minmax(360px,1fr));margin-bottom:1rem">
      <div class="card">
        <h3 style="margin:0 0 0.75rem">Bids due soon</h3>
        ${
          soon.length
            ? `<div class="table-wrap"><table class="data"><thead><tr><th>Due</th><th>Bid</th><th>GC</th><th>Estimators</th></tr></thead><tbody>${soon
                .map(
                  (b) => `<tr class="clickable" data-go="bids">
                  <td style="white-space:nowrap">${bidDueHtml(b)}</td>
                  <td><strong>${esc(b.name)}</strong></td>
                  <td class="muted">${esc(b.gc || "—")}</td>
                  <td class="muted">${esc((b.estimator_names || []).join(", ") || "—")}</td>
                </tr>`
                )
                .join("")}</tbody></table></div>`
            : `<div class="empty">No open bids with a due date.</div>`
        }
      </div>
      <div class="card">
        <h3 style="margin:0 0 0.75rem">Latest daily reports</h3>
        ${
          latest.length
            ? `<div class="table-wrap"><table class="data"><thead><tr><th>Date</th><th>Job</th><th>Foreman</th><th>Pour</th><th>Work</th></tr></thead><tbody>${latest
                .map(
                  (r) => `<tr class="clickable" data-report="${esc(r.id)}">
                  <td style="white-space:nowrap">${esc(dayLabel(r.report_date))}</td>
                  <td><strong>${esc(r.job_name)}</strong></td>
                  <td class="muted">${esc((r.foremen || []).join(", ") || "—")}</td>
                  <td style="white-space:nowrap">${r.concrete_poured ? `<span class="badge ok">${num(r.yards_poured, 1)} yd</span>` : `<span class="muted">—</span>`}</td>
                  <td><div class="muted" style="${clamp}" title="${esc(r.work_accomplished || "")}">${esc(r.work_accomplished || "")}</div></td>
                </tr>`
                )
                .join("")}</tbody></table></div>`
            : `<div class="empty">No daily reports in the last two weeks.</div>`
        }
      </div>
    </div>
    <div class="card">
      <h3 style="margin:0 0 0.75rem">Recent projects</h3>
      ${projectsTable(projects.slice(0, 8), { compact: true })}
    </div>
    <p class="muted" style="color:var(--text-muted);font-size:0.85rem;margin:1rem 0 0">
      Catalogs: ${mixes.length} mix designs · ${materials.length} materials · ${equipment.length} equipment · ${people.length} users
    </p>
  `;
  $$("[data-go]", root).forEach((el) => {
    el.onclick = () => setRoute(el.dataset.go);
  });
  $$("[data-report]", root).forEach((tr) => {
    tr.onclick = () => {
      const r = reports.find((x) => x.id === tr.dataset.report);
      if (r) openReportModal(r, { onChanged: render });
    };
  });
  bindProjectRows(root);
}

function projectsTable(projects, { compact } = {}) {
  if (!projects.length) return `<div class="empty">No projects yet.</div>`;
  return `
    <div class="table-wrap">
      <table class="data">
        <thead>
          <tr>
            <th>Project</th>
            <th>GC</th>
            <th>Location</th>
            <th>Bid due</th>
            <th>Status</th>
            ${compact ? "" : "<th>Types</th>"}
          </tr>
        </thead>
        <tbody>
          ${projects
            .map(
              (p) => `
            <tr class="clickable" data-project-id="${esc(p.id)}">
              <td><strong>${esc(p.name)}</strong></td>
              <td class="muted">${esc(p.gc || "—")}</td>
              <td class="muted">${esc(p.location || "—")}</td>
              <td>${esc(p.bid_due || "—")}</td>
              <td>${statusBadge(p.status)}</td>
              ${
                compact
                  ? ""
                  : `<td><div class="chips">${(p.project_types || [])
                      .map((t) => `<span class="chip">${esc(t)}</span>`)
                      .join("")}</div></td>`
              }
            </tr>`
            )
            .join("")}
        </tbody>
      </table>
    </div>`;
}

function bindProjectRows(root) {
  $$("tr[data-project-id]", root).forEach((tr) => {
    tr.addEventListener("click", () => setRoute("project", { projectId: tr.dataset.projectId }));
  });
}

async function renderProjects(root) {
  root.innerHTML = `<div class="loading">Loading projects…</div>`;
  if (!state.projectTypes.length) state.projectTypes = await Api.projectTypes();
  if (!state.projectStatuses.length) state.projectStatuses = await Api.projectStatuses();
  if (!state.estimators.length) state.estimators = await Api.listEstimators({ active_only: "true" });

  let status = "";
  let q = "";

  async function load() {
    const projects = await Api.listProjects({ status: status || undefined, q: q || undefined });
    $("#projects-body").innerHTML = projectsTable(projects);
    bindProjectRows($("#projects-body"));
  }

  root.innerHTML = `
    <div class="page-header">
      <div>
        <h1>Projects</h1>
        <p>Bid list jobs — GC, due dates, status (Notion-shaped).</p>
      </div>
      <button class="btn primary" id="btn-new-project">+ New project</button>
    </div>
    <div class="toolbar">
      <input id="proj-q" placeholder="Search name / location…" style="min-width:200px" />
      <select id="proj-status">
        <option value="">All statuses</option>
        ${state.projectStatuses.map((s) => `<option value="${esc(s)}">${esc(s.replace(/_/g, " "))}</option>`).join("")}
      </select>
      <button class="btn" id="proj-refresh">Refresh</button>
    </div>
    <div id="projects-body"></div>
  `;

  await load();

  $("#proj-refresh").onclick = () => load().catch((e) => toast(e.message, "err"));
  $("#proj-status").onchange = (e) => {
    status = e.target.value;
    load().catch((e) => toast(e.message, "err"));
  };
  let t;
  $("#proj-q").oninput = (e) => {
    clearTimeout(t);
    t = setTimeout(() => {
      q = e.target.value.trim();
      load().catch((err) => toast(err.message, "err"));
    }, 250);
  };
  $("#btn-new-project").onclick = () => openProjectModal();
}

// ---------- Bid list (sql/082) ----------
//
// Every invite as it came in, apart from the projects that were chosen
// (Chad, 2026-09-09: "a new table... so we are not scrolling thru a ton of
// jobs to find the one i want.. then when we choose that we are estimating,
// it gets copied over"). The whole list is fetched once — a few hundred
// rows — and filtered here, so the boxes answer as you type.

const BID_STATUS_LABEL = {
  not_started: "Not started",
  in_progress: "In progress",
  submitted: "Submitted",
  awarded: "Awarded",
  canceled: "Canceled",
};
const BID_OPEN = new Set(["not_started", "in_progress"]);

/** Days from today to the bid's due date; null with no date. */
function bidDaysLeft(bid) {
  if (!bid.bid_due) return null;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const due = new Date(`${bid.bid_due}T00:00:00`);
  return Math.round((due - today) / 86400000);
}

function bidDueHtml(bid) {
  if (!bid.bid_due) return `<span class="muted">no date</span>`;
  const days = bidDaysLeft(bid);
  const time = bid.bid_due_time ? ` ${String(bid.bid_due_time).slice(0, 5)}` : "";
  const open = BID_OPEN.has(bid.status);
  let cls = "";
  let note = "";
  if (open && days < 0) {
    cls = "warn";
    note = ` · ${-days} day${-days === 1 ? "" : "s"} overdue`;
  } else if (open && days === 0) {
    cls = "warn";
    note = " · today";
  } else if (open && days <= 7) {
    cls = "info";
    note = ` · ${days} day${days === 1 ? "" : "s"}`;
  }
  return `<span class="badge ${cls}" title="${esc(bid.bid_due)}${esc(time)}">${esc(fmtDay(bid.bid_due))}${esc(time)}${note}</span>`;
}

function bidStatusSelect(bid) {
  return `<select data-bid-status="${esc(bid.id)}" title="Change the status here; it saves at once">${Object.entries(BID_STATUS_LABEL)
    .map(([k, label]) => `<option value="${k}"${bid.status === k ? " selected" : ""}>${label}</option>`)
    .join("")}</select>`;
}

function bidsTable(bids) {
  if (!bids.length) return `<div class="empty">No bids match.</div>`;
  const clamp =
    "display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;font-size:0.8rem;max-width:30rem";
  return `<div class="table-wrap"><table class="data">
    <thead><tr>
      <th>Due</th><th>Bid</th><th>GC</th><th>Estimators</th><th>Status</th><th>Notes</th><th></th>
    </tr></thead>
    <tbody>
      ${bids
        .map(
          (b) => `<tr data-bid="${esc(b.id)}">
        <td style="white-space:nowrap">${bidDueHtml(b)}</td>
        <td>
          <strong>${esc(b.name)}</strong>
          ${b.location ? `<div class="muted">${esc(b.location)}</div>` : ""}
          ${(b.project_types || []).length ? `<div class="chips">${b.project_types.map((t) => `<span class="chip">${esc(t)}</span>`).join("")}</div>` : ""}
        </td>
        <td class="muted">${esc(b.gc || "—")}</td>
        <td><div class="chips">${(b.estimator_names || []).map((n) => `<span class="chip">${esc(n)}</span>`).join("") || `<span class="muted">—</span>`}</div></td>
        <td>${bidStatusSelect(b)}</td>
        <td><div class="muted" style="${clamp}" title="${esc(b.notes || "")}">${esc(b.notes || "")}</div>
          ${b.plans_url && isWebLink(b.plans_url) ? `<a href="${esc(b.plans_url)}" target="_blank" rel="noopener" style="font-size:0.8rem">plans ↗</a>` : ""}</td>
        <td style="white-space:nowrap">
          <button type="button" class="btn ghost" data-edit-bid="${esc(b.id)}">Edit</button>
          ${
            b.project_id
              ? `<button type="button" class="btn ghost" data-open-project="${esc(b.project_id)}" title="This bid is being estimated">→ ${esc(b.project_name || "project")}</button>`
              : `<button type="button" class="btn primary ghost" data-estimate-bid="${esc(b.id)}" title="Copy this bid into a new project and open it">Estimate this</button>`
          }
        </td>
      </tr>`
        )
        .join("")}
    </tbody></table></div>`;
}

function bidsBoard(bids) {
  const cols = Object.keys(BID_STATUS_LABEL);
  return `<div class="grid stats" style="align-items:start">${cols
    .map((k) => {
      const rows = bids.filter((b) => b.status === k);
      return `<div class="card"><h3 style="margin:0 0 0.5rem">${BID_STATUS_LABEL[k]} <span class="muted">${rows.length}</span></h3>
        ${rows
          .map(
            (b) => `<div style="padding:0.4rem 0;border-top:1px solid var(--border)">
              <strong>${esc(b.name)}</strong>
              <div class="muted" style="font-size:0.8rem">${esc(b.gc || "")}</div>
              <div style="margin-top:0.2rem">${bidDueHtml(b)}</div>
            </div>`
          )
          .join("") || `<div class="muted">—</div>`}
      </div>`;
    })
    .join("")}</div>`;
}

async function renderBids(root) {
  root.innerHTML = `<div class="loading">Loading bids…</div>`;
  if (!state.projectTypes.length) state.projectTypes = await Api.projectTypes();
  if (!state.estimators.length) state.estimators = await Api.listEstimators({ active_only: "true" });
  let bids = await Api.listBids();
  const filters = { status: "open", estimator: "", q: "", due: "all", view: "table" };

  const filtered = () =>
    bids.filter((b) => {
      if (filters.status === "open" && !BID_OPEN.has(b.status)) return false;
      if (filters.status !== "open" && filters.status !== "all" && b.status !== filters.status) return false;
      if (filters.estimator && !(b.estimator_ids || []).includes(filters.estimator)) return false;
      if (filters.q) {
        const hay = `${b.name} ${b.gc || ""} ${b.location || ""} ${b.notes || ""}`.toLowerCase();
        if (!hay.includes(filters.q.toLowerCase())) return false;
      }
      const days = bidDaysLeft(b);
      if (filters.due === "overdue" && !(days !== null && days < 0)) return false;
      if (filters.due === "week" && !(days !== null && days >= 0 && days <= 7)) return false;
      if (filters.due === "month" && !(days !== null && days >= 0 && days <= 30)) return false;
      return true;
    });

  const counts = () => {
    const open = bids.filter((b) => BID_OPEN.has(b.status));
    const overdue = open.filter((b) => bidDaysLeft(b) !== null && bidDaysLeft(b) < 0).length;
    const week = open.filter((b) => bidDaysLeft(b) !== null && bidDaysLeft(b) >= 0 && bidDaysLeft(b) <= 7).length;
    return { open: open.length, overdue, week, all: bids.length };
  };

  const paint = () => {
    const c = counts();
    $("#bids-counts").innerHTML =
      `<strong>${c.open}</strong> open · <strong>${c.week}</strong> due this week · ` +
      `<strong>${c.overdue}</strong> overdue · ${c.all} on the list`;
    const rows = filtered();
    $("#bids-body").innerHTML = filters.view === "board" ? bidsBoard(rows) : bidsTable(rows);
    wire();
  };

  const wire = () => {
    $$("[data-bid-status]", root).forEach((sel) => {
      sel.onchange = async () => {
        try {
          const updated = await Api.updateBid(sel.dataset.bidStatus, { status: sel.value });
          bids = bids.map((b) => (b.id === updated.id ? updated : b));
          toast(`${updated.name}: ${BID_STATUS_LABEL[updated.status]}`);
          paint();
        } catch (err) {
          toast(err.message, "err");
        }
      };
    });
    $$("[data-edit-bid]", root).forEach((btn) => {
      btn.onclick = () => {
        const bid = bids.find((b) => b.id === btn.dataset.editBid);
        if (bid) openBidModal(bid);
      };
    });
    $$("[data-open-project]", root).forEach((btn) => {
      btn.onclick = () => setRoute("project", { projectId: btn.dataset.openProject });
    });
    $$("[data-estimate-bid]", root).forEach((btn) => {
      btn.onclick = async () => {
        const bid = bids.find((b) => b.id === btn.dataset.estimateBid);
        if (!bid) return;
        if (!confirm(`Estimate "${bid.name}"? It becomes a project, with its GC, dates, plans and notes.`)) return;
        btn.disabled = true;
        try {
          const res = await Api.estimateBid(bid.id);
          toast("Project made from the bid");
          setRoute("project", { projectId: res.project_id });
        } catch (err) {
          toast(err.message, "err");
          btn.disabled = false;
        }
      };
    });
  };

  root.innerHTML = `
    <div class="page-header">
      <div>
        <h1>Bids</h1>
        <p id="bids-counts"></p>
      </div>
      <button class="btn primary" id="btn-new-bid">+ New bid</button>
    </div>
    <div class="toolbar">
      <input id="bids-q" placeholder="Search name / GC / location / notes…" style="min-width:220px" />
      <select id="bids-status">
        <option value="open">Open (not started + in progress)</option>
        <option value="all">All statuses</option>
        ${Object.entries(BID_STATUS_LABEL).map(([k, l]) => `<option value="${k}">${l}</option>`).join("")}
      </select>
      <select id="bids-estimator">
        <option value="">Any estimator</option>
        ${state.estimators.map((e) => `<option value="${esc(e.id)}">${esc(e.full_name)}</option>`).join("")}
      </select>
      <select id="bids-due">
        <option value="all">Any due date</option>
        <option value="overdue">Overdue</option>
        <option value="week">Due this week</option>
        <option value="month">Due in 30 days</option>
      </select>
      <select id="bids-view">
        <option value="table">Table</option>
        <option value="board">Board by status</option>
      </select>
    </div>
    <div id="bids-body"></div>
  `;
  paint();

  let t;
  $("#bids-q").oninput = (e) => {
    clearTimeout(t);
    t = setTimeout(() => {
      filters.q = e.target.value.trim();
      paint();
    }, 150);
  };
  $("#bids-status").onchange = (e) => {
    filters.status = e.target.value;
    paint();
  };
  $("#bids-estimator").onchange = (e) => {
    filters.estimator = e.target.value;
    paint();
  };
  $("#bids-due").onchange = (e) => {
    filters.due = e.target.value;
    paint();
  };
  $("#bids-view").onchange = (e) => {
    filters.view = e.target.value;
    paint();
  };
  $("#btn-new-bid").onclick = () => openBidModal();
}

function openBidModal(existing = null) {
  const isEdit = !!existing;
  const backdrop = document.createElement("div");
  backdrop.className = "modal-backdrop";
  const ids = new Set((existing?.estimator_ids || []).map(String));
  backdrop.innerHTML = `
    <div class="modal" style="width:min(760px,100%)">
      <h2>${isEdit ? "Edit bid" : "New bid"}</h2>
      <form id="bid-form" class="form-grid">
        <div class="field full">
          <label>Project name</label>
          <input name="name" required maxlength="500" value="${esc(existing?.name || "")}" />
        </div>
        <div class="field">
          <label>GC</label>
          <input name="gc" value="${esc(existing?.gc || "")}" />
        </div>
        <div class="field">
          <label>Location</label>
          <input name="location" value="${esc(existing?.location || "")}" />
        </div>
        <div class="field">
          <label>Status</label>
          <select name="status">
            ${Object.entries(BID_STATUS_LABEL)
              .map(([k, l]) => `<option value="${k}"${(existing?.status || "not_started") === k ? " selected" : ""}>${l}</option>`)
              .join("")}
          </select>
        </div>
        <div class="field">
          <label>Bid due</label>
          <input type="date" name="bid_due" value="${esc(existing?.bid_due || "")}" />
        </div>
        <div class="field">
          <label>Due time <span class="muted">(blank = the day)</span></label>
          <input type="time" name="bid_due_time" value="${esc(existing?.bid_due_time ? String(existing.bid_due_time).slice(0, 5) : "")}" />
        </div>
        <div class="field">
          <label>Invite received</label>
          <input type="date" name="bid_date" value="${esc(existing?.bid_date || "")}" />
        </div>
        <div class="field">
          <label>Project types</label>
          <select name="project_types" multiple size="4">
            ${state.projectTypes
              .map((t) => `<option value="${esc(t)}"${(existing?.project_types || []).includes(t) ? " selected" : ""}>${esc(t)}</option>`)
              .join("")}
          </select>
        </div>
        <div class="field">
          <label>Estimators</label>
          <select name="estimator_ids" multiple size="4">
            ${state.estimators
              .map((e) => `<option value="${esc(e.id)}"${ids.has(String(e.id)) ? " selected" : ""}>${esc(e.full_name)}</option>`)
              .join("")}
          </select>
        </div>
        <div class="field">
          <label>Bid price</label>
          <input type="number" name="bid_price" min="0" step="0.01" value="${esc(existing?.bid_price ?? "")}" />
        </div>
        <div class="field full">
          <label>Plans link</label>
          <input name="plans_url" placeholder="https://…" value="${esc(existing?.plans_url || "")}" />
        </div>
        <div class="field full">
          <label>Notes</label>
          <textarea name="notes" rows="4">${esc(existing?.notes || "")}</textarea>
        </div>
        <div class="modal-actions" style="grid-column:1/-1">
          ${isEdit ? `<button type="button" class="btn danger ghost" id="bid-delete">Delete</button>` : ""}
          <button type="button" class="btn ghost" id="bid-cancel">Cancel</button>
          <button type="submit" class="btn primary">Save</button>
        </div>
      </form>
    </div>`;
  document.body.appendChild(backdrop);
  $("#bid-cancel", backdrop).onclick = () => backdrop.remove();
  backdrop.addEventListener("click", (e) => {
    if (e.target === backdrop) backdrop.remove();
  });
  const del = $("#bid-delete", backdrop);
  if (del) {
    del.onclick = async () => {
      if (!confirm(`Delete the bid "${existing.name}"?`)) return;
      try {
        await Api.deleteBid(existing.id);
        toast("Bid deleted");
        backdrop.remove();
        render();
      } catch (err) {
        toast(err.message, "err");
      }
    };
  }
  $("#bid-form", backdrop).onsubmit = async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    const picked = (name) => [...e.target[name].selectedOptions].map((o) => o.value);
    const body = {
      name: String(fd.get("name")).trim(),
      gc: fd.get("gc") || null,
      location: fd.get("location") || null,
      status: fd.get("status"),
      bid_due: fd.get("bid_due") || null,
      bid_due_time: fd.get("bid_due_time") || null,
      bid_date: fd.get("bid_date") || null,
      project_types: picked("project_types"),
      estimator_ids: picked("estimator_ids"),
      bid_price: fd.get("bid_price") === "" ? null : Number(fd.get("bid_price")),
      plans_url: fd.get("plans_url") || null,
      notes: fd.get("notes") || null,
    };
    try {
      if (isEdit) await Api.updateBid(existing.id, body);
      else await Api.createBid(body);
      toast(isEdit ? "Bid updated" : "Bid added");
      backdrop.remove();
      render();
    } catch (err) {
      toast(err.message, "err");
    }
  };
}

function openProjectModal(existing = null) {
  const isEdit = !!existing;
  const backdrop = document.createElement("div");
  backdrop.className = "modal-backdrop";
  backdrop.innerHTML = `
    <div class="modal">
      <h2>${isEdit ? "Edit project" : "New project"}</h2>
      <form id="proj-form" class="form-grid">
        <div class="field full">
          <label>Project name</label>
          <input name="name" required value="${esc(existing?.name || "")}" />
        </div>
        <div class="field">
          <label>GC</label>
          <input name="gc" value="${esc(existing?.gc || "")}" />
        </div>
        <div class="field">
          <label>Location</label>
          <input name="location" value="${esc(existing?.location || "")}" />
        </div>
        <div class="field">
          <label>Job number</label>
          <input name="job_number" value="${esc(existing?.job_number || "")}" />
        </div>
        <div class="field">
          <label>Status</label>
          <select name="status">
            ${state.projectStatuses
              .map(
                (s) =>
                  `<option value="${esc(s)}" ${existing?.status === s ? "selected" : s === "not_started" && !existing ? "selected" : ""}>${esc(s.replace(/_/g, " "))}</option>`
              )
              .join("")}
          </select>
        </div>
        <div class="field">
          <label>Bid due</label>
          <input type="date" name="bid_due" value="${esc(existing?.bid_due || "")}" />
        </div>
        <div class="field">
          <label>Sales tax</label>
          <select name="tax_exempt" title="A project fact. Every section follows it unless the section says otherwise — ROW paving inside a taxable job, say. Changing it reprices the open estimates on the spot; final and archived ones keep their bid numbers.">
            <option value="false" ${existing?.tax_exempt ? "" : "selected"}>Taxable</option>
            <option value="true" ${existing?.tax_exempt ? "selected" : ""}>Exempt — the whole job</option>
          </select>
        </div>
        <div class="field">
          <label>Project types</label>
          <select name="project_types" multiple size="5">
            ${state.projectTypes
              .map(
                (t) =>
                  `<option value="${esc(t)}" ${(existing?.project_types || []).includes(t) ? "selected" : ""}>${esc(t)}</option>`
              )
              .join("")}
          </select>
        </div>
        <div class="field">
          <label>Created by</label>
          <select name="created_by">
            <option value="">—</option>
            ${state.estimators
              .map(
                (e) =>
                  `<option value="${esc(e.id)}" ${existing?.created_by === e.id ? "selected" : ""}>${esc(e.full_name)}</option>`
              )
              .join("")}
          </select>
        </div>
        <div class="field full">
          <label>Plans URL</label>
          <input name="plans_url" value="${esc(existing?.plans_url || "")}" />
        </div>
        <div class="field full">
          <label>Notes</label>
          <textarea name="notes">${esc(existing?.notes || "")}</textarea>
        </div>
        <div class="modal-actions full" style="grid-column:1/-1">
          <button type="button" class="btn ghost" id="cancel">Cancel</button>
          <button type="submit" class="btn primary">Save</button>
        </div>
      </form>
    </div>`;
  document.body.appendChild(backdrop);
  $("#cancel", backdrop).onclick = () => backdrop.remove();
  backdrop.addEventListener("click", (e) => {
    if (e.target === backdrop) backdrop.remove();
  });
  $("#proj-form", backdrop).onsubmit = async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    const types = [...e.target.project_types.selectedOptions].map((o) => o.value);
    const body = {
      name: fd.get("name"),
      gc: fd.get("gc") || null,
      location: fd.get("location") || null,
      job_number: fd.get("job_number") || null,
      status: fd.get("status"),
      bid_due: fd.get("bid_due") || null,
      tax_exempt: fd.get("tax_exempt") === "true",
      project_types: types,
      created_by: fd.get("created_by") || null,
      plans_url: fd.get("plans_url") || null,
      notes: fd.get("notes") || null,
    };
    try {
      if (isEdit) await Api.updateProject(existing.id, body);
      else await Api.createProject(body);
      // The flag is stored on every section at cost time, so flipping it
      // reprices the job's open estimates on the server (final and archived
      // ones keep their bid numbers). Say so — a save that moved money
      // elsewhere should not read as a rename.
      const taxFlipped = isEdit && Boolean(existing.tax_exempt) !== body.tax_exempt;
      toast(
        isEdit
          ? taxFlipped
            ? `Project updated — now ${body.tax_exempt ? "tax exempt" : "taxable"}; open estimates repriced`
            : "Project updated"
          : "Project created"
      );
      backdrop.remove();
      render();
    } catch (err) {
      toast(err.message, "err");
    }
  };
}

async function renderProjectDetail(root) {
  root.innerHTML = `<div class="loading">Loading project…</div>`;
  if (!state.estimators.length) state.estimators = await Api.listEstimators({ active_only: "true" });
  if (!state.projectStatuses.length) state.projectStatuses = await Api.projectStatuses();
  if (!state.projectTypes.length) state.projectTypes = await Api.projectTypes();

  const [project, estimates] = await Promise.all([
    Api.getProject(state.projectId),
    Api.listEstimates({ project_id: state.projectId }),
  ]);

  root.innerHTML = `
    <div class="page-header">
      <div>
        <button class="btn ghost" id="back">← Projects</button>
        <h1 style="margin-top:0.5rem">${esc(project.name)}</h1>
        <p>${esc(project.gc || "No GC")} · ${esc(project.location || "No location")}</p>
      </div>
      <div style="display:flex;gap:0.5rem">
        <button class="btn" id="edit-proj">Edit</button>
        <button class="btn primary" id="new-est">+ New estimate</button>
      </div>
    </div>
    <div class="card" style="margin-bottom:1rem">
      <div class="detail-grid">
        <div><div class="k">Status</div><div class="v">${statusBadge(project.status)}</div></div>
        <div><div class="k">Bid due</div><div class="v">${esc(project.bid_due || "—")}</div></div>
        <div><div class="k">Bid date</div><div class="v">${esc(project.bid_date || "—")}</div></div>
        <div><div class="k">Bid price</div><div class="v">${project.bid_price != null ? "$" + money(project.bid_price) : "—"}</div></div>
        <div><div class="k">Sales tax</div><div class="v" title="Sections follow this unless they say otherwise">${project.tax_exempt ? "exempt" : "taxed"}</div></div>
        <div><div class="k">Types</div><div class="v chips">${(project.project_types || []).map((t) => `<span class="chip">${esc(t)}</span>`).join("") || "—"}</div></div>
        <div><div class="k">Plans</div><div class="v">${isWebLink(project.plans_url) ? `<a href="${esc(project.plans_url)}" target="_blank" rel="noopener">Open link</a>` : project.plans_url ? esc(project.plans_url) : "—"}</div></div>
      </div>
      ${project.notes ? `<p class="muted" style="margin:0;color:var(--text-muted)">${esc(project.notes)}</p>` : ""}
    </div>
    <div class="card">
      <h3 style="margin:0 0 0.75rem">Estimates</h3>
      ${
        estimates.length
          ? `<div class="table-wrap"><table class="data">
        <thead><tr><th>Name</th><th>Version</th><th>Status</th><th>Estimator</th>
          <th class="num">Cost</th><th class="num">Sale</th><th>Updated</th><th></th></tr></thead>
        <tbody>
          ${estimates
            .map(
              (e) => `<tr class="clickable" data-estimate-id="${esc(e.id)}">
              <td><strong>${esc(e.name)}</strong></td>
              <td class="num">${e.version}</td>
              <td>${statusBadge(e.status)}</td>
              <td class="muted">${esc(e.estimator_name || "—")}</td>
              <td class="num">${money(e.calc_total_cost)}</td>
              <td class="num">${money(e.calc_total_sale)}</td>
              <td class="muted">${esc((e.updated_at || "").slice(0, 16).replace("T", " "))}</td>
              <td style="white-space:nowrap">
                <button type="button" class="btn ghost btn-edit-est" data-id="${esc(e.id)}">Edit</button>
              </td>
            </tr>`
            )
            .join("")}
        </tbody></table></div>`
          : `<div class="empty">No estimates yet. Create a draft package for this job.</div>`
      }
      <p style="color:var(--text-muted);font-size:0.85rem;margin:0.75rem 0 0">
        Open an estimate to add its sections — each assembly carries its own
        rates, takeoff and markup.
      </p>
    </div>
  `;

  $("#back").onclick = () => setRoute("projects");
  $("#edit-proj").onclick = () => openProjectModal(project);
  $("#new-est").onclick = () => openEstimateModal(project);
  // Row click opens, the same as the projects list and the sections table.
  // This page used to be the only one that made you find a button.
  $$("tr[data-estimate-id]", root).forEach((tr) => {
    tr.onclick = (ev) => {
      if (ev.target.closest("button")) return;
      setRoute("estimate", { estimateId: tr.dataset.estimateId, projectId: project.id });
    };
  });
  $$(".btn-edit-est", root).forEach((btn) => {
    btn.onclick = (ev) => {
      ev.stopPropagation();
      const est = estimates.find((e) => e.id === btn.dataset.id);
      if (est) openEstimateModal(project, est);
    };
  });
}

function openEstimateModal(project, existing = null) {
  const isEdit = !!existing;
  const backdrop = document.createElement("div");
  backdrop.className = "modal-backdrop";
  const status = existing?.status || "draft";
  backdrop.innerHTML = `
    <div class="modal">
      <h2>${isEdit ? "Edit estimate" : "New estimate"} — ${esc(project.name)}</h2>
      <form id="est-form" class="form-grid">
        <div class="field full">
          <label>Estimate name</label>
          <input name="name" required value="${esc(existing?.name || "Mono Slab base")}" />
        </div>
        <div class="field">
          <label>Version</label>
          <input type="number" name="version" min="1" value="${esc(existing?.version ?? 1)}" />
        </div>
        <div class="field">
          <label>Status</label>
          <select name="status">
            <option value="draft" ${status === "draft" ? "selected" : ""}>draft</option>
            <option value="in_review" ${status === "in_review" ? "selected" : ""}>in review</option>
            <option value="final" ${status === "final" ? "selected" : ""}>final</option>
            <option value="archived" ${status === "archived" ? "selected" : ""}>archived</option>
          </select>
        </div>
        <div class="field">
          <label>Estimator</label>
          <select name="estimator_id">
            <option value="">—</option>
            ${state.estimators
              .map(
                (e) =>
                  `<option value="${esc(e.id)}" ${existing?.estimator_id === e.id ? "selected" : ""}>${esc(e.full_name)}</option>`
              )
              .join("")}
          </select>
        </div>
        <div class="field full">
          <span class="muted" style="color:var(--text-muted);font-size:0.8rem">
            Waste factors and form % belong to each section (its own fields) and to
            <strong>Rules for this job</strong> — not to the estimate. Three waste
            boxes sat here until 2026-09-04 and saved to nothing. Margin and
            contingency below are only the defaults a new section starts at.
          </span>
        </div>
        <div class="field">
          <label>Margin (decimal)</label>
          <input type="number" step="0.01" min="0" max="2" name="margin_pct" placeholder="0.20"
            value="${existing?.margin_pct != null ? esc(existing.margin_pct) : "0.20"}" />
        </div>
        <div class="field">
          <label>Contingency (decimal)</label>
          <input type="number" step="0.01" min="0" max="2" name="contingency_pct" placeholder="0.03"
            value="${existing?.contingency_pct != null ? esc(existing.contingency_pct) : "0.03"}" />
        </div>
        <div class="field full">
          <label>Notes</label>
          <textarea name="notes">${esc(existing?.notes || "")}</textarea>
        </div>
        <div class="modal-actions" style="grid-column:1/-1">
          <button type="button" class="btn ghost" id="cancel">Cancel</button>
          <button type="submit" class="btn primary">${isEdit ? "Save" : "Create"}</button>
        </div>
      </form>
    </div>`;
  document.body.appendChild(backdrop);
  $("#cancel", backdrop).onclick = () => backdrop.remove();
  backdrop.addEventListener("click", (e) => {
    if (e.target === backdrop) backdrop.remove();
  });
  $("#est-form", backdrop).onsubmit = async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    const num = (k) => {
      const v = fd.get(k);
      return v === "" || v == null ? null : Number(v);
    };
    const payload = {
      name: fd.get("name"),
      version: Number(fd.get("version") || 1),
      status: fd.get("status"),
      estimator_id: fd.get("estimator_id") || null,
      margin_pct: num("margin_pct") ?? 0.2,
      contingency_pct: num("contingency_pct") ?? 0.03,
      notes: fd.get("notes") || null,
    };
    try {
      if (isEdit) {
        await Api.updateEstimate(existing.id, payload);
        toast("Estimate updated");
      } else {
        await Api.createEstimate({
          project_id: project.id,
          ...payload,
        });
        toast("Estimate created");
      }
      backdrop.remove();
      render();
    } catch (err) {
      toast(err.message, "err");
    }
  };
}

// The people who can sign in: estimators, the office, the foremen. Chad,
// 2026-09-09: "change the 'estimators' section 'Users', more fitting". The
// API and the table keep their name; nobody sees those.
async function renderEstimators(root) {
  root.innerHTML = `<div class="loading">Loading…</div>`;
  const people = await Api.listEstimators();
  root.innerHTML = `
    <div class="page-header">
      <div>
        <h1>Users</h1>
        <p>Who can sign in, and what each may do.</p>
      </div>
      <button class="btn primary" id="btn-new">+ Add</button>
    </div>
    <div class="table-wrap">
      <table class="data">
        <thead><tr><th>Name</th><th>Username</th><th>Role</th><th>Title</th><th>Phone</th><th>Active</th>${
          canAct("admin") ? "<th>Sign-in</th>" : ""
        }</tr></thead>
        <tbody>
          ${people
            .map(
              (e) => `<tr data-person="${esc(e.id)}">
              <td><strong>${esc(e.full_name)}</strong></td>
              <td class="muted">${esc(e.username)}</td>
              <td>${
                canAct("admin")
                  ? `<select data-role="${esc(e.id)}" title="Each role includes the ones below it; a foreman only files daily reports">${roleOptions(e.role)}</select>`
                  : esc(ROLE_LABELS[e.role] || e.role)
              }</td>
              <td class="muted">${esc(e.title || "—")}</td>
              <td class="muted">${esc(e.phone || "—")}</td>
              <td>${e.is_active ? '<span class="badge ok">yes</span>' : '<span class="badge">no</span>'}</td>
              ${
                canAct("admin")
                  ? `<td style="white-space:nowrap">
                      <button type="button" class="btn ghost" data-pw="${esc(e.id)}">Set password</button>
                      ${e.is_active ? `<button type="button" class="btn ghost" data-off="${esc(e.id)}">Deactivate</button>` : ""}
                    </td>`
                  : ""
              }
            </tr>`
            )
            .join("")}
        </tbody>
      </table>
    </div>`;
  $("#btn-new").onclick = () => openEstimatorModal();
  const byId = new Map(people.map((e) => [e.id, e]));
  $$("[data-role]", root).forEach((sel) => {
    sel.onchange = async () => {
      try {
        await Api.updateEstimator(sel.dataset.role, { role: sel.value });
        toast(`${byId.get(sel.dataset.role)?.full_name || "Role"} is now ${ROLE_LABELS[sel.value]}`);
      } catch (err) {
        toast(err.message, "err");
        render();
      }
    };
  });
  $$("[data-pw]", root).forEach((btn) => {
    btn.onclick = () => openSetPasswordModal(byId.get(btn.dataset.pw));
  });
  $$("[data-off]", root).forEach((btn) => {
    btn.onclick = async () => {
      const who = byId.get(btn.dataset.off);
      if (!confirm(`Deactivate ${who.full_name}? They are signed out everywhere and cannot sign in.`)) return;
      try {
        await Api.deactivateEstimator(btn.dataset.off);
        toast(`${who.full_name} deactivated`);
        render();
      } catch (err) {
        toast(err.message, "err");
      }
    };
  });
}

// ---------- Activity: who changed what (sql/069) ----------

function fmtWhen(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

const singular = (t) => t.replace("-", " ").replace(/s$/, "");

/** A route and a method, as a sentence. The fallback is the route itself. */
const ACTIONS = [
  [/^\/api\/auth\/login$/, (m, e) => (e.status === 200 ? "signed in" : "failed to sign in")],
  [/^\/api\/auth\/logout$/, () => "signed out"],
  [/^\/api\/auth\/password$/, () => "changed their password"],
  [/^\/api\/estimators\/[^/]+\/password$/, () => "set someone's password"],
  [/^\/api\/estimators$/, () => "added a person"],
  [/^\/api\/estimators\/[^/]+$/, (m) => (m === "DELETE" ? "deactivated a person" : "changed a person")],
  [/^\/api\/projects$/, () => "added a project"],
  [/^\/api\/projects\/[^/]+$/, (m) => (m === "DELETE" ? "deleted a project" : "changed a project")],
  [/^\/api\/estimates$/, () => "added an estimate"],
  [/^\/api\/estimates\/[^/]+\/recalc$/, () => "recalculated an estimate"],
  [/^\/api\/estimates\/[^/]+\/prices\/pull$/, () => "pulled the master list onto a price sheet"],
  [/^\/api\/estimates\/[^/]+\/prices\/[^/]+$/, () => "changed a price on a job's sheet"],
  [/^\/api\/estimates\/[^/]+\/rules\/([^/]+)$/, (m, e, k) => `${m === "DELETE" ? "cleared" : "set"} the job rule ${k}`],
  [/^\/api\/estimates\/[^/]+\/sections$/, () => "added a section"],
  [/^\/api\/estimates\/[^/]+$/, (m) => (m === "DELETE" ? "deleted an estimate" : "changed an estimate")],
  [/^\/api\/sections\/[^/]+\/recalc$/, () => "recalculated a section"],
  [/^\/api\/sections\/[^/]+\/beam-types/, () => "saved the beam schedule"],
  [/^\/api\/sections\/[^/]+\/quotes\/([^/]+)$/, (m, e, k) => `${m === "DELETE" ? "cleared" : "set"} the ${k} quote`],
  [/^\/api\/sections\/[^/]+\/rates\/([^/]+)$/, (m, e, k) => `${m === "DELETE" ? "cleared" : "set"} the section rate ${k}`],
  [/^\/api\/sections\/[^/]+\/(labor|equipment|forming-materials)\/lines\/([^/]+)$/, (m, e, set, code) => `changed the ${set.replace("-materials", "")} line ${code}`],
  [/^\/api\/sections\/[^/]+\/forming-materials\/form-percent$/, () => "set the form percent"],
  [/^\/api\/sections\/[^/]+\/(labor|equipment|forming-materials)\/refresh$/, (m, e, set) => `refreshed ${set.replace("-materials", "")}`],
  [/^\/api\/sections\/[^/]+$/, (m) => (m === "DELETE" ? "deleted a section" : "changed a section")],
  [/^\/api\/mono-slabs\/bulk$/, () => "saved the pours"],
  [/^\/api\/mono-slabs\/[^/]+\/grade-beams$/, () => "saved beam lengths on a pour"],
  [/^\/api\/mono-slabs\/[^/]+\/recalc$/, () => "recalculated a pour"],
  [/^\/api\/mono-slabs$/, () => "added a pour"],
  [/^\/api\/mono-slabs\/[^/]+$/, (m) => (m === "DELETE" ? "deleted a pour" : "changed a pour")],
  [/^\/api\/(pier-groups|wall-runs|beam-runs|column-types|deck-levels)\/bulk$/, (m, e, t) => `saved the ${t.replace("-", " ")}`],
  [/^\/api\/(pier-groups|wall-runs|beam-runs|column-types|deck-levels)$/, (m, e, t) => `added a ${singular(t)}`],
  [/^\/api\/(pier-groups|wall-runs|beam-runs|column-types|deck-levels)\/[^/]+$/, (m, e, t) => `${m === "DELETE" ? "deleted" : "changed"} a ${singular(t)}`],
  [/^\/api\/beam-types\/[^/]+$/, (m) => (m === "DELETE" ? "deleted a beam type" : "changed a beam type")],
  [/^\/api\/grade-beams/, () => "changed a beam on a pour"],
  [/^\/api\/(mix-designs|materials|equipment|concrete-suppliers)$/, (m, e, t) => `added a ${singular(t)}`],
  [/^\/api\/(mix-designs|materials|equipment|concrete-suppliers)\/([^/]+)$/, (m, e, t, id) => `${m === "DELETE" ? "retired" : "changed"} ${singular(t)} ${id}`],
  [/^\/api\/system-settings\/recalc-all$/, () => "recalculated every open estimate"],
  [/^\/api\/system-settings\/([^/]+)$/, (m, e, k) => `changed the company setting ${k}`],
];

function describeAction(e) {
  for (const [re, fn] of ACTIONS) {
    const m = e.path.match(re);
    if (m) return fn(e.method, e, ...m.slice(1));
  }
  return `${e.method} ${e.path}`;
}

async function renderActivity(root) {
  root.innerHTML = `<div class="loading">Loading…</div>`;
  const draw = async (filters) => {
    let rows;
    try {
      rows = await Api.listAudit({ limit: 300, ...filters });
    } catch (err) {
      root.innerHTML = `<div class="error-banner">${esc(err.message)}</div>`;
      return;
    }
    root.innerHTML = `
      <div class="page-header">
        <div>
          <h1>Activity</h1>
          <p>Every change anyone made through the app — who, what, when. Newest first.</p>
        </div>
      </div>
      <div class="toolbar" style="display:flex;gap:0.5rem;flex-wrap:wrap;align-items:center;margin-bottom:0.75rem">
        <input id="act-user" placeholder="username" value="${esc(filters.username || "")}" style="width:10rem" />
        <input id="act-path" placeholder="route contains… (a section id, mix-designs)" value="${esc(filters.path || "")}" style="width:22rem" />
        <button type="button" class="btn" id="act-go">Filter</button>
        <span class="muted" style="font-size:0.85rem">${rows.length} shown</span>
      </div>
      <div class="table-wrap">
        <table class="data">
          <thead><tr><th>When</th><th>Who</th><th>What</th><th>Status</th><th>Sent</th></tr></thead>
          <tbody>
            ${rows
              .map(
                (e) => `<tr>
                  <td class="muted" style="white-space:nowrap">${esc(fmtWhen(e.at))}</td>
                  <td><strong>${esc(e.username || "—")}</strong></td>
                  <td>${esc(describeAction(e))}<div class="muted" style="font-size:0.75rem">${esc(e.method)} ${esc(e.path)}</div></td>
                  <td>${
                    e.status < 300
                      ? `<span class="badge ok">${e.status}</span>`
                      : `<span class="badge warn" title="refused or failed">${e.status}</span>`
                  }</td>
                  <td>${
                    e.body == null
                      ? '<span class="muted">—</span>'
                      : `<details><summary class="muted" style="cursor:pointer">body</summary><pre style="margin:0.25rem 0 0;font-size:0.75rem;white-space:pre-wrap">${esc(
                          JSON.stringify(e.body, null, 1)
                        )}</pre></details>`
                  }</td>
                </tr>`
              )
              .join("") || `<tr><td colspan="5" class="muted">Nothing yet.</td></tr>`}
          </tbody>
        </table>
      </div>`;
    $("#act-go", root).onclick = () =>
      draw({ username: $("#act-user", root).value.trim(), path: $("#act-path", root).value.trim() });
    for (const id of ["#act-user", "#act-path"]) {
      $(id, root).onkeydown = (ev) => {
        if (ev.key === "Enter") $("#act-go", root).click();
      };
    }
  };
  await draw({});
}

function roleOptions(current) {
  return ["user", "estimator", "senior_estimator", "admin", "foreman"]
    .map(
      (r) =>
        `<option value="${r}"${r === current ? " selected" : ""}>${r === "foreman" ? "foreman (daily report only)" : ROLE_LABELS[r]}</option>`
    )
    .join("");
}

/** An admin sets someone's password (sql/068). Their open sessions end. */
function openSetPasswordModal(person) {
  const backdrop = document.createElement("div");
  backdrop.className = "modal-backdrop";
  backdrop.innerHTML = `
    <div class="modal">
      <h2>Set password — ${esc(person.full_name)}</h2>
      <form id="setpw-form" class="form-grid" style="grid-template-columns:1fr">
        <div class="field"><label>New password (8+ characters)</label>
          <input name="password" type="password" autocomplete="new-password" minlength="8" required /></div>
        <div class="field"><label>Again</label>
          <input name="again" type="password" autocomplete="new-password" minlength="8" required /></div>
        <div class="modal-actions">
          <button type="button" class="btn ghost" id="cancel">Cancel</button>
          <button type="submit" class="btn primary">Set</button>
        </div>
      </form>
    </div>`;
  document.body.appendChild(backdrop);
  $("#cancel", backdrop).onclick = () => backdrop.remove();
  $("#setpw-form", backdrop).onsubmit = async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    if (fd.get("password") !== fd.get("again")) {
      toast("The two passwords differ", "err");
      return;
    }
    try {
      await Api.setEstimatorPassword(person.id, String(fd.get("password")));
      toast(`Password set for ${person.full_name} — their open sessions were signed out`);
      backdrop.remove();
    } catch (err) {
      toast(err.message, "err");
    }
  };
}

function openEstimatorModal() {
  const backdrop = document.createElement("div");
  backdrop.className = "modal-backdrop";
  backdrop.innerHTML = `
    <div class="modal">
      <h2>New user</h2>
      <form id="est-form" class="form-grid">
        <div class="field"><label>Username</label><input name="username" required /></div>
        <div class="field"><label>Full name</label><input name="full_name" required /></div>
        <div class="field"><label>Email</label><input name="email" type="email" /></div>
        <div class="field"><label>Phone</label><input name="phone" /></div>
        <div class="field"><label>Title</label><input name="title" value="Estimator" /></div>
        <div class="field"><label>Role</label>
          <select name="role">${roleOptions("estimator")}</select>
        </div>
        <div class="modal-actions" style="grid-column:1/-1">
          <button type="button" class="btn ghost" id="cancel">Cancel</button>
          <button type="submit" class="btn primary">Save</button>
        </div>
      </form>
    </div>`;
  document.body.appendChild(backdrop);
  $("#cancel", backdrop).onclick = () => backdrop.remove();
  $("#est-form", backdrop).onsubmit = async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    try {
      await Api.createEstimator({
        username: fd.get("username"),
        full_name: fd.get("full_name"),
        email: fd.get("email") || null,
        phone: fd.get("phone") || null,
        title: fd.get("title") || null,
        role: fd.get("role"),
      });
      toast("User added");
      backdrop.remove();
      state.estimators = [];
      render();
    } catch (err) {
      toast(err.message, "err");
    }
  };
}

const SECTION_LABELS = {
  mono_slab: "Mono slab on grade",
  paving: "Paving",
  sidewalk: "Sidewalks",
  piers: "Piers",
  grade_beams: "Grade beams",
  cont_footings: "Continuous footings",
  walls_footings: "Walls & footings",
  spot_footings: "Spot footings",
  columns: "Columns",
  slabs: "Slabs",
  cip_deck: "CIP elevated deck",
  slab_on_deck: "Slab on deck",
  panels: "Tilt panels",
  miscellaneous: "Miscellaneous",
};

function sectionLabel(kind) {
  return SECTION_LABELS[kind] || kind;
}

// Assemblies that are taken off as a grid of areas rather than as a list of
// pours: sixteen columns across up to twenty-five rows, typed straight down.
// They also form off curb LF, carry no vapor barrier and no grade beams, so
// the section page shows them a different set of everything (sql/036).
const PAVING_KINDS = new Set(["paving", "sidewalk"]);

// Assemblies taken off as a grid of pier GROUPS rather than pours. A pier has
// no square footage, which is why costing allocates these by count (sql/037).
const PIER_KINDS = new Set(["piers"]);
// Walls take off as a wall-plus-footing run, measured in FORM FEET — the third
// takeoff shape, after the pour and the pier group (sql/040).
const WALL_KINDS = new Set(["walls_footings"]);
// Spot footings (sql/072) ride the walls engine with the wall left blank.
const SPOT_KINDS = new Set(["spot_footings"]);
// Separately poured grade beams and continuous footings share one engine
// (sql/073); a footing is its own kind for its label, rates and defaults.
const BEAM_KINDS = new Set(["grade_beams", "cont_footings"]);
const CONT_KINDS = new Set(["cont_footings"]);
// A rebar slab on grade rides the mono-slab engine (sql/074); it types its
// superintendent and saws its joints.
const RB_SLAB_KINDS = new Set(["slabs", "slab_on_deck"]);
// The slab on metal deck (sql/075): the rebar slab with a deck's cells.
const DECK_SLAB_KINDS = new Set(["slab_on_deck"]);
// Sidewalks (sql/076): a paving-family area with finishes, stairs and an edge.
const SIDEWALK_KINDS = new Set(["sidewalk"]);
// Columns are the fourth takeoff shape, and the only one with no geometry to
// measure across: a pour has SF, a pier group has LF, a wall run has form feet,
// and a column type has a SCHEDULE and a COUNT. Everything shared on the
// section allocates by form contact SF — perimeter × height — because that is
// the surface the crew actually handles (sql/045).
const COLUMN_KINDS = new Set(["columns"]);
// The elevated deck is the fifth shape and the first assembly that hangs in
// the air. One row is a LEVEL: an area, a thickness, two mats of bar, an edge,
// and the grade beams running through it. Everything shared allocates by deck
// AREA — same as a mono slab, unlike columns (form SF) or walls (form feet).
const DECK_KINDS = new Set(["cip_deck"]);
// Tilt-wall panels are the seventh shape (sql/077): a panel TYPE and a count,
// with four opening slots. Sold per SF, gross of the openings — the tab's W
// column — and every shared cost allocates by that SF.
const PANEL_KINDS = new Set(["panels"]);
// Miscellaneous is the eighth shape (sql/078): a priced library of site items
// in four families. The sale is typed per item and the margin is the answer;
// there is no forming, labor or equipment line set — every item carries its own.
const MISC_KINDS = new Set(["miscellaneous"]);

async function renderEstimateSummary(root) {
  root.innerHTML = `<div class="loading">Loading job…</div>`;
  const [estimate, sections, sheet, rules] = await Promise.all([
    Api.getEstimate(state.estimateId),
    Api.listSections(state.estimateId),
    // The sheet is what this job pays; the page only needs its headline —
    // how many prices were edited here, and whether the master list has
    // moved since the pull. An older build without sql/048 has no sheet.
    Api.getPriceSheet(state.estimateId).catch(() => null),
    // The job's RULES. A build without the sql/055 screen has no endpoint,
    // and the page is still a page without it.
    Api.estimateRules(state.estimateId).catch(() => null),
  ]);
  const drift = sheet ? sheet.drift : null;
  const driftCount = drift ? drift.drift + drift.new.length : 0;

  // usd(), not "$" + num(): num drops a trailing zero, so a section that sold
  // for $1,587,161.60 read as $1,587,161.6 — which looks like a rounding error
  // in a column of money.
  const money = (x) => usd(x, 2);
  const unpricedCount = sections.reduce((a, x) => a + ((x.calc_unpriced || []).length ? 1 : 0), 0);
  const totalCost = sections.reduce((a, x) => a + Number(x.calc_total_cost || 0), 0);
  const totalSale = sections.reduce((a, x) => a + Number(x.calc_total_sale || 0), 0);

  root.innerHTML = `
    <div class="page-header">
      <div>
        <button class="btn ghost" id="back-proj">← ${esc(estimate.project_name || "Project")}</button>
        <h1 style="margin-top:0.5rem">${esc(estimate.name)}</h1>
        <p>${statusBadge(estimate.status)} · v${estimate.version}
          ${estimate.estimator_name ? " · " + esc(estimate.estimator_name) : ""}
          · new sections default to ${num(Number(estimate.margin_pct ?? 0.2) * 100, 0)}% margin
          ${Number(estimate.contingency_pct) ? " + " + num(Number(estimate.contingency_pct) * 100, 0) + "% conting" : ""}
        </p>
      </div>
      <div style="display:flex;gap:0.5rem;flex-wrap:wrap">
        <button class="btn primary" id="btn-add-section">+ Section</button>
        <button class="btn" id="btn-price-sheet" type="button"
          title="What this job pays for each mix and material">Price sheet</button>
        <button class="btn" id="btn-proposal" type="button"
          title="The bid form: seeded from this estimate, edited on its own page, downloaded as .xlsx">Proposal</button>
        <button class="btn" id="btn-recalc-job" type="button"
          title="Reprice every section from current inputs">Recalculate job</button>
      </div>
    </div>

    ${
      driftCount
        ? `<div class="warn-banner">
             <strong>The master list has moved since this job pulled its prices.</strong>
             ${driftSummaryText(drift)} — this job still bids at the prices it pulled.
             <a href="#prices/${estimate.id}">Open the price sheet</a> to see what changed and pull it if you want it.
           </div>`
        : ""
    }

    ${
      unpricedCount
        ? `<div class="error-banner" style="margin-bottom:1rem">
             <strong>${unpricedCount === 1 ? "One section" : `${unpricedCount} sections`} on this job
             ${unpricedCount === 1 ? "has" : "have"} items the master list could not price.</strong>
             The job total is light by an unknown amount. Open the flagged section${unpricedCount === 1 ? "" : "s"} to see what is missing.
           </div>`
        : ""
    }
    <div class="grid stats">
      <div class="card stat"><div class="label">Cost</div>
        <div class="value">${usd(totalCost, 0)}</div>
        <div class="hint">sum of ${sections.length} section${sections.length === 1 ? "" : "s"}${
          unpricedCount ? ` · <span class="badge warn">${unpricedCount} unpriced</span>` : ""
        }</div></div>
      <div class="card stat"><div class="label">Sale</div>
        <div class="value">${usd(totalSale, 0)}</div>
        <div class="hint">each section at its own markup</div></div>
      <div class="card stat"><div class="label">Sections</div>
        <div class="value">${sections.length}</div>
        <div class="hint">assemblies on this job</div></div>
      ${
        sheet
          ? `<div class="card stat clickable" id="card-prices" style="cursor:pointer" title="Open the price sheet">
        <div class="label">Prices</div>
        <div class="value">${sheet.edited ? `${sheet.edited} edited` : "master list"}</div>
        <div class="hint">${sheet.rows.length} on the sheet${
          sheet.pulled_at ? ` · pulled ${fmtDay(sheet.pulled_at)}` : ""
        }${driftCount ? ` · <span class="badge warn">${driftCount} moved</span>` : ""}</div></div>`
          : ""
      }
    </div>

    ${
      sections.length
        ? `<div class="table-wrap"><table class="data">
      <thead><tr>
        <th>Section</th><th>Type</th><th class="num">Quantity</th>
        <th class="num">Markup</th><th>Tax</th>
        <th class="num">Cost</th><th class="num">$/unit</th><th class="num">Sale</th><th></th>
      </tr></thead>
      <tbody>
        ${sections
          .map(
            (x) => `<tr data-section="${x.id}" class="clickable">
            <td><strong>${esc(x.name)}</strong>${
              (x.calc_unpriced || []).length
                ? ` <span class="badge warn" title="${esc((x.calc_unpriced || []).join(", "))}">${(x.calc_unpriced || []).length} unpriced</span>`
                : ""
            }</td>
            <td class="muted">${
              x.name.trim().toLowerCase() === sectionLabel(x.kind).toLowerCase()
                ? ""
                : esc(sectionLabel(x.kind))
            }</td>
            <td class="num">${x.calc_quantity == null ? "—" : num(Number(x.calc_quantity), 0) + " " + esc(x.unit)}</td>
            <td class="num">${num(Number(x.margin_pct || 0) * 100, 1)}%${
              Number(x.contingency_pct) ? " + " + num(Number(x.contingency_pct) * 100, 1) + "%" : ""
            }</td>
            <td>${
              x.tax_exempt === null
                ? `<span class="muted" title="Inherits the project">${x.effective_tax_exempt ? "exempt" : "taxed"}</span>`
                : x.tax_exempt
                  ? `<span title="Set on this section">exempt ✎</span>`
                  : `<span title="Set on this section">taxed ✎</span>`
            }</td>
            <td class="num">${money(x.calc_total_cost)}</td>
            <td class="num muted">${x.calc_cost_per_unit == null ? "—" : "$" + num(Number(x.calc_cost_per_unit), 4)}</td>
            <td class="num">${money(x.calc_total_sale)}</td>
            <td style="white-space:nowrap">
              <button type="button" class="btn ghost" data-edit-section="${x.id}"
                title="Name, unit, markup, tax and notes">Edit</button>
              <button type="button" class="btn ghost" data-del-section="${x.id}"
                title="Delete this section and its work">Delete</button>
            </td>
          </tr>`
          )
          .join("")}
      </tbody>
    </table></div>
    <p class="muted" style="margin-top:0.5rem;font-size:0.85rem">
      A job total has no $/SF of its own — sections are measured in EA, SF, FF and LS.
    </p>`
        : `<div class="card"><p>No sections yet. A section is one assembly of the job —
           the mono slab, the paving, the piers — each with its own rates and markup.</p></div>`
    }
    ${renderEstimateRulesCard(rules)}
  `;

  wireEstimateRules(estimate);

  const back = $("#back-proj");
  if (back) {
    back.onclick = () => setRoute("project", { projectId: estimate.project_id });
  }

  $$("tr[data-section]").forEach((tr) => {
    tr.style.cursor = "pointer";
    tr.onclick = (ev) => {
      if (ev.target.closest("button")) return;
      setRoute("section", { sectionId: tr.dataset.section });
    };
  });

  // Edit, the way the estimates list has one (Chad, 2026-09-09: "there is an
  // edit button for each estimate, need one for each section").
  $$("[data-edit-section]").forEach((btn) => {
    btn.onclick = (ev) => {
      ev.stopPropagation();
      const row = sections.find((x) => x.id === btn.dataset.editSection);
      if (row) openSectionModal(estimate, row);
    };
  });

  $$("[data-del-section]").forEach((btn) => {
    btn.onclick = async (ev) => {
      ev.stopPropagation();
      const row = sections.find((x) => x.id === btn.dataset.delSection);
      if (!confirm(`Delete section "${row.name}"? Its pours and takeoffs go with it.`)) return;
      btn.disabled = true;
      try {
        // The API refuses a section that still has pours unless forced, so the
        // second confirm is the app asking about real work, not a formality.
        await Api.deleteSection(row.id);
        toast("Section deleted");
        render();
      } catch (err) {
        if (/still has pours/i.test(err.message)) {
          if (confirm(`"${row.name}" still has pours. Delete them too?`)) {
            await Api.deleteSection(row.id, true);
            toast("Section and its pours deleted");
            render();
            return;
          }
        } else {
          toast(err.message, "err");
        }
        btn.disabled = false;
      }
    };
  });

  const addBtn = $("#btn-add-section");
  if (addBtn) addBtn.onclick = () => openSectionModal(estimate);

  const goPrices = () => setRoute("prices", { estimateId: estimate.id });
  const priceBtn = $("#btn-price-sheet");
  if (priceBtn) priceBtn.onclick = goPrices;
  const priceCard = $("#card-prices");
  if (priceCard) priceCard.onclick = goPrices;
  const proposalBtn = $("#btn-proposal");
  if (proposalBtn) proposalBtn.onclick = () => setRoute("proposal", { estimateId: estimate.id });

  const recalcBtn = $("#btn-recalc-job");
  if (recalcBtn) {
    recalcBtn.onclick = async () => {
      recalcBtn.disabled = true;
      recalcBtn.textContent = "Recalculating…";
      try {
        await Api.recalcEstimate(estimate.id);
        toast("Job repriced");
        render();
      } catch (err) {
        toast(err.message, "err");
        recalcBtn.disabled = false;
        recalcBtn.textContent = "Recalculate job";
      }
    };
  }
}

async function openSectionModal(estimate, existing = null) {
  const isEdit = !!existing;
  let kinds = [];
  try {
    kinds = await Api.sectionKinds();
  } catch {
    kinds = Object.keys(SECTION_LABELS);
  }
  const pct = (v) => (v == null || v === "" ? "" : num(Number(v) * 100, 2));
  const taxSel = existing?.tax_exempt == null ? "" : String(existing.tax_exempt);
  const backdrop = document.createElement("div");
  backdrop.className = "modal-backdrop";
  backdrop.innerHTML = `
    <div class="modal">
      <h2>${isEdit ? "Edit section" : "Add section"}</h2>
      <form id="section-form">
        <div class="field">
          <label>Type${isEdit ? ' <span class="muted">(fixed once the section has work)</span>' : ""}</label>
          <select name="kind"${isEdit ? " disabled" : ""}>
            ${kinds.map((k) => `<option value="${k}"${existing?.kind === k ? " selected" : ""}>${esc(sectionLabel(k))}</option>`).join("")}
          </select>
        </div>
        <div class="field">
          <label>Name</label>
          <input name="name" required maxlength="200" placeholder="e.g. ROW paving"
            value="${esc(existing?.name || "")}"${isEdit ? ' data-touched="1"' : ""} />
        </div>
        <div class="field">
          <label>Unit <span class="muted">(what the section is sold per)</span></label>
          <input name="unit" maxlength="8" placeholder="${isEdit ? "" : "the type's own"}"
            value="${esc(existing?.unit || "")}" />
        </div>
        <div class="field">
          <label>Margin % <span class="muted">(blank = job default)</span></label>
          <input type="number" name="margin_pct" min="0" max="200" step="any"
            placeholder="${num(Number(estimate.margin_pct ?? 0.2) * 100, 1)}" value="${pct(existing?.margin_pct)}" />
        </div>
        <div class="field">
          <label>Contingency % <span class="muted">(blank = job default)</span></label>
          <input type="number" name="contingency_pct" min="0" max="200" step="any"
            placeholder="${num(Number(estimate.contingency_pct ?? 0) * 100, 1)}" value="${pct(existing?.contingency_pct)}" />
        </div>
        <div class="field">
          <label>Sales tax</label>
          <select name="tax_exempt">
            <option value=""${taxSel === "" ? " selected" : ""}>Follow the project</option>
            <option value="true"${taxSel === "true" ? " selected" : ""}>Exempt (ROW paving, sidewalks)</option>
            <option value="false"${taxSel === "false" ? " selected" : ""}>Taxable</option>
          </select>
          <p class="muted" style="font-size:0.8rem;margin:0.25rem 0 0">
            Left on "follow the project" unless this section genuinely differs —
            not every paving job is ROW.
          </p>
        </div>
        <div class="field">
          <label>Notes</label>
          <textarea name="notes" rows="2">${esc(existing?.notes || "")}</textarea>
        </div>
        <div class="modal-actions">
          <button type="button" class="btn ghost" id="section-cancel">Cancel</button>
          <button type="submit" class="btn primary">${isEdit ? "Save" : "Add"}</button>
        </div>
      </form>
    </div>`;
  document.body.appendChild(backdrop);

  const form = backdrop.querySelector("#section-form");
  const kindSel = form.querySelector("[name=kind]");
  const nameInput = form.querySelector("[name=name]");
  const syncName = () => {
    if (!nameInput.dataset.touched) nameInput.value = sectionLabel(kindSel.value);
  };
  kindSel.onchange = syncName;
  nameInput.oninput = () => {
    nameInput.dataset.touched = "1";
  };
  syncName();

  backdrop.querySelector("#section-cancel").onclick = () => backdrop.remove();
  form.onsubmit = async (ev) => {
    ev.preventDefault();
    const fd = new FormData(form);
    // A blank percentage means the job's default; a blank unit means the
    // type's own on a new section and "leave it" on an edit.
    const pctOrNull = (k) => {
      const v = fd.get(k);
      return v === "" || v == null ? null : Number(v) / 100;
    };
    const exempt = fd.get("tax_exempt");
    const taxExempt = exempt === "true" ? true : exempt === "false" ? false : null;
    const unit = String(fd.get("unit") || "").trim().toUpperCase();
    const notes = String(fd.get("notes") || "").trim() || null;
    try {
      if (isEdit) {
        const body = {
          name: String(fd.get("name")).trim(),
          // The columns cannot be empty: a blank is the job's own figure.
          margin_pct: pctOrNull("margin_pct") ?? Number(estimate.margin_pct ?? 0.2),
          contingency_pct: pctOrNull("contingency_pct") ?? Number(estimate.contingency_pct ?? 0),
          tax_exempt: taxExempt,
          notes,
        };
        if (unit) body.unit = unit;
        await Api.updateSection(existing.id, body);
        backdrop.remove();
        toast("Section saved");
        render();
        return;
      }
      const body = { kind: fd.get("kind"), name: String(fd.get("name")).trim() };
      const margin = pctOrNull("margin_pct");
      if (margin != null) body.margin_pct = margin;
      const conting = pctOrNull("contingency_pct");
      if (conting != null) body.contingency_pct = conting;
      if (taxExempt != null) body.tax_exempt = taxExempt;
      if (unit) body.unit = unit;
      if (notes) body.notes = notes;
      const created = await Api.createSection(estimate.id, body);
      backdrop.remove();
      toast("Section added");
      setRoute("section", { sectionId: created.id });
    } catch (err) {
      toast(err.message, "err");
    }
  };
}

/**
 * The paving takeoff: a grid of areas.
 *
 * Sixteen columns, up to twenty-five rows, and one Save. A save per field
 * would re-run this section's forming, labor and equipment on every keystroke,
 * because all three key off the section totals — so nothing is written until
 * Save, and the row shows an orange edge while it is unsaved.
 */
/**
 * A takeoff typed as a table.
 *
 * Paving and piers are both entered as grids — sixteen columns across up to
 * twenty-five rows — and the second one is why this is driven by a column spec
 * rather than written twice. A spec entry is either an editable field:
 *
 *     { f: "curb_lf", label: "Curb LF", type: "number", step: "any" }
 *     { f: "mix_design_id", label: "Mix", type: "select", options: mixes }
 *     { f: "slip_form", label: "Slip", type: "check" }
 *
 * ...or a derived column, which reads from the saved row and is never posted:
 *
 *     { label: "CY", derived: (r) => num(r.calc_concrete_cy, 2) }
 *
 * Every editable cell uses step="any". A step of 0.5 once made 24" and 18" bar
 * spacing fail validation, which cost an evening.
 */
/** The control for an editable column: how its <td> opens, and the control. */
function gridControlHtml(r, col) {
  const v = r[col.f];
  if (col.type === "check") {
    return [
      '<td style="text-align:center">',
      `<input type="checkbox" data-f="${col.f}"${v ? " checked" : ""} />`,
    ];
  }
  if (col.type === "select") {
    const opts =
      `<option value=""${v ? "" : " selected"}>—</option>` +
      (col.options || [])
        .map(
          (o) =>
            `<option value="${esc(o.id)}"${
              String(v) === String(o.id) ? " selected" : ""
            }>${esc(o.label)}</option>`
        )
        .join("");
    return ["<td>", `<select data-f="${col.f}">${opts}</select>`];
  }
  if (col.type === "number") {
    // Number() on the way in: the API returns fixed-scale decimals, and
    // "187752.000" in a narrow box reads as a number nobody typed. A
    // column with a `scale` is typed in one unit and stored in another
    // (units.js): the box shows the stored value ÷ scale, and carries the
    // scale so the save can multiply it back.
    const shown = toShown(v, col.scale);
    const scale = col.scale ? ` data-scale="${esc(col.scale)}"` : "";
    return [
      "<td>",
      `<input data-f="${col.f}"${scale} type="number" min="0" step="${
        col.step || "any"
      }" value="${esc(shown)}" />`,
    ];
  }
  return [
    '<td class="name">',
    `<input data-f="${col.f}" value="${esc(v == null ? "" : v)}" placeholder="${esc(
      col.placeholder || ""
    )}" />`,
  ];
}

function gridCellHtml(r, col) {
  if (col.derived) {
    const title = col.title ? ` title="${esc(col.title(r))}"` : "";
    return `<td class="derived"${title}>${r.id ? col.derived(r) : "—"}</td>`;
  }
  const [open, control] = gridControlHtml(r, col);
  return `${open}${control}</td>`;
}

/**
 * Two lines per record — the wall grid, since 2026-09-05 (Chad: "can we divide
 * the wall and footing to separate lines?").
 *
 * A column may carry a `sub`: what the SECOND line shows in that column. It is
 * written exactly like a column — an editable field, a derived value — or a
 * piece of muted text (`{ text: "↳ footing" }`); a `sub` with only a label
 * puts that label in the header and leaves the cell empty. Any column with a
 * `sub` turns the whole grid two-line: the header stacks both labels in one
 * cell (so it stays sticky), every record renders as a `tr.has-sub` with its
 * `tr.sub-line` right under it, and wireGrid reads, marks and deletes the two
 * as one row. The record, the payload and the save are what they always were
 * — this is layout, nothing else. A grid with no `sub` anywhere renders
 * exactly as before.
 *
 * An editable cell on the second line carries its own tag (`tag`, falling
 * back to `label`) with `hint` as its tooltip, because the header over it
 * belongs to the first line: a 0 under THICK" is the footing's WIDTH, and
 * Chad's first look at the split said exactly that — "a little confusing on
 * the rebar mats and dimensions of the footing." Nobody should have to look
 * up to know what a box is.
 */
function gridSubCellHtml(r, sub) {
  if (!sub || (!sub.f && !sub.derived && sub.text == null)) return "<td></td>";
  if (sub.text != null) return `<td class="sub-text">${esc(sub.text)}</td>`;
  if (sub.derived) return gridCellHtml(r, sub);
  const [, control] = gridControlHtml(r, sub);
  const tagText = sub.tag || sub.label;
  const hint = sub.hint ? ` title="${esc(sub.hint)}"` : "";
  const tag = tagText ? `<span class="sub-tag"${hint}>${esc(tagText)}</span>` : "";
  return `<td><span class="tagged">${tag}${control}</span></td>`;
}

function gridRowHtml(r, columns) {
  const id = r.id ? esc(r.id) : "";
  const twoLine = columns.some((c) => c.sub);
  const main = `<tr data-id="${id}"${twoLine ? ' class="has-sub"' : ""}>
    ${columns.map((c) => gridCellHtml(r, c)).join("")}
    <td><button type="button" class="btn danger ghost btn-del-row" data-id="${id}">Del</button></td>
  </tr>`;
  if (!twoLine) return main;
  return (
    main +
    `<tr data-id="${id}" class="sub-line">
    ${columns.map((c) => gridSubCellHtml(r, c.sub)).join("")}
    <td></td>
  </tr>`
  );
}

function gridCardHtml({ id, title, blurb, columns, rows, addLabel, saveLabel }) {
  const twoLine = columns.some((c) => c.sub);
  const body = (rows.length ? rows : [{}]).map((r) => gridRowHtml(r, columns)).join("");
  return `<div class="card" id="${id}">
    <h3 style="margin:0 0 0.25rem">${esc(title)}</h3>
    <p style="color:var(--text-muted);font-size:0.82rem;margin:0 0 0.75rem">${blurb}</p>
    <div class="table-wrap"><table class="data grid-entry">
      <thead><tr>${columns
        .map((c) => {
          const hint = c.hint ? ` title="${esc(c.hint)}"` : "";
          return twoLine
            ? `<th${hint}>${esc(c.label)}<span class="sub-label">${esc(c.sub?.label || "")}</span></th>`
            : `<th${hint}>${esc(c.label)}</th>`;
        })
        .join("")}<th></th></tr></thead>
      <tbody id="${id}-body">${body}</tbody>
    </table></div>
    <div class="grid-bar">
      <button type="button" class="btn" id="${id}-add">+ ${esc(addLabel)}</button>
      <button type="button" class="btn primary" id="${id}-save">${esc(saveLabel)}</button>
      <span class="unsaved" id="${id}-unsaved"></span>
    </div>
  </div>`;
}

/**
 * Read a grid back out of the DOM and save it.
 *
 * Blank stays blank. A column the estimator has not measured is not a zero,
 * and storing it as one would put a $0 curb on an area nobody has walked yet.
 */
/**
 * Grid bodies on the page → "is it dirty?". One `beforeunload` guard for the
 * whole page reads this; a body that has left the document no longer counts.
 * Until 2026-09-06 every render of every grid added a listener of its own and
 * never removed it, so a grid you had dirtied and then navigated away from
 * still asked "Leave site?" when the tab closed (audit P3).
 */
const GRID_DIRTY = new Map();
let unloadGuarded = false;
function guardUnload() {
  if (unloadGuarded) return;
  unloadGuarded = true;
  window.addEventListener("beforeunload", (e) => {
    for (const [body, isDirty] of GRID_DIRTY) {
      if (!body.isConnected) {
        GRID_DIRTY.delete(body);
        continue;
      }
      if (isDirty()) {
        e.preventDefault();
        e.returnValue = "";
        return;
      }
    }
  });
}

/** A link the project page may put in an href: a web address, nothing else. */
function isWebLink(s) {
  return /^https?:[/][/]/i.test(String(s || ""));
}

function wireGrid(root, { id, columns, required, save, remove, blank }) {
  const bodyEl = $(`#${id}-body`, root);
  if (!bodyEl) return;
  const unsaved = $(`#${id}-unsaved`, root);
  let dirty = false;

  // A two-line grid (gridRowHtml's `sub`) is read, marked and deleted a PAIR
  // at a time — the wall line and the footing line under it are one row. On
  // every other grid this is just [tr].
  const linesOf = (tr) => {
    if (!tr) return [];
    if (tr.classList.contains("sub-line")) {
      const main = tr.previousElementSibling;
      return main ? [main, tr] : [tr];
    }
    const next = tr.nextElementSibling;
    return next && next.classList.contains("sub-line") ? [tr, next] : [tr];
  };

  const markDirty = (tr) => {
    dirty = true;
    for (const line of linesOf(tr)) line.classList.add("dirty");
    if (unsaved) unsaved.textContent = "Unsaved changes";
  };
  bodyEl.addEventListener("input", (e) => markDirty(e.target.closest("tr")));
  bodyEl.addEventListener("change", (e) => markDirty(e.target.closest("tr")));

  const addBtn = $(`#${id}-add`, root);
  if (addBtn) {
    addBtn.onclick = () => {
      const tmp = document.createElement("tbody");
      // A grid may name what a NEW row starts as (sql/078: a family's defaults).
      tmp.innerHTML = gridRowHtml(blank || {}, columns);
      const lines = [...tmp.querySelectorAll("tr")]; // one, or a wall line and its footing line
      for (const line of lines) bodyEl.appendChild(line);
      markDirty(lines[0]);
      const first = lines[0].querySelector("input");
      if (first) first.focus();
    };
  }

  bodyEl.addEventListener("click", async (e) => {
    const btn = e.target.closest(".btn-del-row");
    if (!btn) return;
    const tr = btn.closest("tr");
    if (!btn.dataset.id) {
      for (const line of linesOf(tr)) line.remove(); // never saved — nothing to confirm
      markDirty(null);
      return;
    }
    if (!confirm("Delete this row?")) return;
    try {
      await remove(btn.dataset.id);
      toast("Row deleted");
      render();
    } catch (err) {
      toast(err.message, "err");
    }
  });

  const saveBtn = $(`#${id}-save`, root);
  if (!saveBtn) return;
  // A save re-renders the page and throws this closure away. If anything
  // reaches the old handler afterwards it would re-send rows that no longer
  // carry ids and create everything twice — which is what happened the first
  // time this was driven by a script. Disabling the button is not enough,
  // because the button it disables is the detached one; the latch is.
  let saved = false;
  saveBtn.onclick = async () => {
    if (saved) return;
    const rows = [];
    for (const tr of bodyEl.querySelectorAll("tr")) {
      if (tr.classList.contains("sub-line")) continue; // read with the line above it
      const row = {};
      for (const line of linesOf(tr)) {
        line.querySelectorAll("[data-f]").forEach((el) => {
          const f = el.dataset.f;
          if (el.type === "checkbox") {
            row[f] = el.checked;
            return;
          }
          const raw = el.value.trim();
          // A box typed in feet on a column stored in inches (units.js) goes
          // back through its scale; every other box is what it always was.
          const scale = el.dataset.scale ? Number(el.dataset.scale) : 1;
          row[f] = raw === "" ? null : el.type === "number" ? toStored(raw, scale) : raw;
        });
      }
      const empty = required.every((f) => row[f] == null) && !row.description && !row.label;
      if (empty) continue;
      if (tr.dataset.id) row.id = tr.dataset.id;
      rows.push(row);
    }
    if (!rows.length) {
      toast(`Nothing to save — enter at least ${required.join(" and ")}`, "err");
      return;
    }
    saved = true;
    saveBtn.disabled = true;
    try {
      const res = await save(rows);
      toast(
        `Saved ${res.created} new and ${res.updated} existing row${
          res.created + res.updated === 1 ? "" : "s"
        }`
      );
      dirty = false;
      render();
    } catch (err) {
      toast(err.message, "err");
      saved = false;
      saveBtn.disabled = false;
    }
  };

  GRID_DIRTY.set(bodyEl, () => dirty);
  guardUnload();
}

/** The paving takeoff: areas across, driven by curb LF. */
/**
 * Sidewalks (sql/076): one line per walk type — the older template's
 * SIDEWALKS row. Three finishes are flags; the stair treads are LF x rise x
 * run; the thickened edge is a length.
 */
function sidewalkColumns(mixes) {
  return [
    { f: "description", label: "Type", placeholder: "Broom finish" },
    { f: "square_footage", label: "SF", type: "number", step: "1" },
    { f: "thickness_in", label: 'Thk"', type: "number" },
    { f: "sand_thickness_in", label: 'Sand"', type: "number" },
    { f: "mix_design_id", label: "Mix", type: "select", options: mixOptions(mixes) },
    { f: "thick_edge_lf", label: "Thick edge LF", type: "number" },
    { f: "stamped", label: "Stamped", type: "check" },
    { f: "integral_color", label: "Color", type: "check" },
    { f: "acid_etch", label: "Acid etch", type: "check" },
    { f: "traffic_control", label: "Traffic", type: "check" },
    { f: "stair_tread_lf", label: "Stairs LF", type: "number" },
    { f: "stair_tread_rise_in", label: 'Rise"', type: "number" },
    { f: "stair_tread_run_in", label: 'Run"', type: "number" },
    { f: "slab_bar_size", label: "Bar #", type: "select", options: barSizeChoices() },
    { f: "slab_bar_spacing_in", label: 'Spacing"', type: "number" },
    { f: "wire_mesh", label: "Mesh", type: "check" },
    { f: "mesh_gauge", label: "Mesh ga", type: "number", step: "1" },
    { f: "demo_lf", label: "Demo LF", type: "number" },
    {
      label: "CY",
      derived: (r) => num(r.calc_concrete_cy, 2),
      title: (r) =>
        `slab ${num(r.calc_slab_concrete_cy, 2)} + edge ${num(r.calc_edge_concrete_cy, 2)} + stairs ${num(
          r.calc_stair_concrete_cy,
          2
        )}`,
    },
    { label: "Steel lb", derived: (r) => num(r.calc_total_rebar_lb, 0), title: (r) => `edge bars ${num(r.calc_edge_rebar_lb, 0)} lb` },
    { label: "Cost", derived: (r) => usd(r.calc_cost, 0), title: (r) => `${usd(r.calc_cost_per_sf, 2)} / SF` },
  ];
}

function pavingColumns(mixes) {
  return [
    { f: "description", label: "Area", placeholder: "Area name" },
    { f: "square_footage", label: "SF", type: "number", step: "1" },
    { f: "thickness_in", label: 'Thk"', type: "number" },
    { f: "curb_lf", label: "Curb LF", type: "number" },
    { f: "thick_edge_lf", label: "Thick edge LF", type: "number" },
    { f: "mix_design_id", label: "Mix", type: "select", options: mixOptions(mixes) },
    { f: "sand_thickness_in", label: 'Sand"', type: "number" },
    { f: "slab_bar_size", label: "Bar #", type: "select", options: barSizeChoices() },
    { f: "slab_bar_spacing_in", label: 'Spacing"', type: "number" },
    { f: "mesh_gauge", label: "Mesh ga", type: "number", step: "1" },
    { f: "demo_lf", label: "Demo LF", type: "number" },
    { f: "paving_add_per_sf", label: "Add $/SF", type: "number", step: "0.01" },
    { f: "slip_form", label: "Slip", type: "check" },
    { f: "traffic_control", label: "Traffic", type: "check" },
    {
      label: "CY",
      derived: (r) => num(r.calc_concrete_cy, 2),
      title: (r) =>
        `slab ${num(r.calc_slab_concrete_cy, 2)} + curb & edge ${num(
          r.calc_edge_concrete_cy,
          2
        )}`,
    },
    { label: "Steel lb", derived: (r) => num(r.calc_total_rebar_lb, 0) },
    { label: "Cost", derived: (r) => usd(r.calc_cost, 0) },
  ];
}

/** The piers takeoff: one row is a GROUP of identical shafts. */
function pierColumns(mixes) {
  return [
    { f: "label", label: "Group", placeholder: "G" },
    { f: "qty", label: "Piers", type: "number", step: "1" },
    { f: "diameter_in", label: 'Dia"', type: "number" },
    { f: "base_depth_ft", label: "Base ft", type: "number" },
    { f: "rock_penetration_ft", label: "Rock ft", type: "number" },
    { f: "bell_size_in", label: 'Bell"', type: "number" },
    { f: "mix_design_id", label: "Mix", type: "select", options: mixOptions(mixes) },
    { f: "vert_bars_count", label: "Vert n", type: "number", step: "1" },
    { f: "vert_bars_size", label: "Vert #", type: "select", options: barSizeChoices() },
    { f: "tie_size", label: "Tie #", type: "select", options: barSizeChoices() },
    { f: "tie_spacing_in", label: 'Tie sp"', type: "number" },
    { f: "band_tie_count", label: "Band n", type: "number", step: "1" },
    { f: "band_spacing_in", label: 'Band sp"', type: "number" },
    { f: "dowels_count", label: "Dowel n", type: "number", step: "1" },
    { f: "dowels_size", label: "Dowel #", type: "select", options: barSizeChoices() },
    { f: "dowels_length_ft", label: "Dowel ft", type: "number" },
    {
      label: "Depth",
      derived: (r) => num(r.calc_total_depth_ft, 2),
      title: (r) => `base + rock · ${num(r.calc_total_lf, 0)} LF in this group`,
    },
    { label: "CY", derived: (r) => num(r.calc_concrete_cy, 2) },
    {
      label: "Steel lb",
      derived: (r) => num(r.calc_total_rebar_lb, 0),
      title: (r) =>
        `vertical ${num(r.calc_vert_rebar_lb, 0)} + ties ${num(
          r.calc_tie_rebar_lb,
          0
        )} (${num(r.calc_tie_count, 1)} per pier) + dowels ${num(
          r.calc_dowel_rebar_lb,
          0
        )}`,
    },
    {
      label: "Drilling",
      derived: (r) =>
        r.calc_drill_lf_rate == null
          ? `<span class="badge warn">no rate</span>`
          : usd(r.calc_drill_cost, 0),
      title: (r) =>
        r.calc_drill_lf_rate == null
          ? `No drilling rate for ${num(r.diameter_in, 0)}" — add one to the rate table`
          : `${usd(r.calc_drill_lf_rate, 2)}/LF × ${num(r.calc_total_lf, 0)} LF`,
    },
    { label: "Cost / ea", derived: (r) => usd(r.calc_cost_per_unit, 0) },
  ];
}

/**
 * Column types (sql/045). One row is a TYPE and a COUNT, not one column.
 *
 * Three vertical sets across, because the schedule carries three. Sets 2 and 3
 * are blank on every LBJ type and stay blank on most jobs — they are here so a
 * bundled schedule ("8 #8 + 4 #6") does not have to be averaged into one size
 * by hand before it can be typed.
 *
 * FORM SF is the column worth reading twice. It is contact area — perimeter ×
 * height — and it is also the allocation basis for everything shared on the
 * section, so a wrong length or width moves far more than the plywood.
 */
/**
 * Deck levels (sql/052). One row is a LEVEL, not a pour.
 *
 * Two derived columns are worth reading, because both are the reason a number
 * elsewhere on the page moves:
 *
 *   GB FF  is contact area on BOTH faces of every beam. It is also half the
 *          driver of every lumber line on the section, together with the
 *          permanent edge — so widening a beam moves the plywood.
 *   PT SF  is the area of the levels that carry cable, not the deck. A level
 *          with the box unticked is not PT area, and a lump PT quote does not
 *          land on it.
 */
function deckColumns(mixes) {
  return [
    { f: "label", label: "Level", placeholder: "level 2" },
    { f: "area_sf", label: "SF", type: "number" },
    { f: "thickness_in", label: 'Thick"', type: "number" },
    { f: "has_cable", label: "PT", type: "check" },
    { f: "mix_design_id", label: "Mix", type: "select", options: mixOptions(mixes) },
    { f: "perm_edge_lf", label: "Edge LF", type: "number" },
    { f: "top_bar_size", label: "Top #", type: "select", options: barSizeChoices() },
    { f: "top_bar_spacing_in", label: 'Top sp"', type: "number" },
    { f: "bot_bar_size", label: "Bot #", type: "select", options: barSizeChoices() },
    { f: "bot_bar_spacing_in", label: 'Bot sp"', type: "number" },
    { f: "mesh_sf", label: "Mesh SF", type: "number" },
    { f: "stud_rail_lb", label: "Stud lb", type: "number" },
    { f: "carton_form_sf", label: "Carton SF", type: "number" },
    {
      label: "Beams",
      derived: (r) =>
        (r.beams || []).length
          ? `${(r.beams || []).length} · ${num(r.calc_beam_lf, 0)} LF`
          : "—",
      title: () =>
        "Edit the beam schedule on the section's beam types, then set the " +
        "lengths here. Every beam is weighed — the workbook weighs the first " +
        "and charges 7 lb for the second.",
    },
    {
      label: "CY",
      derived: (r) => num(r.calc_concrete_cy, 2),
      title: (r) =>
        `slab ${num(r.calc_slab_cy, 2)} + beams ${num(r.calc_beam_cy, 2)} — ` +
        `SF × thickness / 324, with waste`,
    },
    {
      label: "Steel lb",
      derived: (r) => num(r.calc_total_rebar_lb, 0),
      title: (r) =>
        `mats ${num(r.calc_slab_rebar_lb, 0)} + beams ${num(
          r.calc_beam_rebar_lb,
          0
        )} — 2 / (spacing / 12) × area per mat, waste on every bar`,
    },
    {
      label: "GB FF",
      derived: (r) => num(r.calc_gb_form_ff, 0),
      title: (r) =>
        `LN FT × height / 12 × 2 — BOTH faces. This also drives every lumber ` +
        `line on the section, with the ${num(r.perm_edge_lf, 0)} LF of edge.`,
    },
    {
      label: "PT SF",
      derived: (r) => (r.has_cable ? num(r.calc_pt_sf, 0) : "—"),
      title: (r) =>
        r.has_cable
          ? `${num(r.calc_pt_lb, 0)} lb of cable at 1.15 lb/SF`
          : "no cable on this level — it is not PT area",
    },
    {
      label: "Cost / SF",
      derived: (r) => usd(r.calc_cost_per_unit, 2),
      title: (r) =>
        `sale ${usd(r.calc_sale_per_unit, 2)}/SF · ${usd(r.calc_cost, 0)} for ` +
        `the level`,
    },
  ];
}

function columnColumns(mixes) {
  return [
    { f: "label", label: "Type", placeholder: "C1" },
    { f: "qty", label: "Qty", type: "number", step: "1" },
    { f: "height_ft", label: "Height ft", type: "number" },
    { f: "length_in", label: 'L"', type: "number" },
    { f: "width_in", label: 'W"', type: "number" },
    // Pilasters (sql/051). A column is wrapped; a pilaster has a wall on one
    // or two of its L faces. Form SF is the allocation basis for the whole
    // section, so this is the field that makes a pilaster a pilaster.
    {
      f: "formed_faces",
      label: "Faces",
      type: "select",
      options: [
        { id: 4, label: "4 — column" },
        { id: 3, label: "3 — on a wall" },
        { id: 2, label: "2 — returns only" },
      ],
    },
    { f: "mix_design_id", label: "Mix", type: "select", options: mixOptions(mixes) },
    { f: "vert1_count", label: "V1 n", type: "number", step: "1" },
    { f: "vert1_size", label: "V1 #", type: "select", options: barSizeChoices() },
    { f: "vert2_count", label: "V2 n", type: "number", step: "1" },
    { f: "vert2_size", label: "V2 #", type: "select", options: barSizeChoices() },
    { f: "vert3_count", label: "V3 n", type: "number", step: "1" },
    { f: "vert3_size", label: "V3 #", type: "select", options: barSizeChoices() },
    { f: "tie_size", label: "Tie #", type: "select", options: barSizeChoices() },
    { f: "tie_spacing_in", label: 'Tie sp"', type: "number" },
    { f: "dowel_count", label: "Dowel n", type: "number", step: "1" },
    { f: "dowel_size", label: "Dowel #", type: "select", options: barSizeChoices() },
    { f: "dowel_length_ft", label: "Dowel ft", type: "number" },
    {
      label: "Form SF",
      derived: (r) => num(r.calc_form_sf, 1),
      title: (r) =>
        `${facesFormula(r)} / 12 × ${num(r.height_ft, 0)} ft × ` +
        `${num(r.qty, 0)} — contact area, and the basis this section ` +
        `allocates shared cost by`,
    },
    {
      label: "CY",
      derived: (r) => num(r.calc_concrete_cy, 2),
      title: () =>
        "L × W × height / 3888, with waste. Not rounded up to the whole yard — " +
        "the batch ticket rounds, the bid does not.",
    },
    {
      label: "Steel lb",
      derived: (r) => num(r.calc_total_rebar_lb, 0),
      title: (r) =>
        `vertical ${num(r.calc_vert_rebar_lb, 0)} + ties ${num(
          r.calc_tie_rebar_lb,
          0
        )} + dowels ${num(r.calc_dowel_rebar_lb, 0)} — waste on every bar`,
    },
    {
      label: "Chamfer LF",
      derived: (r) => num(r.calc_chamfer_lf, 0),
      title: (r) =>
        `${Number(r.formed_faces ?? 4) >= 4 ? 4 : 2} corners × ` +
        `${num(r.height_ft, 0)} ft × ${num(r.qty, 0)} — a face against a wall ` +
        `has no chamfer strip on it`,
    },
    {
      label: "Cost / ea",
      derived: (r) => usd(r.calc_cost_per_unit, 0),
      title: (r) =>
        `sale ${usd(r.calc_sale_per_unit, 0)}/column · ${usd(r.calc_cost, 0)} for ` +
        `the type`,
    },
  ];
}

/**
 * The drilling quote.
 *
 * Drilling is the largest single line on a pier job, and in the field it is a
 * hard number from the sub, not an estimate. The rate table is what prices it
 * until that number arrives. This card is where the number arrives.
 *
 * The stale banner is the whole reason the card is more than one input: a lump
 * sum priced against one takeoff, sitting over a bigger one, is a wrong bid
 * with nothing on screen to notice — the exact failure this system keeps
 * producing.
 */
/**
 * Wall runs (sql/040). One row is a wall type AND the footing under it — and
 * since 2026-09-05 it is drawn that way: the wall on one line, the footing on
 * the line below it (the `sub` of each column; see gridRowHtml). Twenty-nine
 * columns became nineteen, and the footing's width sits under the wall's
 * thickness, its bottom mat under the wall's horizontal bars and its top mat
 * under the vertical (sql/059 — the two can differ), its SF / CY / steel / $
 * under the wall's. The split is layout: one record, one payload, one save.
 *
 * The derived columns worth reading: FORM FT is contact area on ONE face (the
 * sheet computes both and halves), and FTG SF is the footing's plan area,
 * which is what footing labor is priced per. The two are different numbers
 * doing different jobs and it is easy to reach for the wrong one. Steel on the
 * wall line is horizontal + vertical + laps, the footing line its own bars —
 * the same split services/walls.py costs them on; the two sum to the type.
 */
/**
 * Miscellaneous (sql/078): the 13 tab's four families of priced site items.
 * A new miscellaneous section is seeded with the tab's 22 items at no quantity;
 * each family's "+ Add" puts the tab's own blank row on the grid (1305 for the
 * round bases, 1324-1326 for the boxes). Chad, 2026-09-08: "have the 4 sections
 * with the ones shown as defaults, minus the quantities.. then a button for each
 * section to add another row".
 */
const MISC_FAMILIES = [
  {
    shape: "round", title: "Round bases", short: "bases", addLabel: "Round base",
    dims: [["dim_a", 'Dia"'], ["dim_b", "Depth ft"]],
    blurb:
      "Light pole and bollard bases, bike racks, pipe bollards: a diameter and a depth. Concrete is " +
      "π r² × depth ÷ 27; steel is dia × depth × the lb factor (the tab's 0.95). Type a " +
      "<strong>quantity</strong> and a <strong>mix</strong> on the ones the job has; every other number " +
      "on the row is the tab's default and can be changed.",
    blank: {
      shape: "round", unit: "EA", unit_sale: 300, labor_per_unit: 100, subcontracted: true, pours_concrete: true,
      dim_a: 12, dim_b: 3, steel_lb_per_in_ft: 0.95, forms_pct_of_sale: 0.1, forms_per_unit: 37.5,
      super_pct_of_labor: 0.2, equip_per_unit: 52,
    },
  },
  {
    shape: "block", title: "Pits, pads and bases", short: "pits and pads", addLabel: "Pit or pad",
    dims: [["dim_a", "LF"], ["dim_b", 'W"'], ["dim_c", 'H"']],
    blurb:
      "Elevator pits, monument bases, transformer pads, gate track: a length, a section and a height. " +
      "Concrete is L × W × H ÷ 3888 with 15% waste, plus a floor (L ÷ 4)² ÷ 27; steel per CY. Forms are a " +
      "share of the sale, plus $ per face SF (L × H ÷ 12) on a pit.",
    blank: {
      shape: "block", unit: "EA", labor_per_unit: 150, subcontracted: true, pours_concrete: true,
      dim_a: 36, dim_b: 12, dim_c: 24, concrete_waste: 0.15, steel_lb_per_cy: 55, forms_pct_of_sale: 0.1,
      super_pct_of_labor: 0.3, equip_per_unit: 50,
    },
  },
  {
    shape: "slab", title: "Footings and slabs", short: "footings", addLabel: "Footing",
    dims: [["dim_a", "SF"], ["dim_b", 'Thk"']],
    blurb:
      "Trellis, gate column, fire pit, site wall and grill footings, landscape curb, counters: an area and a " +
      "thickness. Concrete is SF × thk ÷ 324; steel 132.32 lb a CY (1% of 13,232). Forms as a share of the " +
      "sale or of the concrete.",
    blank: {
      shape: "slab", unit: "EA", labor_per_unit: 150, subcontracted: true, pours_concrete: true,
      dim_a: 9, dim_b: 12, steel_lb_per_cy: 132.32, forms_pct_of_concrete: 0.5, super_pct_of_labor: 0.15,
    },
  },
  {
    shape: "box", title: "Pits, treads, blockouts and ramps", short: "boxes", addLabel: "Box",
    dims: [["dim_a", 'L"'], ["dim_b", 'W"'], ["dim_c", 'D"']],
    blurb:
      "Radon pits, stair treads, pour-back blockouts, ADA ramps: three inch dimensions. Concrete is " +
      "L × W × D ÷ 46656 with 20% waste; steel per CY. The tab's blank rows carry $30 a unit of equipment " +
      "with a $300 minimum and supervision equal to the labor.",
    blank: {
      shape: "box", unit: "LF", labor_per_unit: 150, subcontracted: true, pours_concrete: true,
      dim_a: 48, dim_b: 36, dim_c: 8, concrete_waste: 0.2, steel_lb_per_cy: 211.7, forms_pct_of_concrete: 0.5,
      super_pct_of_labor: 1, equip_per_unit: 30, equip_min: 300,
    },
  },
];

function miscColumns(fam, mixes) {
  const dims = fam.dims.map(([f, label]) => ({ f, label, type: "number" }));
  const steel =
    fam.shape === "round"
      ? [{ f: "steel_lb_per_in_ft", label: "Steel lb/in·ft", type: "number" }]
      : [{ f: "steel_lb_per_cy", label: "Steel lb/CY", type: "number" }];
  const blockOnly =
    fam.shape === "block"
      ? [
          { f: "steel_lb_per_unit", label: "Steel lb ea", type: "number" },
          { f: "forms_per_face_sf", label: "Forms $/face SF", type: "number" },
        ]
      : [];
  const concForms =
    fam.shape === "slab" || fam.shape === "box"
      ? [{ f: "forms_pct_of_concrete", label: "Forms % conc", type: "number" }]
      : [];
  const minimum = fam.shape === "box" ? [{ f: "equip_min", label: "Equip min $", type: "number" }] : [];
  return [
    { f: "code", label: "Code", placeholder: "13xx" },
    { f: "description", label: "Item", placeholder: fam.addLabel },
    {
      f: "unit", label: "U/M", type: "select",
      options: [{ id: "EA", label: "EA" }, { id: "LF", label: "LF" }, { id: "SF", label: "SF" }],
    },
    { f: "qty", label: "Qty", type: "number" },
    { f: "unit_sale", label: "Sale ea", type: "number" },
    { f: "labor_per_unit", label: "Labor ea", type: "number" },
    { f: "subcontracted", label: "Sub", type: "check" },
    { f: "pours_concrete", label: "Conc", type: "check" },
    { f: "mix_design_id", label: "Mix", type: "select", options: mixOptions(mixes) },
    ...dims,
    { f: "concrete_waste", label: "Waste", type: "number" },
    ...steel,
    ...blockOnly,
    { f: "forms_pct_of_sale", label: "Forms % sale", type: "number" },
    { f: "forms_per_unit", label: "Forms $ ea", type: "number" },
    ...concForms,
    { f: "super_pct_of_labor", label: "Super % labor", type: "number" },
    { f: "equip_per_unit", label: "Equip $ ea", type: "number" },
    { f: "equip_pct_of_labor", label: "Equip % labor", type: "number" },
    ...minimum,
    {
      label: "CY",
      derived: (r) => num(r.calc_concrete_cy, 2),
      title: () => "from the shape, with the row's waste — decimal yards, where the tab rounds each row up",
    },
    { label: "Steel lb", derived: (r) => num(r.calc_steel_lb, 0) },
    {
      label: "Sale",
      derived: (r) => usd(r.calc_sale, 0),
      title: (r) => `${num(r.qty, 0)} × ${usd(r.unit_sale, 0)} — typed, the tab's K column`,
    },
    {
      label: "Cost",
      derived: (r) => usd(r.calc_cost, 0),
      title: (r) =>
        `concrete ${usd(r.calc_concrete_cost, 0)} + steel ${usd(r.calc_steel_cost, 0)} + forms ` +
        `${usd(r.calc_forms_cost, 0)} + labor ${usd(r.calc_labor_cost, 0)} + supervision ` +
        `${usd(r.calc_super_cost, 0)} + equipment ${usd(r.calc_equip_cost, 0)} + tax ${usd(r.calc_tax, 0)}`,
    },
    { label: "Cost ea", derived: (r) => usd(r.calc_cost_per_unit, 0) },
    {
      label: "Margin",
      derived: (r) => (r.calc_margin == null ? "—" : num(Number(r.calc_margin) * 100, 1) + "%"),
      title: () => "1 − cost ÷ sale — the tab's Z column, what falls out of the typed sale",
    },
  ];
}

/**
 * Panel types (sql/077): one line per tilt-wall panel type — the 12-PANELS
 * tab's row, with FOUR opening slots where the tab has one (Chad, 2026-09-08).
 * Each opening comes off the concrete, adds a set of the panel's edge bars and
 * puts its perimeter on the lumber and the chamfer. SF is gross — the tab's W
 * column — because forming an opening is work, not less of it.
 */
function panelColumns(mixes) {
  return [
    { f: "label", label: "Type", placeholder: "P1" },
    { f: "qty", label: "Qty", type: "number", step: "1" },
    { f: "mix_design_id", label: "Mix", type: "select", options: mixOptions(mixes) },
    { f: "length_ft", label: "L ft", type: "number" },
    { f: "thickness_in", label: 'Thk"', type: "number" },
    { f: "top_el_ft", label: "Top el", type: "number" },
    { f: "bot_el_ft", label: "Bot el", type: "number" },
    { f: "open1_len_ft", label: "O1 L", type: "number" },
    { f: "open1_wide_ft", label: "O1 W", type: "number" },
    { f: "open2_len_ft", label: "O2 L", type: "number" },
    { f: "open2_wide_ft", label: "O2 W", type: "number" },
    { f: "open3_len_ft", label: "O3 L", type: "number" },
    { f: "open3_wide_ft", label: "O3 W", type: "number" },
    { f: "open4_len_ft", label: "O4 L", type: "number" },
    { f: "open4_wide_ft", label: "O4 W", type: "number" },
    { f: "horiz_spacing_in", label: 'H sp"', type: "number" },
    { f: "horiz_size", label: "H #", type: "select", options: barSizeChoices() },
    { f: "horiz_mats", label: "H mats", type: "number", step: "1" },
    { f: "vert_spacing_in", label: 'V sp"', type: "number" },
    { f: "vert_size", label: "V #", type: "select", options: barSizeChoices() },
    { f: "vert_mats", label: "V mats", type: "number", step: "1" },
    { f: "edge_bar_count", label: "Edge n", type: "number", step: "1" },
    { f: "edge_bar_size", label: "Edge #", type: "select", options: barSizeChoices() },
    { f: "corner_bar_count", label: "Cnr n", type: "number", step: "1" },
    { f: "corner_bar_size", label: "Cnr #", type: "select", options: barSizeChoices() },
    {
      label: "Ht ft",
      derived: (r) => num(r.calc_height_ft, 2),
      title: () => "top elevation less bottom elevation",
    },
    {
      label: "SF ea",
      derived: (r) => num(r.calc_sf_each, 0),
      title: (r) =>
        `${num(r.length_ft, 0)} × ${num(r.calc_height_ft, 2)} — gross, the tab's W column; ` +
        "the openings come off the concrete, not off the area the labor is priced on",
    },
    {
      label: "SF",
      derived: (r) => num(r.calc_sf, 0),
      title: (r) =>
        `SF each × ${num(r.qty, 0)}` +
        (Number(r.calc_opening_sf) ? ` · openings ${num(r.calc_opening_sf, 0)} SF` : ""),
    },
    {
      label: "CY",
      derived: (r) => num(r.calc_concrete_cy, 2),
      title: () => "(L × H − the openings) × thickness / 324 × qty, with waste — not rounded up",
    },
    {
      label: "Steel lb",
      derived: (r) => num(r.calc_total_rebar_lb, 0),
      title: (r) =>
        `${num(r.calc_steel_each_lb, 0)} lb a panel × ${num(r.qty, 0)} — both mats, the edge ` +
        "bars, one set more per opening, the corner bars, with waste on every bar",
    },
    {
      label: "Cost / panel",
      derived: (r) => usd(r.calc_cost_per_panel, 0),
      title: (r) =>
        `sale ${usd(r.calc_sale_per_panel, 0)} a panel · ${usd(r.calc_cost, 0)} for the type`,
    },
  ];
}

/**
 * Beam runs (sql/073): one line per beam type — the 02-Gd Beams tab's row.
 * A continuous footing is the same row on its own kind.
 */
function beamColumns(mixes) {
  return [
    { f: "label", label: "Type", placeholder: "GB1" },
    { f: "mix_design_id", label: "Mix", type: "select", options: mixOptions(mixes) },
    { f: "length_ft", label: "L ft", type: "number" },
    { f: "width_in", label: 'W"', type: "number" },
    { f: "height_in", label: 'H"', type: "number" },
    {
      f: "top_bars_count",
      label: "Top bars",
      type: "number",
      step: "1",
      sub: { f: "top_bars_size", label: "Top #", tag: "#", type: "select", options: barSizeChoices(), hint: "Top bars: size" },
    },
    {
      f: "bottom_bars_count",
      label: "Bot bars",
      type: "number",
      step: "1",
      sub: { f: "bottom_bars_size", label: "Bot #", tag: "#", type: "select", options: barSizeChoices(), hint: "Bottom bars: size" },
    },
    {
      f: "mid_bars_count",
      label: "Mid / side",
      type: "number",
      step: "1",
      sub: { f: "mid_bars_size", label: "Mid #", tag: "#", type: "select", options: barSizeChoices(), hint: "Mid bars: size. The count is per side; the sheet doubles it" },
    },
    {
      f: "stirrup_size",
      label: "Stirrup #",
      type: "select",
      options: barSizeChoices(),
      sub: { f: "stirrup_spacing_in", label: 'Stirrup sp"', tag: 'sp"', type: "number", hint: "Stirrup spacing, inches — a hoop of 2(W + H) every spacing, no hooks" },
    },
    {
      f: "l_bars_size",
      label: "L bar #",
      type: "select",
      options: barSizeChoices(),
      sub: { f: "l_bars_spacing_in", label: 'L sp"', tag: 'sp"', type: "number", hint: "One L bar every spacing along the beam" },
    },
    { f: "l_bars_length_ft", label: "L bar ft", type: "number" },
    {
      f: "pilaster_count",
      label: "Pilasters",
      type: "number",
      step: "1",
      sub: { f: "pilaster_length_in", label: 'Pil L"', tag: 'L"', type: "number", hint: "Pilaster length, inches" },
    },
    { f: "pilaster_width_in", label: 'Pil W"', type: "number" },
    { label: "Face FF", derived: (r) => num(r.calc_face_ff, 0), title: () => "one face — what every $/FF labor rate here is priced on" },
    { label: "CY", derived: (r) => num(r.calc_concrete_cy, 2) },
    { label: "Steel lb", derived: (r) => num(r.calc_total_rebar_lb, 0) },
    { label: "Dig CY", derived: (r) => num(r.calc_excavate_cy, 0), title: (r) => `${num(r.calc_backfill_cy, 0)} CY backfilled` },
    {
      label: "Cost / LF",
      derived: (r) => (r.calc_cost_per_unit != null ? usd(r.calc_cost_per_unit, 2) : "—"),
      title: (r) => `${usd(r.calc_cost, 0)} · sale ${usd(r.calc_sale_per_unit, 2)}/LF`,
    },
  ];
}

/**
 * Spot footings (sql/072): one line per footing type, on the walls engine
 * with the wall left blank. Count x length of each is the run's length, the
 * way the workbook's 06-Footings tab types E = B x size.
 */
function spotFootingColumns(mixes) {
  return [
    { f: "label", label: "Type", placeholder: "F1" },
    { f: "footing_count", label: "Qty", type: "number", step: "1" },
    { f: "footing_each_ft", label: "L ft", type: "number" },
    // Typed in feet, stored in the walls' inches (units.js) — Chad, 2026-09-08:
    // a spread footing is called out in feet. The row, the API and the engine
    // never see the feet.
    {
      f: "ftg_width_in",
      label: "W ft",
      type: "number",
      scale: 12,
      hint: 'Width, typed in feet and stored in inches — 4.5 is 54"',
    },
    { f: "ftg_thick_in", label: 'H"', type: "number" },
    { f: "footing_mix_design_id", label: "Mix", type: "select", options: mixOptions(mixes) },
    { f: "ftg_bot_size", label: "Bot #", type: "select", options: barSizeChoices() },
    { f: "ftg_bot_spacing_in", label: 'Bot sp"', type: "number" },
    { f: "ftg_top_size", label: "Top #", type: "select", options: barSizeChoices() },
    { f: "ftg_top_spacing_in", label: 'Top sp"', type: "number" },
    { f: "weld_plate", label: "Weld plate", type: "check" },
    { f: "backfill", label: "Backfill", type: "check" },
    { label: "SF", derived: (r) => num(r.calc_footing_sf, 0), title: () => "plan area, what footing labor is priced on" },
    { label: "CY", derived: (r) => num(r.calc_footing_concrete_cy, 2) },
    { label: "Steel lb", derived: (r) => num(r.calc_footing_rebar_lb, 0) },
    {
      label: "Cost / ea",
      derived: (r) =>
        r.calc_cost != null && Number(r.footing_count) > 0
          ? usd(Number(r.calc_cost) / Number(r.footing_count), 0)
          : "—",
      title: (r) => `${usd(r.calc_cost, 0)} for ${num(r.footing_count, 0)}`,
    },
  ];
}

function wallColumns(mixes, section = null) {
  // What a blank footing mix means on this section: the section's footing mix
  // (the select above the grid) when one is set, else the wall's own.
  const ftgMixId = section?.footing_mix_design_id;
  const ftgMix =
    ftgMixId == null ? null : (mixes || []).find((m) => String(m.id) === String(ftgMixId));
  const ftgHint =
    ftgMixId == null
      ? "This footing's mix. Blank: no footing mix is set on the section, so it follows the wall's."
      : `This footing's mix. Blank follows the section's footing mix, ${
          ftgMix ? ftgMix.code || ftgMix.description || ftgMix.id : ftgMixId
        }.`;
  const wallSteel = (r) => {
    const parts = [r.calc_horiz_rebar_lb, r.calc_vert_rebar_lb, r.calc_lap_rebar_lb];
    if (parts.every((v) => v == null)) return null;
    return parts.reduce((a, v) => a + Number(v || 0), 0);
  };
  return [
    { f: "label", label: "Type", placeholder: "W1", sub: { label: "Footing", text: "↳ footing" } },
    { f: "length_ft", label: "Length ft", type: "number", sub: { label: "shared" } },
    {
      f: "wall_thick_in",
      label: 'Thick"',
      type: "number",
      sub: {
        f: "ftg_width_in",
        label: 'Width"',
        tag: 'W"',
        type: "number",
        hint: "Footing width, inches — the trench the wall sits in, and the plan area footing labor is priced per",
      },
    },
    {
      f: "wall_height_in",
      label: 'Height"',
      type: "number",
      sub: {
        f: "ftg_thick_in",
        label: 'Thick"',
        tag: 'T"',
        type: "number",
        hint: "Footing thickness, inches",
      },
    },
    { f: "backfill", label: "Backfill", type: "check" },
    {
      f: "mix_design_id",
      label: "Wall mix",
      type: "select",
      options: mixOptions(mixes),
      // The footing's own mix (sql/062). Blank follows the section's footing
      // mix — the select above the grid — then the wall's. Chad, 2026-09-05:
      // "per row footing mix, on the footing line."
      sub: {
        f: "footing_mix_design_id",
        label: "Ftg mix",
        tag: "mix",
        type: "select",
        options: mixOptions(mixes),
        hint: ftgHint,
      },
    },
    // The footing's two mats (sql/059) sit under the wall's two bar sets:
    // bottom under horizontal, top under vertical. Each is its own bar set
    // running both directions; a mat with no spacing or no size is no mat.
    {
      f: "horiz_spacing_in",
      label: 'Horz sp"',
      type: "number",
      sub: {
        f: "ftg_bot_spacing_in",
        label: 'Bot sp"',
        tag: 'bot sp"',
        type: "number",
        hint: "Bottom mat: bar spacing, inches — the same spacing both directions",
      },
    },
    {
      f: "horiz_size",
      label: "Horz #",
      type: "select",
      options: barSizeChoices(),
      sub: {
        f: "ftg_bot_size",
        label: "Bot #",
        tag: "bot #",
        type: "select",
        options: barSizeChoices(),
        hint: "Bottom mat: bar size — the same bar both directions",
      },
    },
    { f: "horiz_mats", label: "Horz faces", type: "number", step: "1" },
    {
      f: "vert_spacing_in",
      label: 'Vert sp"',
      type: "number",
      sub: {
        f: "ftg_top_spacing_in",
        label: 'Top sp"',
        tag: 'top sp"',
        type: "number",
        hint:
          "Top mat: bar spacing, inches — both directions. Leave the top mat blank " +
          "on a one-mat footing.",
      },
    },
    {
      f: "vert_size",
      label: "Vert #",
      type: "select",
      options: barSizeChoices(),
      sub: {
        f: "ftg_top_size",
        label: "Top #",
        tag: "top #",
        type: "select",
        options: barSizeChoices(),
        hint: "Top mat: bar size — a mat with no size or no spacing contributes nothing",
      },
    },
    { f: "vert_mats", label: "Vert faces", type: "number", step: "1" },
    {
      label: "Form ft",
      derived: (r) => num(r.calc_form_ff, 1),
      title: () =>
        "Contact area on ONE face — the sheet computes both faces and halves them. " +
        "Every $/FF rate on this assembly is priced against that convention.",
      sub: {
        label: "Ftg SF",
        derived: (r) => num(r.calc_footing_sf, 1),
        title: () => "Footing plan area — what footing labor is priced per, not form feet",
      },
    },
    {
      label: "CY",
      derived: (r) => num(r.calc_wall_concrete_cy, 2),
      title: (r) =>
        `wall concrete — ${num(r.calc_concrete_cy, 2)} for the type with its footing`,
      sub: {
        label: "Ftg CY",
        derived: (r) => num(r.calc_footing_concrete_cy, 2),
        title: () => "The footing takes the section's footing mix",
      },
    },
    {
      label: "Steel lb",
      derived: (r) => num(wallSteel(r), 0),
      title: (r) =>
        `horizontal ${num(r.calc_horiz_rebar_lb, 0)} + vertical ${num(
          r.calc_vert_rebar_lb,
          0
        )} + laps ${num(r.calc_lap_rebar_lb, 0)} — ${num(
          r.calc_total_rebar_lb,
          0
        )} for the type with its footing`,
      sub: {
        label: "Ftg lb",
        derived: (r) => num(r.calc_footing_rebar_lb, 0),
        title: () => "Footing bars, both directions",
      },
    },
    {
      label: "Earth CY",
      derived: (r) => num(r.calc_excavate_cy, 0),
      title: (r) =>
        `excavate ${num(r.calc_excavate_cy, 0)} · backfill ${num(
          r.calc_backfill_cy,
          0
        )} · sand ${num(r.calc_sand_cy, 0)} · drain ${num(r.calc_drain_lf, 0)} LF`,
    },
    {
      label: "Wall $/FF",
      derived: (r) => usd(r.calc_wall_cost_per_ff, 2),
      title: (r) =>
        `cost ${usd(r.calc_wall_cost, 0)} over ${num(r.calc_form_ff, 0)} form ft · ` +
        `sale ${usd(r.calc_wall_sale_per_ff, 2)}/FF`,
      sub: {
        label: "Ftg $/SF",
        derived: (r) => usd(r.calc_footing_cost_per_sf, 2),
        title: (r) =>
          `cost ${usd(r.calc_footing_cost, 0)} over ${num(r.calc_footing_sf, 0)} SF of ` +
          `footing plan area · sale ${usd(r.calc_footing_sale_per_sf, 2)}/SF`,
      },
    },
    {
      label: "Wall sale/FF",
      derived: (r) => usd(r.calc_wall_sale_per_ff, 2),
      title: () => "Wall cost per form foot × (1 + margin + contingency)",
      sub: {
        label: "Ftg sale/SF",
        derived: (r) => usd(r.calc_footing_sale_per_sf, 2),
        title: () => "Footing cost per SF of plan area × (1 + margin + contingency)",
      },
    },
    {
      // Cost on both lines, sale in the tooltip — one column, one meaning.
      // (Before the split, "Wall total" showed cost and "Ftg total" showed
      // sale; side by side that was survivable, stacked it would mislead.)
      label: "Wall cost",
      derived: (r) => usd(r.calc_wall_cost, 0),
      title: (r) => `sale ${usd(r.calc_wall_sale, 0)}`,
      sub: {
        label: "Ftg cost",
        derived: (r) => usd(r.calc_footing_cost, 0),
        title: (r) =>
          `sale ${usd(r.calc_footing_sale, 0)} — wall + footing always sum to the ` +
          `type, so a difference is in the schedule, not the split.`,
      },
    },
  ];
}

/**
 * Quotes on a section (sql/039).
 *
 * A real supplier number replacing one the app computed. Three kinds so far —
 * drilling, rebar, PT — and the card is the same for all of them because the
 * two things an estimator needs to see are the same: what it replaced, and
 * whether it can still be trusted.
 *
 * The stale banner only ever appears on a LUMP. A unit price follows the
 * takeoff by construction, and warning about it would train people to ignore
 * the banner that matters.
 *
 * Quotes are material only: a rebar quote does not stop TIE STEEL billing.
 * The card says so, because that is the assumption most likely to be wrong in
 * someone's head.
 */
// Units a quote can be priced in, DEFAULT FIRST — the first entry is what an
// unquoted card starts on.
//
// LS used to lead every list, and on 2026-09-01 that put "$0.65" into the mono
// slab as a sixty-five dollar-cent lump sum for 21,945 lb of steel. The app
// took it, spread it, stamped a baseline against the takeoff and showed a green
// "quoted" badge; the section quietly lost $14,252.58 and read as current. A
// fabricator quotes steel per pound far more often than as a package, so per
// pound is what the form should be sitting on when you start typing.
const QUOTE_UNITS = {
  drilling: ["LS"],
  rebar: ["LB", "TON", "CWT", "LS"],
  pt: ["SF", "LS"],
  shoring: ["LS", "SF"],
};

const QUOTE_META = {
  drilling: {
    label: "Drilling",
    blurb:
      "The driller's price for the holes. Replaces the $/LF rate table, spread across the pier groups.",
    fallback: "the $/LF rate table is pricing this by diameter",
  },
  rebar: {
    label: "Rebar",
    blurb:
      "The fabricator's price for the steel. <strong>Material only</strong> — TIE STEEL labor still bills.",
    fallback: "the catalog rate is pricing the steel",
  },
  pt: {
    label: "Post-tension",
    blurb:
      "The PT sub's price for the package. Lands only on pours that are actually post-tensioned.",
    fallback: "the catalog $/SF is pricing the PT",
  },
  shoring: {
    label: "Forms & shoring",
    blurb:
      "The rental house's price for forms, shoring and reshoring, for the job. Replaces the three rental lines on the deck; the labor still bills.",
    fallback: "the three $/SF rates are pricing the rentals",
  },
};

function quoteUnitLabel(unit) {
  return unit === "LS" ? "lump sum" : `per ${unit.toLowerCase()}`;
}

/**
 * A quote's money, at a scale that survives the mistake it is meant to expose.
 *
 * `usd(0.65, 0)` renders "$1", which turns the sixty-five-cent lump — the exact
 * error this comparison exists to catch — into a plausible-looking dollar. Cents
 * matter precisely when the number is absurdly small.
 */
function quoteUsd(v) {
  const n = Math.abs(Number(v) || 0);
  return usd(v, n > 0 && n < 100 ? 2 : 0);
}

/**
 * The ratio, in words when a decimal would read as zero.
 *
 * 0.65 against $13,167 is 0.00005x, which `num(r, 2)` renders as "0×" — true,
 * useless, and it makes the banner look like it is guessing.
 */
function ratioText(r) {
  const n = Number(r);
  if (!isFinite(n)) return "";
  if (n < 0.01) return "under 1% of catalog";
  if (n >= 100) return `${num(n, 0)}× catalog`;
  return `${num(n, 2)}×`;
}

function quoteCardHtml(section, kind, quote) {
  const meta = QUOTE_META[kind] || { label: kind, blurb: "", fallback: "computed" };
  const q = quote || null;
  const stale = !!(q && q.stale);
  const isLump = !q || q.unit === "LS";
  // Quote against catalog. `catalog_verdict` is null when there was no honest
  // comparison to draw — no takeoff, or no catalog price behind it — and that
  // is NOT the same as passing, so it renders as "could not check" rather than
  // silently as fine.
  const verdict = q ? q.catalog_verdict : null;
  const offBand = verdict === "far_below" || verdict === "far_above";

  return `
  <div class="card quote-card" data-quote-kind="${kind}" style="margin-bottom:1rem">
    <h3 style="margin:0 0 0.35rem">
      ${esc(meta.label)}
      ${
        q
          ? `<span class="badge ${stale || offBand ? "warn" : "ok"}">quoted</span>`
          : `<span class="badge">computed</span>`
      }
      ${
        offBand
          ? `<span class="badge warn">${
              verdict === "far_below" ? "far below catalog" : "far above catalog"
            }</span>`
          : ""
      }
    </h3>
    <p style="margin:0 0 0.85rem;color:var(--text-muted);font-size:0.85rem">${
      q ? meta.blurb : `No quote yet — ${meta.fallback}. Enter one to replace it.`
    }</p>

    ${
      stale
        ? `<div class="error-banner">
             <strong>This quote is out of date.</strong>
             ${
               q.baseline_qty == null
                 ? `It has no recorded takeoff to check against, so there is no way to tell
                    what it was priced for. Re-save it to stamp it against the current
                    ${num(q.current_qty, 0)} ${esc(q.baseline_unit || "")}.`
                 : `It was priced against <strong>${num(q.baseline_qty, 0)} ${esc(
                     q.baseline_unit || ""
                   )}</strong> and the takeoff is now
                    <strong>${num(q.current_qty, 0)} ${esc(q.baseline_unit || "")}</strong>
                    (${Number(q.current_qty) > Number(q.baseline_qty) ? "+" : ""}${num(
                     Number(q.current_qty) - Number(q.baseline_qty),
                     0
                   )}).
                    The lump has not moved — go back to the supplier, or clear it and let
                    the computed price stand.`
             }
           </div>`
        : ""
    }

    ${
      offBand
        ? `<div class="error-banner">
             <strong>This quote is ${
               verdict === "far_below" ? "far below" : "far above"
             } what the catalog would charge.</strong>
             It charges <strong>${quoteUsd(q.quoted_total)}</strong> for the package
             where the catalog says <strong>${quoteUsd(q.catalog_total)}</strong> —
             <strong>${ratioText(q.catalog_ratio)}</strong>.
             ${
               verdict === "far_below"
                 ? `That is the shape of a decimal-point or unit mistake: a $/lb
                    rate typed as a lump, or $/ton entered as $/lb. If the price
                    is real, it is a good buy and this notice is only a notice.`
                 : `That is the shape of a lump typed into a rate box. Check the
                    <strong>Priced per</strong> field against the supplier's paper.`
             }
           </div>`
        : ""
    }

    ${
      q && q.catalog_total != null
        ? `<p style="margin:0 0 0.75rem;color:var(--text-muted);font-size:0.85rem">
             Quoted <strong>${quoteUsd(q.quoted_total)}</strong>
             · catalog <strong>${quoteUsd(q.catalog_total)}</strong>
             · <strong>${ratioText(q.catalog_ratio)}</strong>
             ${
               // Only when the ratio rendered as a number — "under 1% of
               // catalog (100% under)" says the same thing twice.
               Number(q.catalog_ratio) < 0.01 || Number(q.catalog_ratio) >= 100
                 ? ""
                 : Number(q.catalog_ratio) < 1
                 ? `(${num((1 - Number(q.catalog_ratio)) * 100, 0)}% under)`
                 : Number(q.catalog_ratio) > 1
                 ? `(${num((Number(q.catalog_ratio) - 1) * 100, 0)}% over)`
                 : ""
             }
           </p>`
        : q
        ? `<p style="margin:0 0 0.75rem;color:var(--text-muted);font-size:0.85rem"
              title="No takeoff to compare against, or the catalog carries no price for it. Not the same as agreeing with the quote.">
             Quoted <strong>${quoteUsd(q.quoted_total ?? q.amount)}</strong>
             · <em>no catalog price to compare against</em>
           </p>`
        : ""
    }

    <div class="form-grid" style="margin-bottom:0.75rem">
      <div class="field">
        <label>Amount</label>
        <input class="q-amount" type="number" step="0.0001" min="0"
               placeholder="computed" value="${q ? q.amount : ""}" />
        <small style="color:var(--text-muted)">Empty or 0 hands it back to the computed price.</small>
      </div>
      <div class="field">
        <label>Priced per</label>
        <select class="q-unit">
          ${(QUOTE_UNITS[kind] || ["LS"])
            .map(
              (u, i) =>
                `<option value="${u}"${
                  q ? (q.unit === u ? " selected" : "") : i === 0 ? " selected" : ""
                }>${u} — ${quoteUnitLabel(u)}</option>`
            )
            .join("")}
        </select>
        <small style="color:var(--text-muted)">Only a lump can go stale. A lump is the
          <em>whole package</em>, not a rate — check this before you save.</small>
      </div>
      <div class="field full">
        <label>Who quoted it, and what it covers</label>
        <input class="q-note" type="text" maxlength="1000"
               placeholder="e.g. Acme 8/28 — material delivered, excludes rock"
               value="${esc((q && q.note) || "")}" />
        <small style="color:var(--text-muted)">The exclusions are the part that costs money later.</small>
      </div>
      <div class="field">
        <label>&nbsp;</label>
        <button class="btn q-save" type="button">Save quote</button>
      </div>
    </div>

    ${
      q && !isLump
        ? `<p style="margin:0;color:var(--text-muted);font-size:0.85rem">
             Follows the takeoff — ${num(q.current_qty, 0)} ${esc(
             q.baseline_unit || ""
           )} at ${usd(q.amount, 4)}/${esc(q.unit)}. Nothing to go stale.
           </p>`
        : ""
    }
  </div>`;
}

function quoteCardsHtml(section) {
  const kinds = section.quote_kinds || [];
  if (!kinds.length) return "";
  const byKind = Object.fromEntries((section.quotes || []).map((q) => [q.kind, q]));
  return kinds.map((k) => quoteCardHtml(section, k, byKind[k])).join("");
}

/**
 * The formed perimeter in words, for the Form SF tooltip — so the grid shows
 * WHY a pilaster's contact area is smaller than a column's of the same size.
 * The unformed face is always an L face (sql/051).
 */
function facesFormula(r) {
  const L = `${num(r.length_in, 0)}"`;
  const W = `${num(r.width_in, 0)}"`;
  const faces = Number(r.formed_faces ?? 4);
  if (faces === 3) return `(${L} + ${W} × 2)`;
  if (faces === 2) return `(${W} × 2)`;
  return `(${L} + ${W}) × 2`;
}

/**
 * The one thing a pilaster section has to be checked by hand for (sql/051).
 *
 * A wall-side type carries its own full L × W × height, because that is the
 * honest reading of the schedule in front of you. Whether the WALL run also
 * carries a rectangle through the same pilaster is a question about how the
 * wall was taken off, and it was open when this was built — Chad, 2026-09-02:
 * "not sure — I'd have to look at a job." So the app does not net anything
 * out; it says so, once, where the person who knows is standing.
 *
 * Silently deducting concrete somebody entered would be the worse error.
 */
function pilasterNoteHtml(rows) {
  const wallSide = (rows || []).filter((r) => Number(r.formed_faces ?? 4) < 4);
  if (!wallSide.length) return "";
  const n = wallSide.reduce((a, r) => a + Number(r.qty || 0), 0);
  return `<div class="warn-banner">
    <strong>${wallSide.length === 1 ? "One type is" : `${wallSide.length} types are`}
    formed against a wall</strong> — ${num(n, 0)} pilaster${n === 1 ? "" : "s"}, so
    form area and chamfer are reduced accordingly.
    <span style="display:block;margin-top:0.35rem">Their concrete is counted
    <strong>in full</strong> here. If the wall run they sit on was taken off
    straight through, that CY is on the job twice — worth a look at the walls
    section before this goes out.</span>
  </div>`;
}

function mixOptions(mixes) {
  return (mixes || []).map((m) => ({
    id: m.id,
    label: m.code || m.description || m.id,
  }));
}

/**
 * The banner a section shows when the master list could not price something
 * on it (sql/047).
 *
 * Until 2026-09-02 a NULL catalog price multiplied through as zero and vanished
 * into the total — a fresh install bid $324k of concrete at nothing and every
 * card looked fine. Chad: "I dont like concrete prices starting @ $0." The
 * arithmetic still has to multiply by zero; this is where it stops being quiet
 * about it. Rendered ABOVE the stat cards so the total is never read without
 * its qualifier.
 */
function unpricedBannerHtml(section) {
  const items = section.calc_unpriced || [];
  if (!items.length) return "";
  const untyped = items.some((x) => /not typed/.test(x));
  const unpriced = items.filter((x) => !/not typed/.test(x));
  return `<div class="error-banner" style="margin-bottom:1rem">
    <strong>${items.length === 1 ? "One thing on this section is costed at nothing." : `${items.length} things on this section are costed at nothing.`}</strong>
    The totals below are <strong>light by an unknown amount</strong>:
    <ul style="margin:0.5rem 0 0 1.2rem">
      ${items.map((x) => `<li>${esc(x)}</li>`).join("")}
    </ul>
    <span style="display:block;margin-top:0.5rem">${
      unpriced.length
        ? `Price ${unpriced.length === 1 ? "it" : "them"} on this job's
      <a href="#prices/${section.estimate_id}">price sheet</a> — or on the master list, then pull${untyped ? "; " : " — and "}`
        : ""
    }${
      untyped
        ? `type the superintendent days on the <strong>Labor</strong> tab below — the rental ladder follows them — and `
        : ""
    }<strong>Recalculate</strong>.</span>
  </div>`;
}

async function renderSectionDetail(root) {
  root.innerHTML = `<div class="loading">Loading section…</div>`;
  if (!state.mixes.length) state.mixes = await Api.listMixes({ active_only: true });
  if (!state.barSizes.length) {
    state.barSizes = (await Api.listBarSizes().catch(() => [])).map((b) => b.size);
  }

  // One assembly of a job (sql/033-034). Everything on this page — pours, beam
  // types, forming, labor, equipment, markup, the vapor barrier — belongs to
  // the section, not to the estimate above it.
  const section = await Api.getSection(state.sectionId);
  const estimate = await Api.getEstimate(section.estimate_id);
  state.estimateId = estimate.id;

  // Paving is a different assembly, not a mono slab with some fields blank:
  // it forms off curb LF, lays no vapor barrier, has no grade beams, and is
  // taken off as a grid of areas rather than a list of pours (sql/036).
  const isPaving = PAVING_KINDS.has(section.kind);
  const isSidewalk = SIDEWALK_KINDS.has(section.kind);
  const isPiers = PIER_KINDS.has(section.kind);
  const isWalls = WALL_KINDS.has(section.kind);
  const isSpot = SPOT_KINDS.has(section.kind);
  const isBeams = BEAM_KINDS.has(section.kind);
  const isCont = CONT_KINDS.has(section.kind);
  const isColumns = COLUMN_KINDS.has(section.kind);
  const isDeck = DECK_KINDS.has(section.kind);
  const isPanels = PANEL_KINDS.has(section.kind);
  const isMisc = MISC_KINDS.has(section.kind);
  // Piers, walls, columns, decks, panels and misc items keep their takeoffs
  // in their own tables, not in pours.
  const notPours = isPiers || isWalls || isColumns || isDeck || isBeams || isPanels || isMisc;
  const isGrid = isPaving || isPiers || isWalls || isSpot || isColumns || isDeck || isBeams || isPanels || isMisc;

  const [
    slabs, totals, beamTypes, forming, labor, equip,
    pierRows, pierT, wallRows, wallT, beamRows, beamT, colRows, colT, deckRows, deckT, panRows, panT, miscRows, miscT, rates, mats,
  ] = await Promise.all([
    notPours ? Promise.resolve([]) : Api.listMonoSlabs(section.id),
    notPours ? Promise.resolve(null) : Api.monoSlabTotals(section.id),
    isGrid ? Promise.resolve(null) : Api.listBeamTypes(section.id).catch(() => null),
    Api.formingMaterials(section.id).catch(() => null),
    Api.laborMaterials(section.id).catch(() => null),
    Api.estimateEquipment(section.id).catch(() => null),
    isPiers ? Api.listPierGroups(section.id) : Promise.resolve([]),
    isPiers ? Api.pierTotals(section.id) : Promise.resolve(null),
    isWalls || isSpot ? Api.listWallRuns(section.id) : Promise.resolve([]),
    isWalls || isSpot ? Api.wallTotals(section.id) : Promise.resolve(null),
    isBeams ? Api.listBeamRuns(section.id) : Promise.resolve([]),
    isBeams ? Api.beamTotals(section.id) : Promise.resolve(null),
    isColumns ? Api.listColumnTypes(section.id) : Promise.resolve([]),
    isColumns ? Api.columnTotals(section.id) : Promise.resolve(null),
    isDeck ? Api.listDeckLevels(section.id) : Promise.resolve([]),
    isDeck ? Api.deckTotals(section.id) : Promise.resolve(null),
    isPanels ? Api.listPanelTypes(section.id) : Promise.resolve([]),
    isPanels ? Api.panelTotals(section.id) : Promise.resolve(null),
    isMisc ? Api.listMiscItems(section.id) : Promise.resolve([]),
    isMisc ? Api.miscTotals(section.id) : Promise.resolve(null),
    // The rate ladder for this section (sql/055). Never fatal: a section
    // whose takeoff will not build still shows its quantities.
    Api.sectionRates(section.id).catch(() => null),
    // Never fatal to the page: a section with no breakdown still shows its
    // quantities, it just shows them without the money.
    Api.sectionMaterialCosts(section.id).catch(() => null),
  ]);

  // key -> the line, so a card can ask for its own dollars by name.
  const mat = matIndex(mats);

  // The Margin % / Conting % boxes below are seeded from the SECTION, which is
  // also what Apply writes to. They used to be filled from estimate.margin_pct
  // — the default a NEW section is created with — while the button PATCHed the
  // section. Two consequences, and the second is the bad one: a section at 18%
  // displayed the job's 15% and sprang back to 15 after every successful save,
  // so the margin looked unchangeable; and pressing Apply without touching the
  // box silently overwrote the section's real markup with the job default.
  //
  // That note used to live in an HTML comment inside the template literal
  // below, with `estimate.margin_pct` in backticks. This file is loaded as
  // type="module", and a backtick inside a template literal ENDS IT — the
  // whole page died with "SyntaxError: Unexpected identifier 'estimate'" and
  // nothing rendered but "Loading…". Prose about the code goes in a JS comment
  // out here. Nothing inside a template literal may contain a backtick or a
  // ${ that is not a real interpolation.
  root.innerHTML = `
    <div class="page-header">
      <div>
        <button class="btn ghost" id="back-estimate">← ${esc(estimate.name)}</button>
        <h1 style="margin-top:0.5rem">${esc(section.name)}</h1>
        <p>${statusBadge(estimate.status)}${
          section.name.trim().toLowerCase() === sectionLabel(section.kind).toLowerCase()
            ? ""
            : " · " + esc(sectionLabel(section.kind))
        }
          · measured in ${esc(section.unit)}
          · ${section.tax_exempt === null
              ? (section.effective_tax_exempt ? "tax exempt (project)" : "taxed (project)")
              : (section.tax_exempt ? "<strong>tax exempt</strong> (set here)" : "<strong>taxed</strong> (set here)")}
          · waste C/S/R:
          ${[
            ["waste_concrete", "effective_waste_concrete"],
            ["waste_sand", "effective_waste_sand"],
            ["waste_rebar", "effective_waste_rebar"],
          ]
            .map(([own, eff]) => {
              // An unset factor is no longer necessarily the company's: since
              // sql/036 an assembly can carry its own. Show what was used, and
              // say where it came from.
              const used = section[eff] != null ? Number(section[eff]) : null;
              if (section[own] != null) return `<strong>${Number(section[own])}</strong>`;
              return used == null
                ? "sys"
                : `<span title="not set on this section — inherited">${used}</span>`;
            })
            .join(" / ")}
          · margin ${num(Number(section.margin_pct ?? 0.2) * 100, 1)}%
          · conting ${num(Number(section.contingency_pct ?? 0) * 100, 1)}%
        </p>
        <p style="margin:0.4rem 0 0;display:flex;gap:0.5rem;align-items:center;flex-wrap:wrap;font-size:0.85rem">
          <label class="muted" for="est-margin-pct">Margin %</label>
          <input type="number" id="est-margin-pct" min="0" max="200" step="0.5" style="width:4.5rem"
            value="${esc(Math.round(Number(section.margin_pct ?? estimate.margin_pct ?? 0.2) * 1000) / 10)}" />
          <label class="muted" for="est-conting-pct">Conting %</label>
          <input type="number" id="est-conting-pct" min="0" max="200" step="0.5" style="width:4.5rem"
            value="${esc(Math.round(Number(section.contingency_pct ?? estimate.contingency_pct ?? 0) * 1000) / 10)}" />
          <button type="button" class="btn" id="btn-apply-markup">Apply markup</button>
          <span class="muted" style="color:var(--text-muted);font-size:0.8rem">this section only${
            section.margin_pct != null &&
            estimate.margin_pct != null &&
            Number(section.margin_pct) !== Number(estimate.margin_pct)
              ? ` · job default is ${num(Number(estimate.margin_pct) * 100, 1)}%`
              : ""
          }</span>
        </p>
        ${
          isWalls || isSpot
            ? `<p style="margin:0.4rem 0 0;display:flex;gap:0.5rem;align-items:center;flex-wrap:wrap;font-size:0.85rem">
                 <label class="muted" for="sec-footing-mix">Footing mix</label>
                 <select id="sec-footing-mix"
                   title="One mix for every footing in this section — the sheet's R8. Blank: each footing follows its wall's mix.">
                   <option value=""${section.footing_mix_design_id == null ? " selected" : ""}>follows the wall's mix</option>
                   ${mixOptions(state.mixes)
                     .map(
                       (o) =>
                         `<option value="${esc(o.id)}"${
                           String(section.footing_mix_design_id) === String(o.id) ? " selected" : ""
                         }>${esc(o.label)}</option>`
                     )
                     .join("")}
                 </select>
                 <span class="muted" style="color:var(--text-muted);font-size:0.8rem">every footing in this section — each wall's own mix is on its row</span>
               </p>`
            : ""
        }
        ${
          isGrid
            ? `<p style="margin:0.4rem 0 0;color:var(--text-muted);font-size:0.82rem">
                 No vapor barrier on this assembly — ${
                   isPiers
                     ? "a pier is a hole"
                     : isBeams
                     ? "a beam sits in its trench"
                     : isWalls
                     ? "nothing goes under a wall"
                     : isColumns
                     ? "a column stands on something already poured"
                     : "the paving sheet has no poly line"
                 },
                 so no wrap SF is computed and none is priced.
               </p>`
            : `<p style="margin:0.4rem 0 0;display:flex;gap:0.5rem;align-items:center;flex-wrap:wrap;font-size:0.85rem">
          <label class="muted" for="est-vapor">Vapor barrier</label>
          <select id="est-vapor" style="min-width:17rem"></select>
          <span class="muted" id="est-vapor-rate" style="color:var(--text-muted);font-size:0.8rem"></span>
        </p>
        <p style="margin:0.4rem 0 0;display:flex;gap:0.5rem;align-items:center;flex-wrap:wrap;font-size:0.85rem">
          <label class="muted" for="est-tape">Seam tape</label>
          <select id="est-tape" style="min-width:17rem"></select>
          <label class="muted" for="est-tape-ratio">rolls per barrier roll</label>
          <input type="number" id="est-tape-ratio" min="0" step="0.25" style="width:4.5rem" />
          <span class="muted" id="est-tape-note" style="color:var(--text-muted);font-size:0.8rem"></span>
        </p>`
        }
      </div>
      <div style="display:flex;gap:0.5rem;flex-wrap:wrap">
        ${
          isGrid
            ? `<button class="btn ghost" id="btn-jump-areas" type="button">${
                isPiers
                  ? "Pier groups"
                  : isCont
                  ? "Footing types"
                  : isBeams
                  ? "Beam types"
                  : isSpot
                  ? "Spot footings"
                  : isWalls
                  ? "Wall runs"
                  : isColumns
                  ? "Column types"
                  : isMisc
                  ? "Misc items"
                  : isDeck
                  ? "Deck levels"
                  : "Paving areas"
              }</button>`
            : `<button class="btn primary" id="btn-add-slab">+ Mono slab pour</button>
        <button class="btn ghost" id="btn-jump-beams" type="button">Beam schedule</button>`
        }
        ${isMisc ? "" : `<button class="btn ghost" id="btn-jump-forming" type="button">Forming materials</button>`}
        ${isDeck || isBeams || isPanels ? `<button class="btn ghost" id="btn-jump-rentals" type="button">Rentals</button>` : ""}
        ${isMisc ? "" : `<button class="btn ghost" id="btn-jump-labor" type="button">Labor &amp; supervision</button>
        <button class="btn ghost" id="btn-jump-equip" type="button">Equipment</button>`}
        <button class="btn" id="btn-recalc-estimate" type="button"
          title="Rewrite pours and stored takeoffs from current inputs — use after changing company defaults">Recalculate</button>
        <button class="btn" id="btn-edit-section" type="button"
          title="Name, unit, markup, tax and notes">Edit section</button>
        <button class="btn danger" id="btn-del-estimate">Delete section</button>
      </div>
    </div>

    ${unpricedBannerHtml(section)}
    ${isColumns ? pilasterNoteHtml(colRows) : ""}

    ${
      isColumns
        ? `<div class="grid stats">
      <div class="card stat"><div class="label">Columns</div><div class="value">${colT.column_count}</div><div class="hint">${colT.type_count} type${colT.type_count === 1 ? "" : "s"} on the schedule</div></div>
      <div class="card stat"><div class="label">Form SF</div><div class="value">${num(colT.total_form_sf, 0)}</div><div class="hint">contact area · <strong>perimeter × height</strong>, and what every shared cost here is spread by</div></div>
      <div class="card stat"><div class="label">Concrete CY</div><div class="value">${num(colT.total_concrete_cy, 2)}</div><div class="hint">not rounded up — the batch ticket rounds, the bid does not</div>${moneyRow(
        matCost(mat, "concrete")
      )}</div>
      <div class="card stat"><div class="label">Steel</div><div class="value">${num(colT.total_rebar_lb, 0)}</div><div class="hint">lb · vert ${num(colT.total_vert_rebar_lb, 0)} + ties ${num(colT.total_tie_rebar_lb, 0)} + dowels ${num(colT.total_dowel_rebar_lb, 0)} · waste on <em>every</em> bar</div>${moneyRow(
        matCost(mat, "rebar")
      )}</div>
      <div class="card stat"><div class="label">Chamfer</div><div class="value">${num(colT.total_chamfer_lf, 0)}</div><div class="hint">LF · exposed corners × height × <strong>quantity</strong> — four wrapped, two against a wall</div></div>
      <div class="card stat"><div class="label">Cost / form SF</div><div class="value">${usd(colT.cost_per_form_sf, 2)}</div><div class="hint">the number to compare across jobs</div></div>
      <div class="card stat"><div class="label">Cost</div><div class="value">${usd(section.calc_total_cost ?? colT.total_cost, 0)}</div><div class="hint">direct + takeoffs + tax</div></div>
      <div class="card stat"><div class="label">Sale</div><div class="value">${usd(section.calc_total_sale ?? colT.total_sale, 0)}</div><div class="hint">cost × (1 + margin + conting)</div></div>
      <div class="card stat"><div class="label">Sale / column</div><div class="value">${usd(section.calc_sale_per_unit ?? colT.total_sale_per_unit, 0)}</div><div class="hint">cost ${usd(section.calc_cost_per_unit ?? colT.total_cost_per_unit, 0)}/column</div></div>
    </div>`
        : isMisc
        ? `<div class="grid stats">
      <div class="card stat"><div class="label">Sale</div><div class="value">${usd(section.calc_total_sale ?? miscT.total_sale, 0)}</div><div class="hint">typed per item, the tab's K · at this section's ${num(Number(section.margin_pct ?? 0) * 100, 0)}% the cost would sell for ${usd(miscT.sale_at_markup, 0)}</div></div>
      <div class="card stat"><div class="label">Cost</div><div class="value">${usd(section.calc_total_cost ?? miscT.total_cost, 0)}</div><div class="hint">concrete, steel, forms, labor, supervision, equipment, and tax on the purchases</div></div>
      <div class="card stat"><div class="label">Margin</div><div class="value">${miscT.total_margin == null ? "—" : num(Number(miscT.total_margin) * 100, 1) + "%"}</div><div class="hint">1 − cost ÷ sale — the answer on this tab, not the input</div></div>
      <div class="card stat"><div class="label">Items</div><div class="value">${num(miscT.item_count, 0)}</div><div class="hint">of ${num(miscT.row_count, 0)} on the page carry a quantity</div></div>
      <div class="card stat"><div class="label">Concrete CY</div><div class="value">${num(miscT.total_concrete_cy, 2)}</div><div class="hint">decimal yards — the tab rounds each row up</div>${moneyRow(matCost(mat, "concrete"))}</div>
      <div class="card stat"><div class="label">Steel</div><div class="value">${num(miscT.total_steel_lb, 0)}</div><div class="hint">lb, from each item's shape</div>${moneyRow(matCost(mat, "rebar"))}</div>
      <div class="card stat"><div class="label">Labor</div><div class="value">${usd(miscT.total_labor_cost, 0)}</div><div class="hint">typed per item · supervision ${usd(miscT.total_super_cost, 0)} · sub ${usd(miscT.total_sub_labor_cost, 0)}</div></div>
      <div class="card stat"><div class="label">Forms</div><div class="value">${usd(miscT.total_forms_cost, 0)}</div><div class="hint">allowances, taxed as the purchase they are</div></div>
      <div class="card stat"><div class="label">Equipment</div><div class="value">${usd(miscT.total_equip_cost, 0)}</div><div class="hint">typed per item — no ladder, no fuel</div></div>
    </div>`
        : isPanels
        ? `<div class="grid stats">
      <div class="card stat"><div class="label">Panels</div><div class="value">${num(panT.panel_count, 0)}</div><div class="hint">${panT.type_count} type${panT.type_count === 1 ? "" : "s"} on the schedule</div></div>
      <div class="card stat"><div class="label">SF</div><div class="value">${num(panT.total_sf, 0)}</div><div class="hint">gross — the tab's W column · openings ${num(panT.total_opening_sf, 0)} SF come off the concrete</div></div>
      <div class="card stat"><div class="label">Concrete CY</div><div class="value">${num(panT.total_concrete_cy, 2)}</div><div class="hint">openings deducted, with waste — not rounded up</div>${moneyRow(matCost(mat, "concrete"))}</div>
      <div class="card stat"><div class="label">Steel</div><div class="value">${num(panT.total_rebar_lb, 0)}</div><div class="hint">lb · both mats, edge bars, a set more per opening, corner bars — waste on <em>every</em> bar</div>${moneyRow(matCost(mat, "rebar"))}</div>
      <div class="card stat"><div class="label">Formed edge</div><div class="value">${num(panT.total_perimeter_lf, 0)}</div><div class="hint">LF of panel edge · openings ${num(panT.total_opening_lf, 0)} LF — what the lumber and the chamfer run off</div></div>
      <div class="card stat"><div class="label">Bottom LF</div><div class="value">${num(panT.total_bottom_lf, 0)}</div><div class="hint">carton forms, the durrock retainer and the backfill run along it</div></div>
      <div class="card stat"><div class="label">Cost</div><div class="value">${usd(section.calc_total_cost ?? panT.total_cost, 0)}</div><div class="hint">direct + takeoffs + tax</div></div>
      <div class="card stat"><div class="label">Sale</div><div class="value">${usd(section.calc_total_sale ?? panT.total_sale, 0)}</div><div class="hint">cost × (1 + margin + conting)</div></div>
      <div class="card stat"><div class="label">Sale / SF</div><div class="value">${usd(section.calc_sale_per_unit ?? panT.total_sale_per_unit, 2)}</div><div class="hint">cost ${usd(section.calc_cost_per_unit ?? panT.total_cost_per_unit, 2)}/SF — the tab's I56</div></div>
      <div class="card stat"><div class="label">Sale / panel</div><div class="value">${usd(panT.sale_per_panel, 0)}</div><div class="hint">cost ${usd(panT.cost_per_panel, 0)} a panel — the tab's X column</div></div>
    </div>`
        : isBeams
        ? `<div class="grid stats">
      <div class="card stat"><div class="label">${isCont ? "Footing types" : "Beam types"}</div><div class="value">${beamT.run_count}</div><div class="hint">${num(beamT.total_length_ft, 0)} LF</div></div>
      <div class="card stat"><div class="label">Face feet</div><div class="value">${num(beamT.total_face_ff, 0)}</div><div class="hint">one face — ${num(beamT.total_contact_ff, 0)} FF of contact both faces</div></div>
      <div class="card stat"><div class="label">Concrete CY</div><div class="value">${num(beamT.total_concrete_cy, 2)}</div><div class="hint">with waste</div>${moneyRow(matCost(mat, "concrete"))}</div>
      <div class="card stat"><div class="label">Steel</div><div class="value">${num(beamT.total_rebar_lb, 0)}</div><div class="hint">lb — bars, stirrups and L bars, with waste</div>${moneyRow(matCost(mat, "rebar"))}</div>
      <div class="card stat"><div class="label">Earthwork</div><div class="value">${num(beamT.total_excavate_cy, 0)}</div><div class="hint">CY dug · ${num(beamT.total_backfill_cy, 0)} CY backfilled</div></div>
      <div class="card stat"><div class="label">Pilasters</div><div class="value">${num(beamT.pilaster_count, 0)}</div><div class="hint">${num(beamT.total_pilaster_ff, 0)} FF of pilaster face</div></div>
      <div class="card stat"><div class="label">Cost</div><div class="value">${usd(section.calc_total_cost ?? beamT.total_cost, 0)}</div><div class="hint">direct + takeoff lines + supervision + equipment</div></div>
      <div class="card stat"><div class="label">Sale</div><div class="value">${usd(section.calc_total_sale ?? beamT.total_sale, 0)}</div><div class="hint">cost × (1 + margin + contingency)</div></div>
      <div class="card stat"><div class="label">Cost / LF</div><div class="value">${usd(section.calc_cost_per_unit, 2)}</div><div class="hint">sale ${usd(section.calc_sale_per_unit, 2)} / LF</div></div>
      <div class="card stat"><div class="label">Sale / FF</div><div class="value">${usd(beamT.sale_per_ff, 2)}</div><div class="hint">cost ${usd(beamT.cost_per_ff, 2)} / FF — the sheet's C40</div></div>
    </div>`
        : isSpot
        ? `<div class="grid stats">
      <div class="card stat"><div class="label">Footings</div><div class="value">${num(wallT.footing_count, 0)}</div><div class="hint">${wallT.run_count} type${wallT.run_count === 1 ? "" : "s"} · ${num(wallT.total_length_ft, 0)} LF end to end</div></div>
      <div class="card stat"><div class="label">Footing SF</div><div class="value">${num(wallT.total_footing_sf, 0)}</div><div class="hint">plan area, what footing labor is priced on</div></div>
      <div class="card stat"><div class="label">Concrete CY</div><div class="value">${num(wallT.total_footing_concrete_cy, 2)}</div><div class="hint">with waste</div>${moneyRow(matCost(mat, "footing_concrete"))}</div>
      <div class="card stat"><div class="label">Steel</div><div class="value">${num(wallT.total_footing_rebar_lb, 0)}</div><div class="hint">lb, both mats both ways, with laps</div>${moneyRow(matCost(mat, "rebar"))}</div>
      <div class="card stat"><div class="label">Earthwork</div><div class="value">${num(wallT.total_excavate_cy, 0)}</div><div class="hint">CY dug · ${num(wallT.total_backfill_cy, 0)} CY backfilled</div></div>
      <div class="card stat"><div class="label">Weld plates</div><div class="value">${num(wallT.weld_plate_count, 0)}</div><div class="hint">one per footing that carries one</div>${moneyRow(matCost(mat, "weld_plates"))}</div>
      <div class="card stat"><div class="label">Cost</div><div class="value">${usd(section.calc_total_cost ?? wallT.total_cost, 0)}</div><div class="hint">direct + takeoff lines + supervision + equipment</div></div>
      <div class="card stat"><div class="label">Sale</div><div class="value">${usd(section.calc_total_sale ?? wallT.total_sale, 0)}</div><div class="hint">cost × (1 + margin + contingency)</div></div>
      <div class="card stat"><div class="label">Cost / footing</div><div class="value">${usd(section.calc_cost_per_unit, 0)}</div><div class="hint">sale ${usd(section.calc_sale_per_unit, 0)}</div></div>
      <div class="card stat"><div class="label">Footing / SF</div><div class="value">${usd(wallT.footing_sale_per_sf, 2)}</div><div class="hint">cost ${usd(wallT.footing_cost_per_sf, 2)} — the sheet's Z column</div></div>
    </div>`
        : isWalls
        ? `<div class="grid stats">
      <div class="card stat"><div class="label">Wall runs</div><div class="value">${wallT.run_count}</div><div class="hint">${num(wallT.total_length_ft, 0)} LF of wall</div></div>
      <div class="card stat"><div class="label">Form feet</div><div class="value">${num(wallT.total_form_ff, 0)}</div><div class="hint">one face — the sheet halves both</div></div>
      <div class="card stat"><div class="label">Footing SF</div><div class="value">${num(wallT.total_footing_sf, 0)}</div><div class="hint">plan area, what footing labor rides</div></div>
      <div class="card stat"><div class="label">Concrete CY</div><div class="value">${num(wallT.total_concrete_cy, 2)}</div><div class="hint">wall ${num(wallT.total_wall_concrete_cy, 1)} + footing ${num(wallT.total_footing_concrete_cy, 1)}</div>${moneyRow(
        [matCost(mat, "wall_concrete"), matCost(mat, "footing_concrete")]
          .filter(Boolean)
          .join(" + ")
      )}</div>
      <div class="card stat"><div class="label">Steel</div><div class="value">${num(wallT.total_rebar_lb, 0)}</div><div class="hint">lb · horz ${num(wallT.total_horiz_rebar_lb, 0)} + vert ${num(wallT.total_vert_rebar_lb, 0)} + ftg ${num(wallT.total_footing_rebar_lb, 0)}</div>${moneyRow(matCost(mat, "rebar"))}</div>
      <div class="card stat"><div class="label">Earthwork</div><div class="value">${num(wallT.total_excavate_cy, 0)}</div><div class="hint">CY dug · ${num(wallT.total_backfill_cy, 0)} backfilled · ${num(wallT.total_sand_cy, 0)} sand</div>${moneyRow(
        matCost(mat, "sand") ? matCost(mat, "sand") + " sand" : ""
      )}</div>
      <div class="card stat"><div class="label">French drain</div><div class="value">${num(wallT.total_drain_lf, 0)}</div><div class="hint">LF · material and labor both</div></div>
      <div class="card stat"><div class="label">Cost</div><div class="value">${usd(section.calc_total_cost ?? wallT.total_cost, 0)}</div><div class="hint">direct + takeoffs + tax</div></div>
      <div class="card stat"><div class="label">Sale</div><div class="value">${usd(section.calc_total_sale ?? wallT.total_sale, 0)}</div><div class="hint">cost × (1 + margin + conting)</div></div>
      <div class="card stat"><div class="label">Wall / FF</div><div class="value">${usd(wallT.wall_sale_per_ff, 2)}</div><div class="hint">cost ${usd(wallT.wall_cost_per_ff, 2)}/FF · ${usd(wallT.total_wall_sale, 0)} total</div></div>
      <div class="card stat"><div class="label">Footing / SF</div><div class="value">${usd(wallT.footing_sale_per_sf, 2)}</div><div class="hint">cost ${usd(wallT.footing_cost_per_sf, 2)}/SF · ${usd(wallT.total_footing_sale, 0)} total</div></div>
    </div>`
        : isPiers
        ? `<div class="grid stats">
      <div class="card stat"><div class="label">Piers</div><div class="value">${pierT.pier_count}</div><div class="hint">${pierT.group_count} group${pierT.group_count === 1 ? "" : "s"}</div></div>
      <div class="card stat"><div class="label">Drilled LF</div><div class="value">${num(pierT.total_lf, 0)}</div>${moneyRow(matCost(mat, "drilling"))}</div>
      <div class="card stat"><div class="label">Concrete CY</div><div class="value">${num(pierT.total_concrete_cy, 2)}</div><div class="hint">shaft ${num(pierT.total_shaft_concrete_cy, 1)}${Number(pierT.total_bell_concrete_cy) ? " + bells " + num(pierT.total_bell_concrete_cy, 1) : ""}</div>${moneyRow(matCost(mat, "concrete"))}</div>
      <div class="card stat"><div class="label">Steel</div><div class="value">${num(pierT.total_rebar_lb, 0)}</div><div class="hint">lb · vert ${num(pierT.total_vert_rebar_lb, 0)} + ties ${num(pierT.total_tie_rebar_lb, 0)} + dowels ${num(pierT.total_dowel_rebar_lb, 0)}</div>${moneyRow(matCost(mat, "rebar"))}</div>
      <div class="card stat"><div class="label">Ties</div><div class="value">${num(pierT.total_tie_count, 0)}</div><div class="hint">hoops, incl. the confinement band</div></div>
      <div class="card stat"><div class="label">Drilling</div><div class="value">${usd(pierT.total_drill_cost, 0)}</div><div class="hint">${
        pierT.drill_quote_stale
          ? `<span class="badge warn">quote is stale</span>`
          : pierT.drill_source === "quote"
          ? "quoted lump sum"
          : pierT.groups_without_drill_rate
          ? `<span class="badge warn">${pierT.groups_without_drill_rate} group(s) have no rate</span>`
          : "from the $/LF rate table, by diameter"
      }</div></div>
      <div class="card stat"><div class="label">Cost</div><div class="value">${usd(section.calc_total_cost ?? pierT.total_cost, 0)}</div><div class="hint">direct + takeoffs + tax</div></div>
      <div class="card stat"><div class="label">Sale</div><div class="value">${usd(section.calc_total_sale ?? pierT.total_sale, 0)}</div><div class="hint">cost × (1 + margin + conting)</div></div>
      <div class="card stat"><div class="label">Sale / pier</div><div class="value">${usd(section.calc_sale_per_unit ?? pierT.total_sale_per_unit, 0)}</div><div class="hint">cost ${usd(section.calc_cost_per_unit ?? pierT.total_cost_per_unit, 0)}/pier</div></div>
    </div>`
        : isDeck
        ? `<div class="grid stats">
      <div class="card stat"><div class="label">Levels</div><div class="value">${deckT.level_count}</div></div>
      <div class="card stat"><div class="label">Deck SF</div><div class="value">${num(deckT.total_sf, 0)}</div><div class="hint">what every shared cost is allocated by</div></div>
      <div class="card stat"><div class="label">Concrete CY</div><div class="value">${num(deckT.total_concrete_cy, 2)}</div><div class="hint">slab ${num(deckT.total_slab_cy, 1)} + beams ${num(deckT.total_beam_cy, 1)}</div>${moneyRow(matCost(mat, "concrete"))}</div>
      <div class="card stat"><div class="label">SF / CY</div><div class="value">${num(sfPerCy(deckT.total_sf, deckT.total_concrete_cy), 1)}</div></div>
      <div class="card stat"><div class="label">Steel</div><div class="value">${num(deckT.total_rebar_lb, 0)}</div><div class="hint">lb · ${num(deckT.total_rebar_tons, 2)} tons · mats ${num(deckT.total_slab_rebar_lb, 0)} + beams ${num(deckT.total_beam_rebar_lb, 0)}</div>${moneyRow(matCost(mat, "rebar"))}</div>
      <div class="card stat"><div class="label">PT</div><div class="value">${num(deckT.total_pt_sf, 0)}</div><div class="hint">SF with cable · ${num(deckT.total_pt_lb, 0)} lb</div>${moneyRow(matCost(mat, "pt"))}</div>
      <div class="card stat"><div class="label">Lumber driver</div><div class="value">${num(deckT.lumber_driver_lf, 0)}</div><div class="hint">LF · edge ${num(deckT.total_perm_edge_lf, 0)} + GB faces ${num(deckT.total_gb_form_ff, 0)}</div></div>
      <div class="card stat"><div class="label">Cost</div><div class="value">${usd(section.calc_total_cost ?? deckT.total_cost, 0)}</div><div class="hint">direct + takeoffs + tax</div></div>
      <div class="card stat"><div class="label">Sale</div><div class="value">${usd(section.calc_total_sale ?? deckT.total_sale, 0)}</div><div class="hint">cost × (1 + margin + conting)</div></div>
      <div class="card stat"><div class="label">Sale / SF</div><div class="value">${usd(section.calc_sale_per_unit ?? deckT.total_sale_per_unit, 2)}</div><div class="hint">cost ${usd(section.calc_cost_per_unit ?? deckT.total_cost_per_unit, 2)}/SF</div></div>
    </div>`
        : isSidewalk
        ? `<div class="grid stats">
      <div class="card stat"><div class="label">Walk types</div><div class="value">${totals.slab_count}</div></div>
      <div class="card stat"><div class="label">Total SF</div><div class="value">${num(totals.total_sf, 0)}</div><div class="hint">what the lumber, labor and cure run off</div></div>
      <div class="card stat"><div class="label">Concrete CY</div><div class="value">${num(totals.total_concrete_cy, 2)}</div><div class="hint">slab ${num(totals.total_slab_concrete_cy, 1)} + edge ${num(totals.total_edge_concrete_cy, 1)} + stairs ${num(totals.total_stair_concrete_cy, 1)}</div>${moneyRow(matCost(mat, "concrete"))}</div>
      <div class="card stat"><div class="label">Sand CY</div><div class="value">${num(totals.total_sand_cy, 2)}</div>${moneyRow(matCost(mat, "sand"))}</div>
      <div class="card stat"><div class="label">Steel</div><div class="value">${num(totals.total_rebar_lb, 0)}</div><div class="hint">lb · the mat and the edge bars</div>${moneyRow(matCost(mat, "rebar"))}</div>
      <div class="card stat"><div class="label">Finishes</div><div class="value">${num(totals.total_stamped_sf, 0)}</div><div class="hint">SF stamped · ${num(totals.total_integral_color_cy, 1)} CY colored · ${num(totals.total_acid_etch_sf, 0)} SF etched</div></div>
      <div class="card stat"><div class="label">Edge &amp; stairs</div><div class="value">${num(totals.total_thick_edge_lf, 0)}</div><div class="hint">LF of thickened edge · ${num(totals.total_stair_tread_lf, 0)} LF of stair tread</div></div>
      <div class="card stat"><div class="label">Joints</div><div class="value">${num(
        forming && forming.drivers ? forming.drivers.construction_joint_lf : 0,
        0
      )}</div><div class="hint">LF expansion · ${num(
        forming && forming.drivers ? forming.drivers.control_joint_lf : 0,
        0
      )} control</div></div>
      <div class="card stat"><div class="label">Cost</div><div class="value">${usd(section.calc_total_cost ?? totals.total_cost, 0)}</div><div class="hint">direct + takeoffs + tax</div></div>
      <div class="card stat"><div class="label">Sale</div><div class="value">${usd(section.calc_total_sale ?? totals.total_sale, 0)}</div><div class="hint">cost × (1 + margin + conting)</div></div>
      <div class="card stat"><div class="label">Sale / SF</div><div class="value">${usd(section.calc_sale_per_unit ?? totals.total_sale_per_sf, 2)}</div><div class="hint">cost ${usd(section.calc_cost_per_unit ?? totals.total_cost_per_sf, 2)}/SF</div></div>
    </div>`
        : isPaving
        ? `<div class="grid stats">
      <div class="card stat"><div class="label">Areas</div><div class="value">${totals.slab_count}</div></div>
      <div class="card stat"><div class="label">Total SF</div><div class="value">${num(totals.total_sf, 0)}</div></div>
      <div class="card stat"><div class="label">Curb LF</div><div class="value">${num(totals.total_curb_lf, 0)}</div><div class="hint">what the forming package is driven by</div></div>
      <div class="card stat"><div class="label">Concrete CY</div><div class="value">${num(totals.total_concrete_cy, 2)}</div><div class="hint">slab ${num(totals.total_slab_concrete_cy, 1)} + curb &amp; edge ${num(totals.total_edge_concrete_cy, 1)}</div>${moneyRow(matCost(mat, "concrete"))}</div>
      <div class="card stat"><div class="label">SF / CY</div><div class="value">${num(sfPerCy(totals.total_sf, totals.total_concrete_cy), 1)}</div></div>
      <div class="card stat"><div class="label">Sand CY</div><div class="value">${num(totals.total_sand_cy, 2)}</div>${moneyRow(matCost(mat, "sand"))}</div>
      <div class="card stat"><div class="label">Steel</div><div class="value">${num(totals.total_rebar_lb, 0)}</div><div class="hint">lb · mat only, no support steel</div>${moneyRow(matCost(mat, "rebar"))}</div>
      <div class="card stat"><div class="label">Joints</div><div class="value">${num(
        forming && forming.drivers ? forming.drivers.construction_joint_lf : 0,
        0
      )}</div><div class="hint">LF construction · ${num(
        forming && forming.drivers ? forming.drivers.control_joint_lf : 0,
        0
      )} control</div></div>
      <div class="card stat"><div class="label">Demo LF</div><div class="value">${num(totals.total_demo_lf, 0)}</div><div class="hint">slip formed ${num(totals.total_slip_form_sf, 0)} SF</div></div>
      <div class="card stat"><div class="label">Cost</div><div class="value">${usd(section.calc_total_cost ?? totals.total_cost, 0)}</div><div class="hint">direct + takeoffs + tax</div></div>
      <div class="card stat"><div class="label">Sale</div><div class="value">${usd(section.calc_total_sale ?? totals.total_sale, 0)}</div><div class="hint">cost × (1 + margin + conting)</div></div>
      <div class="card stat"><div class="label">Sale / SF</div><div class="value">${usd(section.calc_sale_per_unit ?? totals.total_sale_per_sf, 2)}</div><div class="hint">cost ${usd(section.calc_cost_per_unit ?? totals.total_cost_per_sf, 2)}/SF</div></div>
    </div>`
        : `<div class="grid stats">
      <div class="card stat"><div class="label">Pours</div><div class="value">${totals.slab_count}</div>${
        Number(totals.total_qty) !== Number(totals.slab_count)
          ? `<div class="hint">${totals.total_qty} buildings — garden style</div>`
          : ""
      }</div>
      <div class="card stat"><div class="label">Total SF</div><div class="value">${num(totals.total_sf, 0)}</div></div>
      <div class="card stat"><div class="label">Concrete CY</div><div class="value">${num(totals.total_concrete_cy, 2)}</div><div class="hint">slab ${num(totals.total_slab_concrete_cy, 1)} + beams ${num(totals.total_gb_concrete_cy, 1)} (GB+Exp+Drop)</div>${moneyRow(matCost(mat, "concrete"))}</div>
      <div class="card stat"><div class="label">SF / CY</div><div class="value">${num(sfPerCy(totals.total_sf, totals.total_concrete_cy), 1)}</div><div class="hint">total SF ÷ CY (slab + beams)</div></div>
      <div class="card stat"><div class="label">Sand CY</div><div class="value">${num(totals.total_sand_cy, 2)}</div>${moneyRow(matCost(mat, "sand"))}</div>
      <div class="card stat"><div class="label">Slab mat</div><div class="value">${num(totals.total_slab_bar_lb, 0)}</div><div class="hint">lb · ${num(totals.total_slab_bar_lf, 0)} LF each way</div>${moneyRow(
        matAt(mat, "rebar", totals.total_slab_bar_lb)
      )}</div>
      <div class="card stat"><div class="label">Support rebar</div><div class="value">${num(totals.total_support_rebar_lb, 0)}</div><div class="hint">lb · chairs/dowels only</div>${moneyRow(
        matAt(mat, "rebar", totals.total_support_rebar_lb)
      )}</div>
      <div class="card stat"><div class="label">PT cable LF</div><div class="value">${num(totals.total_pt_cable_lf, 0)}</div><div class="hint">slab + GB PT</div></div>
      <div class="card stat"><div class="label">PT weight</div><div class="value">${num(totals.total_pt_cable_lb, 0)}</div><div class="hint">lb (rate method)</div>${moneyRow(
        matCost(mat, "pt")
      )}</div>
      <div class="card stat"><div class="label">Total rebar</div><div class="value">${num(totals.total_rebar_lb, 0)}</div><div class="hint">lb · ${num(Number(totals.total_rebar_lb) / 2000, 2)} tons (mat + support + beams)</div>${moneyRow(matCost(mat, "rebar"))}</div>
      <div class="card stat"><div class="label">Poly / Stego</div><div class="value">${num(totals.total_poly_sf, 0)}</div><div class="hint">SF · pour ${num(totals.total_poly_slab_sf, 0)} + beams ${num(totals.total_poly_gb_sf, 0)} + waste</div>${moneyRow(
        [matCost(mat, "poly"), matCost(mat, "tape") ? matCost(mat, "tape") + " tape" : ""]
          .filter(Boolean)
          .join(" + ")
      )}</div>
      <div class="card stat"><div class="label">Cost</div><div class="value">${usd(section.calc_total_cost ?? totals.total_cost, 0)}</div><div class="hint">direct + takeoffs + tax</div></div>
      <div class="card stat"><div class="label">Sale</div><div class="value">${usd(section.calc_total_sale ?? totals.total_sale, 0)}</div><div class="hint">cost × (1 + margin + conting)</div></div>
      <div class="card stat"><div class="label">Sale / SF</div><div class="value">${usd(section.calc_sale_per_unit ?? totals.total_sale_per_sf, 2)}</div><div class="hint">cost ${usd(section.calc_cost_per_unit ?? totals.total_cost_per_sf, 2)}/SF</div></div>
    </div>`
    }

    ${quoteCardsHtml(section)}

    ${
      isDeck
        ? gridCardHtml({
            id: "deck-levels",
            title: "Deck levels",
            blurb:
              "One row is a <strong>level</strong> — an area, a thickness, two " +
              "mats of bar, a permanent edge, and the grade beams running " +
              "through it. The workbook gives every level two rows and sums " +
              "across the pair; there is one row per level here. " +
              "<strong>GB FF</strong> is beam contact area on <em>both</em> " +
              "faces, and it does two jobs: it prices the GB forming labor and, " +
              "together with the edge, it drives <em>every lumber line</em> on " +
              "this section — so a wider beam moves the plywood. " +
              "<strong>PT</strong> is per level, not per deck: a level with the " +
              "box unticked is not post-tensioned area and a lump PT quote will " +
              "not land on it. Supervision here is <strong>typed</strong>, like " +
              "piers and walls, and the whole rental ladder — the crane " +
              "included — rides those days.",
            columns: deckColumns(state.mixes),
            rows: deckRows,
            addLabel: "Level",
            saveLabel: "Save levels",
          })
        : isColumns
        ? gridCardHtml({
            id: "column-types",
            title: "Column types",
            blurb:
              "One row is a <strong>column type and how many of it</strong> — the " +
              "schedule, not a location. <strong>Form SF</strong> is the " +
              "<strong>formed perimeter</strong> / 12 × height: real contact " +
              "area, and the basis every shared cost on this section is " +
              "allocated by. <strong>Faces</strong> is what makes a pilaster a " +
              "pilaster — a column is wrapped <code>(L + W) × 2</code>, a " +
              "pilaster on a wall is <code>L + W × 2</code>, and one poured " +
              "monolithic with it is <code>W × 2</code>. Enter <strong>L along " +
              "the wall</strong>; the face you drop is always an L face. Three " +
              "vertical sets are available because the schedule carries three; a " +
              "set with no count or no size contributes nothing rather than a " +
              "zero-weight bar. Rebar waste applies to <em>every</em> bar here, " +
              "including the verticals. Supervision is driven by the total column " +
              "COUNT, so changing a quantity on one row reprices every other row.",
            columns: columnColumns(state.mixes),
            rows: colRows,
            addLabel: "Column type",
            saveLabel: "Save column types",
          })
        : isMisc
        ? MISC_FAMILIES.map((fam) =>
            gridCardHtml({
              id: `misc-${fam.shape}`,
              title: fam.title,
              blurb: fam.blurb,
              columns: miscColumns(fam, state.mixes),
              rows: (() => {
                const rs = miscRows.filter((r) => r.shape === fam.shape);
                return rs.length ? rs : [fam.blank];
              })(),
              addLabel: fam.addLabel,
              saveLabel: `Save ${fam.short}`,
            })
          ).join("")
        : isPanels
        ? gridCardHtml({
            id: "panel-types",
            title: "Panel types",
            blurb:
              "One line per tilt-wall panel type: <strong>how many</strong>, the length, thickness " +
              "and top and bottom elevations, up to <strong>four openings</strong> as L × W, the " +
              "<strong>horizontal and vertical mats</strong> as a spacing, a size and how many mats, " +
              "and the <strong>edge and corner bars</strong> as a count and a size. Each opening comes " +
              "off the concrete, adds one more set of the edge bars and puts its perimeter on the " +
              "lumber and the chamfer. <strong>SF is gross</strong>, the tab's W column — the labor is " +
              "priced on it and every shared cost here is spread by it. Supervision days are " +
              "<strong>entered</strong>, and the equipment ladder rides them.",
            columns: panelColumns(state.mixes),
            rows: panRows,
            addLabel: "Panel type",
            saveLabel: "Save panel types",
          })
        : isBeams
        ? gridCardHtml({
            id: "beam-runs",
            title: isCont ? "Continuous footings" : "Grade beams",
            blurb:
              (isCont
                ? "One line per footing type — the same row as a separately poured beam, on its own kind. "
                : "One line per beam type: the <strong>separately poured</strong> beam, formed on both faces " +
                  "and poured before the slab. A monolithic beam belongs on the mono slab's schedule, not here. ") +
              "<strong>Length</strong>, width and height of the type; <strong>top and bottom bars</strong> as a " +
              "count and a size; <strong>mid bars</strong> per side; <strong>stirrups</strong> as a size at a " +
              "spacing; <strong>L bars</strong> as a size at a spacing along the beam, each of a length; " +
              "<strong>pilasters</strong> as a count of L\" × W\" blocks. <strong>Face FF</strong> is one face, " +
              "the convention every $/FF rate here is priced against; the section sells per <strong>LF</strong>.",
            columns: beamColumns(state.mixes),
            rows: beamRows,
            addLabel: isCont ? "Footing type" : "Beam type",
            saveLabel: isCont ? "Save footings" : "Save beams",
          })
        : isSpot
        ? gridCardHtml({
            id: "spot-footings",
            title: "Spot footings",
            blurb:
              "One line per footing type: <strong>how many</strong>, and the length and " +
              "width of each in feet, the thickness in inches. The workbook's 06-Footings tab is the walls " +
              "tab with the wall left blank, and so is this: every footing formula, rate " +
              "and lumber line is the walls section's. The <strong>bottom and top mats</strong> " +
              "are each their own bar set running both ways. <strong>Weld plate</strong> puts " +
              "one plate per footing on the material list, priced from the catalog — " +
              "unpriced, not free, until the catalog has a price for it. " +
              "<strong>Backfill</strong> turns on excavation swell.",
            columns: spotFootingColumns(state.mixes),
            rows: wallRows,
            addLabel: "Footing type",
            saveLabel: "Save footings",
          })
        : isWalls
        ? gridCardHtml({
            id: "wall-runs",
            title: "Wall runs",
            blurb:
              "Each wall type is <strong>two lines</strong>: the wall, and the " +
              "<strong>footing under it</strong> on the line below — they share a " +
              "length, and the footing's width drives the trench the wall sits in. " +
              "<strong>Faces</strong> is how many curtains of wall steel: 2 is both " +
              "faces. The footing's <strong>bottom and top mats</strong> are each their " +
              "own bar set running both directions — leave the top blank on a one-mat " +
              "footing. <strong>Form ft</strong> " +
              "is contact area on <em>one</em> face, which is the convention every " +
              "$/FF rate here is priced against. <strong>Backfill</strong> turns on " +
              "sand, excavation swell and the french drain — leave it off for an " +
              "interior wall. The wall and the footing are costed " +
              "<strong>separately</strong>, each on its own driver — the wall per form " +
              "foot, the footing per SF of plan area — so a bad schedule shows up in " +
              "one rate and not the other. They always sum to the type.",
            columns: wallColumns(state.mixes, section),
            rows: wallRows,
            addLabel: "Wall type",
            saveLabel: "Save wall runs",
          })
        : isPiers
        ? gridCardHtml({
            id: "pier-groups",
            title: "Pier groups",
            blurb:
              "One row is a <strong>group of identical piers</strong>, not one pier — " +
              "enter how many and the schedule they share. Depth is base + rock. " +
              "<strong>Band n / sp</strong> is the confinement at the top, as the " +
              "drawing calls it out: a count at a spacing, e.g. 3 #3 at 3\". " +
              "Verticals are cut to length, so there is no lap to carry.",
            columns: pierColumns(state.mixes),
            rows: pierRows,
            addLabel: "Group",
            saveLabel: "Save groups",
          })
        : isSidewalk
        ? gridCardHtml({
            id: "paving-areas",
            title: "Sidewalk types",
            blurb:
              "One line per walk type, the way the SIDEWALKS tab is laid out. The " +
              "lumber, the labor and the cure run off <strong>SF</strong>; the " +
              "<strong>thick edge</strong> adds LF × 1.8 × 0.18 / 27 CY, two #3 bars and " +
              "$/LF of labor; <strong>stairs</strong> add LF × rise × (run + 12) / 3888 CY " +
              "and $/LF; the three <strong>finish</strong> flags put stamped SF, colored " +
              "CY and etched SF on the contract lines. <strong>Supervision derives from " +
              "concrete</strong>: CY ÷ 10 × 1.5 + 5 days.",
            columns: sidewalkColumns(state.mixes),
            rows: slabs,
            addLabel: "Walk type",
            saveLabel: "Save walks",
          })
        : isPaving
        ? gridCardHtml({
            id: "paving-areas",
            title: "Paving areas",
            blurb:
              "Type down a column and press <strong>Save areas</strong> once. Curb LF " +
              "is the important one — paving forms off the curb, not off a perimeter, " +
              "so every lumber line in the package below is driven by that column. " +
              "Concrete picks up <code>curb / 108</code> and " +
              "<code>thick edge × 1.5 × 0.18 / 27</code> on top of " +
              "<code>SF × thk / 324</code>.",
            columns: pavingColumns(state.mixes),
            rows: slabs,
            addLabel: "Area",
            saveLabel: "Save areas",
          })
        : `
    <div class="card">
      <h3 style="margin:0 0 0.75rem">Mono slab pours</h3>
      ${
        slabs.length
          ? `<div class="table-wrap"><table class="data">
        <thead>
          <tr>
            <th>Description</th>
            <th title="Garden style: buildings of this type — the whole row is multiplied">Qty</th>
            <th>SF</th>
            <th>Thk"</th>
            <th>PT</th>
            <th>Mix</th>
            <th>Sand"</th>
            <th>CY total</th>
            <th>SF/CY</th>
            <th>PT LF</th>
            <th>Slab mat</th>
            <th>Total rebar</th>
            <th>Poly SF</th>
            <th>Cost</th>
            <th>Sale</th>
            <th>Cost/SF</th>
            <th>Sale/SF</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          ${slabs
            .map((s) => {
              const bb = s.beam_breakdown || {};
              const g = bb.grade_beam || {};
              const e = bb.exposed || {};
              const d = bb.drop || {};
              // Garden style (sql/079): the row's figures are qty buildings'
              // worth, so the ratios read against the row's SF, not one building's.
              const rowQty = s.qty == null ? 1 : Number(s.qty);
              const rowSf = Number(s.square_footage) * rowQty;
              const pourSfPerCy = s.calc_sf_per_cy != null
                ? Number(s.calc_sf_per_cy)
                : sfPerCy(rowSf, s.calc_concrete_cy);
              const slabOnlySfPerCy = sfPerCy(rowSf, s.calc_slab_concrete_cy);
              const costTitle =
                `direct ${usd(s.calc_direct_cost, 0)}` +
                ` + allocated ${usd(s.calc_allocated_cost, 0)}` +
                ` = ${usd(s.calc_cost, 0)}`;
              const cyTitle =
                `slab ${num(s.calc_slab_concrete_cy, 2)}` +
                ` + GB ${num(g.concrete_cy, 2)}` +
                ` + Exp ${num(e.concrete_cy, 2)}` +
                ` + Drop ${num(d.concrete_cy, 2)}` +
                ` = beams ${num(s.calc_gb_concrete_cy, 2)}`;
              const sfCyTitle =
                `SF ${num(rowSf, 0)} ÷ total CY ${num(s.calc_concrete_cy, 2)}` +
                ` = ${num(pourSfPerCy, 1)} SF/CY` +
                (slabOnlySfPerCy != null
                  ? ` · slab only ${num(slabOnlySfPerCy, 1)} SF/CY`
                  : "");
              const matTitle = s.slab_bar_size
                ? `#${s.slab_bar_size} @ ${num(s.slab_bar_spacing_in, 1)}" each way` +
                  ` · 2 × ${num(s.square_footage, 0)} SF × 12 / ${num(s.slab_bar_spacing_in, 1)}` +
                  (rowQty !== 1 ? ` × ${rowQty}` : "") +
                  ` = ${num(s.calc_slab_bar_lf, 0)} LF → ${num(s.calc_slab_bar_lb, 0)} lb (incl. lap)`
                : "No slab mat — enter bar size + spacing on this pour";
              const rebarTitle =
                `mat ${num(s.calc_slab_bar_lb, 0)}` +
                ` + support ${num(s.calc_support_rebar_lb, 0)}` +
                ` + GB ${num(g.rebar_lb, 0)}` +
                ` + Exp ${num(e.rebar_lb, 0)}` +
                ` + Drop ${num(d.rebar_lb, 0)}` +
                ` = beams ${num(s.calc_grade_beam_rebar_lb, 0)}`;
              const polyTitle =
                `pour ${num(s.calc_poly_slab_sf, 0)}` +
                ` + GB wrap ${num(g.poly_sf, 0)}` +
                ` + Exp ${num(e.poly_sf, 0)}` +
                ` + Drop ${num(d.poly_sf, 0)}` +
                ` = beams ${num(s.calc_poly_gb_sf, 0)}` +
                ` → total w/ waste ${num(s.calc_poly_sf, 0)}` +
                ` · wrap = ((2×H″)/12)×L`;
              const kindHint = [
                Number(e.count) ? `Exp ${e.count}` : "",
                Number(d.count) ? `Drop ${d.count}` : "",
                Number(g.count) ? `GB ${g.count}` : "",
              ]
                .filter(Boolean)
                .join(" · ");
              return `<tr>
              <td>
                <strong>${esc(s.description || "Pour")}</strong>
                ${s.location ? `<div class="muted">${esc(s.location)}</div>` : ""}
                ${
                  s.post_tension && s.pt_spacing_in
                    ? `<div class="muted">PT @ ${num(s.pt_spacing_in, 1)}" o.c.</div>`
                    : ""
                }
                ${kindHint ? `<div class="muted">${esc(kindHint)}</div>` : ""}
              </td>
              <td class="num" title="Garden style: buildings of this type">${
                rowQty === 1 ? `<span class="muted">1</span>` : `<strong>× ${rowQty}</strong>`
              }</td>
              <td class="num">${num(s.square_footage, 1)}${
                rowQty !== 1 ? `<div class="muted">= ${num(rowSf, 0)}</div>` : ""
              }</td>
              <td class="num">${num(s.thickness_in, 2)}</td>
              <td>${s.post_tension ? '<span class="badge accent">PT</span>' : "—"}</td>
              <td class="muted">${esc(s.mix_design_code || s.mix_design_name || "—")}</td>
              <td class="num">${s.sand_thickness_in != null ? num(s.sand_thickness_in, 2) : "—"}</td>
              <td class="num" title="${esc(cyTitle)}"><strong>${num(s.calc_concrete_cy, 2)}</strong></td>
              <td class="num" title="${esc(sfCyTitle)}">${num(pourSfPerCy, 1)}</td>
              <td class="num" title="slab ${num(s.calc_pt_slab_lf, 0)} + GB PT ${num(s.calc_pt_gb_lf, 0)} LF">${num(s.calc_pt_cable_lf, 0)}</td>
              <td class="num" title="${esc(matTitle)}">
                ${s.slab_bar_size
                  ? `${num(s.calc_slab_bar_lb, 0)}<div class="muted">#${s.slab_bar_size} @ ${num(s.slab_bar_spacing_in, 1)}"</div>`
                  : "—"}
              </td>
              <td class="num" title="${esc(rebarTitle)}">${num(s.calc_total_rebar_lb, 0)}</td>
              <td class="num" title="${esc(polyTitle)}">${num(s.calc_poly_sf, 0)}</td>
              <td class="num" title="${esc(costTitle)}"><strong>${usd(s.calc_cost, 0)}</strong></td>
              <td class="num">${usd(s.calc_sale, 0)}</td>
              <td class="num">${usd(s.calc_cost_per_sf, 2)}</td>
              <td class="num">${usd(s.calc_sale_per_sf, 2)}</td>
              <td style="white-space:nowrap">
                <button type="button" class="btn ghost btn-edit-slab" data-id="${esc(s.id)}">Edit</button>
                <button type="button" class="btn primary ghost btn-gb" data-id="${esc(s.id)}" data-kind="grade_beam" title="Grade beams — concrete & rebar into pour">GBs</button>
                <button type="button" class="btn ghost btn-gb" data-id="${esc(s.id)}" data-kind="exposed" title="Exposed GBs — same CY/rebar into pour (+ forming/labor later)">Exp</button>
                <button type="button" class="btn ghost btn-gb" data-id="${esc(s.id)}" data-kind="drop" title="Drops — same CY/rebar into pour (+ forming/labor later)">Drops</button>
                <button type="button" class="btn danger ghost btn-del-slab" data-id="${esc(s.id)}">Del</button>
              </td>
            </tr>`;
            })
            .join("")}
        </tbody>
      </table></div>`
          : `<div class="empty">No mono slabs yet. Add a pour to calculate CY and rebar.</div>`
      }
      <p style="color:var(--text-muted);font-size:0.82rem;margin:0.85rem 0 0">
        Calcs: concrete/sand CY with waste. <strong>Qty</strong> multiplies the whole row —
        garden style, one row per building type. <strong>Slab mat</strong> =
        <code>2 × SF × 12 / spacing</code> LF each way × lb/ft × (1+waste_rebar for laps);
        support rebar is chairs/dowels only at lb/SF.
        <strong>Poly/Stego SF</strong> = pour SF + beam wrap
        <code>((2×H″) / 12) × L</code> (two sides only) for GBs, Exp, and Drops, × (1+waste_poly default 10%).
        Hover Poly / CY / mat / rebar for breakdown.
      </p>
    </div>`}

    ${isGrid ? "" : renderBeamTypesCard(beamTypes)}
    ${isMisc ? "" : renderFormingCard(forming)}
    ${isDeck || isBeams || isPanels ? renderRentalsCard(forming, isBeams || isPanels ? "Form rental" : null) : ""}
    ${isMisc ? "" : renderLaborCard(labor)}
    ${isMisc ? "" : renderEquipmentCard(equip)}
    ${isMisc ? "" : renderSectionRatesCard(rates)}
  `;

  // Up from a section is the job, not the project — the job is where the other
  // sections are.
  $("#back-estimate").onclick = () =>
    setRoute("estimate", { estimateId: estimate.id });
  const btnAddSlab = $("#btn-add-slab");
  if (btnAddSlab) btnAddSlab.onclick = () => openMonoSlabModal(section);

  if (isGrid) {
    if (isDeck) {
      // `area_sf` alone is what the bulk endpoint requires — everything on
      // this assembly is square feet — but a level with an area and no
      // thickness has no concrete, so both are asked for here before
      // anything is sent.
      wireGrid(root, {
        id: "deck-levels",
        columns: deckColumns(state.mixes),
        required: ["area_sf", "thickness_in"],
        save: (rows) => Api.bulkSaveDeckLevels(section.id, rows),
        remove: (id) => Api.deleteDeckLevel(id),
      });
    } else if (isColumns) {
      // `height_ft` alone is what the bulk endpoint requires of a new row — a
      // column with no height is not a column — but a row with a height and no
      // quantity is a schedule entry nobody is building, so both are asked for
      // here before anything is sent.
      wireGrid(root, {
        id: "column-types",
        columns: columnColumns(state.mixes),
        required: ["qty", "height_ft"],
        save: (rows) => Api.bulkSaveColumnTypes(section.id, rows),
        remove: (id) => Api.deleteColumnType(id),
      });
    } else if (isMisc) {
      // One grid a family, each saving its own rows; the bulk route leaves the
      // rows it was not sent alone, so the other three families keep theirs.
      for (const fam of MISC_FAMILIES) {
        wireGrid(root, {
          id: `misc-${fam.shape}`,
          columns: miscColumns(fam, state.mixes),
          required: ["qty", "unit_sale"],
          blank: fam.blank,
          save: (rows) =>
            Api.bulkSaveMiscItems(section.id, rows.map((r) => ({ shape: fam.shape, ...r }))),
          remove: (id) => Api.deleteMiscItem(id),
        });
      }
    } else if (isPanels) {
      wireGrid(root, {
        id: "panel-types",
        columns: panelColumns(state.mixes),
        required: ["qty", "length_ft", "thickness_in"],
        save: (rows) => Api.bulkSavePanelTypes(section.id, rows),
        remove: (id) => Api.deletePanelType(id),
      });
    } else if (isBeams) {
      wireGrid(root, {
        id: "beam-runs",
        columns: beamColumns(state.mixes),
        required: ["length_ft", "width_in", "height_in"],
        save: (rows) => Api.bulkSaveBeamRuns(section.id, rows),
        remove: (id) => Api.deleteBeamRun(id),
      });
    } else if (isSpot) {
      wireGrid(root, {
        id: "spot-footings",
        columns: spotFootingColumns(state.mixes),
        required: ["footing_count", "footing_each_ft", "ftg_width_in", "ftg_thick_in"],
        save: (rows) => Api.bulkSaveWallRuns(section.id, rows),
        remove: (id) => Api.deleteWallRun(id),
      });
    } else if (isWalls) {
      wireGrid(root, {
        id: "wall-runs",
        columns: wallColumns(state.mixes, section),
        required: ["length_ft", "wall_height_in"],
        save: (rows) => Api.bulkSaveWallRuns(section.id, rows),
        remove: (id) => Api.deleteWallRun(id),
      });
    } else if (isPiers) {
      wireGrid(root, {
        id: "pier-groups",
        columns: pierColumns(state.mixes),
        required: ["qty", "diameter_in"],
        save: (rows) => Api.bulkSavePierGroups(section.id, rows),
        remove: (id) => Api.deletePierGroup(id),
      });
    } else if (isSidewalk) {
      wireGrid(root, {
        id: "paving-areas",
        columns: sidewalkColumns(state.mixes),
        required: ["square_footage", "thickness_in"],
        save: (rows) => Api.bulkSaveMonoSlabs(section.id, rows),
        remove: (id) => Api.deleteMonoSlab(id),
      });
    } else {
      wireGrid(root, {
        id: "paving-areas",
        columns: pavingColumns(state.mixes),
        required: ["square_footage", "thickness_in"],
        save: (rows) => Api.bulkSaveMonoSlabs(section.id, rows),
        remove: (id) => Api.deleteMonoSlab(id),
      });
    }
    const jumpAreas = $("#btn-jump-areas");
    if (jumpAreas) {
      jumpAreas.onclick = () => {
        const el = document.getElementById(
          isPiers
            ? "pier-groups"
            : isWalls
            ? "wall-runs"
            : isColumns
            ? "column-types"
            : isPanels
            ? "panel-types"
            : isMisc
            ? "misc-round"
            : isDeck
            ? "deck-levels"
            : "paving-areas"
        );
        if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
      };
    }
  }

  const jumpBeams = $("#btn-jump-beams");
  if (jumpBeams) {
    jumpBeams.onclick = () => {
      const el = document.getElementById("beam-schedule");
      if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
    };
  }
  const btnAddType = $("#btn-add-beam-type");
  if (btnAddType) btnAddType.onclick = () => openBeamTypeModal(section);
  $$(".btn-edit-type", root).forEach((btn) => {
    btn.onclick = () => {
      const t = (beamTypes || []).find((x) => x.id === btn.dataset.id);
      if (t) openBeamTypeModal(section, t);
    };
  });
  $$(".btn-del-type", root).forEach((btn) => {
    btn.onclick = async () => {
      const pours = Number(btn.dataset.pours) || 0;
      const msg = pours
        ? `Delete “${btn.dataset.label}”?\n\nIt is used by ${pours} pour(s). ` +
          `Deleting removes it from all of them.`
        : `Delete “${btn.dataset.label}”?`;
      if (!confirm(msg)) return;
      try {
        await Api.deleteBeamType(btn.dataset.id, pours > 0);
        toast("Beam type deleted");
        render();
      } catch (err) {
        toast(err.message, "err");
      }
    };
  });
  const jumpForming = $("#btn-jump-forming");
  if (jumpForming) {
    jumpForming.onclick = () => {
      const el = document.getElementById("forming-materials");
      if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
    };
  }
  const jumpRentals = $("#btn-jump-rentals");
  if (jumpRentals) {
    jumpRentals.onclick = () => {
      const el = document.getElementById("form-rentals");
      if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
    };
  }
  const jumpLabor = $("#btn-jump-labor");
  if (jumpLabor) {
    jumpLabor.onclick = () => {
      const el = document.getElementById("labor-supervision");
      if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
    };
  }
  const jumpEquip = $("#btn-jump-equip");
  if (jumpEquip) {
    jumpEquip.onclick = () => {
      const el = document.getElementById("estimate-equipment");
      if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
    };
  }
  // Include / exclude one lumber line (sql/056). Same gesture as the labor and
  // equipment cards, and the answer to a warning the estimator could not
  // previously reply to. Reverts the box on failure so the screen never claims
  // a decision the server did not take.
  $$(".forming-enabled").forEach((cb) => {
    cb.onchange = async () => {
      const code = cb.dataset.code;
      if (!code) return;
      try {
        await Api.toggleFormingLine(section.id, code, cb.checked);
        render();
      } catch (err) {
        toast(err.message, "err");
        cb.checked = !cb.checked;
      }
    };
  });
  const btnRefreshForming = $("#btn-refresh-forming");
  if (btnRefreshForming) {
    btnRefreshForming.onclick = async () => {
      btnRefreshForming.disabled = true;
      try {
        await Api.refreshFormingMaterials(section.id);
        toast("Forming materials refreshed from pours");
        render();
      } catch (err) {
        toast(err.message, "err");
        btnRefreshForming.disabled = false;
      }
    };
  }
  const btnApplyFormPct = $("#btn-apply-form-percent");
  if (btnApplyFormPct) {
    btnApplyFormPct.onclick = async () => {
      const inp = $("#form-percent-input");
      const pct = Number(inp && inp.value);
      if (Number.isNaN(pct) || pct < 0 || pct > 200) {
        toast("Enter form % between 0 and 200", "err");
        return;
      }
      const form_percent = pct / 100; // UI shows 50 → store 0.50
      btnApplyFormPct.disabled = true;
      try {
        await Api.setFormPercent(section.id, form_percent);
        toast(`Form % set to ${pct}% — 2×4/2×6/2×10/ply/masonite updated`);
        render();
      } catch (err) {
        toast(err.message, "err");
        btnApplyFormPct.disabled = false;
      }
    };
  }
  const btnRefreshLabor = $("#btn-refresh-labor");
  if (btnRefreshLabor) {
    btnRefreshLabor.onclick = async () => {
      btnRefreshLabor.disabled = true;
      try {
        await Api.refreshLabor(section.id);
        toast("Labor & supervision refreshed from pours");
        render();
      } catch (err) {
        toast(err.message, "err");
        btnRefreshLabor.disabled = false;
      }
    };
  }
  $$(".labor-save").forEach((btn) => {
    btn.onclick = async () => {
      const code = btn.dataset.code;
      const tr = btn.closest("tr");
      if (!tr || !code) return;
      const enabled = tr.querySelector(".labor-enabled")?.checked ?? true;
      const rateEl = tr.querySelector(".labor-rate");
      const qtyEl = tr.querySelector(".labor-qty");
      // Saving is an explicit override: mark manual so a later refresh does
      // not reset what was typed here. Only what CHANGED is sent (sql/058).
      // This handler used to send the rate box back on every save, touched or
      // not, and a sent rate is a typed rate: typing the superintendent's days
      // on piers, walls or a deck froze the day rate beside them, and a later
      // company or price-sheet change never reached the line.
      // Slab labor qty still comes from pours; supervision qty is editable.
      const changed = (el) =>
        !!el && el.dataset.orig !== undefined && Number(el.value) !== Number(el.dataset.orig);
      const body = { enabled, mark_manual: true };
      if (changed(rateEl)) {
        const rate = Number(rateEl.value);
        if (Number.isNaN(rate) || rate < 0) {
          toast("Rate must be ≥ 0", "err");
          return;
        }
        body.rate = rate;
      }
      if (changed(qtyEl)) {
        const qty = Number(qtyEl.value);
        if (Number.isNaN(qty) || qty < 0) {
          toast("Qty must be ≥ 0", "err");
          return;
        }
        body.qty = qty;
      }
      btn.disabled = true;
      try {
        await Api.patchLaborLine(section.id, code, body);
        toast(`Saved ${code}`);
        render();
      } catch (err) {
        toast(err.message, "err");
        btn.disabled = false;
      }
    };
  });
  $$(".labor-enabled").forEach((cb) => {
    cb.onchange = async () => {
      const code = cb.dataset.code;
      if (!code) return;
      try {
        // null leaves the pins alone. `false` HANDS THE LINE BACK — it is the
        // API's "undo my override" — and this checkbox sent it until
        // 2026-09-04, so unticking a typed superintendent un-pinned the days.
        await Api.patchLaborLine(section.id, code, {
          enabled: cb.checked,
          mark_manual: null,
        });
        render();
      } catch (err) {
        toast(err.message, "err");
        cb.checked = !cb.checked;
      }
    };
  });
  // The footing's mix is one per section (sql/040 — the sheet's R8); the
  // wall's is per row. Until 2026-09-05 the field existed on the API and
  // nowhere on the screen — Chad: "there is a field to chose mix designs for
  // walls but not for the footing." The PATCH re-costs the section's runs on
  // the spot (it is a costing field on the router), so the page re-renders.
  const selFtgMix = $("#sec-footing-mix");
  if (selFtgMix) {
    selFtgMix.onchange = async () => {
      const v = selFtgMix.value;
      try {
        await Api.updateSection(section.id, {
          footing_mix_design_id: v === "" ? null : Number(v),
        });
        toast(
          v === ""
            ? "Footings follow each wall's mix again — repriced"
            : `Footing mix set to ${selFtgMix.selectedOptions[0]?.textContent || v} — footings repriced`
        );
        render();
      } catch (err) {
        toast(err.message, "err");
      }
    };
  }
  // One switch per section (sql/052). The PATCH rebuilds the labor lines —
  // the flag lives on the line, not just the section, so the sub's sheet can
  // be built from the stored takeoff rather than re-derived.
  const cbSub = $("#labor-subcontracted");
  if (cbSub) {
    cbSub.onchange = async () => {
      try {
        await Api.updateSection(section.id, { labor_subcontracted: cbSub.checked });
        toast(
          cbSub.checked
            ? "Field labor is subcontracted — supervision stays ours"
            : "Field labor is back on our crew"
        );
        render();
      } catch (err) {
        toast(err.message, "err");
        cbSub.checked = !cbSub.checked;
      }
    };
  }

  if (rates && !isMisc) wireSectionRates(root, section);

  const btnRefreshEquip = $("#btn-refresh-equip");
  if (btnRefreshEquip) {
    btnRefreshEquip.onclick = async () => {
      btnRefreshEquip.disabled = true;
      try {
        await Api.refreshEstimateEquipment(section.id);
        toast("Equipment refreshed from super days / pour CY");
        render();
      } catch (err) {
        toast(err.message, "err");
        btnRefreshEquip.disabled = false;
      }
    };
  }
  $$(".equip-save").forEach((btn) => {
    btn.onclick = async () => {
      const code = btn.dataset.code;
      const tr = btn.closest("tr");
      if (!tr || !code) return;
      const enabled = tr.querySelector(".equip-enabled")?.checked ?? true;
      const rateEl = tr.querySelector(".equip-rate");
      const daysEl = tr.querySelector(".equip-days");
      // Only what CHANGED is sent (sql/058) — same reason as the labor card:
      // a sent rate is a typed rate, and giving a machine days must not
      // freeze its day rate against the price sheet.
      const changed = (el) =>
        !!el && el.dataset.orig !== undefined && Number(el.value) !== Number(el.dataset.orig);
      const body = { enabled, mark_manual: true };
      if (changed(rateEl)) body.rate = Number(rateEl.value);
      if (changed(daysEl)) body.days_qty = Number(daysEl.value);
      if (
        (body.rate !== undefined && (Number.isNaN(body.rate) || body.rate < 0)) ||
        (body.days_qty !== undefined && (Number.isNaN(body.days_qty) || body.days_qty < 0))
      ) {
        toast("Rate and days/qty must be ≥ 0", "err");
        return;
      }
      btn.disabled = true;
      try {
        await Api.patchEstimateEquipmentLine(section.id, code, body);
        toast(`Saved ${code}`);
        render();
      } catch (err) {
        toast(err.message, "err");
        btn.disabled = false;
      }
    };
  });
  $$(".equip-enabled").forEach((cb) => {
    cb.onchange = async () => {
      const code = cb.dataset.code;
      if (!code) return;
      try {
        await Api.patchEstimateEquipmentLine(section.id, code, {
          enabled: cb.checked,
          mark_manual: false,
        });
        render();
      } catch (err) {
        toast(err.message, "err");
        cb.checked = !cb.checked;
      }
    };
  });
  const btnMarkup = $("#btn-apply-markup");
  if (btnMarkup) {
    btnMarkup.onclick = async () => {
      const m = Number($("#est-margin-pct")?.value);
      const c = Number($("#est-conting-pct")?.value);
      if (Number.isNaN(m) || m < 0 || m > 200 || Number.isNaN(c) || c < 0 || c > 200) {
        toast("Margin and contingency must be 0–200%", "err");
        return;
      }
      btnMarkup.disabled = true;
      try {
        // Markup is priced on the section (sql/033). The estimate's figures
        // are only the default a new section starts at.
        await Api.updateSection(section.id, {
          margin_pct: m / 100,
          contingency_pct: c / 100,
        });
        toast(`Markup set to ${m}% + ${c}% contingency`);
        render();
      } catch (err) {
        toast(err.message, "err");
        btnMarkup.disabled = false;
      }
    };
  }
  // Quotes (sql/039). One wiring for every card, because the cards are the same
  // shape — saving stamps the baseline for a lump and re-costs the section, so
  // the page is re-rendered off the result rather than patched in place.
  document.querySelectorAll(".quote-card").forEach((card) => {
    const kind = card.dataset.quoteKind;
    const btn = card.querySelector(".q-save");
    if (!btn) return;
    btn.onclick = async () => {
      const raw = String(card.querySelector(".q-amount")?.value ?? "").trim();
      const amount = raw === "" ? 0 : Number(raw);
      if (Number.isNaN(amount) || amount < 0) {
        toast("A quote has to be a positive number, or empty", "err");
        return;
      }
      const unit = card.querySelector(".q-unit")?.value || "LS";
      btn.disabled = true;
      try {
        await Api.putSectionQuote(section.id, kind, {
          amount,
          unit,
          note: String(card.querySelector(".q-note")?.value ?? "").trim() || null,
        });
        toast(
          amount === 0
            ? `${QUOTE_META[kind]?.label || kind} quote cleared — back to the computed price`
            : unit === "LS"
            ? `${QUOTE_META[kind]?.label || kind} quoted at ${usd(amount, 0)}`
            : `${QUOTE_META[kind]?.label || kind} quoted at ${usd(amount, 4)}/${unit}`
        );
        render();
      } catch (err) {
        toast(err.message, "err");
        btn.disabled = false;
      }
    };
  });
  // Vapor barrier picker — the product is named on the estimate (sql/030) rather
  // than matched by name. Rolls price by the coverage in their own name.
  const vaporSel = $("#est-vapor");
  if (vaporSel) {
    const coverageSf = (name) => {
      const m = String(name).match(/(\d+(?:\.\d+)?)\s*['"]?\s*[x\u00d7]\s*(\d+(?:\.\d+)?)/i);
      return m ? Number(m[1]) * Number(m[2]) : null;
    };
    const perSf = (r) => {
      if (String(r.unit || "").toUpperCase() === "SF") return Number(r.unit_cost);
      const c = coverageSf(r.name);
      return c && r.unit_cost != null ? Number(r.unit_cost) / c : null;
    };
    const showRate = (rolls) => {
      const r = rolls.find((x) => String(x.id) === vaporSel.value);
      const p = r ? perSf(r) : null;
      const el = $("#est-vapor-rate");
      if (!el) return;
      // Nobody chose, and the company has no default either: the section is
      // wrapped in whatever a name search found. Say so — that search is
      // how a bid was once priced on black site poly (sql/030).
      const fallback = !r && totals && totals.vapor_barrier_source === "fallback";
      el.textContent = fallback
        ? totals.vapor_barrier
          ? `no company default set — using ${totals.vapor_barrier}. Choose a roll here, or set the default in Settings.`
          : "no company default set and nothing found — poly is UNPRICED on this section"
        : !r
          ? `using the company default${totals && totals.vapor_barrier ? ` — ${totals.vapor_barrier}` : ""}`
          : p == null
            ? "no roll size in the name — this would price at $0"
            : `$${p.toFixed(4)} / SF`;
      el.style.color = fallback ? "#e8c25a" : "";
    };
    Api.listMaterials({ category: "vapor_barrier", active_only: true })
      .then((rolls) => {
        const cur = section.vapor_barrier_material_id;
        vaporSel.innerHTML =
          `<option value="">— company default —</option>` +
          rolls
            .map((r) => {
              const p = perSf(r);
              const tag = p == null ? " (no roll size)" : ` — $${p.toFixed(4)}/SF`;
              const sel = String(cur) === String(r.id) ? " selected" : "";
              return `<option value="${r.id}"${sel}>${esc(r.name)}${tag}</option>`;
            })
            .join("");
        showRate(rolls);
        vaporSel.onchange = async () => {
          vaporSel.disabled = true;
          try {
            // The PATCH re-costs the pours itself — no quantity changed, so
            // there is nothing to re-take-off.
            await Api.setVaporBarrier(section.id, vaporSel.value ? Number(vaporSel.value) : null);
            toast("Vapor barrier set — estimate repriced");
            render();
          } catch (err) {
            toast(err.message, "err");
            vaporSel.disabled = false;
          }
        };
      })
      .catch((err) => {
        vaporSel.innerHTML = `<option value="">— could not load —</option>`;
        toast("Vapor barrier list: " + err.message, "err");
      });
  }

  // Seam tape — bought per roll of wrap, not per SF of slab (sql/031). The
  // product is named on the estimate like the barrier; the ratio is a company
  // setting, so changing it moves every open estimate on the next recalc.
  const tapeSel = $("#est-tape");
  const tapeRatio = $("#est-tape-ratio");
  if (tapeSel) {
    const note = (msg) => {
      const el = $("#est-tape-note");
      if (el) el.textContent = msg;
    };
    const describe = (tapes) => {
      const t = tapes.find((x) => String(x.id) === tapeSel.value);
      const ratio = Number(tapeRatio?.value || 0);
      if (!t) return note("no tape priced");
      if (!(ratio > 0)) return note("ratio is 0 — no tape is priced");
      const each = Number(t.unit_cost);
      note(`${ratio} × $${each.toFixed(2)} per barrier roll`);
    };
    Promise.all([
      Api.listMaterials({ q: "tape", active_only: true }),
      Api.listSettings("vapor_tape_"),
    ])
      .then(([tapes, settings]) => {
        const ratioSetting = settings.find(
          (s) => s.key === "vapor_tape_rolls_per_barrier_roll",
        );
        if (tapeRatio) tapeRatio.value = ratioSetting ? Number(ratioSetting.value) : 0;

        const cur = section.vapor_tape_material_id;
        tapeSel.innerHTML =
          `<option value="">— company default —</option>` +
          tapes
            .map((t) => {
              const price = t.unit_cost == null ? " (no price)" : ` — $${Number(t.unit_cost).toFixed(2)}/${esc(t.unit || "EA")}`;
              const sel = String(cur) === String(t.id) ? " selected" : "";
              return `<option value="${t.id}"${sel}>${esc(t.name)}${price}</option>`;
            })
            .join("");
        describe(tapes);

        tapeSel.onchange = async () => {
          tapeSel.disabled = true;
          try {
            await Api.setVaporTape(section.id, tapeSel.value ? Number(tapeSel.value) : null);
            toast("Seam tape set — estimate repriced");
            render();
          } catch (err) {
            toast(err.message, "err");
            tapeSel.disabled = false;
          }
        };

        if (tapeRatio) {
          tapeRatio.onchange = async () => {
            tapeRatio.disabled = true;
            try {
              await Api.updateSetting(
                "vapor_tape_rolls_per_barrier_roll",
                String(Number(tapeRatio.value) || 0),
              );
              await Api.recalcSection(section.id);
              toast("Tape ratio saved — this section repriced");
              render();
            } catch (err) {
              toast(err.message, "err");
              tapeRatio.disabled = false;
            }
          };
        }
      })
      .catch((err) => {
        tapeSel.innerHTML = `<option value="">— could not load —</option>`;
        toast("Seam tape list: " + err.message, "err");
      });
  }

  const btnRecalc = $("#btn-recalc-estimate");
  if (btnRecalc) {
    btnRecalc.onclick = async () => {
      btnRecalc.disabled = true;
      btnRecalc.textContent = "Recalculating…";
      try {
        await Api.recalcSection(section.id);
        toast("Section recalculated from current inputs");
        render();
      } catch (err) {
        toast(err.message, "err");
        btnRecalc.disabled = false;
        btnRecalc.textContent = "Recalculate";
      }
    };
  }
  $("#btn-edit-section").onclick = () => openSectionModal(estimate, section);
  $("#btn-del-estimate").onclick = async () => {
    const msg =
      `Delete section “${section.name}”?\n\n` +
      `This permanently removes its pours, beam types and takeoffs. ` +
      `The rest of the job is untouched.`;
    if (!confirm(msg)) return;
    try {
      await Api.deleteSection(section.id, true);
      toast("Section deleted");
      setRoute("estimate", { estimateId: estimate.id });
    } catch (err) {
      toast(err.message, "err");
    }
  };
  $$(".btn-edit-slab", root).forEach((btn) => {
    btn.onclick = () => {
      const slab = slabs.find((s) => s.id === btn.dataset.id);
      openMonoSlabModal(section, slab);
    };
  });
  $$(".btn-gb", root).forEach((btn) => {
    btn.onclick = () => {
      const slab = slabs.find((s) => s.id === btn.dataset.id);
      openGradeBeamsModal(slab, btn.dataset.kind || "grade_beam");
    };
  });
  $$(".btn-del-slab", root).forEach((btn) => {
    btn.onclick = async () => {
      if (!confirm("Delete this mono slab pour?")) return;
      try {
        await Api.deleteMonoSlab(btn.dataset.id);
        toast("Pour deleted");
        render();
      } catch (err) {
        toast(err.message, "err");
      }
    };
  });
}

/**
 * The estimate's beam schedule — where sections are defined.
 *
 * Types are estimate-level (sql/025), so they get their own section here rather
 * than being reachable only through a pour. Lengths still belong to the pour and
 * are entered from its GBs / Exp / Drops buttons.
 */
function renderBeamTypesCard(types) {
  if (!types) {
    return `<div class="card" id="beam-schedule" style="margin-top:1rem">
      <h3 style="margin:0 0 0.5rem">Beam schedule</h3>
      <div class="empty">Could not load beam types.</div>
    </div>`;
  }

  const money = (v) => (v == null ? "—" : num(v, 0));
  const kinds = [
    ["grade_beam", "Grade beams"],
    ["exposed", "Exposed GBs"],
    ["drop", "Drops"],
    ["brick_ledge", "Brick ledge"],
  ];

  const totalLf = types.reduce((a, t) => a + Number(t.total_lf || 0), 0);
  const totalCy = types.reduce((a, t) => a + Number(t.total_concrete_cy || 0), 0);
  const totalLb = types.reduce((a, t) => a + Number(t.total_rebar_lb || 0), 0);

  function group(kind, title) {
    const rows = types.filter((t) => t.kind === kind);
    if (!rows.length) return "";
    const showPt = kind === "grade_beam";
    return `
      <h4 style="margin:1rem 0 0.5rem">${esc(title)}</h4>
      <div class="table-wrap"><table class="data">
        <thead>
          <tr>
            <th>Type</th><th>Section</th><th>Top</th><th>Bottom</th><th>Mid</th>
            <th>Stirrups</th>${showPt ? "<th>PT</th>" : ""}
            <th>Used in</th><th>Total LF</th><th>CY</th><th>Rebar lb</th><th></th>
          </tr>
        </thead>
        <tbody>
          ${rows
            .map((t) => {
              const bars = (c, s) => (c && s ? `${c} - #${s}` : "—");
              const unused = !Number(t.pour_count);
              return `<tr data-beam-type="${esc(t.id)}" class="${unused ? "muted" : ""}">
                <td><strong>${esc(t.label)}</strong>
                  ${t.notes ? `<div class="muted">${esc(t.notes)}</div>` : ""}</td>
                <td class="muted">${num(t.width_in, 0)}″ × ${num(t.height_in, 0)}″</td>
                <td class="muted">${esc(bars(t.top_bars_count, t.top_bars_size))}</td>
                <td class="muted">${esc(bars(t.bottom_bars_count, t.bottom_bars_size))}</td>
                <td class="muted">${esc(bars(t.mid_bars_count, t.mid_bars_size))}</td>
                <td class="muted">${
                  t.stirrup_size && t.stirrup_spacing_in
                    ? `#${t.stirrup_size} @ ${num(t.stirrup_spacing_in, 0)}″`
                    : "—"
                }</td>
                ${showPt ? `<td class="num muted">${t.pt_cables_count ?? "—"}</td>` : ""}
                <td class="num">${
                  unused
                    ? `<span title="Defined but not used by any pour">not used</span>`
                    : `${t.pour_count} pour${t.pour_count === 1 ? "" : "s"}`
                }</td>
                <td class="num"><strong>${money(t.total_lf)}</strong></td>
                <td class="num muted">${num(t.total_concrete_cy, 2)}</td>
                <td class="num muted">${money(t.total_rebar_lb)}</td>
                <td style="white-space:nowrap">
                  <button type="button" class="btn ghost btn-edit-type" data-id="${esc(t.id)}">Edit</button>
                  <button type="button" class="btn danger ghost btn-del-type"
                    data-id="${esc(t.id)}" data-label="${esc(t.label)}"
                    data-pours="${esc(t.pour_count)}">Del</button>
                </td>
              </tr>`;
            })
            .join("")}
        </tbody>
      </table></div>`;
  }

  return `
    <div class="card" id="beam-schedule" style="margin-top:1rem">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:1rem;flex-wrap:wrap;margin-bottom:0.5rem">
        <div>
          <h3 style="margin:0">Beam schedule</h3>
          <p style="margin:0.25rem 0 0;color:var(--text-muted);font-size:0.85rem">
            Sections defined once for this estimate, in <code>estimate_beam_types</code>.
            Pours reference a type and supply only length — enter those with the
            <strong>GBs</strong> / <strong>Exp</strong> / <strong>Drops</strong> buttons above.
            <br />Editing a section here <strong>changes every pour that uses it</strong>.
          </p>
        </div>
        <div style="display:flex;gap:0.5rem;align-items:center;flex-wrap:wrap">
          <div class="card stat" style="min-width:10rem;margin:0">
            <div class="label">Types</div>
            <div class="value" style="font-size:1.1rem">${types.length}</div>
            <div class="hint">${num(totalLf, 0)} LF total</div>
          </div>
          <div class="card stat" style="min-width:10rem;margin:0">
            <div class="label">Beam CY</div>
            <div class="value" style="font-size:1.1rem">${num(totalCy, 1)}</div>
            <div class="hint">${num(totalLb, 0)} lb rebar</div>
          </div>
          <button type="button" class="btn primary" id="btn-add-beam-type">+ Add type</button>
        </div>
      </div>
      ${
        types.length
          ? kinds.map(([k, title]) => group(k, title)).join("")
          : `<div class="empty">No beam types yet. Add one, then enter its length on each pour.</div>`
      }
    </div>`;
}

/** Add or edit one section. Editing moves every pour using it. */
function openBeamTypeModal(section, existing = null, defaultKind = "grade_beam") {
  const isEdit = !!existing;
  const kind = existing?.kind || defaultKind;
  const backdrop = document.createElement("div");
  backdrop.className = "modal-backdrop";
  const usedNote =
    isEdit && Number(existing.pour_count)
      ? `<div class="badge warn" style="margin-bottom:0.75rem">
           Used by ${existing.pour_count} pour${existing.pour_count === 1 ? "" : "s"}
           (${num(existing.total_lf, 0)} LF) — saving recalculates all of them.
         </div>`
      : "";
  backdrop.innerHTML = `
    <div class="modal" style="width:min(760px,100%)">
      <h2>${isEdit ? "Edit beam type" : "New beam type"}</h2>
      <p style="margin:-0.5rem 0 0.85rem;color:var(--text-muted);font-size:0.9rem">
        ${esc(section.name)} · this beam type is shared by every pour in the section that uses it
      </p>
      ${usedNote}
      <form id="bt-form" class="form-grid">
        <div class="field">
          <label>Label *</label>
          <input name="label" required value="${esc(existing?.label || "")}"
            placeholder="Beam 1 (type 1)" />
        </div>
        <div class="field">
          <label>Kind</label>
          <select name="kind">
            <option value="grade_beam" ${kind === "grade_beam" ? "selected" : ""}>Grade beam</option>
            <option value="exposed" ${kind === "exposed" ? "selected" : ""}>Exposed GB</option>
            <option value="drop" ${kind === "drop" ? "selected" : ""}>Drop</option>
            <option value="brick_ledge" ${kind === "brick_ledge" ? "selected" : ""}>Brick ledge</option>
          </select>
        </div>
        <div class="field">
          <label>Width (in) *</label>
          <input type="number" name="width_in" required min="0" step="0.1"
            value="${esc(existing?.width_in ?? "")}" />
          <span class="muted" id="wh-hint" style="color:var(--text-muted);font-size:0.78rem;${kind === "brick_ledge" ? "" : "display:none"}">
            The added width x full depth — 0 x 0 if the ledge adds no concrete
          </span>
        </div>
        <div class="field">
          <label>Height (in) *</label>
          <input type="number" name="height_in" required min="0" step="0.1"
            value="${esc(existing?.height_in ?? "")}" />
        </div>
        <div class="field" id="face-field" style="${kind === "brick_ledge" ? "" : "display:none"}">
          <label>Form face depth (in)</label>
          <input type="number" name="form_face_in" min="0" step="0.5"
            placeholder="blank = height"
            value="${esc(existing?.form_face_in ?? "")}" />
          <span class="muted" style="color:var(--text-muted);font-size:0.78rem">
            The formed void at the top of the beam — 10&quot; on a typical 6&quot; x 10&quot; ledge
          </span>
        </div>
        <div class="field full" style="grid-column:1/-1;border-top:1px solid var(--border);padding-top:0.75rem">
          <div style="color:var(--text-muted);font-size:0.75rem;text-transform:uppercase">Bar schedule</div>
        </div>
        <div class="field">
          <label>Top bars</label>
          <div style="display:flex;gap:0.4rem">
            <input type="number" name="top_bars_count" min="0" step="1" style="width:4rem"
              value="${esc(existing?.top_bars_count ?? "")}" />
            <select name="top_bars_size">${barSizeOptions(existing?.top_bars_size)}</select>
          </div>
        </div>
        <div class="field">
          <label>Bottom bars</label>
          <div style="display:flex;gap:0.4rem">
            <input type="number" name="bottom_bars_count" min="0" step="1" style="width:4rem"
              value="${esc(existing?.bottom_bars_count ?? "")}" />
            <select name="bottom_bars_size">${barSizeOptions(existing?.bottom_bars_size)}</select>
          </div>
        </div>
        <div class="field">
          <label>Mid bars</label>
          <div style="display:flex;gap:0.4rem">
            <input type="number" name="mid_bars_count" min="0" step="1" style="width:4rem"
              value="${esc(existing?.mid_bars_count ?? "")}" />
            <select name="mid_bars_size">${barSizeOptions(existing?.mid_bars_size)}</select>
          </div>
        </div>
        <div class="field">
          <label>Stirrups</label>
          <div style="display:flex;gap:0.4rem;align-items:center">
            <select name="stirrup_size">${barSizeOptions(existing?.stirrup_size)}</select>
            <span class="muted">@</span>
            <!-- step="any": min 0.1 with step 0.5 made every whole inch invalid
                 (0.1, 0.6 … 23.6, 24.1), so 24" o.c. was rejected. -->
            <input type="number" name="stirrup_spacing_in" min="0.1" step="any" style="width:4.5rem"
              placeholder="in" value="${esc(existing?.stirrup_spacing_in ?? "")}" />
          </div>
        </div>
        <div class="field" id="pt-field" style="${kind === "grade_beam" ? "" : "display:none"}">
          <label>PT cables through section</label>
          <input type="number" name="pt_cables_count" min="0" step="1"
            placeholder="grade beams only"
            value="${esc(existing?.pt_cables_count ?? "")}" />
        </div>
        <div class="field full">
          <label>Notes</label>
          <textarea name="notes">${esc(existing?.notes || "")}</textarea>
        </div>
        <div class="modal-actions" style="grid-column:1/-1">
          <button type="button" class="btn ghost" id="cancel">Cancel</button>
          <button type="submit" class="btn primary">${isEdit ? "Save section" : "Add type"}</button>
        </div>
      </form>
    </div>`;
  document.body.appendChild(backdrop);
  $("#cancel", backdrop).onclick = () => backdrop.remove();
  backdrop.addEventListener("click", (e) => {
    if (e.target === backdrop) backdrop.remove();
  });
  // PT cables only apply to beams poured with the SOG.
  $('select[name="kind"]', backdrop).onchange = (e) => {
    const k = e.target.value;
    $("#pt-field", backdrop).style.display = k === "grade_beam" ? "" : "none";
    // A ledge is the only kind that can be 0 x 0, and the only one that is formed
    // to a depth different from its concrete depth.
    $("#face-field", backdrop).style.display = k === "brick_ledge" ? "" : "none";
    const hint = $("#wh-hint", backdrop);
    if (hint) hint.style.display = k === "brick_ledge" ? "" : "none";
  };

  $("#bt-form", backdrop).onsubmit = async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    const optNum = (k) => {
      const v = fd.get(k);
      return v === "" || v == null ? null : Number(v);
    };
    const body = {
      label: fd.get("label"),
      kind: fd.get("kind"),
      width_in: Number(fd.get("width_in")),
      height_in: Number(fd.get("height_in")),
      top_bars_count: optNum("top_bars_count"),
      top_bars_size: optNum("top_bars_size"),
      bottom_bars_count: optNum("bottom_bars_count"),
      bottom_bars_size: optNum("bottom_bars_size"),
      mid_bars_count: optNum("mid_bars_count"),
      mid_bars_size: optNum("mid_bars_size"),
      stirrup_size: optNum("stirrup_size"),
      stirrup_spacing_in: optNum("stirrup_spacing_in"),
      form_face_in: fd.get("kind") === "brick_ledge" ? optNum("form_face_in") : null,
      pt_cables_count: fd.get("kind") === "grade_beam" ? optNum("pt_cables_count") : null,
      notes: fd.get("notes") || null,
    };
    try {
      if (isEdit) {
        await Api.updateBeamType(existing.id, body);
        toast("Section saved — pours using it were recalculated");
      } else {
        await Api.createBeamType(section.id, body);
        toast("Beam type added");
      }
      backdrop.remove();
      render();
    } catch (err) {
      toast(err.message, "err");
    }
  };
}

function renderFormingCard(forming) {
  if (!forming) {
    return `<div class="card" id="forming-materials" style="margin-top:1rem">
      <h3 style="margin:0 0 0.5rem">Forming materials</h3>
      <div class="empty">Could not load forming takeoff. Check API / refresh the page.</div>
    </div>`;
  }
  const d = forming.drivers || {};
  // The deck's rentals have a card of their own (sql/071).
  const lines = (forming.lines || []).filter((ln) => ln.group !== "rentals");
  const money = (v) =>
    v == null || v === ""
      ? "—"
      : Number(v).toLocaleString(undefined, {
          style: "currency",
          currency: "USD",
          maximumFractionDigits: 0,
        });
  const refreshed = forming.refreshed_at
    ? new Date(forming.refreshed_at).toLocaleString()
    : "—";
  const formPctPct = Math.round(Number(d.form_percent || 0) * 1000) / 10; // e.g. 50
  const formCodes = new Set(["2x4", "2x6", "2x10", "ply", "siding"]);
  return `
    <div class="card" id="forming-materials" style="margin-top:1rem">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:1rem;flex-wrap:wrap;margin-bottom:0.75rem">
        <div>
          <h3 style="margin:0">Forming materials</h3>
          <p style="margin:0.25rem 0 0;color:var(--text-muted);font-size:0.85rem">
            Stored in <code>estimate_forming_lines</code>.
            ${
              PIER_KINDS.has(d.kind)
                ? `<strong>${num(d.pier_count, 0)} piers</strong> ·
                   <strong>${num(d.total_lf, 0)} LF</strong> drilled
                   <span title="Not one lumber line on this sheet runs off a perimeter">(counts and steel, no perimeter)</span>`
                : COLUMN_KINDS.has(d.kind)
                ? `<strong>${num(d.column_count, 0)} columns</strong> ·
                   <strong>${num(d.form_sf, 0)} SF</strong> of form contact
                   <span title="The faces you actually build. A free-standing column is wrapped on all four; a pilaster has a wall on one or two of them, set per type in the schedule. A wall, by contrast, is formed on the face you can reach — which is why the $/SF rates here look small beside the wall sheet's $/FF.">(formed faces only)</span>
                   · chamfer <strong>${num(d.chamfer_lf, 0)} LF</strong>`
                : PANEL_KINDS.has(d.kind)
                ? `<strong>${num(d.panel_count, 0)} panels</strong> ·
                   formed edge <strong>${num(d.perimeter_lf, 0)} LF</strong>
                   <span title="The panel edges — 2L + 2H per panel — plus every opening's perimeter, which is what the 2x4, the 2x8, the stakes and the chamfer run off. The tab carries no opening lumber.">(+ openings ${num(d.opening_lf, 0)} LF)</span>
                   · bottom <strong>${num(d.bottom_lf, 0)} LF</strong>`
                : BEAM_KINDS.has(d.kind)
                ? `<strong>${num(d.beam_lf, 0)} LF</strong> of beam ·
                   <strong>${num(d.face_ff, 0)} FF</strong>
                   <span title="One face — the tab's I63, what every $/FF rate here is priced against">(one face)</span>
                   · contact <strong>${num(d.contact_ff, 0)} FF</strong>`
                : SPOT_KINDS.has(d.kind)
                ? `footing <strong>${num(d.footing_sf, 0)} SF</strong>
                   <span title="Spot footings: the lumber block runs off the footing alone, the way the sheet's 06-Footings tab does">(no wall)</span>`
                : WALL_KINDS.has(d.kind)
                ? `<strong>${num(d.wall_lf, 0)} LF</strong> of wall ·
                   <strong>${num(d.form_ff, 0)} FF</strong>
                   <span title="One face — every $/FF rate on this assembly is priced against that convention">(one face)</span>
                   · footing <strong>${num(d.footing_sf, 0)} SF</strong>`
                : PAVING_KINDS.has(d.kind)
                ? `Curb <strong>${num(d.curb_lf, 0)} LF</strong>
                   <span title="Every lumber line on the paving sheet reads the curb column, not a perimeter">(what the lumber runs on)</span>
                   · joints <strong>${num(d.construction_joint_lf, 0)}</strong> /
                     <strong>${num(d.control_joint_lf, 0)} LF</strong>`
                : `Perim <strong>${num(d.perimeter_lf, 0)} LF</strong>
                   · drops <strong>${num(d.drops_ff, 0)} LF</strong> <span title="Sum of drop-kind grade beams on this estimate">(from drop beams)</span>`
            }
            ${
              PIER_KINDS.has(d.kind) ||
              COLUMN_KINDS.has(d.kind) ||
              WALL_KINDS.has(d.kind) ||
              BEAM_KINDS.has(d.kind)
                ? ""
                : `· SF <strong>${num(d.total_sf, 0)}</strong>`
            }
            · last refresh <strong>${esc(refreshed)}</strong>
          </p>
          <div style="display:flex;align-items:center;gap:0.5rem;flex-wrap:wrap;margin-top:0.65rem${
            PIER_KINDS.has(d.kind) ? ";display:none" : ""
          }">
            <label for="form-percent-input" style="font-size:0.85rem;color:var(--text-muted)">
              % of forms
            </label>
            <input type="number" id="form-percent-input" min="0" max="200" step="1"
              value="${formPctPct}"
              style="width:4.5rem"
              title="Excel % of forming — multiplies 2x4, 2x6, 2x10, ply, masonite only" />
            <span class="muted" style="font-size:0.85rem">%</span>
            <button type="button" class="btn primary" id="btn-apply-form-percent">Apply form %</button>
            <span class="muted" style="font-size:0.8rem">
              Applies to <strong>2×4, 2×6, 2×10, plywood, masonite</strong> only
              (not nails, bracing, anchors, chairs…).
              ${d.form_percent_system_default != null
                ? `System default ${num(Number(d.form_percent_system_default) * 100, 0)}%.`
                : ""}
            </span>
          </div>
        </div>
        <div style="display:flex;gap:0.5rem;align-items:center;flex-wrap:wrap">
          <div class="card stat" style="min-width:11rem;margin:0">
            <div class="label">Forming mat’l</div>
            <div class="value" style="font-size:1.25rem">${money(forming.materials_ext_cost ?? forming.total_ext_cost)}</div>
          </div>
          <button type="button" class="btn" id="btn-refresh-forming">Refresh from pours</button>
        </div>
      </div>
      ${
        lines.length
          ? `<div class="table-wrap"><table class="data">
        <thead>
          <tr>
            <th title="Uncheck a line that is not used on this job. It keeps its quantity and stops asking to be priced.">Use</th>
            <th>Material</th>
            <th>Qty</th>
            <th>Unit</th>
            <th>Unit $</th>
            <th>Ext $</th>
            <th>Formula</th>
          </tr>
        </thead>
        <tbody>
          ${lines
            .map(
              (ln) => `<tr data-forming-code="${esc(ln.code)}" class="${
                ln.enabled === false || Number(ln.qty) === 0 ? "muted" : ""
              }">
              <td style="width:2.5rem">
                <input type="checkbox" class="forming-enabled" data-code="${esc(ln.code)}"
                  ${ln.enabled === false ? "" : "checked"}
                  title="Include in estimate. Unchecked = not used on this job — the line keeps its quantity, extends at $0, and drops off the unpriced list." />
              </td>
              <td style="max-width:30rem">
                <strong>${esc(ln.label)}</strong>
                ${ln.enabled === false ? ` <span class="badge" title="Not used on this job">not used</span>` : ""}
                ${formCodes.has(ln.code) ? ` <span class="badge accent" title="Scaled by form %">form%</span>` : ""}
                ${ln.material_name && ln.material_name !== ln.label
                  ? `<div class="muted">${esc(ln.material_name)}</div>`
                  : ""}
                ${ln.notes ? `<div class="muted" style="white-space:normal">${esc(ln.notes)}</div>` : ""}
                ${ln.is_manual ? `<div class="badge">manual</div>` : ""}
                ${ln.missing_price
                  ? ` <span class="badge warn" title="A real quantity with no catalog price behind it. This line adds $0 to the total — the total is light by whatever it should cost.">unpriced</span>`
                  : ""}
              </td>
              <td class="num"><strong>${num(ln.qty, Number(ln.qty) >= 20 || Number(ln.qty) === 0 ? 0 : 2)}</strong></td>
              <td class="muted">${esc(ln.unit)}</td>
              <td class="num muted">${ln.unit_cost != null ? num(ln.unit_cost, 2) : ln.missing_price ? `<span class="badge warn">none</span>` : "—"}</td>
              <td class="num">${ln.ext_cost != null ? money(ln.ext_cost) : ln.missing_price ? `<span class="badge warn">$0 — unpriced</span>` : "—"}</td>
              <td class="muted" style="font-size:0.78rem">${esc(ln.formula || "")}</td>
            </tr>`
            )
            .join("")}
        </tbody>
      </table></div>`
          : `<div class="empty">No lines stored yet — click <strong>Refresh from pours</strong>.</div>`
      }
      <p style="color:var(--text-muted);font-size:0.8rem;margin:0.75rem 0 0">
        After changing pours (perimeter / drops / SF), click <strong>Refresh from pours</strong>
        to rewrite stored quantities. Keyway, chamfer, redwood, form release start at 0 (manual later).
      </p>
    </div>`;
}

/**
 * The deck's rentals — forms, shoring, reshoring — on a card of their own
 * (sql/071). Same line set as the forming card, same Use switch, so the one
 * refresh rewrites both; when a shoring quote is on the section the three
 * lines give way to the one quote line.
 */
function renderRentalsCard(forming, title = null) {
  const lines = ((forming && forming.lines) || []).filter((ln) => ln.group === "rentals");
  const quoted = lines.some((ln) => ln.code === "shoring_quote");
  return `
    <div class="card" id="form-rentals" style="margin-top:1rem">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:1rem;flex-wrap:wrap;margin-bottom:0.75rem">
        <div>
          <h3 style="margin:0">${title || "Form rentals, shoring &amp; reshoring"}</h3>
          <p style="margin:0.25rem 0 0;color:var(--text-muted);font-size:0.85rem">
            Rented for the job, priced per SF of deck with an allowance each. Rates on the section card;
            ${
              quoted
                ? "a <strong>shoring quote</strong> on the Quotes card is pricing all three."
                : "a <strong>shoring quote</strong> on the Quotes card replaces all three."
            }
            Refreshes with the forming materials.
          </p>
        </div>
        <div class="card stat" style="min-width:11rem;margin:0">
          <div class="label">Rentals</div>
          <div class="value" style="font-size:1.25rem">${usd(forming ? forming.rentals_ext_cost : null, 0)}</div>
        </div>
      </div>
      ${
        lines.length
          ? `<div class="table-wrap"><table class="data">
        <thead><tr><th title="Uncheck a line that is not used on this job">Use</th><th>Line</th><th>Qty</th><th>Unit</th><th>Unit $</th><th>Ext $</th><th>Formula</th></tr></thead>
        <tbody>
          ${lines
            .map(
              (ln) => `<tr data-forming-code="${esc(ln.code)}" class="${ln.enabled === false ? "muted" : ""}">
              <td style="width:2.5rem">
                <input type="checkbox" class="forming-enabled" data-code="${esc(ln.code)}" ${ln.enabled === false ? "" : "checked"} />
              </td>
              <td style="max-width:30rem">
                <strong>${esc(ln.label)}</strong>
                ${ln.enabled === false ? ` <span class="badge" title="Not used on this job">not used</span>` : ""}
                ${ln.code === "shoring_quote" ? ` <span class="badge ok">quoted</span>` : ""}
                ${ln.missing_price ? ` <span class="badge warn" title="A real quantity with no price behind it">unpriced</span>` : ""}
                ${ln.notes ? `<div class="muted" style="white-space:normal">${esc(ln.notes)}</div>` : ""}
              </td>
              <td class="num"><strong>${num(ln.qty, 0)}</strong></td>
              <td class="muted">${esc(ln.unit)}</td>
              <td class="num muted">${ln.unit_cost != null ? num(ln.unit_cost, 2) : `<span class="badge warn">none</span>`}</td>
              <td class="num">${ln.ext_cost != null ? usd(ln.ext_cost, 0) : `<span class="badge warn">$0 — unpriced</span>`}</td>
              <td class="muted" style="font-size:0.78rem">${esc(ln.formula || "")}</td>
            </tr>`
            )
            .join("")}
        </tbody>
      </table></div>`
          : `<div class="empty">No rental lines stored yet — click <strong>Refresh from pours</strong> on the forming card.</div>`
      }
    </div>`;
}

function renderLaborCard(labor) {
  if (!labor) {
    return `<div class="card" id="labor-supervision" style="margin-top:1rem">
      <h3 style="margin:0 0 0.5rem">Labor &amp; supervision</h3>
      <div class="empty">Could not load labor takeoff.</div>
    </div>`;
  }
  const d = labor.drivers || {};
  const money = (v) =>
    v == null || v === ""
      ? "—"
      : Number(v).toLocaleString(undefined, {
          style: "currency",
          currency: "USD",
          maximumFractionDigits: 0,
        });
  const refreshed = labor.refreshed_at
    ? new Date(labor.refreshed_at).toLocaleString()
    : "—";
  // Paving is its own sheet with its own line set and its own supervision
  // ladder — 25,000 SF a week against the slab sheet's 16,000 (sql/035-036).
  const isPav = PAVING_KINDS.has(d.kind);
  const isPie = PIER_KINDS.has(d.kind);
  // Columns are the only assembly whose duration comes from a COUNT rather
  // than an area or a typed number of days: 20 columns a week on a five-day
  // week. Reporting it as SF/week would be a number nobody set.
  const isCol = COLUMN_KINDS.has(d.kind);
  // Walls read "04 LABOR / SUPERVISION — SF 0 · drops 0 LF" until 2026-09-01,
  // because there was no walls branch and it fell through to the mono-slab
  // wording. A zero next to a label that does not apply is worse than no
  // label: it reads as a takeoff that came back empty.
  const isWal = WALL_KINDS.has(d.kind);
  const isSpot = SPOT_KINDS.has(d.kind);
  const isBeam = BEAM_KINDS.has(d.kind);
  const isCont = CONT_KINDS.has(d.kind);
  const isRb = RB_SLAB_KINDS.has(d.kind);
  const isSw = SIDEWALK_KINDS.has(d.kind);
  // The elevated deck. Its labor can be SUBCONTRACTED — one switch on the
  // section (sql/052), which sets the flag on every FIELD line and leaves
  // supervision alone, because a superintendent is yours whoever swings the
  // hammer. The money does not move; which bucket it is in does, and the sub
  // has to be told what he is pricing.
  const isDck = DECK_KINDS.has(d.kind);
  // Panels (sql/077): the tab marks every labor row as sub, so the switch
  // the deck has shows here too.
  const isPan = PANEL_KINDS.has(d.kind);
  const subbed = (labor.lines || []).some((ln) => ln.subcontracted);
  const superSfPerWeek =
    d.super_weeks && Number(d.super_weeks) > 0
      ? Number(d.total_sf) / Number(d.super_weeks)
      : isPav
        ? 25000
        : 16000;

  function groupTable(group, title) {
    const lines = (labor.lines || []).filter((ln) => ln.group_name === group);
    if (!lines.length) return "";
    // Slab labor qty comes from pours (SF, drops, tons) — not user-edited.
    // Supervision qty (e.g. foreman days) stays editable.
    const qtyEditable = group === "supervision";
    return `
      <h4 style="margin:1rem 0 0.5rem">${esc(title)}</h4>
      <div class="table-wrap"><table class="data">
        <thead>
          <tr>
            <th>On</th>
            <th>Item</th>
            <th>Rate</th>
            <th>Unit</th>
            <th>Qty</th>
            <th>Ext $</th>
            <th>Formula</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          ${lines
            .map(
              (ln) => `<tr data-labor-code="${esc(ln.code)}" class="${ln.enabled ? "" : "muted"}">
              <td>
                <input type="checkbox" class="labor-enabled" data-code="${esc(ln.code)}"
                  ${ln.enabled ? "checked" : ""} title="Include in estimate" />
              </td>
              <td>
                <strong>${esc(ln.label)}</strong>
                ${ln.is_manual ? ` <span class="badge" title="${ln.rate_is_manual ? "Typed — a refresh keeps the quantity and the rate" : "Typed quantity — the rate still follows the price sheet and the rates card"}">${ln.rate_is_manual ? "manual" : "manual qty"}</span>` : ""}
                ${ln.subcontracted ? ` <span class="badge" title="Subcontracted — this line goes on the sub's sheet, not our crew's">sub</span>` : ""}
                ${ln.notes ? `<div class="muted">${esc(ln.notes)}</div>` : ""}
              </td>
              <td>
                <input type="number" class="labor-rate" data-code="${esc(ln.code)}"
                  min="0" step="0.01" value="${esc(ln.rate)}" data-orig="${esc(ln.rate)}" style="width:5rem" />
              </td>
              <td class="muted">${esc(ln.unit)}</td>
              <td class="num">
                ${
                  qtyEditable
                    ? `<input type="number" class="labor-qty" data-code="${esc(ln.code)}"
                        min="0" step="0.01" value="${esc(ln.qty)}" data-orig="${esc(ln.qty)}" style="width:6rem" />`
                    : `<span title="From pours — refresh to update">${num(ln.qty, Number(ln.qty) >= 20 || Number(ln.qty) === 0 ? 0 : 2)}</span>`
                }
              </td>
              <td class="num"><strong>${money(ln.ext_cost)}</strong></td>
              <td class="muted" style="font-size:0.78rem">${esc(ln.formula || "")}</td>
              <td>
                <button type="button" class="btn ghost labor-save" data-code="${esc(ln.code)}">Save</button>
              </td>
            </tr>`
            )
            .join("")}
        </tbody>
      </table></div>`;
  }

  return `
    <div class="card" id="labor-supervision" style="margin-top:1rem">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:1rem;flex-wrap:wrap;margin-bottom:0.5rem">
        <div>
          <h3 style="margin:0">Labor &amp; supervision</h3>
          <p style="margin:0.25rem 0 0;color:var(--text-muted);font-size:0.85rem">
            Excel <strong>${
              isPie
                ? "01-PIERS LABOR"
                : isCol
                ? "07-COLUMNS LABOR"
                : isPan
                ? "12-PANELS LABOR"
                : isCont
                ? "02-CONT FOOTINGS LABOR"
                : isBeam
                ? "02-GRADE BEAMS LABOR"
                : isSpot
                ? "06-FOOTINGS LABOR"
                : isWal
                ? "06-WALLS LABOR"
                : isSw
                ? "SIDEWALKS LABOR"
                : isPav
                ? "10-PAVING LABOR"
                : isDck
                ? "08-CIP EL. DECK LABOR"
                : DECK_SLAB_KINDS.has(d.kind)
                ? "09-SLAB ON DECK LABOR"
                : isRb
                ? "05-SLABS LABOR"
                : "04 LABOR / SUPERVISION"
            }</strong> — stored in
            <code>estimate_labor_lines</code>.
            ${
              isPie
                ? `<strong>${num(d.pier_count, 0)} piers</strong> · <strong>${num(d.total_lf, 0)} LF</strong>`
                : isCol
                ? `<strong>${num(d.column_count, 0)} columns</strong> · form <strong>${num(d.form_sf, 0)} SF</strong>`
                : isPan
                ? `<strong>${num(d.panel_count, 0)} panels</strong> · <strong>${num(d.total_sf, 0)} SF</strong> gross · bottom <strong>${num(d.bottom_lf, 0)} LF</strong>`
                : isBeam
                ? `<strong>${num(d.beam_lf, 0)} LF</strong> of beam · <strong>${num(d.face_ff, 0)} FF</strong> (one face)`
                : isSpot
                ? `footing <strong>${num(d.footing_sf, 0)} SF</strong>`
                : isWal
                ? `<strong>${num(d.wall_lf, 0)} LF</strong> of wall · <strong>${num(d.form_ff, 0)} FF</strong> · footing <strong>${num(d.footing_sf, 0)} SF</strong>`
                : isDck
                ? `<strong>${num(d.total_sf, 0)} SF</strong> of deck · edge <strong>${num(d.perm_edge_lf, 0)} LF</strong> · GB faces <strong>${num(d.gb_form_ff, 0)} FF</strong> · cable <strong>${num(d.pt_lb, 0)} lb</strong>`
                : `SF <strong>${num(d.total_sf, 0)}</strong>`
            }
            ${
              isPie || isCol || isWal || isDck || isBeam
                ? ""
                : isPav
                ? `· curb <strong>${num(d.curb_lf, 0)} LF</strong>`
                : `· drops <strong>${num(d.drops_ff, 0)} LF</strong> <span title="Sum of drop-kind grade beams on this estimate">(from drop beams)</span>`
            }
            · rebar <strong>${num(d.total_rebar_tons, 2)} ton</strong>
            · super <strong>${num(d.super_weeks, 2)} wk / ${num(d.super_days, 1)} days</strong>
            · refreshed <strong>${esc(refreshed)}</strong>
          </p>
        </div>
        <div style="display:flex;gap:0.5rem;align-items:center;flex-wrap:wrap">
          ${
            isDck || isPan
              ? `<label class="card stat" style="min-width:12rem;margin:0;cursor:pointer"
                    title="One switch for the section. Subbed labor costs the same — it moves which sheet the line goes on, and supervision is never subbed.">
                   <div class="label">Field labor</div>
                   <div class="value" style="font-size:1rem">
                     <input type="checkbox" id="labor-subcontracted" ${subbed ? "checked" : ""} />
                     ${subbed ? "subcontracted" : "our crew"}
                   </div>
                 </label>`
              : ""
          }
          <div class="card stat" style="min-width:10rem;margin:0">
            <div class="label">Labor</div>
            <div class="value" style="font-size:1.1rem">${money(labor.total_labor_cost)}</div>
          </div>
          <div class="card stat" style="min-width:10rem;margin:0">
            <div class="label">Supervision</div>
            <div class="value" style="font-size:1.1rem">${money(labor.total_supervision_cost)}</div>
          </div>
          <div class="card stat" style="min-width:10rem;margin:0">
            <div class="label">${isPie || isCol || isWal || isBeam ? "Total" : "Total / SF"}</div>
            <div class="value" style="font-size:1.1rem">${money(labor.total_cost)}</div>
            <div class="hint">${
              isPie
                ? (d.pier_count ? usd(Number(labor.total_cost) / Number(d.pier_count), 0) + " / pier" : "—")
                : isCol
                ? (d.column_count ? usd(Number(labor.total_cost) / Number(d.column_count), 0) + " / column" : "—")
                : isBeam
                ? (Number(d.beam_lf) ? usd(Number(labor.total_cost) / Number(d.beam_lf), 2) + " / LF" : "—")
                : isWal
                ? (Number(d.form_ff) ? usd(Number(labor.total_cost) / Number(d.form_ff), 2) + " / form ft" : "—")
                : labor.cost_per_sf != null
                ? num(labor.cost_per_sf, 2) + " $/SF"
                : "—"
            }</div>
          </div>
          <button type="button" class="btn" id="btn-refresh-labor">Refresh from pours</button>
        </div>
      </div>
      ${groupTable(
        "labor",
        isPie ? "Pier labor" : isCol ? "Column labor" : isPan ? "Panel labor" : isCont ? "Footing labor" : isBeam ? "Beam labor" : isSpot ? "Footing labor" : isWal ? "Wall labor" : isPav ? "Paving labor" : isDck ? "Deck labor" : "Slab labor"
      )}
      ${groupTable("supervision", "Supervision")}
      <p style="color:var(--text-muted);font-size:0.8rem;margin:0.75rem 0 0">
        Toggle <strong>On</strong> and edit <strong>rate</strong>, then <strong>Save</strong>.
        ${isPie ? "Pier" : isCol ? "Column" : isPan ? "Panel" : isCont ? "Footing" : isBeam ? "Beam" : isSpot ? "Footing" : isWal ? "Wall" : isPav ? "Paving" : "Slab"} labor
        <strong>qty is from ${
          isPie
            ? "the groups"
            : isCol
            ? "the schedule"
            : isPan
            ? "the panel types"
            : isBeam
            ? "the beam types"
            : isWal
            ? "the runs"
            : isPav
            ? "areas"
            : "pours"
        }</strong>
        (not editable) — use <strong>Refresh from pours</strong> after
        ${
          isPie
            ? "piers / depth / rebar"
            : isCol
            ? "quantity / size / rebar"
            : isPan
            ? "quantity / size / openings / bars"
            : isBeam
            ? "length / size / bars"
            : isWal
            ? "length / height / rebar"
            : isPav
            ? "SF / curb / rebar"
            : "SF/drops/rebar"
        } change.
        ${
          isPie || isWal || isBeam || isRb || isPan
            ? "<strong>Supervision days are entered, not derived</strong> — there is no " +
              "area to divide. Change the superintendent days and the equipment ladder " +
              "moves with them."
            : isCol
            ? `<strong>Super days come from the column COUNT</strong>, not an area:
               ${num(d.column_count, 0)} ÷ ${num(d.sf_per_week, 0)} a week
               × ${num(d.days_per_week, 0)}-day week = ${num(d.super_days, 1)} days.
               A column crew is not on site seven days running, and 68 columns is a
               duration whatever their size. Changing a quantity on ONE type moves
               the superintendent, the foreman and the whole rental ladder for every
               other type.`
            : `Supervision qty (e.g. foreman days) can be edited. Super days = SF ÷ ${num(
                superSfPerWeek,
                0
              )} weeks × 7.`
        }
      </p>
    </div>`;
}

function renderEquipmentCard(equip) {
  if (!equip) {
    return `<div class="card" id="estimate-equipment" style="margin-top:1rem">
      <h3 style="margin:0 0 0.5rem">Equipment</h3>
      <div class="empty">Could not load equipment takeoff.</div>
    </div>`;
  }
  const d = equip.drivers || {};
  const money = (v) =>
    v == null || v === ""
      ? "—"
      : Number(v).toLocaleString(undefined, {
          style: "currency",
          currency: "USD",
          maximumFractionDigits: 0,
        });
  const refreshed = equip.refreshed_at
    ? new Date(equip.refreshed_at).toLocaleString()
    : "—";

  function groupTable(group, title) {
    const lines = (equip.lines || []).filter((ln) => ln.group_name === group);
    if (!lines.length) return "";
    const qtyLabel = group === "equipment" ? "Days" : "Qty";
    return `
      <h4 style="margin:1rem 0 0.5rem">${esc(title)}</h4>
      <div class="table-wrap"><table class="data">
        <thead>
          <tr>
            <th>On</th>
            <th>Item</th>
            <th>${qtyLabel}</th>
            <th>Billable</th>
            <th>Rate</th>
            <th>Unit</th>
            <th>Ext $</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          ${lines
            .map(
              (ln) => `<tr data-equip-code="${esc(ln.code)}" class="${ln.enabled ? "" : "muted"}">
              <td>
                <input type="checkbox" class="equip-enabled" data-code="${esc(ln.code)}"
                  ${ln.enabled ? "checked" : ""} />
              </td>
              <td>
                <strong>${esc(ln.label)}</strong>
                ${ln.is_manual ? ` <span class="badge" title="${ln.rate_is_manual ? "Typed — a refresh keeps the quantity and the rate" : "Typed quantity — the rate still follows the price sheet and the rates card"}">${ln.rate_is_manual ? "manual" : "manual qty"}</span>` : ""}
                ${ln.subcontracted ? ` <span class="badge" title="Subcontracted — this line goes on the sub's sheet, not our crew's">sub</span>` : ""}
                ${ln.notes ? `<div class="muted">${esc(ln.notes)}</div>` : ""}
                <div class="muted" style="font-size:0.75rem">${esc(ln.formula || "")}</div>
              </td>
              <td>
                <input type="number" class="equip-days" data-code="${esc(ln.code)}"
                  min="0" step="0.1" value="${esc(ln.days_qty)}" data-orig="${esc(ln.days_qty)}" style="width:5.5rem"
                  title="${group === "equipment" ? "Calendar days on rent" : "Quantity (CY, SF, …)"}" />
              </td>
              <td class="num muted" title="After Excel rental tiers (week/month caps)">${num(ln.billable_units, 1)}</td>
              <td>
                <input type="number" class="equip-rate" data-code="${esc(ln.code)}"
                  min="0" step="0.01" value="${esc(ln.rate)}" data-orig="${esc(ln.rate)}" style="width:5rem" />
                ${ln.missing_price
                  ? `<div><span class="badge warn" title="Not on this job's price sheet and no assembly rate — this number is a placeholder from the code, not a price anyone set. Price the machine on the price sheet, or in the catalog and pull.">placeholder rate</span></div>`
                  : ln.price_source === "rate"
                  ? `<div class="muted" style="font-size:0.72rem" title="From assembly_rates, not the equipment catalog">assembly rate</div>`
                  : ""}
              </td>
              <td class="muted">${esc(ln.unit)}</td>
              <td class="num"><strong>${money(ln.ext_cost)}</strong></td>
              <td>
                <button type="button" class="btn ghost equip-save" data-code="${esc(ln.code)}">Save</button>
              </td>
            </tr>`
            )
            .join("")}
        </tbody>
      </table></div>`;
  }

  return `
    <div class="card" id="estimate-equipment" style="margin-top:1rem">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:1rem;flex-wrap:wrap;margin-bottom:0.5rem">
        <div>
          <h3 style="margin:0">Equipment</h3>
          <p style="margin:0.25rem 0 0;color:var(--text-muted);font-size:0.85rem">
            Excel <strong>${
              PIER_KINDS.has(d.kind)
                ? "01-PIERS EQUIPMENT"
                : COLUMN_KINDS.has(d.kind)
                ? "07-COLUMNS EQUIPMENT"
                : PANEL_KINDS.has(d.kind)
                ? "12-PANELS EQUIPMENT"
                : CONT_KINDS.has(d.kind)
                ? "02-CONT FOOTINGS EQUIPMENT"
                : BEAM_KINDS.has(d.kind)
                ? "02-GRADE BEAMS EQUIPMENT"
                : SPOT_KINDS.has(d.kind)
                ? "06-FOOTINGS EQUIPMENT"
                : WALL_KINDS.has(d.kind)
                ? "06-WALLS EQUIPMENT"
                : SIDEWALK_KINDS.has(d.kind)
                ? "SIDEWALKS EQUIPMENT"
                : PAVING_KINDS.has(d.kind)
                ? "10-PAVING EQUIPMENT"
                : DECK_KINDS.has(d.kind)
                ? "08-CIP EL. DECK EQUIPMENT"
                : DECK_SLAB_KINDS.has(d.kind)
                ? "09-SLAB ON DECK EQUIPMENT"
                : RB_SLAB_KINDS.has(d.kind)
                ? "05-SLABS EQUIPMENT"
                : "04 EQUIPMENT"
            }</strong> — stored in <code>estimate_equipment_lines</code>.
            Super days <strong>${num(d.super_days, 1)}</strong>
            → equip days <strong>${num(d.equip_days, 0)}</strong> (ladder)
            · pour CY <strong>${num(d.total_concrete_cy, 1)}</strong>
            · refreshed <strong>${esc(refreshed)}</strong>
          </p>
        </div>
        <div style="display:flex;gap:0.5rem;align-items:center;flex-wrap:wrap">
          <div class="card stat" style="min-width:10rem;margin:0">
            <div class="label">Fleet</div>
            <div class="value" style="font-size:1.1rem">${money(equip.total_equipment_cost)}</div>
          </div>
          <div class="card stat" style="min-width:10rem;margin:0">
            <div class="label">Contract</div>
            <div class="value" style="font-size:1.1rem">${money(equip.total_contract_cost)}</div>
          </div>
          <div class="card stat" style="min-width:10rem;margin:0">
            <div class="label">Total</div>
            <div class="value" style="font-size:1.1rem">${money(equip.total_cost)}</div>
            <div class="hint">${equip.cost_per_sf != null ? num(equip.cost_per_sf, 2) + " $/SF" : "—"}</div>
          </div>
          <button type="button" class="btn" id="btn-refresh-equip">Refresh</button>
        </div>
      </div>
      ${groupTable("equipment", "Day-rate fleet")}
      ${groupTable("contract", "Contract / services")}
      <p style="color:var(--text-muted);font-size:0.8rem;margin:0.75rem 0 0">
        Days default from superintendent duration (Excel ladder: e.g. ~27 super days → 60 equip days).
        <strong>Billable</strong> uses rental tiers (week/month caps), not raw days × rate.
        Edit days/rate and <strong>Save</strong> to lock a line. Pumping qty = pour concrete CY.
      </p>
    </div>`;
}

// Fallback only — the catalog (sql/066, GET /api/bar-sizes) is the truth and
// is loaded into state.barSizes; #14 and #18 joined it on 2026-09-05.
const BAR_SIZES = [3, 4, 5, 6, 7, 8, 9, 10, 11, 14, 18];

/** The bar catalog as grid select options: #3 … #18, blank meaning none. */
function barSizeChoices() {
  return (state.barSizes.length ? state.barSizes : BAR_SIZES).map((s) => ({ id: s, label: `#${s}` }));
}

/** Excel 04 pour roles — same bar-schedule shape, different kind */
const BEAM_KIND_META = {
  grade_beam: {
    title: "Grade beams",
    short: "GB",
    labelPrefix: "GB Type",
    hint: "Poured with SOG (Excel GRADE BEAMS). PT cables optional. Concrete & rebar add to this pour.",
    showPt: true,
  },
  exposed: {
    title: "Exposed grade beams",
    short: "Exp",
    labelPrefix: "EXP Type",
    hint: "Excel EXP GB — same CY/rebar as GBs into this pour. Extra forming & labor priced later.",
    showPt: false,
  },
  drop: {
    title: "Drops",
    short: "Drops",
    labelPrefix: "Drop Type",
    hint: "Excel Drops — same CY/rebar as GBs into this pour. Extra forming & labor priced later.",
    showPt: false,
  },
  brick_ledge: {
    title: "Brick ledge",
    short: "Ledge",
    labelPrefix: "Ledge",
    hint: "Priced as the thickening it is — concrete, rebar and poly like any beam. What it adds is forming (a 2x6 along the length, ply over the face depth) and its own labor line. Use 0 x 0 for a ledge that is only formed.",
    showPt: false,
  },
};

function barSizeOptions(selected) {
  return (
    `<option value="">—</option>` +
    (state.barSizes.length ? state.barSizes : BAR_SIZES).map(
      (s) =>
        `<option value="${s}" ${Number(selected) === s ? "selected" : ""}>#${s}</option>`
    ).join("")
  );
}

function emptyBeamType(i, kind = "grade_beam") {
  const prefix = (BEAM_KIND_META[kind] || BEAM_KIND_META.grade_beam).labelPrefix;
  return {
    id: null,
    label: `${prefix} ${i}`,
    kind,
    width_in: "",
    height_in: "",
    top_bars_count: "",
    top_bars_size: "",
    bottom_bars_count: "",
    bottom_bars_size: "",
    mid_bars_count: "",
    mid_bars_size: "",
    stirrup_size: "",
    stirrup_spacing_in: "",
    pt_cables_count: "",
    pour_count: 0,
    total_lf: 0,
  };
}

/** One editable row of the estimate's beam schedule. */
function beamTypeRowHtml(t, idx, showPt) {
  const ptCell = showPt
    ? `<td><input type="number" name="pt_cables_count" min="0" step="1"
         value="${esc(t.pt_cables_count ?? "")}" style="width:3rem" title="PT cables through this section" /></td>`
    : "";
  const used = Number(t.pour_count) || 0;
  return `
    <tr data-type-idx="${idx}" data-type-id="${esc(t.id ?? "")}">
      <td><input name="label" value="${esc(t.label || "")}" style="width:8rem" /></td>
      <td><input type="number" name="width_in" min="0" step="0.1" value="${esc(t.width_in ?? "")}" style="width:4rem" /></td>
      <td><input type="number" name="height_in" min="0" step="0.1" value="${esc(t.height_in ?? "")}" style="width:4rem" /></td>
      <td><input type="number" name="top_bars_count" min="0" step="1" value="${esc(t.top_bars_count ?? "")}" style="width:3rem" /></td>
      <td><select name="top_bars_size">${barSizeOptions(t.top_bars_size)}</select></td>
      <td><input type="number" name="bottom_bars_count" min="0" step="1" value="${esc(t.bottom_bars_count ?? "")}" style="width:3rem" /></td>
      <td><select name="bottom_bars_size">${barSizeOptions(t.bottom_bars_size)}</select></td>
      <td><input type="number" name="mid_bars_count" min="0" step="1" value="${esc(t.mid_bars_count ?? "")}" style="width:3rem" /></td>
      <td><select name="mid_bars_size">${barSizeOptions(t.mid_bars_size)}</select></td>
      <td><select name="stirrup_size">${barSizeOptions(t.stirrup_size)}</select></td>
      <td><input type="number" name="stirrup_spacing_in" min="0" step="0.5" value="${esc(t.stirrup_spacing_in ?? "")}" style="width:3.5rem" placeholder="in" /></td>
      ${ptCell}
      <td class="num muted" title="Pours using this type across the estimate">
        ${used ? `${used} pour${used === 1 ? "" : "s"}<div class="muted">${num(t.total_lf, 0)} LF</div>` : "—"}
      </td>
    </tr>`;
}

/**
 * Beam entry, in two halves:
 *   1. the estimate's schedule (a type is defined once)
 *   2. how many LF of each type this pour uses
 * Editing a type moves every pour that references it, so the two are saved
 * separately and the shared edit is called out.
 */
async function openGradeBeamsModal(slab, kind = "grade_beam") {
  const meta = BEAM_KIND_META[kind] || BEAM_KIND_META.grade_beam;
  const showPt = !!meta.showPt;

  const backdrop = document.createElement("div");
  backdrop.className = "modal-backdrop";
  backdrop.innerHTML = `<div class="modal" style="width:min(1150px,100%)"><div class="loading">Loading ${esc(meta.title.toLowerCase())}…</div></div>`;
  document.body.appendChild(backdrop);

  let types = [];
  let usages = [];
  try {
    [types, usages] = await Promise.all([
      Api.listBeamTypes(slab.section_id, kind),
      Api.listGradeBeams(slab.id, kind),
    ]);
  } catch (err) {
    toast(err.message, "err");
    backdrop.remove();
    return;
  }

  // length this pour uses of each type, keyed by type id
  const lengthByType = new Map(usages.map((u) => [u.beam_type_id, u.length_lf]));
  let draftTypes = types.map((t) => ({ ...t }));

  function paint() {
    const totalLf = usages.reduce((a, u) => a + Number(u.length_lf || 0), 0);
    const totalCy = usages.reduce((a, u) => a + Number(u.calc_concrete_cy || 0), 0);
    const totalLb = usages.reduce((a, u) => a + Number(u.calc_rebar_lb || 0), 0);
    const ptHead = showPt ? "<th>PT #</th>" : "";

    $(".modal", backdrop).innerHTML = `
      <h2>${esc(meta.title)} — ${esc(slab.description || "Pour")}</h2>
      <p style="margin:-0.4rem 0 1rem;color:var(--text-muted);font-size:0.9rem">
        ${meta.hint}
        ${usages.length ? `· this pour: <strong>${num(totalLf, 0)} LF</strong> · <strong>${num(totalCy, 2)} CY</strong> · rebar <strong>${num(totalLb, 1)} lb</strong>` : ""}
      </p>

      <h4 style="margin:0 0 0.4rem">1. ${esc(meta.title)} schedule for this estimate</h4>
      <p style="margin:0 0 0.6rem;color:var(--text-muted);font-size:0.82rem">
        Defined once and shared by every pour. <strong>Editing a row changes every pour that uses it.</strong>
      </p>
      <div class="table-wrap" style="max-height:34vh">
        <table class="data" id="type-table">
          <thead>
            <tr>
              <th>Type / label</th><th>W"</th><th>H"</th>
              <th>Top #</th><th>Top sz</th><th>Bot #</th><th>Bot sz</th>
              <th>Mid #</th><th>Mid sz</th><th>Stirrup</th><th>@ in</th>
              ${ptHead}<th>Used</th>
            </tr>
          </thead>
          <tbody>
            ${draftTypes.map((t, i) => beamTypeRowHtml(t, i, showPt)).join("") ||
              `<tr><td colspan="13" class="muted">No ${esc(meta.title.toLowerCase())} yet — add one.</td></tr>`}
          </tbody>
        </table>
      </div>
      <div style="display:flex;gap:0.5rem;margin:0.6rem 0 1.2rem">
        <button type="button" class="btn" id="type-add">+ Add type</button>
        <button type="button" class="btn primary" id="type-save">Save schedule</button>
      </div>

      <h4 style="margin:0 0 0.4rem">2. Lengths in this pour</h4>
      <p style="margin:0 0 0.6rem;color:var(--text-muted);font-size:0.82rem">
        Enter LF of each type used here. Blank or 0 removes it from this pour.
        CY = (W″ × H″ × L) / (144 × 27) × (1+waste); poly wrap = ((2×H″)/12) × L.
      </p>
      ${
        draftTypes.filter((t) => t.id).length
          ? `<div class="table-wrap" style="max-height:30vh">
        <table class="data" id="usage-table">
          <thead><tr><th>Type</th><th>Section</th><th>LF in this pour</th><th>CY</th><th>rebar lb</th><th>poly SF</th></tr></thead>
          <tbody>
            ${draftTypes
              .filter((t) => t.id)
              .map((t) => {
                const u = usages.find((x) => x.beam_type_id === t.id);
                return `<tr data-usage-type="${esc(t.id)}">
                  <td><strong>${esc(t.label)}</strong></td>
                  <td class="muted">${num(t.width_in, 0)}×${num(t.height_in, 0)}"</td>
                  <td><input type="number" class="usage-lf" min="0" step="0.1"
                       value="${esc(lengthByType.get(t.id) ?? "")}" style="width:6rem" /></td>
                  <td class="num muted">${u ? num(u.calc_concrete_cy, 2) : "—"}</td>
                  <td class="num muted">${u ? num(u.calc_rebar_lb, 1) : "—"}</td>
                  <td class="num muted">${u ? num(u.calc_poly_sf, 0) : "—"}</td>
                </tr>`;
              })
              .join("")}
          </tbody>
        </table></div>`
          : `<div class="empty">Save a schedule row first, then enter its length here.</div>`
      }

      <div class="modal-actions" style="justify-content:flex-end;margin-top:1rem;gap:0.5rem">
        <button type="button" class="btn ghost" id="cancel">Close</button>
        <button type="button" class="btn primary" id="usage-save">Save lengths</button>
      </div>`;

    $("#cancel", backdrop).onclick = () => backdrop.remove();
    $("#type-add", backdrop).onclick = () => {
      draftTypes = collectTypes().concat([emptyBeamType(draftTypes.length + 1, kind)]);
      paint();
    };
    $("#type-save", backdrop).onclick = () => saveTypes();
    const us = $("#usage-save", backdrop);
    if (us) us.onclick = () => saveUsages();
  }

  function collectTypes() {
    return $$("#type-table tbody tr[data-type-idx]", backdrop).map((tr) => {
      const g = (n) => {
        const el = tr.querySelector(`[name="${n}"]`);
        return el ? el.value : "";
      };
      const n = (name) => {
        const v = g(name);
        return v === "" ? null : Number(v);
      };
      const idx = Number(tr.dataset.typeIdx);
      const prev = draftTypes[idx] || {};
      return {
        id: tr.dataset.typeId || null,
        kind,
        label: g("label") || null,
        width_in: n("width_in"),
        height_in: n("height_in"),
        top_bars_count: n("top_bars_count"),
        top_bars_size: n("top_bars_size"),
        bottom_bars_count: n("bottom_bars_count"),
        bottom_bars_size: n("bottom_bars_size"),
        mid_bars_count: n("mid_bars_count"),
        mid_bars_size: n("mid_bars_size"),
        stirrup_size: n("stirrup_size"),
        stirrup_spacing_in: n("stirrup_spacing_in"),
        pt_cables_count: showPt ? n("pt_cables_count") : null,
        pour_count: prev.pour_count || 0,
        total_lf: prev.total_lf || 0,
      };
    });
  }

  async function saveTypes() {
    const rows = collectTypes();
    const bad = rows.find(
      (r) => !r.label || !(r.width_in > 0) || !(r.height_in > 0)
    );
    if (bad) {
      toast("Every type needs a label, width and height", "err");
      return;
    }
    const btn = $("#type-save", backdrop);
    btn.disabled = true;
    try {
      // The whole schedule in one request: one recalc of the section, one
      // commit, and a bad row saves nothing. Until 2026-09-06 this PATCHed the
      // types one at a time — five recalcs for five types (audit P3).
      const res = await Api.saveBeamTypes(
        slab.section_id,
        rows.map((r) => {
          const body = { ...r, id: r.id || null };
          delete body.pour_count;
          delete body.total_lf;
          return body;
        })
      );
      toast(
        `Schedule saved (${res.created} new, ${res.updated} updated) — pours using these types were recalculated`
      );
      types = await Api.listBeamTypes(slab.section_id, kind);
      usages = await Api.listGradeBeams(slab.id, kind);
      lengthByType.clear();
      usages.forEach((u) => lengthByType.set(u.beam_type_id, u.length_lf));
      draftTypes = types.map((t) => ({ ...t }));
      paint();
      render();
    } catch (err) {
      toast(err.message, "err");
      btn.disabled = false;
    }
  }

  async function saveUsages() {
    const beams = $$("#usage-table tbody tr[data-usage-type]", backdrop)
      .map((tr) => ({
        beam_type_id: tr.dataset.usageType,
        length_lf: Number(tr.querySelector(".usage-lf")?.value || 0),
      }))
      .filter((b) => b.length_lf > 0);
    const btn = $("#usage-save", backdrop);
    btn.disabled = true;
    try {
      await Api.replaceGradeBeams(slab.id, beams, kind);
      toast(`Saved ${beams.length} ${meta.title.toLowerCase()} length(s)`);
      backdrop.remove();
      render();
    } catch (err) {
      toast(err.message, "err");
      btn.disabled = false;
    }
  }

  paint();
  backdrop.addEventListener("click", (e) => {
    if (e.target === backdrop) backdrop.remove();
  });
}

function openMonoSlabModal(section, existing = null) {
  const isEdit = !!existing;
  const backdrop = document.createElement("div");
  backdrop.className = "modal-backdrop";
  const mixOpts = state.mixes
    .map(
      (m) =>
        `<option value="${m.id}" ${existing?.mix_design_id === m.id ? "selected" : ""}>${esc(m.name)}</option>`
    )
    .join("");

  backdrop.innerHTML = `
    <div class="modal" style="width:min(720px,100%)">
      <h2>${isEdit ? "Edit mono slab" : "New mono slab pour"}</h2>
      <p style="margin:-0.5rem 0 1rem;color:var(--text-muted);font-size:0.9rem">
        Section: ${esc(section.name)} · calcs refresh on save
      </p>
      <form id="slab-form" class="form-grid">
        <div class="field">
          <label>Description / location</label>
          <input name="description" placeholder="Garden Style, Bld 1 Pour 3"
            value="${esc(existing?.description || "")}" />
        </div>
        <div class="field">
          <label>Location note</label>
          <input name="location" value="${esc(existing?.location || "")}" />
        </div>
        <div class="field">
          <label>Quantity</label>
          <input type="number" name="qty" min="0" step="1"
            value="${existing?.qty ?? 1}"
            title="Garden style: how many buildings of this type. Every quantity and cost on the row is multiplied by it; blank reads as 1, 0 keeps the row and prices nothing." />
        </div>
        <div class="field">
          <label>Square footage *</label>
          <input type="number" name="square_footage" required min="0" step="0.001"
            value="${existing?.square_footage ?? ""}" />
        </div>
        <div class="field">
          <label>Thickness (in) *</label>
          <input type="number" name="thickness_in" required min="0.001" step="0.001"
            value="${existing?.thickness_in ?? "4"}" />
        </div>
        <div class="field">
          <label>Sand thickness (in)</label>
          <input type="number" name="sand_thickness_in" min="0" step="0.001"
            value="${existing?.sand_thickness_in ?? ""}" />
        </div>
        <div class="field">
          <label>Perimeter edge (LF)</label>
          <input type="number" name="perimeter_edge_lf" min="0" step="0.001"
            value="${existing?.perimeter_edge_lf ?? ""}" />
        </div>
        <div class="field">
          <label>Mix design</label>
          <select name="mix_design_id">
            <option value="">—</option>
            ${mixOpts}
          </select>
        </div>
        <div class="field">
          <label>Post tension</label>
          <select name="post_tension">
            <option value="false" ${!existing?.post_tension ? "selected" : ""}>No</option>
            <option value="true" ${existing?.post_tension ? "selected" : ""}>Yes</option>
          </select>
        </div>
        <div class="field">
          <label>Wire mesh</label>
          <select name="wire_mesh">
            <option value="false" ${!existing?.wire_mesh ? "selected" : ""}>No</option>
            <option value="true" ${existing?.wire_mesh ? "selected" : ""}>Yes</option>
          </select>
        </div>
        <div class="field full" style="grid-column:1/-1;border-top:1px solid var(--border);padding-top:0.75rem;margin-top:0.25rem">
          <div style="color:var(--text-muted);font-size:0.75rem;text-transform:uppercase;margin-bottom:0.5rem">
            SOG rebar &amp; PT cables — mat from size + spacing; support blank = 0.1 lb/SF; PT LF uses spacing + GB cable counts
          </div>
        </div>
        <div class="field">
          <label>Slab bar size</label>
          <select name="slab_bar_size" title="Slab mat bar size, e.g. #4 @ 18&quot; O.C.E.W.">
            ${barSizeOptions(existing?.slab_bar_size)}
          </select>
        </div>
        <div class="field">
          <label>Slab bar spacing (in o.c.)</label>
          <!-- step="any" — same trap as stirrup spacing: 18" was invalid. -->
          <input type="number" name="slab_bar_spacing_in" min="0.1" step="any"
            placeholder="e.g. 18 — each way"
            title="Each way. LF = 2 × SF × 12 / spacing"
            value="${existing?.slab_bar_spacing_in != null ? esc(existing.slab_bar_spacing_in) : ""}" />
        </div>
        <div class="field">
          <label>Support rebar lb/SF</label>
          <input type="number" name="support_rebar_lb_per_sf" min="0" step="0.01"
            placeholder="default 0.1"
            title="Chairs / dowels / misc only — the mat is priced from size + spacing"
            value="${existing?.support_rebar_lb_per_sf != null ? esc(existing.support_rebar_lb_per_sf) : ""}" />
        </div>
        <div class="field">
          <label>PT cable spacing (in o.c.)</label>
          <input type="number" name="pt_spacing_in" min="0.1" step="0.1"
            placeholder="e.g. 48"
            value="${existing?.pt_spacing_in != null ? esc(existing.pt_spacing_in) : ""}" />
        </div>
        <div class="field">
          <label>PT weight lb/SF (optional)</label>
          <input type="number" name="pt_lb_per_sf" min="0" step="0.01"
            placeholder="legacy weight only"
            value="${existing?.pt_lb_per_sf != null ? esc(existing.pt_lb_per_sf) : ""}" />
        </div>
        <div class="field full">
          <label>Notes</label>
          <textarea name="notes">${esc(existing?.notes || "")}</textarea>
        </div>
        ${
          isEdit
            ? `<div class="field full" style="background:var(--bg);border:1px solid var(--border);border-radius:8px;padding:0.75rem">
            <div class="k" style="color:var(--text-muted);font-size:0.75rem;text-transform:uppercase;margin-bottom:0.35rem">Current calcs</div>
            <div style="display:flex;flex-wrap:wrap;gap:1rem;font-family:var(--mono);font-size:0.9rem">
              <span>CY total ${num(existing.calc_concrete_cy, 2)}
                (slab ${num(existing.calc_slab_concrete_cy, 2)} + GB ${num(existing.calc_gb_concrete_cy, 2)})</span>
              <span>Sand ${num(existing.calc_sand_cy, 2)}</span>
              <span>Mat ${num(existing.calc_slab_bar_lb, 0)} lb
                ${existing.slab_bar_size ? `(#${existing.slab_bar_size} @ ${num(existing.slab_bar_spacing_in, 1)}" EW, ${num(existing.calc_slab_bar_lf, 0)} LF)` : "(none)"}</span>
              <span>Support ${num(existing.calc_support_rebar_lb, 0)} lb
                @ ${num(existing.effective_support_rebar_lb_per_sf, 2)} lb/SF</span>
              <span>PT ${num(existing.calc_pt_cable_lf, 0)} LF
                (slab ${num(existing.calc_pt_slab_lf, 0)} + GB ${num(existing.calc_pt_gb_lf, 0)})</span>
              <span>PT wt ${num(existing.calc_pt_cable_lb, 0)} lb</span>
              <span>Total rebar ${num(existing.calc_total_rebar_lb, 0)} lb</span>
            </div>
          </div>`
            : ""
        }
        <div class="modal-actions" style="grid-column:1/-1">
          <button type="button" class="btn ghost" id="cancel">Cancel</button>
          <button type="submit" class="btn primary">Save &amp; calculate</button>
        </div>
      </form>
    </div>`;
  document.body.appendChild(backdrop);
  $("#cancel", backdrop).onclick = () => backdrop.remove();
  backdrop.addEventListener("click", (e) => {
    if (e.target === backdrop) backdrop.remove();
  });

  $("#slab-form", backdrop).onsubmit = async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    const optNum = (k) => {
      const v = fd.get(k);
      if (v === "" || v == null) return null;
      return Number(v);
    };
    const body = {
      description: fd.get("description") || null,
      location: fd.get("location") || null,
      // Garden style (sql/079): buildings of this type. Blank is one.
      qty: fd.get("qty") === "" || fd.get("qty") == null ? 1 : Number(fd.get("qty")),
      square_footage: Number(fd.get("square_footage")),
      thickness_in: Number(fd.get("thickness_in")),
      sand_thickness_in: optNum("sand_thickness_in"),
      perimeter_edge_lf: optNum("perimeter_edge_lf"),
      mix_design_id: fd.get("mix_design_id") ? Number(fd.get("mix_design_id")) : null,
      post_tension: fd.get("post_tension") === "true",
      wire_mesh: fd.get("wire_mesh") === "true",
      slab_bar_size: optNum("slab_bar_size"),
      slab_bar_spacing_in: optNum("slab_bar_spacing_in"),
      support_rebar_lb_per_sf: optNum("support_rebar_lb_per_sf"),
      pt_lb_per_sf: optNum("pt_lb_per_sf"),
      pt_spacing_in: optNum("pt_spacing_in"),
      notes: fd.get("notes") || null,
    };
    try {
      if (isEdit) {
        await Api.updateMonoSlab(existing.id, body);
        toast("Pour updated · calcs refreshed");
      } else {
        await Api.createMonoSlab({ ...body, section_id: section.id });
        toast("Pour added · calcs refreshed");
      }
      backdrop.remove();
      render();
    } catch (err) {
      toast(err.message, "err");
    }
  };
}

// ---------- Catalogs (materials, equipment, mix designs) ----------
//
// Saving a price here does not touch stored estimates: costing reads catalog
// prices at recalc time, so a change lands on the next recalc. The reprice bar
// below is how you push it through — and it deliberately leaves final and
// archived estimates at the numbers they were bid with.

/** Set once a catalog price changes, so the reprice bar can say so. */
let catalogDirty = false;

/** How many sections a recalc report rewrote — it lists each estimate's sections (audit P3). */
function sectionsMoved(report) {
  return (report.recalculated || []).reduce((n, e) => n + (e.sections || []).length, 0);
}

async function reprice(btn, statusEl) {
  const original = btn.textContent;
  btn.disabled = true;
  btn.textContent = "Repricing…";
  try {
    const report = await Api.recalcAllEstimates();
    const n = report.recalculated?.length ?? 0;
    const m = sectionsMoved(report);
    const skipped = report.skipped ?? [];
    catalogDirty = false;
    statusEl.textContent = skipped.length
      ? `Repriced ${n} open estimate${n === 1 ? "" : "s"} · left ${skipped.length} final/archived alone`
      : `Repriced ${n} open estimate${n === 1 ? "" : "s"}`;
    toast(`Repriced ${n} estimate${n === 1 ? "" : "s"} · ${m} section${m === 1 ? "" : "s"}`);
    $("#reprice-bar")?.classList.remove("dirty");
  } catch (err) {
    toast(err.message, "err");
  } finally {
    btn.disabled = false;
    btn.textContent = original;
  }
}

function repriceBarHtml() {
  return `
    <div id="reprice-bar" class="card ${catalogDirty ? "dirty" : ""}"
         style="display:flex;align-items:center;gap:0.75rem;flex-wrap:wrap;margin-bottom:1rem">
      <div style="flex:1;min-width:16rem">
        <strong>Prices don't reach estimates on their own.</strong>
        <div class="muted" style="color:var(--text-muted);font-size:0.85rem">
          Repricing rewrites open estimates (draft, in review). Final and archived
          ones keep the numbers they were bid with.
        </div>
      </div>
      <span id="reprice-status" class="muted"
            style="color:var(--text-muted);font-size:0.85rem"></span>
      <button class="btn primary" id="reprice-btn">Reprice open estimates</button>
    </div>`;
}

function wireRepriceBar(root) {
  const btn = $("#reprice-btn", root);
  if (!btn) return;
  btn.onclick = () => reprice(btn, $("#reprice-status", root));
}

function markCatalogDirty() {
  catalogDirty = true;
  $("#reprice-bar")?.classList.add("dirty");
  const s = $("#reprice-status");
  if (s) s.textContent = "Open estimates are out of date";
}

/**
 * A modal form built from a field spec. Returns the values as an object, with
 * blanks as null and numbers as numbers, so it can go straight to the API.
 */
function openRowModal({ title, subtitle = "", fields, values = {}, saveLabel = "Save", onSave }) {
  const backdrop = document.createElement("div");
  backdrop.className = "modal-backdrop";
  const fieldHtml = (f) => {
    const v = values[f.name];
    const cls = `field${f.full ? " full" : ""}`;
    const style = f.full ? ' style="grid-column:1/-1"' : "";
    let input;
    if (f.type === "select") {
      input = `<select name="${f.name}">${f.options
        .map(
          (o) =>
            `<option value="${esc(o.value)}" ${String(v ?? "") === String(o.value) ? "selected" : ""}>${esc(o.label)}</option>`
        )
        .join("")}</select>`;
    } else if (f.type === "textarea") {
      input = `<textarea name="${f.name}">${esc(v ?? "")}</textarea>`;
    } else if (f.type === "checkbox") {
      input = `<label style="display:flex;gap:0.4rem;align-items:center;font-weight:400">
        <input type="checkbox" name="${f.name}" ${v ? "checked" : ""} /> ${esc(f.checkboxLabel || "")}
      </label>`;
    } else {
      const attrs = [
        `type="${f.type || "text"}"`,
        `name="${f.name}"`,
        f.required ? "required" : "",
        f.step ? `step="${f.step}"` : "",
        f.min != null ? `min="${f.min}"` : "",
        f.placeholder ? `placeholder="${esc(f.placeholder)}"` : "",
        `value="${esc(v ?? "")}"`,
      ]
        .filter(Boolean)
        .join(" ");
      input = `<input ${attrs} />`;
    }
    const hint = f.hint
      ? `<span class="muted" style="color:var(--text-muted);font-size:0.78rem">${esc(f.hint)}</span>`
      : "";
    return `<div class="${cls}"${style}>
      ${f.type === "checkbox" ? "" : `<label>${esc(f.label)}${f.required ? " *" : ""}</label>`}
      ${input}${hint}
    </div>`;
  };

  backdrop.innerHTML = `
    <div class="modal" style="width:min(720px,100%)">
      <h2>${esc(title)}</h2>
      ${
        subtitle
          ? `<p style="margin:-0.5rem 0 0.85rem;color:var(--text-muted);font-size:0.9rem">${esc(subtitle)}</p>`
          : ""
      }
      <form id="row-form" class="form-grid">
        ${fields.map(fieldHtml).join("")}
        <div class="modal-actions" style="grid-column:1/-1">
          <button type="button" class="btn ghost" id="cancel">Cancel</button>
          <button type="submit" class="btn primary">${esc(saveLabel)}</button>
        </div>
      </form>
    </div>`;
  document.body.appendChild(backdrop);
  const close = () => {
    backdrop.remove();
    document.removeEventListener("keydown", onKey);
  };
  function onKey(e) {
    if (e.key === "Escape") close();
  }
  document.addEventListener("keydown", onKey);
  $("#cancel", backdrop).onclick = close;
  backdrop.addEventListener("click", (e) => {
    if (e.target === backdrop) close();
  });

  $("#row-form", backdrop).onsubmit = async (e) => {
    e.preventDefault();
    const form = e.target;
    const fd = new FormData(form);
    const body = {};
    for (const f of fields) {
      if (f.type === "checkbox") {
        body[f.name] = form.elements[f.name].checked;
        continue;
      }
      const raw = fd.get(f.name);
      const s = typeof raw === "string" ? raw.trim() : raw;
      if (s === "" || s == null) {
        body[f.name] = null;
      } else if (f.type === "number") {
        body[f.name] = Number(s);
      } else {
        body[f.name] = s;
      }
    }
    const submit = $('button[type="submit"]', form);
    submit.disabled = true;
    try {
      await onSave(body);
      close();
    } catch (err) {
      toast(err.message, "err");
      submit.disabled = false;
    }
  };
}

async function renderMixes(root) {
  root.innerHTML = `<div class="loading">Loading mix designs…</div>`;
  let showInactive = false;

  const mixFields = () => [
    { name: "code", label: "Code", required: true, placeholder: "3000SC" },
    { name: "name", label: "Name", required: true, placeholder: "3000 PSI SC" },
    { name: "strength_psi", label: "PSI", type: "number", step: "50", min: 0 },
    { name: "unit_cost", label: "Unit cost ($/CY)", type: "number", step: "0.01", min: 0,
      hint: "Blank falls back to the cheapest supplier quote" },
    { name: "has_ash", label: "Ash", type: "checkbox", checkboxLabel: "Contains fly ash" },
    { name: "has_air", label: "Air", type: "checkbox", checkboxLabel: "Air entrained" },
    { name: "notes", label: "Notes", type: "textarea", full: true },
  ];

  async function load() {
    const mixes = await Api.listMixes({ active_only: !showInactive });
    $("#mix-body").innerHTML = `
      <div class="table-wrap">
        <table class="data">
          <thead><tr>
            <th>Code</th><th>Name</th><th>PSI</th><th>Ash</th><th>Air</th>
            <th>Unit cost</th><th></th>
          </tr></thead>
          <tbody>
            ${mixes
              .map(
                (m) => `<tr ${m.is_active === false ? 'style="opacity:0.5"' : ""}>
                <td class="muted">${esc(m.code)}</td>
                <td><strong>${esc(m.name)}</strong>${m.is_active === false ? " (inactive)" : ""}</td>
                <td class="num">${m.strength_psi ?? "—"}</td>
                <td>${m.has_ash ? "✓" : ""}</td>
                <td>${m.has_air ? "✓" : ""}</td>
                <td class="num">${m.unit_cost != null ? money(m.unit_cost) : "—"}</td>
                <td style="white-space:nowrap;text-align:right">
                  <button class="btn ghost" data-edit="${m.id}">Edit</button>
                  ${m.is_active === false ? "" : `<button class="btn ghost" data-off="${m.id}">Deactivate</button>`}
                </td>
              </tr>`
              )
              .join("")}
          </tbody>
        </table>
      </div>
      <p class="muted" style="color:var(--text-muted);font-size:0.85rem">${mixes.length} mixes</p>`;

    $$("#mix-body [data-edit]").forEach((b) => {
      b.onclick = () => {
        const m = mixes.find((x) => String(x.id) === b.dataset.edit);
        openRowModal({
          title: "Edit mix design",
          subtitle: m.name,
          fields: mixFields(),
          values: m,
          saveLabel: "Save mix",
          onSave: async (body) => {
            await Api.updateMix(m.id, body);
            markCatalogDirty();
            toast("Mix saved");
            await load();
          },
        });
      };
    });
    $$("#mix-body [data-off]").forEach((b) => {
      b.onclick = async () => {
        const m = mixes.find((x) => String(x.id) === b.dataset.off);
        if (!confirm(`Deactivate ${m.name}? Estimates already using it keep their numbers.`)) return;
        try {
          await Api.deactivateMix(m.id);
          toast("Mix deactivated");
          await load();
        } catch (err) {
          toast(err.message, "err");
        }
      };
    });
  }

  root.innerHTML = `
    <div class="page-header">
      <div>
        <h1>Mix designs</h1>
        <p>SC / ASH / Air-ASH matrix + 3000 integral color.</p>
      </div>
      <button class="btn primary" id="mix-new">+ New mix</button>
    </div>
    ${repriceBarHtml()}
    <div class="toolbar">
      <label style="display:flex;gap:0.4rem;align-items:center">
        <input type="checkbox" id="mix-inactive" /> Show inactive
      </label>
    </div>
    <div id="mix-body"></div>`;

  wireRepriceBar(root);
  await load();

  $("#mix-inactive").onchange = (e) => {
    showInactive = e.target.checked;
    load().catch((err) => toast(err.message, "err"));
  };
  $("#mix-new").onclick = () =>
    openRowModal({
      title: "New mix design",
      fields: mixFields(),
      values: { has_ash: false, has_air: false },
      saveLabel: "Add mix",
      onSave: async (body) => {
        await Api.createMix(body);
        markCatalogDirty();
        toast("Mix added");
        await load();
      },
    });
}


async function renderMaterials(root) {
  root.innerHTML = `<div class="loading">Loading materials…</div>`;
  let cats = await Api.materialCategories();
  let category = "";
  let q = "";
  let showInactive = false;

  const matFields = () => [
    { name: "name", label: "Name", required: true, full: true,
      hint: "Costing matches materials by name — renaming can change what a takeoff finds" },
    { name: "category", label: "Category", required: true,
      placeholder: cats[0] || "lumber" },
    { name: "unit", label: "Unit", required: true, placeholder: "EA / LF / SF / CY / TON" },
    { name: "unit_cost", label: "Unit cost ($)", type: "number", step: "0.0001", min: 0 },
    { name: "unit_note", label: "Unit note", placeholder: "per 100 SF roll" },
    { name: "code", label: "Code" },
    { name: "supplier_ref", label: "Supplier ref" },
    { name: "price_as_of", label: "Priced as of", type: "date" },
    { name: "description", label: "Description", type: "textarea", full: true },
  ];

  async function load() {
    const rows = await Api.listMaterials({
      active_only: !showInactive,
      category: category || undefined,
      q: q || undefined,
    });
    $("#mat-body").innerHTML = `
      <div class="table-wrap">
        <table class="data">
          <thead><tr>
            <th>Name</th><th>Category</th><th>Unit</th><th>Cost</th>
            <th>Note</th><th>As of</th><th></th>
          </tr></thead>
          <tbody>
            ${rows
              .map(
                (m) => `<tr ${m.is_active ? "" : 'style="opacity:0.5"'}>
                <td><strong>${esc(m.name)}</strong>${m.is_active ? "" : " (inactive)"}</td>
                <td class="muted">${esc(m.category)}</td>
                <td>${esc(m.unit)}</td>
                <td class="num">${m.unit_cost != null ? money(m.unit_cost) : "—"}</td>
                <td class="muted">${esc(m.unit_note || "")}</td>
                <td class="muted">${esc(m.price_as_of || "—")}</td>
                <td style="white-space:nowrap;text-align:right">
                  <button class="btn ghost" data-edit="${m.id}">Edit</button>
                  ${
                    m.is_active
                      ? `<button class="btn ghost" data-off="${m.id}">Deactivate</button>`
                      : `<button class="btn ghost" data-on="${m.id}">Reactivate</button>`
                  }
                </td>
              </tr>`
              )
              .join("")}
          </tbody>
        </table>
      </div>
      <p class="muted" style="color:var(--text-muted);font-size:0.85rem">${rows.length} items</p>`;

    $$("#mat-body [data-edit]").forEach((b) => {
      b.onclick = () => {
        const m = rows.find((x) => String(x.id) === b.dataset.edit);
        openRowModal({
          title: "Edit material",
          subtitle: m.name,
          fields: matFields(),
          values: m,
          saveLabel: "Save material",
          onSave: async (body) => {
            await Api.updateMaterial(m.id, body);
            markCatalogDirty();
            toast("Material saved");
            await load();
          },
        });
      };
    });
    $$("#mat-body [data-off]").forEach((b) => {
      b.onclick = async () => {
        const m = rows.find((x) => String(x.id) === b.dataset.off);
        if (!confirm(`Deactivate ${m.name}? Takeoffs that price off it will stop finding it.`)) return;
        try {
          await Api.deactivateMaterial(m.id);
          toast("Material deactivated");
          await load();
        } catch (err) {
          toast(err.message, "err");
        }
      };
    });
    $$("#mat-body [data-on]").forEach((b) => {
      b.onclick = async () => {
        try {
          await Api.updateMaterial(b.dataset.on, { is_active: true });
          toast("Material reactivated");
          await load();
        } catch (err) {
          toast(err.message, "err");
        }
      };
    });
  }

  root.innerHTML = `
    <div class="page-header">
      <div>
        <h1>Materials</h1>
        <p>Unit-price catalog from Pricing (New Current Worksheet).</p>
      </div>
      <button class="btn primary" id="mat-new">+ New material</button>
    </div>
    ${repriceBarHtml()}
    <div class="toolbar">
      <input id="mat-q" placeholder="Search…" style="min-width:180px" />
      <select id="mat-cat">
        <option value="">All categories</option>
        ${cats.map((c) => `<option value="${esc(c)}">${esc(c)}</option>`).join("")}
      </select>
      <label style="display:flex;gap:0.4rem;align-items:center">
        <input type="checkbox" id="mat-inactive" /> Show inactive
      </label>
    </div>
    <div id="mat-body"></div>`;

  wireRepriceBar(root);
  await load();

  $("#mat-cat").onchange = (e) => {
    category = e.target.value;
    load().catch((err) => toast(err.message, "err"));
  };
  $("#mat-inactive").onchange = (e) => {
    showInactive = e.target.checked;
    load().catch((err) => toast(err.message, "err"));
  };
  $("#mat-new").onclick = () =>
    openRowModal({
      title: "New material",
      fields: matFields(),
      values: { category, unit: "EA" },
      saveLabel: "Add material",
      onSave: async (body) => {
        await Api.createMaterial(body);
        markCatalogDirty();
        toast("Material added");
        cats = await Api.materialCategories();
        await load();
      },
    });
  let t;
  $("#mat-q").oninput = (e) => {
    clearTimeout(t);
    t = setTimeout(() => {
      q = e.target.value.trim();
      load().catch((err) => toast(err.message, "err"));
    }, 250);
  };
}

async function renderEquipment(root) {
  root.innerHTML = `<div class="loading">Loading equipment…</div>`;
  const cats = await Api.equipmentCategories();
  let showInactive = false;

  const equipFields = () => [
    { name: "name", label: "Name", required: true, full: true, placeholder: "MINI EXCAVATOR" },
    { name: "category", label: "Category", type: "select",
      options: cats.map((c) => ({ value: c, label: c })) },
    { name: "unit", label: "Unit", required: true, placeholder: "DAY / YD / HOUR" },
    { name: "unit_cost", label: "Rate ($)", type: "number", step: "0.01", min: 0 },
    { name: "unit_note", label: "Rate note", placeholder: "weekly rate ÷ 5" },
    { name: "code", label: "Code" },
    { name: "price_as_of", label: "Priced as of", type: "date" },
    { name: "is_owned", label: "Owned", type: "checkbox",
      checkboxLabel: "Company owned (not rented)" },
    { name: "description", label: "Description", type: "textarea", full: true },
  ];

  async function load() {
    const rows = await Api.listEquipment({ active_only: !showInactive });
    $("#eq-body").innerHTML = `
      <div class="table-wrap">
        <table class="data">
          <thead><tr>
            <th>Name</th><th>Category</th><th>Unit</th><th>Rate</th>
            <th>Note</th><th>Owned</th><th></th>
          </tr></thead>
          <tbody>
            ${rows
              .map(
                (e) => `<tr ${e.is_active ? "" : 'style="opacity:0.5"'}>
                <td><strong>${esc(e.name)}</strong>${e.is_active ? "" : " (inactive)"}</td>
                <td class="muted">${esc(e.category)}</td>
                <td>${esc(e.unit)}</td>
                <td class="num">${money(e.unit_cost)}</td>
                <td class="muted">${esc(e.unit_note || "")}</td>
                <td>${e.is_owned ? "✓" : ""}</td>
                <td style="white-space:nowrap;text-align:right">
                  <button class="btn ghost" data-edit="${e.id}">Edit</button>
                  ${
                    e.is_active
                      ? `<button class="btn ghost" data-off="${e.id}">Deactivate</button>`
                      : `<button class="btn ghost" data-on="${e.id}">Reactivate</button>`
                  }
                </td>
              </tr>`
              )
              .join("")}
          </tbody>
        </table>
      </div>
      <p class="muted" style="color:var(--text-muted);font-size:0.85rem">${rows.length} items</p>`;

    $$("#eq-body [data-edit]").forEach((b) => {
      b.onclick = () => {
        const e = rows.find((x) => String(x.id) === b.dataset.edit);
        openRowModal({
          title: "Edit equipment",
          subtitle: e.name,
          fields: equipFields(),
          values: e,
          saveLabel: "Save equipment",
          onSave: async (body) => {
            await Api.updateEquipment(e.id, body);
            markCatalogDirty();
            toast("Equipment saved");
            await load();
          },
        });
      };
    });
    $$("#eq-body [data-off]").forEach((b) => {
      b.onclick = async () => {
        const e = rows.find((x) => String(x.id) === b.dataset.off);
        if (!confirm(`Deactivate ${e.name}? Takeoffs that price off it will stop finding it.`)) return;
        try {
          await Api.deactivateEquipment(e.id);
          toast("Equipment deactivated");
          await load();
        } catch (err) {
          toast(err.message, "err");
        }
      };
    });
    $$("#eq-body [data-on]").forEach((b) => {
      b.onclick = async () => {
        try {
          await Api.updateEquipment(b.dataset.on, { is_active: true });
          toast("Equipment reactivated");
          await load();
        } catch (err) {
          toast(err.message, "err");
        }
      };
    });
  }

  root.innerHTML = `
    <div class="page-header">
      <div>
        <h1>Equipment</h1>
        <p>Rental rates from Pricing EQUIPMENT RENTAL.</p>
      </div>
      <button class="btn primary" id="eq-new">+ New equipment</button>
    </div>
    ${repriceBarHtml()}
    <div class="toolbar">
      <label style="display:flex;gap:0.4rem;align-items:center">
        <input type="checkbox" id="eq-inactive" /> Show inactive
      </label>
    </div>
    <div id="eq-body"></div>`;

  wireRepriceBar(root);
  await load();

  $("#eq-inactive").onchange = (e) => {
    showInactive = e.target.checked;
    load().catch((err) => toast(err.message, "err"));
  };
  $("#eq-new").onclick = () =>
    openRowModal({
      title: "New equipment",
      fields: equipFields(),
      values: { category: "other", unit: "DAY", is_owned: false },
      saveLabel: "Add equipment",
      onSave: async (body) => {
        await Api.createEquipment(body);
        markCatalogDirty();
        toast("Equipment added");
        await load();
      },
    });
}

// ================================================================ prices ====
// The job's price sheet (sql/048). Every estimate carries its own copy of the
// master list's mix and material prices, pulled when the estimate was created.
// From then on THIS sheet is what the job pays: a catalog change does not move
// a bid that has already gone out, and a plant's break on one job stays on
// that job. Chad, 2026-09-02: "as we start an estimate, it pulls those
// numbers and we can update when a supplier gives us a quote."
//
// Two rules the screen has to make visible:
//   - an edited row is never overwritten by a pull; it is shown as a conflict
//     (was / now / yours) and kept until someone resets it by hand;
//   - a master item with no price is reported, never copied as $0.

function fmtDay(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

/** A price the way the sheet stores it — up to four decimals, no trailing noise. */
function priceText(v) {
  if (v == null || v === "") return "—";
  const n = Number(v);
  if (Number.isNaN(n)) return "—";
  return "$" + n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 4 });
}

function driftSummaryText(d) {
  if (!d) return "";
  const parts = [];
  if (d.changed.length) parts.push(`${d.changed.length} price${d.changed.length === 1 ? "" : "s"} changed`);
  if (d.new.length) parts.push(`${d.new.length} new item${d.new.length === 1 ? "" : "s"}`);
  if (d.conflicts.length)
    parts.push(`${d.conflicts.length} moved under ${d.conflicts.length === 1 ? "an edit" : "your edits"}`);
  return parts.join(", ");
}

// Concrete first, then the materials A–Z, then the machines, then the
// company's rates, then each assembly's overrides of them.
const PRICE_GROUP_ORDER = ["concrete"];
const PRICE_GROUP_LAST = ["equipment", "drilling", "labor & company rates"];

function priceGroupLabel(key) {
  if (key === "concrete") return "Concrete — mix designs";
  if (key === "equipment") return "Equipment — day rates";
  if (key === "drilling") return "Drilling — by shaft diameter, per LF";
  if (key === "labor & company rates") return "Labor & company rates";
  if (key.endsWith(" rates")) return sectionLabel(key.replace(/ rates$/, "")) + " — where it differs from the company rate";
  return (key || "other").replace(/_/g, " ");
}

function priceGroupRank(key) {
  const first = PRICE_GROUP_ORDER.indexOf(key);
  if (first !== -1) return first;
  const last = PRICE_GROUP_LAST.indexOf(key);
  if (last !== -1) return 100 + last;
  if (key.endsWith(" rates")) return 200;
  return 50;
}

/** A sheet value the way its unit reads: a ratio stays a ratio; money is money. */
function sheetValueText(v, unit) {
  if (unit === "RATIO") return v == null ? "—" : num(Number(v) * 100, 2) + "%";
  return priceText(v);
}

/** A rate at zero is a statement (paving pumps nothing); a mix at zero is the
 *  bug decision 5 exists to stop. The API enforces the same split. */
function zeroAllowed(row) {
  return row.kind === "setting" || row.kind === "assembly_rate";
}

async function renderPriceSheet(root) {
  root.innerHTML = `<div class="loading">Loading price sheet…</div>`;
  const [estimate, sheet] = await Promise.all([
    Api.getEstimate(state.estimateId),
    Api.getPriceSheet(state.estimateId),
  ]);
  const drift = sheet.drift;
  const driftKey = (x) => `${x.kind}:${x.scope || ""}:${x.ref_key || x.ref_id}`;
  const moved = new Map(); // row key -> drift entry, for the "moved" badge
  drift.changed.forEach((x) => moved.set(driftKey(x), x));
  drift.conflicts.forEach((x) => moved.set(driftKey(x), x));
  const retired = new Set(drift.retired.map(driftKey));
  const driftCount = drift.drift + drift.new.length;

  // Group by category; concrete first, then the material categories A–Z.
  const groups = new Map();
  sheet.rows.forEach((r) => {
    const key = r.kind === "mix" ? "concrete" : r.category || "other";
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(r);
  });
  const groupKeys = [...groups.keys()].sort((a, b) => {
    const ra = priceGroupRank(a);
    const rb = priceGroupRank(b);
    if (ra !== rb) return ra - rb;
    return a.localeCompare(b);
  });
  groups.forEach((rows) => rows.sort((a, b) => a.label.localeCompare(b.label)));

  const rowKey = (r) => `${r.kind}:${r.scope || ""}:${r.ref_key || r.ref_id}`;
  const rowHtml = (r) => {
    const key = rowKey(r);
    const mv = moved.get(key);
    const fmt = (v) => sheetValueText(v, r.unit);
    const badges = [];
    if (r.is_edited) badges.push(`<span class="badge warn" title="Set on this job; a pull will not touch it">edited</span>`);
    if (mv)
      badges.push(
        `<span class="badge info" title="Master list is now ${fmt(mv.now)} (was ${fmt(mv.was)} when pulled)">master ${fmt(mv.now)}</span>`
      );
    if (retired.has(key)) badges.push(`<span class="badge" title="No longer on the master list; kept here">retired</span>`);
    const isRatio = r.unit === "RATIO";
    return `<tr data-price="${r.id}" class="${r.is_edited ? "edited" : ""}">
      <td><strong>${esc(r.label)}</strong>${
        r.ref_key && r.kind !== "drill_rate" ? ` <span class="muted" style="font-size:0.75rem;font-family:var(--mono)">${esc(r.ref_key)}</span>` : ""
      }${badges.length ? " " + badges.join(" ") : ""}</td>
      <td class="muted">${isRatio ? "" : esc(r.unit || "")}</td>
      <td class="num muted" title="What the master list said when this row was pulled">${fmt(r.catalog_value)}</td>
      <td class="num">
        <input type="number" step="any" min="0" data-f="value" value="${Number(r.value)}"
          title="${isRatio ? "As a decimal — 0.0825 is 8.25%" : "What this job pays"}" />
      </td>
      <td><input type="text" class="note" data-f="note" maxlength="200"
        value="${esc(r.note || "")}" placeholder="${r.is_edited ? "who quoted it" : ""}" /></td>
      <td style="white-space:nowrap">${
        r.is_edited
          ? `<button type="button" class="btn ghost" data-reset="${r.id}"
              title="Put the master list price back and let pulls move it again">Reset</button>`
          : ""
      }</td>
    </tr>`;
  };

  root.innerHTML = `
    <div class="page-header">
      <div>
        <button class="btn ghost" id="back-est">← ${esc(estimate.name)}</button>
        <h1 style="margin-top:0.5rem">Price sheet</h1>
        <p>What <strong>${esc(estimate.name)}</strong> pays for each mix and material.
          ${sheet.pulled_at ? `Pulled from the master list ${fmtDay(sheet.pulled_at)}.` : ""}
          Edit a price here and it reaches every section of this job — and no other job.</p>
      </div>
      <div style="display:flex;gap:0.5rem;flex-wrap:wrap">
        <button class="btn primary" id="btn-pull" type="button"
          title="Bring this sheet up to today's master list. Prices you edited are kept.">Pull master list…</button>
      </div>
    </div>

    ${
      driftCount
        ? `<div class="warn-banner">
             <strong>The master list has moved since the pull.</strong> ${driftSummaryText(drift)}.
             Nothing on this job changes until you pull. Rows that moved are tagged with the master's current price.
           </div>`
        : ""
    }
    ${
      drift.unpriced.length
        ? `<div class="warn-banner">
             <strong>${drift.unpriced.length === 1 ? "One master-list item has" : `${drift.unpriced.length} master-list items have`} no price</strong>
             and so ${drift.unpriced.length === 1 ? "is" : "are"} not on this sheet. A section that uses one is flagged there and costed at $0 for it:
             <span class="muted">${drift.unpriced.map((u) => esc(u.label)).join(", ")}</span>.
           </div>`
        : ""
    }

    <div class="grid stats">
      <div class="card stat"><div class="label">On the sheet</div>
        <div class="value">${sheet.rows.length}</div>
        <div class="hint">mixes and materials</div></div>
      <div class="card stat"><div class="label">Edited for this job</div>
        <div class="value">${sheet.edited}</div>
        <div class="hint">${sheet.edited ? "kept through every pull" : "everything at the master list"}</div></div>
      <div class="card stat"><div class="label">Master list since pull</div>
        <div class="value">${driftCount ? driftCount : "—"}</div>
        <div class="hint">${driftCount ? "moved · not applied" : "no change"}</div></div>
    </div>

    ${
      sheet.rows.length
        ? `<div class="table-wrap"><table class="data price-sheet">
      <thead><tr>
        <th>Item</th><th>Unit</th><th class="num">Master list</th><th class="num">This job</th><th>Note</th><th></th>
      </tr></thead>
      <tbody>
        ${groupKeys
          .map(
            (g) => `<tr><td class="group" colspan="6">${esc(priceGroupLabel(g))}</td></tr>` +
              groups.get(g).map(rowHtml).join("")
          )
          .join("")}
      </tbody>
    </table></div>
    <p class="muted" style="margin-top:0.5rem;font-size:0.85rem">
      Master list is what the catalog said when this row was last pulled. This job is what the
      estimate bids at. A price typed here is marked <span class="badge warn">edited</span> and
      a later pull leaves it alone; Reset puts the master price back.
    </p>`
        : `<div class="card"><p>This job has no price sheet yet. Pull the master list to start one.</p></div>`
    }
  `;

  $("#back-est").onclick = () => setRoute("estimate", { estimateId: estimate.id });
  $("#btn-pull").onclick = () => openPullModal(estimate, () => render());

  const rows = new Map(sheet.rows.map((r) => [r.id, r]));

  const save = async (tr, body) => {
    const id = tr.dataset.price;
    tr.querySelectorAll("input,button").forEach((el) => (el.disabled = true));
    try {
      const updated = await Api.updatePrice(estimate.id, id, body);
      rows.set(id, updated);
      toast(
        body.reset
          ? `${updated.label} back at the master list — job repriced`
          : body.value != null
            ? `${updated.label} at ${sheetValueText(updated.value, updated.unit)} on this job — job repriced`
            : "Note saved"
      );
      // The row's badges and Reset button depend on is_edited, and the
      // totals changed, so just redraw; it is one request.
      render();
    } catch (err) {
      toast(err.message, "err");
      tr.querySelectorAll("input,button").forEach((el) => (el.disabled = false));
    }
  };

  $$("tr[data-price]").forEach((tr) => {
    const r = rows.get(tr.dataset.price);
    const valueInput = tr.querySelector('input[data-f="value"]');
    const noteInput = tr.querySelector('input[data-f="note"]');

    valueInput.onchange = () => {
      const v = Number(valueInput.value);
      if (!(v > 0) && !(v === 0 && zeroAllowed(r))) {
        toast("A price has to be more than $0 — leave the master list unpriced instead", "err");
        valueInput.value = Number(r.value);
        return;
      }
      if (v === Number(r.value)) return;
      save(tr, { value: v });
    };
    valueInput.onkeydown = (ev) => {
      if (ev.key === "Enter") valueInput.blur();
      if (ev.key === "Escape") {
        valueInput.value = Number(r.value);
        valueInput.blur();
      }
    };
    noteInput.onchange = () => {
      const n = noteInput.value.trim();
      if (n === (r.note || "")) return;
      save(tr, { note: n || null });
    };
    noteInput.onkeydown = (ev) => {
      if (ev.key === "Enter") noteInput.blur();
    };
    const resetBtn = tr.querySelector("[data-reset]");
    if (resetBtn) resetBtn.onclick = () => save(tr, { reset: true });
  });
}

/**
 * The pull, previewed before it is applied. A dry run lists exactly what
 * would move; nothing on the job changes until "Pull" is pressed, and even
 * then the edited rows do not.
 */
async function openPullModal(estimate, onDone) {
  const backdrop = document.createElement("div");
  backdrop.className = "modal-backdrop";
  backdrop.innerHTML = `<div class="modal" style="width:min(760px,100%)"><h2>Pull master list</h2>
    <div class="loading">Comparing this sheet with the master list…</div></div>`;
  document.body.appendChild(backdrop);
  backdrop.addEventListener("click", (ev) => {
    if (ev.target === backdrop) backdrop.remove();
  });

  let d;
  try {
    d = await Api.pullPriceSheet(estimate.id, true);
  } catch (err) {
    backdrop.remove();
    toast(err.message, "err");
    return;
  }

  // "Forming labor (paving)" for an assembly's own rate; the item name otherwise.
  const pullLabel = (x) =>
    esc(x.label) + (x.scope ? ` <span class="muted">(${esc(sectionLabel(x.scope))})</span>` : "");
  const list = (title, items, line, note) =>
    items.length
      ? `<h3 style="margin:1rem 0 0.35rem">${title} <span class="muted">(${items.length})</span></h3>
         ${note ? `<p class="muted" style="margin:0 0 0.35rem;font-size:0.85rem">${note}</p>` : ""}
         <ul style="margin:0 0 0 1.2rem;max-height:14rem;overflow:auto">${items.map(line).join("")}</ul>`
      : "";

  const willChange = d.new.length + d.changed.length;
  const modal = backdrop.querySelector(".modal");
  modal.innerHTML = `
    <h2>Pull master list</h2>
    <p class="muted">${
      willChange || d.conflicts.length
        ? `Pulling brings this sheet up to today's master list.`
        : `This sheet already matches the master list.`
    }</p>
    ${list("Will change", d.changed, (x) =>
      `<li>${pullLabel(x)}: ${sheetValueText(x.was, x.unit)} → <strong>${sheetValueText(x.now, x.unit)}</strong></li>`
    )}
    ${list("Will be added", d.new, (x) =>
      `<li>${pullLabel(x)} at <strong>${sheetValueText(x.catalog_value, x.unit)}</strong>${x.unit && x.unit !== "RATIO" ? ` / ${esc(x.unit)}` : ""}</li>`,
      "On the master list but not on this sheet — a machine or material is costed at $0 on this job until pulled; a rate falls to its built-in default."
    )}
    ${list("Kept — you edited these", d.conflicts, (x) =>
      `<li>${pullLabel(x)}: master ${sheetValueText(x.was, x.unit)} → ${sheetValueText(x.now, x.unit)}; <strong>this job stays at ${sheetValueText(x.yours, x.unit)}</strong></li>`,
      "A pull never overwrites a price set on this job. Reset a row on the sheet if you want the master's number."
    )}
    ${list("Unpriced on the master list", d.unpriced, (x) =>
      `<li>${esc(x.label)}${x.on_sheet ? ` — this job keeps ${priceText(x.value)}` : " — not on this sheet"}</li>`,
      "Nothing is copied as $0. Price these on the master list, or on this sheet."
    )}
    ${list("No longer on the master list", d.retired, (x) =>
      `<li>${esc(x.label)} — kept at ${priceText(x.value)}</li>`
    )}
    <div class="actions" style="display:flex;gap:0.5rem;justify-content:flex-end;margin-top:1.25rem">
      <button type="button" class="btn ghost" id="pull-cancel">Cancel</button>
      <button type="button" class="btn primary" id="pull-apply" ${willChange ? "" : "disabled"}>
        ${willChange ? `Pull ${willChange} price${willChange === 1 ? "" : "s"} and reprice the job` : "Nothing to pull"}
      </button>
    </div>`;

  modal.querySelector("#pull-cancel").onclick = () => backdrop.remove();
  const apply = modal.querySelector("#pull-apply");
  apply.onclick = async () => {
    apply.disabled = true;
    apply.textContent = "Pulling…";
    try {
      const r = await Api.pullPriceSheet(estimate.id);
      backdrop.remove();
      toast(
        `Pulled ${r.new.length + r.changed.length} price${r.new.length + r.changed.length === 1 ? "" : "s"}` +
          (r.conflicts.length ? `; ${r.conflicts.length} edited row${r.conflicts.length === 1 ? "" : "s"} kept` : "") +
          " — job repriced"
      );
      if (onDone) onDone();
    } catch (err) {
      toast(err.message, "err");
      apply.disabled = false;
      apply.textContent = "Pull";
    }
  };
}

/**
 * Company settings — the master figures every new estimate starts from.
 *
 * This screen exists because sql/053 shipped `mobilization_ls` with no way to
 * set it: the only settings UI in the app was the vapor-tape picker, and half
 * a dozen numbers that decide what every bid costs — the tax rate, the fuel
 * uplift, the supervision day rates — were reachable only through the
 * database.
 *
 * The one thing it has to teach, and the reason every row wears a badge:
 *
 *   A PRICE is frozen on each estimate's price sheet when that estimate
 *   pulls. Editing it here changes what NEW work is priced at and LEAVES
 *   EVERY EXISTING JOB ALONE — by design, so a bid that went out last spring
 *   keeps the numbers it was bid with.
 *
 *   A RULE is read live. Editing it REWRITES EVERY OPEN ESTIMATE on the spot,
 *   because a correction to how the work is computed has to reach old jobs.
 *
 * Same screen, opposite consequences, and getting them the wrong way round is
 * how somebody raises a rate here, sees LBJ not move, and raises it again.
 * The badge, the group blurbs and the save toast all say which one happened.
 *
 * The taxonomy is SERVED, not re-derived here: `is_price`, `group`, `unit`
 * and `scope` all come off the row. A second copy of that split in JavaScript
 * is a copy that would disagree with the one deciding the money.
 */
// ---------- Proposal (sql/080) ----------
//
// The estimate pushed onto the bid form. One per estimate, seeded from the
// takeoff, edited here, downloaded as the .xlsx. The unit price and the
// extended never PRINT — the form's print area stops at STATUS, by the
// standing rule of 2026-08-28 — but they show here beside the estimate's own
// sale, so a rewrite never drifts unnoticed.

const PROPOSAL_BLOCKS = [
  ["alternates", "Alternates", "The five that repeat: bollards, pumping per setup, +1\" in lieu of lime, retaining walls, transformer pads."],
  ["equipment_rates", "Additional equipment rates", "Day and hour rates, one per line."],
  ["labor_rates", "Additional labor rates", ""],
  ["qualifications", "Qualifications", ""],
  ["exclusions", "Exclusions", "Anything not listed is excluded; name the subgrade and the asphalt."],
  ["terms", "Terms and conditions", "Numbered on the form, one paragraph per line."],
];

/** Six textareas, one per block, each holding the block's items one per line. */
function proposalBlocksHtml(blocks) {
  return PROPOSAL_BLOCKS.map(([key, label, hint]) => {
    const items = (blocks && blocks[key]) || [];
    const text = items.map((i) => (typeof i === "string" ? i : i.text)).join("\n");
    return `<div class="field" style="margin-bottom:0.75rem">
      <label>${esc(label)}</label>
      <textarea data-block="${key}" rows="${Math.min(14, Math.max(3, items.length + 1))}"
        style="width:100%;font-family:inherit;font-size:0.85rem">${esc(text)}</textarea>
      ${hint ? `<div class="muted" style="font-size:0.8rem">${esc(hint)}</div>` : ""}
    </div>`;
  }).join("");
}

/** A textarea's lines as a block: trimmed, blanks dropped. */
function blockLines(textarea) {
  return String(textarea ? textarea.value : "")
    .split("\n")
    .map((t) => t.trim())
    .filter(Boolean);
}

function proposalSectionColumns() {
  return [
    { f: "title", label: "Section title", placeholder: "BUILDING FOUNDATIONS - POST-TENSIONED SLAB ON GRADE" },
    { f: "sort_order", label: "Order", type: "number", step: "1" },
    { label: "Lines", derived: (r) => String(r.line_count ?? 0) },
    { label: "Proposal", derived: (r) => usd(r.total, 0), title: () => "the sum of the section's included lines — what prints as SECTION TOTAL" },
    {
      label: "Estimate",
      derived: (r) => (r.estimate_sale == null ? "—" : usd(r.estimate_sale, 0)),
      title: (r) =>
        r.estimate_sale == null
          ? "No takeoff rows filed here — typed lines only"
          : "What the takeoff rows filed in this section sell for in the estimate, wherever they were taken off",
    },
    { label: "Difference", derived: (r) => (r.difference == null ? "—" : usd(r.difference, 0)) },
  ];
}

function proposalLineColumns(sections = []) {
  return [
    {
      f: "description",
      label: "Description",
      placeholder: "PLAN MARK ITEM @ LOCATION (thickness, psi, reinforcing, finish, per detail)",
    },
    // Where the line goes on the form (Chad, 2026-09-08: the spot footings
    // that are in the mono slab under that section, the rest under site
    // work). Filing a line elsewhere moves it on save, words and numbers with it.
    {
      f: "proposal_section_id",
      label: "Section",
      type: "select",
      options: sections.map((s) => ({ id: s.id, label: s.title || "(untitled)" })),
      hint: "Where the line goes on the form. Pick another section and save to move it there.",
    },
    { f: "qty", label: "Qty", type: "number" },
    { f: "unit", label: "Unit", placeholder: "SF" },
    {
      f: "status",
      label: "Status",
      type: "select",
      options: [
        { id: "INCLUDED", label: "Included" },
        { id: "EXCLUDED", label: "Excluded" },
      ],
    },
    { f: "unit_price", label: "Unit price", type: "number", step: "0.01" },
    {
      label: "Extended",
      derived: (r) => usd(r.extended, 0),
      title: (r) =>
        r.status === "EXCLUDED"
          ? "Excluded: the quantity prints, the price does not, and it adds nothing"
          : `${num(r.qty, 3)} × ${usd(r.unit_price, 4)}`,
    },
    {
      label: "From",
      derived: (r) =>
        r.source_id
          ? r.source_missing
            ? `<span class="badge warn" title="The takeoff row behind this line is gone or at no quantity — delete the line, or keep it typed">gone</span>`
            : `<span class="muted" title="Seeded from the takeoff; Refresh re-reads its quantity and price and keeps these words">${esc(r.source_label || r.source_table)}</span>`
          : `<span class="muted" title="Typed by hand; a refresh never touches it">typed</span>`,
    },
  ];
}

async function renderProposal(root) {
  root.innerHTML = `<div class="loading">Loading proposal…</div>`;
  const estimate = await Api.getEstimate(state.estimateId);
  let p = null;
  try {
    p = await Api.proposalForEstimate(estimate.id);
  } catch (err) {
    if (!/no proposal/i.test(err.message)) throw err;
  }
  const back = () => setRoute("estimate", { estimateId: estimate.id });

  if (!p) {
    root.innerHTML = `
      <div class="page-header">
        <div>
          <button class="btn ghost" id="back-estimate">← ${esc(estimate.name)}</button>
          <h1 style="margin-top:0.5rem">Proposal</h1>
          <p>${esc(estimate.project_name || "")} · this estimate has no proposal yet</p>
        </div>
      </div>
      <div class="card">
        <p style="margin:0 0 0.75rem">
          A proposal is the estimate pushed onto the bid form: one section per estimate section, one
          line per costed takeoff row with its quantity and its sale per unit, the company's standing
          text copied in. Every line is yours to rewrite; a refresh brings the numbers back up to date
          and keeps your words.
        </p>
        <button type="button" class="btn primary" id="btn-make-proposal">Create the proposal from this estimate</button>
      </div>`;
    $("#back-estimate").onclick = back;
    $("#btn-make-proposal").onclick = async (e) => {
      e.target.disabled = true;
      try {
        await Api.createProposal(estimate.id);
        toast("Proposal seeded from the estimate");
        render();
      } catch (err) {
        toast(err.message, "err");
        e.target.disabled = false;
      }
    };
    return;
  }

  const lineCount = p.sections.reduce((a, sct) => a + sct.lines.length, 0);
  const missing = p.sections.reduce((a, sct) => a + sct.lines.filter((l) => l.source_missing).length, 0);
  const diffHint =
    p.difference == null
      ? "the estimate has no sale yet"
      : Math.abs(Number(p.difference)) < 5
        ? "the rounding of unit prices to four places"
        : "rewritten prices, typed lines, or an estimate that moved — Refresh to re-read it";
  const drawings = p.drawings && p.drawings.length
    ? p.drawings
    : ["ARCHITECTURAL", "STRUCTURAL", "CIVIL", "LANDSCAPE"].map((d) => ({ discipline: d, firm: "", plan_date: "" }));

  root.innerHTML = `
    <div class="page-header">
      <div>
        <button class="btn ghost" id="back-estimate">← ${esc(estimate.name)}</button>
        <h1 style="margin-top:0.5rem">Proposal</h1>
        <p>${esc(p.project_name || "")} · rev ${p.rev} · ${esc(p.proposal_date)} · <code>${esc(p.file_name)}</code></p>
      </div>
      <div style="display:flex;gap:0.5rem;flex-wrap:wrap">
        <button class="btn" id="btn-refresh-proposal" type="button"
          title="Pull the estimate onto the proposal again: fresh quantities and prices on every seeded line, new rows and sections added, your descriptions kept">Refresh from estimate</button>
        <a class="btn primary" id="btn-download-proposal" href="${Api.proposalXlsxUrl(p.id)}" download="${esc(p.file_name)}"
          title="The bid form as .xlsx — unit prices held outside the print area">Download .xlsx</a>
        <button class="btn danger ghost" id="btn-del-proposal" type="button">Delete proposal</button>
      </div>
    </div>

    <div class="grid stats">
      <div class="card stat"><div class="label">Proposal total</div><div class="value">${usd(p.total, 0)}</div><div class="hint">the section totals — what prints as the lump sum</div></div>
      <div class="card stat"><div class="label">Estimate sale</div><div class="value">${p.estimate_sale == null ? "—" : usd(p.estimate_sale, 0)}</div><div class="hint">every section at its markup</div></div>
      <div class="card stat"><div class="label">Difference</div><div class="value">${p.difference == null ? "—" : usd(p.difference, 0)}</div><div class="hint">${esc(diffHint)}</div></div>
      <div class="card stat"><div class="label">Lines</div><div class="value">${lineCount}</div><div class="hint">${missing ? `${missing} with no takeoff row behind` : `across ${p.sections.length} section${p.sections.length === 1 ? "" : "s"}`}</div></div>
    </div>

    <div class="card" id="proposal-header">
      <h3 style="margin:0 0 0.25rem">Header</h3>
      <p class="muted" style="margin:0 0 0.75rem;color:var(--text-muted);font-size:0.85rem">
        What the form prints above the lines. Seeded from the project; type over anything. The file is
        named to the standard, <code>&lt;Job&gt; - Proposal - &lt;#&gt; - &lt;date&gt;_&lt;rev&gt;</code>.
      </p>
      <form class="form-grid" id="proposal-header-form">
        <div class="field"><label>Submitted to</label><input name="submitted_to" value="${esc(p.submitted_to || "")}" /></div>
        <div class="field"><label>Attention</label><input name="attn" value="${esc(p.attn || "")}" placeholder="Name, title" /></div>
        <div class="field"><label>Email</label><input name="email" value="${esc(p.email || "")}" /></div>
        <div class="field"><label>Phone</label><input name="phone" value="${esc(p.phone || "")}" /></div>
        <div class="field"><label>Date</label><input type="date" name="proposal_date" value="${esc(p.proposal_date || "")}" /></div>
        <div class="field"><label>Revision</label><input type="number" name="rev" min="1" step="1" value="${esc(p.rev)}" title="The playbook's counter, _01 upward per job; the file name carries it" /></div>
        <div class="field"><label>Job</label><input name="job_label" value="${esc(p.job_label || "")}" /></div>
        <div class="field"><label>Location</label><input name="location" value="${esc(p.location || "")}" /></div>
        <div class="field" style="grid-column:1/-1"><label>Intro</label><textarea name="intro" rows="2" style="width:100%;font-family:inherit">${esc(p.intro || "")}</textarea></div>
        <div class="field" style="grid-column:1/-1"><label>Payment</label><input name="payment_terms" value="${esc(p.payment_terms || "")}" /></div>
        <div class="field full" style="grid-column:1/-1;border-top:1px solid var(--border);padding-top:0.75rem;margin-top:0.25rem">
          <div style="color:var(--text-muted);font-size:0.75rem;text-transform:uppercase;margin-bottom:0.5rem">Drawings supplied · date of plans</div>
        </div>
        ${drawings
          .map(
            (d, i) => `
        <div class="field"><label>${esc(d.discipline)}</label><input name="firm_${i}" value="${esc(d.firm || "")}" placeholder="Firm" /><input type="hidden" name="disc_${i}" value="${esc(d.discipline)}" /></div>
        <div class="field"><label>Date of plans</label><input type="date" name="date_${i}" value="${esc(d.plan_date || "")}" /></div>`
          )
          .join("")}
        <div class="modal-actions" style="grid-column:1/-1">
          <button type="submit" class="btn primary">Save header</button>
        </div>
      </form>
    </div>

    ${gridCardHtml({
      id: "proposal-sections",
      title: "Sections",
      blurb:
        "One per estimate section, in order, seeded with the section's name — retitle them the way the " +
        "GC will level them (courtyards by their plan name, ROW split from onsite, garage on its own). " +
        "<strong>Order</strong> sorts them; a section added here starts empty. A line goes wherever you " +
        "file it — its Section box, or a whole section's lines at once from the card below. " +
        "<strong>Estimate</strong> is what the takeoff rows filed in a section sell for, wherever they were " +
        "taken off, so the tie-out follows the lines: a difference beyond pennies is a rewritten price, a " +
        "typed line, or an estimate that moved.",
      columns: proposalSectionColumns(),
      rows: p.sections,
      addLabel: "Section",
      saveLabel: "Save sections",
    })}

    ${p.sections
      .map(
        (sct, i) =>
          gridCardHtml({
            id: `proposal-lines-${sct.id}`,
            title: `${i + 1}. ${sct.title || "(untitled)"}`,
            blurb:
              (sct.estimate_sale != null
                ? `Estimate ${usd(sct.estimate_sale, 0)} for the rows filed here · proposal ${usd(sct.total, 0)} · difference ${usd(sct.difference, 0)}. `
                : `Proposal ${usd(sct.total, 0)}, typed lines only. `) +
              (sct.estimate_section_name ? `Seeded from the <strong>${esc(sct.estimate_section_name)}</strong> section. ` : "") +
              "Write each description to the standard: plan mark, item, location, thickness, psi, reinforcing, " +
              "finish, the governing detail. An <strong>excluded</strong> line keeps its quantity on the form and " +
              "prices nothing — measured and excluded, not missed." +
              (p.sections.length > 1 && sct.lines.length
                ? ` <span style="white-space:nowrap">Move all ${sct.lines.length} lines to ` +
                  `<select data-move-from="${esc(sct.id)}"><option value="">—</option>${p.sections
                    .filter((o) => o.id !== sct.id)
                    .map((o) => `<option value="${esc(o.id)}">${esc(o.title || "(untitled)")}</option>`)
                    .join("")}</select> ` +
                  `<button type="button" class="btn ghost" data-move-btn="${esc(sct.id)}">Move</button></span>`
                : ""),
            columns: proposalLineColumns(p.sections),
            rows: sct.lines,
            addLabel: "Line",
            saveLabel: "Save lines",
          })
      )
      .join("")}

    <div class="card" id="proposal-text">
      <h3 style="margin:0 0 0.25rem">Standing text</h3>
      <p class="muted" style="margin:0 0 0.75rem;color:var(--text-muted);font-size:0.85rem">
        Copied from the company's library the day this proposal was made; edit it here for this job,
        or under Settings for every job after it. One bullet per line.
      </p>
      ${proposalBlocksHtml(p.items)}
      <button type="button" class="btn primary" id="btn-save-text">Save text</button>
    </div>
  `;

  $("#back-estimate").onclick = back;

  $("#btn-refresh-proposal").onclick = async (e) => {
    e.target.disabled = true;
    try {
      const res = await Api.refreshProposal(p.id);
      toast(
        `Refreshed: ${res.updated} line${res.updated === 1 ? "" : "s"} moved, ${res.added_lines} added, ` +
          `${res.added_sections} section${res.added_sections === 1 ? "" : "s"} added, ${res.missing} with no row behind`
      );
      render();
    } catch (err) {
      toast(err.message, "err");
      e.target.disabled = false;
    }
  };

  $("#btn-del-proposal").onclick = async () => {
    if (!confirm("Delete this proposal? The estimate is untouched; a new one can be seeded from it.")) return;
    try {
      await Api.deleteProposal(p.id);
      toast("Proposal deleted");
      back();
    } catch (err) {
      toast(err.message, "err");
    }
  };

  $("#proposal-header-form").onsubmit = async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    const str = (k) => String(fd.get(k) ?? "");
    const body = {
      submitted_to: str("submitted_to"),
      attn: str("attn"),
      email: str("email"),
      phone: str("phone"),
      proposal_date: str("proposal_date"),
      rev: str("rev") === "" ? "" : Number(str("rev")),
      job_label: str("job_label"),
      location: str("location"),
      intro: str("intro"),
      payment_terms: str("payment_terms"),
      drawings: drawings.map((d, i) => ({
        discipline: str(`disc_${i}`) || d.discipline,
        firm: str(`firm_${i}`),
        plan_date: str(`date_${i}`),
      })),
    };
    try {
      await Api.updateProposal(p.id, body);
      toast("Header saved");
      render();
    } catch (err) {
      toast(err.message, "err");
    }
  };

  wireGrid(root, {
    id: "proposal-sections",
    columns: proposalSectionColumns(),
    required: ["title"],
    save: async (rows) => {
      const before = p.sections.length;
      const res = await Api.bulkSaveProposalSections(p.id, rows);
      return { created: Math.max(0, res.sections.length - before), updated: Math.min(before, rows.length) };
    },
    remove: (id) => Api.deleteProposalSection(id),
  });
  $$("[data-move-btn]", root).forEach((btn) => {
    btn.onclick = async () => {
      const from = btn.dataset.moveBtn;
      const sel = root.querySelector(`select[data-move-from="${CSS.escape(from)}"]`);
      if (!sel || !sel.value) {
        toast("Pick the section to move the lines to", "err");
        return;
      }
      btn.disabled = true;
      try {
        await Api.moveProposalLines(from, sel.value);
        toast("Lines moved");
        render();
      } catch (err) {
        toast(err.message, "err");
        btn.disabled = false;
      }
    };
  });
  for (const sct of p.sections) {
    wireGrid(root, {
      id: `proposal-lines-${sct.id}`,
      columns: proposalLineColumns(p.sections),
      required: ["description"],
      blank: { status: "INCLUDED" },
      save: async (rows) => {
        const before = sct.lines.length;
        const res = await Api.bulkSaveProposalLines(sct.id, rows);
        const after = res.sections.find((x) => x.id === sct.id);
        const n = after ? after.lines.length : before;
        return { created: Math.max(0, n - before), updated: Math.min(before, rows.length) };
      },
      remove: (id) => Api.deleteProposalLine(id),
    });
  }

  $("#btn-save-text").onclick = async (e) => {
    e.target.disabled = true;
    try {
      for (const [key] of PROPOSAL_BLOCKS) {
        await Api.replaceProposalItems(p.id, key, blockLines($(`#proposal-text textarea[data-block="${key}"]`, root)));
      }
      toast("Standing text saved");
      render();
    } catch (err) {
      toast(err.message, "err");
      e.target.disabled = false;
    }
  };
}

async function renderSettings(root) {
  root.innerHTML = `<div class="loading">Loading company settings…</div>`;
  const rows = await Api.listSettings();

  // Rows arrive alphabetical by key. The GROUPS are ordered by the server's
  // own list (`group_order`), which puts the tax rate and the day rates ahead
  // of the vapor-barrier defaults — alphabetical would open this page on
  // "Vapor barrier", which is nobody's first question.
  const groups = [];
  for (const r of rows) {
    let g = groups.find((x) => x.name === r.group);
    if (!g) groups.push((g = { name: r.group, order: r.group_order ?? 99, rows: [] }));
    g.rows.push(r);
  }
  groups.sort((a, b) => a.order - b.order || a.name.localeCompare(b.name));

  const prices = rows.filter((r) => r.is_price).length;
  const unset = rows.filter((r) => !r.is_set).length;
  const odd = rows.filter((r) => r.unclassified);

  const GROUP_BLURB = {
    "Tax & uplifts":
      "The two ratios that turn quantities into money. They do not compound — " +
      "the workbook applies them as <code>× (1 + tax + fuel)</code>, and so does this.",
    Supervision:
      "Day rates, plus the pacing that decides how many days. The rates are " +
      "prices; the pacing is a rule, and an assembly with its own pace " +
      "(columns count 20 a week on a five-day week) overrides it.",
    Mobilization:
      "Getting the iron to the job and home again — one round trip. Set it " +
      "here to seed every new section, or type it on a section's " +
      "MOBILIZATION line when a job is unusual.",
    "Labor rates":
      "The COMPANY figure for each line. Every assembly can override it — " +
      "paving forms at $0.30/SF against the slab sheet's $0.45 — so this is " +
      "the fallback, not the answer.",
    Equipment: "Day rates for machines with no catalog row of their own.",
    "Waste & allowances":
      "Rules, all of them. A change here rewrites every open estimate, " +
      "because a waste factor is how the work is computed rather than what " +
      "it costs.",
    "Forming quantities":
      "Divisors and coverages — SF per box, sheets per SF. Read these as " +
      "quantities, never as money: <code>nails_16p_per_sf</code> is SF per " +
      "box, not dollars.",
    "Vapor barrier":
      "What a section gets when it names no barrier of its own. Changing a " +
      "default moves real money on every estimate that has not chosen.",
    Quotes:
      "How far from our own catalog a quote may sit before the card warns. " +
      "Deliberately wide — it catches decimal points and unit mixups, not " +
      "good buys.",
  };

  root.innerHTML = `
    <div class="page-header">
      <div>
        <h1>Company settings</h1>
        <p>
          The master figures every new estimate starts from —
          ${rows.length} of them, ${prices} prices and
          ${rows.length - prices} rules.
        </p>
      </div>
      <button type="button" class="btn ghost" id="btn-recalc-all"
        title="Rewrite every open estimate from current inputs. Final and archived bids keep their numbers.">
        Recalculate open estimates
      </button>
    </div>

    <div class="card" style="margin-bottom:1rem">
      <p style="margin:0 0 0.4rem"><strong>A price and a rule behave differently, and it matters.</strong></p>
      <p style="margin:0;color:var(--text-muted);font-size:0.9rem">
        <span class="badge">price</span>
        is frozen on each estimate's price sheet when that estimate pulls.
        Changing one here sets what <em>new</em> work is priced at and
        <strong>leaves existing jobs alone</strong> — a bid that has gone out
        keeps the numbers it was bid with. An open job picks it up when you
        pull its sheet, and shows it as drift until you do.
        <br />
        <span class="badge warn">rule</span>
        is read live. Changing one <strong>rewrites every open estimate now</strong>,
        because a correction to how the work is computed has to reach the jobs
        it was wrong on. The save will tell you how many it rewrote.
      </p>
    </div>

    ${
      unset
        ? `<div class="error-banner" style="margin-bottom:1rem">
             <strong>${unset} setting${unset === 1 ? " has" : "s have"} no value.</strong>
             A blank is not a zero — the sections that reach for it report it as
             unpriced rather than costing it at nothing. Give it a number here,
             or leave it blank on purpose.
           </div>`
        : ""
    }
    ${
      odd.length
        ? `<div class="error-banner" style="margin-bottom:1rem">
             <strong>${odd.length} key${odd.length === 1 ? " is" : "s are"} classified as neither a price nor a rule:</strong>
             ${odd.map((r) => `<code>${esc(r.key)}</code>`).join(", ")}.
             Nothing decides whether ${odd.length === 1 ? "it freezes" : "they freeze"}
             on a sheet. Worth naming in <code>price_book.py</code>.
           </div>`
        : ""
    }

    ${groups
      .map(
        (g) => `
      <div class="card" style="margin-bottom:1rem" id="grp-${esc(
        g.name.replace(/[^a-z]/gi, "").toLowerCase()
      )}">
        <h3 style="margin:0 0 0.25rem">${esc(g.name)}</h3>
        ${
          GROUP_BLURB[g.name]
            ? `<p class="muted" style="margin:0 0 0.75rem;color:var(--text-muted);font-size:0.85rem">${GROUP_BLURB[g.name]}</p>`
            : ""
        }
        <div class="table-wrap"><table class="data">
          <thead><tr>
            <th>Setting</th>
            <th style="width:4.5rem"></th>
            <th style="width:9rem">Value</th>
            <th style="width:4.5rem">Unit</th>
            <th style="width:9rem">Rewrites</th>
            <th style="width:8rem"></th>
          </tr></thead>
          <tbody>
            ${g.rows.map(settingRowHtml).join("")}
          </tbody>
        </table></div>
      </div>`
      )
      .join("")}

    <div class="card" style="margin-bottom:1rem" id="grp-proposaltext">
      <h3 style="margin:0 0 0.25rem">Proposal text</h3>
      <p class="muted" style="margin:0 0 0.75rem;color:var(--text-muted);font-size:0.85rem">
        The standing blocks every new proposal copies — alternates, equipment and labor rates,
        qualifications, exclusions, terms. One bullet per line; the terms one paragraph per line.
        A proposal already made keeps its own copy, so a change here reaches the next job.
      </p>
      <div id="proposal-library" class="muted">Loading…</div>
    </div>
  `;

  wireSettings(root);
  wireProposalLibrary(root);
}

/** The company's standing proposal text (sql/080): six blocks, each a textarea, one save. */
async function wireProposalLibrary(root) {
  const host = $("#proposal-library", root);
  if (!host) return;
  let lib;
  try {
    lib = await Api.proposalLibrary();
  } catch (err) {
    host.textContent = err.message;
    return;
  }
  host.classList.remove("muted");
  host.innerHTML =
    proposalBlocksHtml(lib.blocks) +
    `<button type="button" class="btn primary" id="btn-save-library">Save proposal text</button>`;
  $("#btn-save-library", host).onclick = async () => {
    const btn = $("#btn-save-library", host);
    btn.disabled = true;
    try {
      for (const [key] of PROPOSAL_BLOCKS) {
        await Api.replaceProposalLibraryBlock(key, blockLines($(`textarea[data-block="${key}"]`, host)));
      }
      toast("Proposal text saved — the next proposal copies it");
    } catch (err) {
      toast(err.message, "err");
    } finally {
      btn.disabled = false;
    }
  };
}

/** What a change to this key rewrites, in words rather than four booleans. */
function scopeText(scope) {
  const on = Object.entries(scope || {})
    .filter(([, v]) => v)
    .map(([k]) => k);
  if (!on.length) return "nothing stored";
  if (on.length === 4) return "every takeoff";
  return on.join(" · ");
}

function settingRowHtml(r) {
  const badge = r.is_price
    ? `<span class="badge" title="Frozen on each estimate's price sheet. Changing it here sets what NEW work is priced at.">price</span>`
    : `<span class="badge warn" title="Read live. Changing it rewrites every open estimate.">rule</span>`;
  // A boolean setting is a switch, not a number somebody types "true" into.
  const isBool = r.value === "true" || r.value === "false";
  const input = isBool
    ? `<select data-k="${esc(r.key)}" class="setting-input">
         <option value="true"${r.value === "true" ? " selected" : ""}>true</option>
         <option value="false"${r.value === "false" ? " selected" : ""}>false</option>
       </select>`
    : `<input data-k="${esc(r.key)}" class="setting-input" type="text" inputmode="decimal"
         value="${esc(r.value == null ? "" : r.value)}"
         placeholder="${r.is_set ? "" : "not set"}" style="width:8rem" />`;

  // The description is CLAMPED to two lines with the whole of it on hover.
  // Unclamped, the long ones (mobilization, the quote band) pushed the Value
  // column off the right edge of the card and the screen lost the boxes it
  // exists to show.
  const clamp =
    "display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;" +
    "overflow:hidden;font-size:0.8rem;max-width:38rem";
  return `<tr data-setting="${esc(r.key)}"${r.is_set ? "" : ' class="muted"'}>
    <td>
      <strong>${esc(r.label || r.key)}</strong>
      ${r.label ? `<div class="muted"><code>${esc(r.key)}</code></div>` : ""}
      ${
        r.description
          ? `<div class="muted" style="${clamp}" title="${esc(r.description)}">${esc(r.description)}</div>`
          : ""
      }
    </td>
    <td>${badge}</td>
    <td>${input}</td>
    <td class="muted">${esc(r.unit || "")}</td>
    <td class="muted" style="font-size:0.8rem">${esc(scopeText(r.scope))}</td>
    <td style="white-space:nowrap">
      <button type="button" class="btn ghost setting-save" data-k="${esc(r.key)}">Save</button>
      ${
        // Only offer to blank a PRICE. Blanking a rule would leave the code
        // default in charge with nothing on screen saying so, which is the
        // opposite of what this screen is for.
        r.is_price && r.is_set
          ? `<button type="button" class="btn danger ghost setting-clear" data-k="${esc(r.key)}"
               title="Clear back to unset. Not zero — sections that reach for it will report it as unpriced.">Clear</button>`
          : ""
      }
    </td>
  </tr>`;
}

function wireSettings(root) {
  const save = async (key, value) => {
    const btn = root.querySelector(`.setting-save[data-k="${CSS.escape(key)}"]`);
    if (btn) btn.disabled = true;
    try {
      const report = await Api.updateSetting(key, value);
      const n = (report.recalculated || []).length;
      const m = sectionsMoved(report);
      const skipped = (report.skipped || []).length;
      let msg =
        value === null
          ? `${key} cleared`
          : `${key} saved`;
      // The whole point of the badge, said again at the moment it matters.
      if (n) msg += ` — rewrote ${n} open estimate${n === 1 ? "" : "s"} (${m} section${m === 1 ? "" : "s"})`;
      else msg += " — no stored estimate changed";
      if (skipped) msg += `, ${skipped} final/archived left alone`;
      toast(msg);
      render();
    } catch (err) {
      toast(err.message, "err");
      if (btn) btn.disabled = false;
    }
  };

  $$(".setting-save").forEach((btn) => {
    btn.onclick = () => {
      const key = btn.dataset.k;
      const el = root.querySelector(`.setting-input[data-k="${CSS.escape(key)}"]`);
      const raw = (el?.value ?? "").trim();
      // An emptied box means UNSET, which is a real state here and not a zero.
      // Sending "" would land as the string "" and read back as unset anyway,
      // but null says so on purpose.
      save(key, raw === "" ? null : raw);
    };
  });

  $$(".setting-clear").forEach((btn) => {
    btn.onclick = () => save(btn.dataset.k, null);
  });

  const rc = $("#btn-recalc-all");
  if (rc) {
    rc.onclick = async () => {
      rc.disabled = true;
      try {
        const report = await Api.recalcAllEstimates();
        const n = (report.recalculated || []).length;
        const m = sectionsMoved(report);
        const s = (report.skipped || []).length;
        toast(
          `Rewrote ${n} open estimate${n === 1 ? "" : "s"} (${m} section${m === 1 ? "" : "s"})` +
            (s ? `, left ${s} final/archived at their bid numbers` : "")
        );
      } catch (err) {
        toast(err.message, "err");
      }
      rc.disabled = false;
    };
  }
}

/**
 * Rates on ONE section (sql/055).
 *
 * Chad, 2026-09-04, asked where a per-job rate change belongs: "I think making
 * rates changes per section is what I would like the best" — because what
 * makes a sub cheaper is the size of THESE pours, not the whole job.
 *
 * The editing is the easy half. The card's real job is **saying where each
 * number came from**, because a rate you cannot trace is a rate you cannot
 * defend three months later:
 *
 *     section   this section said so                 ← beats everything
 *     job       the estimate's price sheet, or its rule override
 *     assembly  what a paving section does
 *     company   what S&S does
 *     default   the literal in the code, when nothing else answered
 *
 * Every row carries the whole ladder in its tooltip, so "$0.42 here where the
 * company says $0.55" reads as a decision rather than a typo.
 *
 * Collapsed to the overrides by default. A paving section reads 37 rates and
 * a card that opens on all of them is one nobody scrolls past.
 */
/**
 * Rules for this job (sql/055's `estimate_rules`, given a screen).
 *
 * The card that was missing from the middle of the ladder. What it has to
 * teach, and the reason the blurb leads with it:
 *
 *   a PRICE is frozen on this job's price sheet at the pull, so a company
 *   change leaves the bid alone;
 *
 *   a RULE is read LIVE, so a correction to how the work is COMPUTED reaches
 *   the jobs it was made for.
 *
 * Which is why prices are not on this card at all, and why the sentence
 * pointing at the price sheet is not an afterthought.
 */
function renderEstimateRulesCard(rules) {
  if (!rules) return "";
  const rows = rules.rows || [];
  if (!rows.length) {
    return `<div class="card" id="estimate-rules" style="margin-top:1rem">
      <h3 style="margin:0 0 0.35rem">Rules for this job</h3>
      <p class="muted" style="margin:0;color:var(--text-muted);font-size:0.85rem">
        Nothing to set yet — rules appear here once the job has a section that
        reads one.
      </p>
    </div>`;
  }
  const set = rows.filter((r) => r.job_value != null);
  const rest = rows.filter((r) => r.job_value == null);

  // Grouped by the SERVED taxonomy, in the SERVED order. Sorting by name here
  // is how the settings screen ended up alphabetical with tax below vapour
  // barrier — the order is a decision, and it is made once, server-side.
  const groups = [];
  rest.forEach((r) => {
    let g = groups.find((x) => x.name === r.group);
    if (!g) groups.push((g = { name: r.group, order: r.group_order, rows: [] }));
    g.rows.push(r);
  });
  groups.sort((a, b) => a.order - b.order);

  return `
    <div class="card" id="estimate-rules" style="margin-top:1rem">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:1rem;flex-wrap:wrap">
        <div style="max-width:52rem">
          <h3 style="margin:0">Rules for this job</h3>
          <p style="margin:0.25rem 0 0;color:var(--text-muted);font-size:0.85rem">
            A <strong>rule</strong> is how the work is computed — waste factors,
            divisors, supervision pacing, geometry. Rules are read
            <strong>live</strong>, so setting one here changes this job now and
            a company correction still reaches it later. Set on the job, it
            beats the assembly and the company; a section can still say
            something different on its own card.
            <br />
            A <strong>price</strong> is not here. Prices are frozen on this
            job's <a href="#prices/${esc(rules.estimate_id)}">price sheet</a> at
            the pull — that is the point of them — so they are edited there.
          </p>
        </div>
        <div class="card stat" style="min-width:9rem;margin:0">
          <div class="label">Set on this job</div>
          <div class="value">${set.length}</div>
          <div class="hint">of ${rows.length} in play</div>
        </div>
      </div>

      ${
        set.length
          ? `<div class="table-wrap" style="margin-top:0.75rem"><table class="data">
               <thead><tr>
                 <th>Rule</th><th style="width:8rem">This job</th>
                 <th style="width:8rem">Would be</th><th>Why</th><th style="width:6rem"></th>
               </tr></thead>
               <tbody>${set.map((r) => estimateRuleRowHtml(r, true)).join("")}</tbody>
             </table></div>`
          : `<p class="muted" style="margin:0.75rem 0 0;color:var(--text-muted);font-size:0.85rem">
               Nothing is set on this job — every rule below comes from the
               assembly or the company.
             </p>`
      }

      ${groups
        .map(
          (g) => `<details style="margin-top:0.5rem">
          <summary style="cursor:pointer;color:var(--text-muted);font-size:0.85rem">
            ${esc(g.name)} · ${g.rows.length}
          </summary>
          <div class="table-wrap" style="margin-top:0.5rem"><table class="data">
            <thead><tr>
              <th>Rule</th><th style="width:8rem">This job</th>
              <th style="width:8rem">From</th><th>Why</th><th style="width:6rem"></th>
            </tr></thead>
            <tbody>${g.rows.map((r) => estimateRuleRowHtml(r, false)).join("")}</tbody>
          </table></div>
        </details>`
        )
        .join("")}
    </div>`;
}

/** The ladder in words, for the tooltip. Assembly values are per KIND. */
function ruleLadderText(r) {
  const bits = [];
  if (r.job_value != null) bits.push(`job ${Number(r.job_value)}`);
  Object.keys(r.assembly_values || {})
    .sort()
    .forEach((k) => bits.push(`${k} ${Number(r.assembly_values[k])}`));
  if (r.company_value != null) bits.push(`company ${Number(r.company_value)}`);
  if (r.default_value != null) bits.push(`code default ${Number(r.default_value)}`);
  return bits.length ? bits.join("  ·  ") : "nothing has a value for this";
}

function estimateRuleRowHtml(r, isSet) {
  // "Would be" on a row that is set is what the job falls BACK to — not
  // `r.source`, which after a write always reads "job" and would make the
  // column say a number came from the row replacing it. Same bug the section
  // card had and the same fix.
  let fallback = r.value;
  let fallbackSource = r.source;
  if (isSet) {
    const asm = Object.values(r.assembly_values || {});
    const one = asm.length && asm.every((v) => Number(v) === Number(asm[0]));
    const ladder = [
      ["assembly", one ? asm[0] : null],
      ["company", r.company_value],
      ["default", r.default_value],
    ].find(([, v]) => v !== null && v !== undefined);
    fallback = ladder ? ladder[1] : null;
    fallbackSource = ladder ? ladder[0] : "nothing";
  }

  // Who is NOT listening, and why. A job rule that quietly does nothing on
  // half the sections is the class of bug this app keeps finding in the
  // workbook — so it is stated on the row, not left to be discovered.
  const off = r.overridden_by || [];
  const columnKind = off.some((s) => s.source === "column");
  const notListening = off.length
    ? `<div class="badge warn" title="${esc(
        off
          .map((s) => `${s.name}: ${Number(s.value)} (${s.source === "column" ? "set on the section" : "section rate"})`)
          .join("  ·  ")
      )}">${
        off.length === 1
          ? `1 section ${columnKind ? "sets its own" : "overrides this"}`
          : `${off.length} sections ${columnKind ? "set their own" : "override this"}`
      }</div>`
    : "";

  return `<tr data-rule="${esc(r.key)}">
    <td style="max-width:26rem">
      <strong>${esc(r.label)}</strong>
      ${
        r.is_section_column
          ? ` <span class="badge" title="Also a field on each section. A section that has its own value uses that instead — it is read before this ladder runs.">per-section field</span>`
          : ""
      }
      <div class="muted"><code>${esc(r.key)}</code>${r.unit ? ` · ${esc(r.unit)}` : ""}</div>
      ${
        r.description
          ? `<div class="muted" style="white-space:normal;font-size:0.78rem">${esc(r.description)}</div>`
          : ""
      }
      ${notListening}
    </td>
    <td class="num">
      <input type="number" step="any" class="rule-val" data-k="${esc(r.key)}"
        value="${r.job_value == null ? "" : Number(r.job_value)}"
        placeholder="${fallback == null ? "" : Number(fallback)}" style="width:6.5rem" />
    </td>
    <td class="num muted" title="${esc(ruleLadderText(r))}">
      ${fallback == null ? "—" : Number(fallback)}
      <div class="muted" style="font-size:0.75rem">${esc(fallbackSource)}</div>
    </td>
    <td>
      <input type="text" class="rule-note" data-k="${esc(r.key)}" maxlength="200"
        value="${esc(r.note || "")}" placeholder="${isSet ? "who said so" : ""}" />
    </td>
    <td style="white-space:nowrap">
      <button type="button" class="btn ghost rule-save" data-k="${esc(r.key)}">Save</button>
      ${
        isSet
          ? `<button type="button" class="btn danger ghost rule-clear" data-k="${esc(r.key)}"
               title="Remove the job rule and let the assembly or company decide again">Clear</button>`
          : ""
      }
    </td>
  </tr>`;
}

function wireEstimateRules(estimate) {
  // Every write repriced the WHOLE job, so the page is re-rendered rather than
  // patched: the section table above it is now stale by definition.
  $$(".rule-save").forEach((btn) => {
    btn.onclick = async () => {
      const key = btn.dataset.k;
      const val = $(`.rule-val[data-k="${CSS.escape(key)}"]`);
      const note = $(`.rule-note[data-k="${CSS.escape(key)}"]`);
      const raw = (val?.value ?? "").trim();
      btn.disabled = true;
      try {
        // An emptied box is "stop overriding", not zero. A zero rule is a
        // statement somebody makes on purpose; a blank is not one.
        if (raw === "") {
          await Api.clearEstimateRule(estimate.id, key);
          toast("Rule cleared — the assembly or company decides again");
        } else {
          await Api.setEstimateRule(estimate.id, key, raw, note?.value || null);
          toast("Rule set on this job — every section repriced");
        }
        render();
      } catch (err) {
        toast(err.message, "err");
        btn.disabled = false;
      }
    };
  });
  $$(".rule-clear").forEach((btn) => {
    btn.onclick = async () => {
      btn.disabled = true;
      try {
        await Api.clearEstimateRule(estimate.id, btn.dataset.k);
        toast("Rule cleared — the assembly or company decides again");
        render();
      } catch (err) {
        toast(err.message, "err");
        btn.disabled = false;
      }
    };
  });
}

function renderSectionRatesCard(rates) {
  if (!rates) return "";
  const rows = rates.rows || [];
  // Chad's policy, 2026-09-04: "each section should be separate from the
  // others for labor ... materials should be standard across the estimate.
  // concrete and materials are quoted per job so should be edited that way."
  //
  // So the job-level rates are SHOWN — you still want to see what this section
  // is paying for PT cable — but read-only, with somewhere to go. Hiding them
  // would leave the card looking like the whole story when it is not.
  const mine = rows.filter((r) => r.level !== "estimate");
  const jobOnly = rows.filter((r) => r.level === "estimate");
  const over = mine.filter((r) => r.source === "section");
  const rest = mine.filter((r) => r.source !== "section");

  return `
    <div class="card" id="section-rates" style="margin-top:1rem">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:1rem;flex-wrap:wrap">
        <div>
          <h3 style="margin:0">Rates on this section</h3>
          <p style="margin:0.25rem 0 0;color:var(--text-muted);font-size:0.85rem">
            <strong>Rates are always per section.</strong> Every rate this
            section reads is its own — seeded when the section was created,
            from the job's price sheet or the company's defaults — and nothing
            that happens to those afterwards moves this section. Change one
            here and it is this section's number; <em>Clear</em> hands it back
            to whatever the job, the assembly or the company says today.
            <strong>Supervision day rates, mobilization, equipment day rates
            and materials are set for the whole job</strong> on the
            <a href="#prices/${esc(rates.estimate_id)}">price sheet</a> —
            they are quoted per job, so they are edited that way.
          </p>
        </div>
        <div class="card stat" style="min-width:9rem;margin:0">
          <div class="label">This section's own</div>
          <div class="value">${over.length}</div>
          <div class="hint">of ${mine.length} it reads</div>
        </div>
      </div>

      ${
        over.length
          ? `<div class="table-wrap" style="margin-top:0.75rem"><table class="data">
               <thead><tr>
                 <th>Rate</th><th style="width:4.5rem"></th><th style="width:8rem">This section</th>
                 <th style="width:8rem">Would be</th><th>Why</th><th style="width:6rem"></th>
               </tr></thead>
               <tbody>${over.map((r) => sectionRateRowHtml(r, true)).join("")}</tbody>
             </table></div>`
          : `<p class="muted" style="margin:0.75rem 0 0;color:var(--text-muted);font-size:0.85rem">
               Nothing is this section's own yet — every rate below comes from
               the job, the assembly or the company. (Sections made before
               2026-09-05 were seeded by the backfill; a section with no takeoff
               rows may read nothing until it has some.)
             </p>`
      }

      <details style="margin-top:0.75rem">
        <summary style="cursor:pointer;color:var(--text-muted);font-size:0.85rem">
          ${rest.length} more this section reads — click to set one
        </summary>
        <div class="table-wrap" style="margin-top:0.5rem"><table class="data">
          <thead><tr>
            <th>Rate</th><th style="width:4.5rem"></th><th style="width:8rem">This section</th>
            <th style="width:8rem">From</th><th>Why</th><th style="width:6rem"></th>
          </tr></thead>
          <tbody>${rest.map((r) => sectionRateRowHtml(r, false)).join("")}</tbody>
        </table></div>
      </details>

      ${
        jobOnly.length
          ? `<details style="margin-top:0.5rem">
               <summary style="cursor:pointer;color:var(--text-muted);font-size:0.85rem">
                 ${jobOnly.length} set for the whole job — materials, tax and
                 company conventions
               </summary>
               <p class="muted" style="margin:0.5rem 0 0;color:var(--text-muted);font-size:0.8rem">
                 These are the same on every section of this job. Change one on
                 the <a href="#prices/${esc(rates.estimate_id)}">price sheet</a>
                 or in <strong>Company settings</strong>.
               </p>
               <div class="table-wrap" style="margin-top:0.5rem"><table class="data">
                 <thead><tr>
                   <th>Rate</th><th style="width:4.5rem"></th>
                   <th style="width:8rem">This job</th><th style="width:8rem">From</th>
                 </tr></thead>
                 <tbody>${jobOnly.map(jobRateRowHtml).join("")}</tbody>
               </table></div>
             </details>`
          : ""
      }
    </div>`;
}

/** A job-level rate, shown so the section is legible — not editable here. */
function jobRateRowHtml(r) {
  return `<tr${r.was_read ? "" : ' class="muted"'}>
    <td>
      <strong>${esc(r.label)}</strong>
      <div class="muted"><code>${esc(r.key)}</code>${r.unit ? ` · ${esc(r.unit)}` : ""}</div>
    </td>
    <td><span class="badge info" title="Set for the whole job — materials are quoted per job, not per section">job</span></td>
    <td class="num">${r.value == null ? "\u2014" : Number(r.value)}</td>
    <td class="num muted" style="font-size:0.8rem" title="${esc(rateLadderText(r))}">${esc(r.source)}</td>
  </tr>`;
}

/** The ladder in words, for the tooltip. */
function rateLadderText(r) {
  const bits = [];
  const add = (name, v) => {
    if (v !== null && v !== undefined) bits.push(`${name} ${Number(v)}`);
  };
  add("section", r.section_value);
  add("job", r.job_value);
  add("assembly", r.assembly_value);
  add("company", r.company_value);
  add("code default", r.default_value);
  return bits.length ? bits.join("  ·  ") : "nothing has a value for this";
}

function sectionRateRowHtml(r, isOverride) {
  const badge = r.is_price
    ? `<span class="badge" title="A price. Frozen on the job's sheet unless set here.">price</span>`
    : `<span class="badge warn" title="A rule — how the work is computed. Read live unless set here.">rule</span>`;
  // "Would be" on an override is what the section would fall back to; on a
  // normal row it is where the live number came from. Same column, and the
  // header changes with it, because both answer "and if I clear this?".
  // On an override, this is what the section would fall BACK to, and the
  // little label under it has to name that rung — not `r.source`, which after
  // an override always reads "section" and made the column say a number came
  // from the very row that was replacing it.
  let fallback = r.value;
  let fallbackSource = r.source;
  if (isOverride) {
    const ladder = [
      ["job", r.job_value],
      ["assembly", r.assembly_value],
      ["company", r.company_value],
      ["default", r.default_value],
    ].find(([, v]) => v !== null && v !== undefined);
    fallback = ladder ? ladder[1] : null;
    fallbackSource = ladder ? ladder[0] : "nothing";
  }
  return `<tr data-rate="${esc(r.key)}"${r.was_read ? "" : ' class="muted"'}>
    <td>
      <strong>${esc(r.label)}</strong>
      <div class="muted"><code>${esc(r.key)}</code>${
        r.unit ? ` · ${esc(r.unit)}` : ""
      }${r.was_read ? "" : " · not read by this section today"}</div>
    </td>
    <td>${badge}</td>
    <td class="num">
      <input type="number" step="any" min="0" class="rate-val" data-k="${esc(r.key)}"
        value="${r.section_value == null ? "" : Number(r.section_value)}"
        placeholder="${fallback == null ? "" : Number(fallback)}" style="width:6.5rem" />
    </td>
    <td class="num muted" title="${esc(rateLadderText(r))}">
      ${fallback == null ? "—" : Number(fallback)}
      <div class="muted" style="font-size:0.75rem">${esc(fallbackSource)}</div>
    </td>
    <td>
      <input type="text" class="rate-note" data-k="${esc(r.key)}" maxlength="200"
        value="${esc(r.note || "")}"
        placeholder="${isOverride ? "who said so" : ""}" />
    </td>
    <td style="white-space:nowrap">
      <button type="button" class="btn ghost rate-save" data-k="${esc(r.key)}">Save</button>
      ${
        isOverride
          ? `<button type="button" class="btn danger ghost rate-clear" data-k="${esc(r.key)}"
               title="Hand this rate back — the job, the assembly or the company decides again, and follows them from now on">Clear</button>`
          : ""
      }
    </td>
  </tr>`;
}

function wireSectionRates(root, section) {
  $$(".rate-save").forEach((btn) => {
    btn.onclick = async () => {
      const key = btn.dataset.k;
      const val = root.querySelector(`.rate-val[data-k="${CSS.escape(key)}"]`);
      const note = root.querySelector(`.rate-note[data-k="${CSS.escape(key)}"]`);
      const raw = (val?.value ?? "").trim();
      btn.disabled = true;
      try {
        if (raw === "") {
          // An emptied box is "stop overriding", not "zero". A zero rate is a
          // statement somebody makes on purpose; a blank is not one.
          await Api.clearSectionRate(section.id, key);
          toast(`${key} back to the job / assembly / company rate`);
        } else {
          await Api.setSectionRate(section.id, key, raw, note?.value);
          toast(`${key} set on this section — the section was recalculated`);
        }
        render();
      } catch (err) {
        toast(err.message, "err");
        btn.disabled = false;
      }
    };
  });
  $$(".rate-clear").forEach((btn) => {
    btn.onclick = async () => {
      btn.disabled = true;
      try {
        await Api.clearSectionRate(section.id, btn.dataset.k);
        toast(`${btn.dataset.k} back to the job / assembly / company rate`);
        render();
      } catch (err) {
        toast(err.message, "err");
        btn.disabled = false;
      }
    };
  });
}

async function render() {
  const root = $("#app");
  if (state.user && state.user.role === "foreman" && state.route !== "report") {
    // The field's role (sql/084): the daily report is the whole app.
    setRoute("report");
    return;
  }
  try {
    if (state.route === "home") await renderHome(root);
    else if (state.route === "projects") await renderProjects(root);
    else if (state.route === "bids") await renderBids(root);
    else if (state.route === "daily") await renderDaily(root);
    else if (state.route === "calendar") await renderCalendar(root);
    else if (state.route === "report") await renderReportForm(root);
    else if (state.route === "project") await renderProjectDetail(root);
    else if (state.route === "estimate") await renderEstimateSummary(root);
    else if (state.route === "section") await renderSectionDetail(root);
    else if (state.route === "prices") await renderPriceSheet(root);
    else if (state.route === "proposal") await renderProposal(root);
    else if (state.route === "users") await renderEstimators(root);
    else if (state.route === "mixes") await renderMixes(root);
    else if (state.route === "materials") await renderMaterials(root);
    else if (state.route === "equipment") await renderEquipment(root);
    else if (state.route === "settings") await renderSettings(root);
    else if (state.route === "activity") await renderActivity(root);
    else {
      root.innerHTML = `<div class="error-banner">Unknown page: ${esc(state.route)}</div>`;
    }
  } catch (err) {
    root.innerHTML = `<div class="error-banner">${esc(err.message)}</div>
      <p class="muted" style="color:var(--text-muted)">Is the API running on port 8001?</p>`;
  }
}

function syncNavActive() {
  $$(".nav button").forEach((b) => {
    const active =
      b.dataset.route === state.route ||
      (state.route === "project" && b.dataset.route === "projects") ||
      (state.route === "estimate" && b.dataset.route === "projects") ||
      (state.route === "section" && b.dataset.route === "projects") ||
      (state.route === "prices" && b.dataset.route === "projects") ||
      (state.route === "proposal" && b.dataset.route === "projects") ||
      (state.route === "report" && b.dataset.route === "daily");
    b.classList.toggle("active", active);
  });
}

// ---------- Sign-in (sql/068) ----------
//
// Every API route but sign-in needs a session, and the role decides what the
// session may write (backend/app/policy.py). The API is the gate; here the
// nav just stops offering what the role cannot do, and a 403 shows as the
// server's own sentence in a toast.

const ROLE_RANK = { user: 0, estimator: 1, senior_estimator: 2, admin: 3 };
const ROLE_LABELS = {
  user: "user",
  estimator: "estimator",
  senior_estimator: "senior estimator",
  admin: "admin",
  // Apart from the ladder (sql/084): the daily report and nothing else.
  foreman: "foreman",
};

/** Is the signed-in person at least this role? */
function canAct(role) {
  return !!state.user && (ROLE_RANK[state.user.role] ?? -1) >= (ROLE_RANK[role] ?? 99);
}

function renderSignIn() {
  closeAllModals();
  $$(".nav button").forEach((b) => {
    b.disabled = true;
  });
  paintUserFoot();
  const root = $("#app");
  root.innerHTML = `
    <div class="card" style="max-width:24rem;margin:4rem auto">
      <h2 style="margin-top:0">Sign in</h2>
      <p style="color:var(--text-muted);font-size:0.9rem;margin-top:0">
        Your S&amp;S Concrete username and password.
      </p>
      <form id="signin-form" class="form-grid" style="grid-template-columns:1fr">
        <div class="field"><label>Username</label>
          <input name="username" autocomplete="username" required autofocus /></div>
        <div class="field"><label>Password</label>
          <input name="password" type="password" autocomplete="current-password" required /></div>
        <div id="signin-error" class="error-banner hidden"></div>
        <div class="modal-actions"><button type="submit" class="btn primary">Sign in</button></div>
      </form>
    </div>`;
  $("#signin-form", root).onsubmit = async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    const btn = e.target.querySelector("button[type=submit]");
    btn.disabled = true;
    try {
      state.user = await Api.login(String(fd.get("username")).trim(), String(fd.get("password")));
      enter();
    } catch (err) {
      const box = $("#signin-error", root);
      box.textContent = err.message;
      box.classList.remove("hidden");
      btn.disabled = false;
    }
  };
}

function paintUserFoot() {
  const el = $("#user-foot");
  if (!el) return;
  if (!state.user) {
    el.innerHTML = "";
    return;
  }
  el.innerHTML = `Signed in as <strong>${esc(state.user.full_name)}</strong> · ${esc(
    ROLE_LABELS[state.user.role] || state.user.role
  )}<br /><a href="#" id="btn-password">change password</a> · <a href="#" id="btn-signout">sign out</a>`;
  $("#btn-signout", el).onclick = async (e) => {
    e.preventDefault();
    try {
      await Api.logout();
    } catch {
      // the cookie is gone either way
    }
    state.user = null;
    renderSignIn();
  };
  $("#btn-password", el).onclick = (e) => {
    e.preventDefault();
    openPasswordModal();
  };
}

/** The nav offers what the role can do; everything else is the API's 403. */
function applyRole() {
  paintUserFoot();
  const field = !!state.user && state.user.role === "foreman";
  $$(".nav .section-label").forEach((el) => el.classList.toggle("hidden", field));
  $$(".nav button").forEach((b) => {
    b.disabled = false;
    if (field) {
      // The field's role (sql/084): the daily report and nothing else.
      b.classList.toggle("hidden", b.dataset.route !== "report");
      return;
    }
    if (b.dataset.route === "report") {
      b.classList.add("hidden"); // the office reaches the form from Daily reports
      return;
    }
    const need =
      b.dataset.route === "users"
        ? "admin"
        : b.dataset.route === "settings" || b.dataset.route === "activity"
        ? "senior_estimator"
        : null;
    b.classList.toggle("hidden", !!need && !canAct(need));
  });
}

function openPasswordModal() {
  const backdrop = document.createElement("div");
  backdrop.className = "modal-backdrop";
  backdrop.innerHTML = `
    <div class="modal">
      <h2>Change password</h2>
      <form id="pw-form" class="form-grid" style="grid-template-columns:1fr">
        <div class="field"><label>Current password</label>
          <input name="current" type="password" autocomplete="current-password" required /></div>
        <div class="field"><label>New password (8+ characters)</label>
          <input name="next" type="password" autocomplete="new-password" minlength="8" required /></div>
        <div class="field"><label>Again</label>
          <input name="again" type="password" autocomplete="new-password" minlength="8" required /></div>
        <div class="modal-actions">
          <button type="button" class="btn ghost" id="cancel">Cancel</button>
          <button type="submit" class="btn primary">Change</button>
        </div>
      </form>
    </div>`;
  document.body.appendChild(backdrop);
  $("#cancel", backdrop).onclick = () => backdrop.remove();
  $("#pw-form", backdrop).onsubmit = async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    if (fd.get("next") !== fd.get("again")) {
      toast("The two new passwords differ", "err");
      return;
    }
    try {
      await Api.changePassword(String(fd.get("current")), String(fd.get("next")));
      toast("Password changed — your other sessions were signed out");
      backdrop.remove();
    } catch (err) {
      toast(err.message, "err");
    }
  };
}

/** Signed in: read the hash and render it. */
function enter() {
  applyRole();
  const p = parseHash();
  state.route = p.route;
  state.projectId = p.projectId;
  state.estimateId = p.estimateId;
  state.sectionId = p.sectionId || null;
  state.reportId = p.reportId || null;
  syncNavActive();
  render();
}

async function init() {
  $$(".nav button").forEach((btn) => {
    btn.addEventListener("click", () => setRoute(btn.dataset.route));
  });
  window.addEventListener("hashchange", () => {
    if (!state.user) return; // the sign-in screen stays until there is a session
    closeAllModals();
    const p = parseHash();
    state.route = p.route;
    state.projectId = p.projectId;
    state.estimateId = p.estimateId;
    state.sectionId = p.sectionId || null;
  state.reportId = p.reportId || null;
    syncNavActive();
    render();
  });
  // A 401 from any request (the session expired, or a password reset ended
  // it) brings the sign-in screen back; the hash is kept, so signing in
  // returns to the same page.
  window.addEventListener("estimating:signin", () => {
    if (state.user === null) return;
    state.user = null;
    renderSignIn();
  });
  checkHealth();
  try {
    state.user = await Api.me();
  } catch {
    state.user = null;
  }
  if (!state.user) {
    renderSignIn();
    return;
  }
  enter();
}

initDaily({ state, $, $$, esc, toast, setRoute, canAct, render });
init();
