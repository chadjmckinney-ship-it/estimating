import { Api } from "./api.js";

const $ = (sel, el = document) => el.querySelector(sel);
const $$ = (sel, el = document) => [...el.querySelectorAll(sel)];

const state = {
  route: "home",
  projectId: null,
  estimateId: null,
  estimators: [],
  projectTypes: [],
  projectStatuses: [],
  mixes: [],
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

function num(n, digits = 2) {
  if (n == null || n === "") return "—";
  const v = Number(n);
  if (Number.isNaN(v)) return "—";
  return v.toLocaleString(undefined, {
    minimumFractionDigits: 0,
    maximumFractionDigits: digits,
  });
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

function setRoute(route, params = {}) {
  state.route = route;
  state.projectId = params.projectId || null;
  state.estimateId = params.estimateId || null;
  $$(".nav button").forEach((b) => {
    const active =
      b.dataset.route === route ||
      (route === "project" && b.dataset.route === "projects") ||
      (route === "estimate" && b.dataset.route === "projects");
    b.classList.toggle("active", active);
  });
  render();
  let hash = `#${route}`;
  if (route === "project" && state.projectId) hash = `#project/${state.projectId}`;
  if (route === "estimate" && state.estimateId) hash = `#estimate/${state.estimateId}`;
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
  return { route: h, projectId: null, estimateId: null };
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

async function renderHome(root) {
  root.innerHTML = `<div class="loading">Loading dashboard…</div>`;
  const [projects, estimates, mixes, materials, equipment, estimators] = await Promise.all([
    Api.listProjects(),
    Api.listEstimates(),
    Api.listMixes({ active_only: true }),
    Api.listMaterials({ active_only: true }),
    Api.listEquipment({ active_only: true }),
    Api.listEstimators({ active_only: true }),
  ]);
  const open = projects.filter((p) => !["archived", "awarded", "lost", "no_bid"].includes(p.status));
  root.innerHTML = `
    <div class="page-header">
      <div>
        <h1>Estimating</h1>
        <p>S&amp;S Concrete — Mono Slab first. Catalogs and bids live here.</p>
      </div>
      <button class="btn primary" id="go-projects">View projects</button>
    </div>
    <div class="grid stats">
      <div class="card stat"><div class="label">Projects</div><div class="value">${projects.length}</div><div class="hint">${open.length} open</div></div>
      <div class="card stat"><div class="label">Estimates</div><div class="value">${estimates.length}</div><div class="hint">draft packages</div></div>
      <div class="card stat"><div class="label">Mix designs</div><div class="value">${mixes.length}</div></div>
      <div class="card stat"><div class="label">Materials</div><div class="value">${materials.length}</div></div>
      <div class="card stat"><div class="label">Equipment</div><div class="value">${equipment.length}</div></div>
      <div class="card stat"><div class="label">Estimators</div><div class="value">${estimators.length}</div></div>
    </div>
    <div class="card">
      <h3 style="margin:0 0 0.75rem">Recent projects</h3>
      ${projectsTable(projects.slice(0, 8), { compact: true })}
    </div>
  `;
  $("#go-projects")?.addEventListener("click", () => setRoute("projects"));
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
      project_types: types,
      created_by: fd.get("created_by") || null,
      plans_url: fd.get("plans_url") || null,
      notes: fd.get("notes") || null,
    };
    try {
      if (isEdit) await Api.updateProject(existing.id, body);
      else await Api.createProject(body);
      toast(isEdit ? "Project updated" : "Project created");
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
        <div><div class="k">Types</div><div class="v chips">${(project.project_types || []).map((t) => `<span class="chip">${esc(t)}</span>`).join("") || "—"}</div></div>
        <div><div class="k">Plans</div><div class="v">${project.plans_url ? `<a href="${esc(project.plans_url)}" target="_blank" rel="noopener">Open link</a>` : "—"}</div></div>
      </div>
      ${project.notes ? `<p class="muted" style="margin:0;color:var(--text-muted)">${esc(project.notes)}</p>` : ""}
    </div>
    <div class="card">
      <h3 style="margin:0 0 0.75rem">Estimates</h3>
      ${
        estimates.length
          ? `<div class="table-wrap"><table class="data">
        <thead><tr><th>Name</th><th>Version</th><th>Status</th><th>Estimator</th><th>Waste C/S/R</th><th>Updated</th><th></th></tr></thead>
        <tbody>
          ${estimates
            .map(
              (e) => `<tr data-estimate-id="${esc(e.id)}">
              <td><strong>${esc(e.name)}</strong></td>
              <td class="num">${e.version}</td>
              <td>${statusBadge(e.status)}</td>
              <td class="muted">${esc(e.estimator_name || "—")}</td>
              <td class="muted num">${[e.waste_concrete, e.waste_sand, e.waste_rebar].map((x) => (x == null ? "—" : Number(x))).join(" / ")}</td>
              <td class="muted">${esc((e.updated_at || "").slice(0, 16).replace("T", " "))}</td>
              <td>
                <button type="button" class="btn ghost btn-open-est" data-id="${esc(e.id)}">Open</button>
                <button type="button" class="btn ghost btn-edit-est" data-id="${esc(e.id)}">Edit</button>
              </td>
            </tr>`
            )
            .join("")}
        </tbody></table></div>`
          : `<div class="empty">No estimates yet. Create a draft package for this job.</div>`
      }
      <p style="color:var(--text-muted);font-size:0.85rem;margin:0.75rem 0 0">
        Open an estimate to enter Mono Slab pours and see locked calcs.
      </p>
    </div>
  `;

  $("#back").onclick = () => setRoute("projects");
  $("#edit-proj").onclick = () => openProjectModal(project);
  $("#new-est").onclick = () => openEstimateModal(project);
  $$(".btn-open-est", root).forEach((btn) => {
    btn.onclick = () =>
      setRoute("estimate", { estimateId: btn.dataset.id, projectId: project.id });
  });
  $$(".btn-edit-est", root).forEach((btn) => {
    btn.onclick = () => {
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
        <div class="field">
          <label>Waste concrete</label>
          <input type="number" step="0.01" min="0" max="1" name="waste_concrete" placeholder="0.05"
            value="${existing?.waste_concrete != null ? esc(existing.waste_concrete) : ""}" />
        </div>
        <div class="field">
          <label>Waste sand</label>
          <input type="number" step="0.01" min="0" max="1" name="waste_sand" placeholder="0.05"
            value="${existing?.waste_sand != null ? esc(existing.waste_sand) : ""}" />
        </div>
        <div class="field">
          <label>Waste rebar</label>
          <input type="number" step="0.01" min="0" max="1" name="waste_rebar" placeholder="0"
            value="${existing?.waste_rebar != null ? esc(existing.waste_rebar) : ""}" />
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
      waste_concrete: num("waste_concrete"),
      waste_sand: num("waste_sand"),
      waste_rebar: num("waste_rebar"),
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

async function renderEstimators(root) {
  root.innerHTML = `<div class="loading">Loading…</div>`;
  const people = await Api.listEstimators();
  root.innerHTML = `
    <div class="page-header">
      <div>
        <h1>Estimators</h1>
        <p>People who own projects and estimates.</p>
      </div>
      <button class="btn primary" id="btn-new">+ Add</button>
    </div>
    <div class="table-wrap">
      <table class="data">
        <thead><tr><th>Name</th><th>Username</th><th>Role</th><th>Title</th><th>Phone</th><th>Active</th></tr></thead>
        <tbody>
          ${people
            .map(
              (e) => `<tr>
              <td><strong>${esc(e.full_name)}</strong></td>
              <td class="muted">${esc(e.username)}</td>
              <td>${statusBadge(e.role)}</td>
              <td class="muted">${esc(e.title || "—")}</td>
              <td class="muted">${esc(e.phone || "—")}</td>
              <td>${e.is_active ? '<span class="badge ok">yes</span>' : '<span class="badge">no</span>'}</td>
            </tr>`
            )
            .join("")}
        </tbody>
      </table>
    </div>`;
  $("#btn-new").onclick = () => openEstimatorModal();
}

function openEstimatorModal() {
  const backdrop = document.createElement("div");
  backdrop.className = "modal-backdrop";
  backdrop.innerHTML = `
    <div class="modal">
      <h2>New estimator</h2>
      <form id="est-form" class="form-grid">
        <div class="field"><label>Username</label><input name="username" required /></div>
        <div class="field"><label>Full name</label><input name="full_name" required /></div>
        <div class="field"><label>Email</label><input name="email" type="email" /></div>
        <div class="field"><label>Phone</label><input name="phone" /></div>
        <div class="field"><label>Title</label><input name="title" value="Estimator" /></div>
        <div class="field"><label>Role</label>
          <select name="role">
            <option value="estimator">estimator</option>
            <option value="admin">admin</option>
            <option value="viewer">viewer</option>
          </select>
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
      toast("Estimator added");
      backdrop.remove();
      state.estimators = [];
      render();
    } catch (err) {
      toast(err.message, "err");
    }
  };
}

async function renderEstimateDetail(root) {
  root.innerHTML = `<div class="loading">Loading estimate…</div>`;
  if (!state.mixes.length) state.mixes = await Api.listMixes({ active_only: true });

  const [estimate, slabs, totals, forming, labor, equip] = await Promise.all([
    Api.getEstimate(state.estimateId),
    Api.listMonoSlabs(state.estimateId),
    Api.monoSlabTotals(state.estimateId),
    Api.formingMaterials(state.estimateId).catch(() => null),
    Api.laborMaterials(state.estimateId).catch(() => null),
    Api.estimateEquipment(state.estimateId).catch(() => null),
  ]);

  root.innerHTML = `
    <div class="page-header">
      <div>
        <button class="btn ghost" id="back-proj">← ${esc(estimate.project_name || "Project")}</button>
        <h1 style="margin-top:0.5rem">${esc(estimate.name)}</h1>
        <p>${statusBadge(estimate.status)} · v${estimate.version}
          ${estimate.estimator_name ? " · " + esc(estimate.estimator_name) : ""}
          · waste C/S/R:
          ${[estimate.waste_concrete, estimate.waste_sand, estimate.waste_rebar]
            .map((x) => (x == null ? "sys" : Number(x)))
            .join(" / ")}
        </p>
      </div>
      <div style="display:flex;gap:0.5rem;flex-wrap:wrap">
        <button class="btn primary" id="btn-add-slab">+ Mono slab pour</button>
        <button class="btn ghost" id="btn-jump-forming" type="button">Forming materials</button>
        <button class="btn ghost" id="btn-jump-labor" type="button">Labor &amp; supervision</button>
        <button class="btn ghost" id="btn-jump-equip" type="button">Equipment</button>
        <button class="btn" id="btn-recalc-estimate" type="button"
          title="Rewrite pours and stored takeoffs from current inputs — use after changing company defaults">Recalculate</button>
        <button class="btn danger" id="btn-del-estimate">Delete estimate</button>
      </div>
    </div>

    <div class="grid stats">
      <div class="card stat"><div class="label">Pours</div><div class="value">${totals.slab_count}</div></div>
      <div class="card stat"><div class="label">Total SF</div><div class="value">${num(totals.total_sf, 0)}</div></div>
      <div class="card stat"><div class="label">Concrete CY</div><div class="value">${num(totals.total_concrete_cy, 2)}</div><div class="hint">slab ${num(totals.total_slab_concrete_cy, 1)} + beams ${num(totals.total_gb_concrete_cy, 1)} (GB+Exp+Drop)</div></div>
      <div class="card stat"><div class="label">SF / CY</div><div class="value">${num(sfPerCy(totals.total_sf, totals.total_concrete_cy), 1)}</div><div class="hint">total SF ÷ CY (slab + beams)</div></div>
      <div class="card stat"><div class="label">Sand CY</div><div class="value">${num(totals.total_sand_cy, 2)}</div></div>
      <div class="card stat"><div class="label">Slab mat</div><div class="value">${num(totals.total_slab_bar_lb, 0)}</div><div class="hint">lb · ${num(totals.total_slab_bar_lf, 0)} LF each way</div></div>
      <div class="card stat"><div class="label">Support rebar</div><div class="value">${num(totals.total_support_rebar_lb, 0)}</div><div class="hint">lb · chairs/dowels only</div></div>
      <div class="card stat"><div class="label">PT cable LF</div><div class="value">${num(totals.total_pt_cable_lf, 0)}</div><div class="hint">slab + GB PT</div></div>
      <div class="card stat"><div class="label">PT weight</div><div class="value">${num(totals.total_pt_cable_lb, 0)}</div><div class="hint">lb (rate method)</div></div>
      <div class="card stat"><div class="label">Total rebar</div><div class="value">${num(totals.total_rebar_lb, 0)}</div><div class="hint">lb · ${num(Number(totals.total_rebar_lb) / 2000, 2)} tons (mat + support + beams)</div></div>
      <div class="card stat"><div class="label">Poly / Stego</div><div class="value">${num(totals.total_poly_sf, 0)}</div><div class="hint">SF · pour ${num(totals.total_poly_slab_sf, 0)} + beams ${num(totals.total_poly_gb_sf, 0)} + waste</div></div>
    </div>

    <div class="card">
      <h3 style="margin:0 0 0.75rem">Mono slab pours</h3>
      ${
        slabs.length
          ? `<div class="table-wrap"><table class="data">
        <thead>
          <tr>
            <th>Description</th>
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
              const pourSfPerCy = sfPerCy(s.square_footage, s.calc_concrete_cy);
              const slabOnlySfPerCy = sfPerCy(s.square_footage, s.calc_slab_concrete_cy);
              const cyTitle =
                `slab ${num(s.calc_slab_concrete_cy, 2)}` +
                ` + GB ${num(g.concrete_cy, 2)}` +
                ` + Exp ${num(e.concrete_cy, 2)}` +
                ` + Drop ${num(d.concrete_cy, 2)}` +
                ` = beams ${num(s.calc_gb_concrete_cy, 2)}`;
              const sfCyTitle =
                `SF ${num(s.square_footage, 0)} ÷ total CY ${num(s.calc_concrete_cy, 2)}` +
                ` = ${num(pourSfPerCy, 1)} SF/CY` +
                (slabOnlySfPerCy != null
                  ? ` · slab only ${num(slabOnlySfPerCy, 1)} SF/CY`
                  : "");
              const matTitle = s.slab_bar_size
                ? `#${s.slab_bar_size} @ ${num(s.slab_bar_spacing_in, 1)}" each way` +
                  ` · 2 × ${num(s.square_footage, 0)} SF × 12 / ${num(s.slab_bar_spacing_in, 1)}` +
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
              <td class="num">${num(s.square_footage, 1)}</td>
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
        Calcs: concrete/sand CY with waste. <strong>Slab mat</strong> =
        <code>2 × SF × 12 / spacing</code> LF each way × lb/ft × (1+waste_rebar for laps);
        support rebar is chairs/dowels only at lb/SF.
        <strong>Poly/Stego SF</strong> = pour SF + beam wrap
        <code>((2×H″) / 12) × L</code> (two sides only) for GBs, Exp, and Drops, × (1+waste_poly default 10%).
        Hover Poly / CY / mat / rebar for breakdown.
      </p>
    </div>

    ${renderFormingCard(forming)}
    ${renderLaborCard(labor)}
    ${renderEquipmentCard(equip)}
  `;

  $("#back-proj").onclick = () =>
    setRoute("project", { projectId: estimate.project_id });
  $("#btn-add-slab").onclick = () => openMonoSlabModal(estimate);
  const jumpForming = $("#btn-jump-forming");
  if (jumpForming) {
    jumpForming.onclick = () => {
      const el = document.getElementById("forming-materials");
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
  const btnRefreshForming = $("#btn-refresh-forming");
  if (btnRefreshForming) {
    btnRefreshForming.onclick = async () => {
      btnRefreshForming.disabled = true;
      try {
        await Api.refreshFormingMaterials(estimate.id);
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
        await Api.setFormPercent(estimate.id, form_percent);
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
        await Api.refreshLabor(estimate.id);
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
      const rate = Number(tr.querySelector(".labor-rate")?.value);
      const qtyEl = tr.querySelector(".labor-qty");
      // Saving is an explicit override: mark manual so a later refresh (or a
      // system_settings rate change) does not reset what was typed here.
      // Slab labor qty still comes from pours; supervision qty is editable.
      const body = { enabled, rate, mark_manual: true };
      if (qtyEl) {
        const qty = Number(qtyEl.value);
        if (Number.isNaN(qty) || qty < 0) {
          toast("Qty must be ≥ 0", "err");
          return;
        }
        body.qty = qty;
      }
      if (Number.isNaN(rate) || rate < 0) {
        toast("Rate must be ≥ 0", "err");
        return;
      }
      btn.disabled = true;
      try {
        await Api.patchLaborLine(estimate.id, code, body);
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
        await Api.patchLaborLine(estimate.id, code, {
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
  const btnRefreshEquip = $("#btn-refresh-equip");
  if (btnRefreshEquip) {
    btnRefreshEquip.onclick = async () => {
      btnRefreshEquip.disabled = true;
      try {
        await Api.refreshEstimateEquipment(estimate.id);
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
      const rate = Number(tr.querySelector(".equip-rate")?.value);
      const days = Number(tr.querySelector(".equip-days")?.value);
      if (Number.isNaN(rate) || rate < 0 || Number.isNaN(days) || days < 0) {
        toast("Rate and days/qty must be ≥ 0", "err");
        return;
      }
      btn.disabled = true;
      try {
        await Api.patchEstimateEquipmentLine(estimate.id, code, {
          enabled,
          rate,
          days_qty: days,
          mark_manual: true,
        });
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
        await Api.patchEstimateEquipmentLine(estimate.id, code, {
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
  const btnRecalc = $("#btn-recalc-estimate");
  if (btnRecalc) {
    btnRecalc.onclick = async () => {
      btnRecalc.disabled = true;
      btnRecalc.textContent = "Recalculating…";
      try {
        await Api.recalcEstimate(estimate.id);
        toast("Recalculated from current inputs");
        render();
      } catch (err) {
        toast(err.message, "err");
        btnRecalc.disabled = false;
        btnRecalc.textContent = "Recalculate";
      }
    };
  }
  $("#btn-del-estimate").onclick = async () => {
    const msg =
      `Delete estimate “${estimate.name}”?\n\n` +
      `This permanently removes all mono slab pours and grade beams on it.`;
    if (!confirm(msg)) return;
    try {
      await Api.deleteEstimate(estimate.id);
      toast("Estimate deleted");
      setRoute("project", { projectId: estimate.project_id });
    } catch (err) {
      toast(err.message, "err");
    }
  };
  $$(".btn-edit-slab", root).forEach((btn) => {
    btn.onclick = () => {
      const slab = slabs.find((s) => s.id === btn.dataset.id);
      openMonoSlabModal(estimate, slab);
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

function renderFormingCard(forming) {
  if (!forming) {
    return `<div class="card" id="forming-materials" style="margin-top:1rem">
      <h3 style="margin:0 0 0.5rem">Forming materials</h3>
      <div class="empty">Could not load forming takeoff. Check API / refresh the page.</div>
    </div>`;
  }
  const d = forming.drivers || {};
  const lines = forming.lines || [];
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
            Perim <strong>${num(d.perimeter_lf, 0)} LF</strong>
            · drops <strong>${num(d.drops_ff, 0)} LF</strong> <span title="Sum of drop-kind grade beams on this estimate">(from drop beams)</span>
            · SF <strong>${num(d.total_sf, 0)}</strong>
            · last refresh <strong>${esc(refreshed)}</strong>
          </p>
          <div style="display:flex;align-items:center;gap:0.5rem;flex-wrap:wrap;margin-top:0.65rem">
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
          <div class="card stat" style="min-width:8rem;margin:0">
            <div class="label">Forming mat’l</div>
            <div class="value" style="font-size:1.25rem">${money(forming.total_ext_cost)}</div>
          </div>
          <button type="button" class="btn" id="btn-refresh-forming">Refresh from pours</button>
        </div>
      </div>
      ${
        lines.length
          ? `<div class="table-wrap"><table class="data">
        <thead>
          <tr>
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
              (ln) => `<tr class="${Number(ln.qty) === 0 ? "muted" : ""}">
              <td>
                <strong>${esc(ln.label)}</strong>
                ${formCodes.has(ln.code) ? ` <span class="badge accent" title="Scaled by form %">form%</span>` : ""}
                ${ln.material_name && ln.material_name !== ln.label
                  ? `<div class="muted">${esc(ln.material_name)}</div>`
                  : ""}
                ${ln.notes ? `<div class="muted">${esc(ln.notes)}</div>` : ""}
                ${ln.is_manual ? `<div class="badge">manual</div>` : ""}
              </td>
              <td class="num"><strong>${num(ln.qty, Number(ln.qty) >= 20 || Number(ln.qty) === 0 ? 0 : 2)}</strong></td>
              <td class="muted">${esc(ln.unit)}</td>
              <td class="num muted">${ln.unit_cost != null ? num(ln.unit_cost, 2) : "—"}</td>
              <td class="num">${ln.ext_cost != null ? money(ln.ext_cost) : "—"}</td>
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
                ${ln.is_manual ? ` <span class="badge">manual</span>` : ""}
                ${ln.notes ? `<div class="muted">${esc(ln.notes)}</div>` : ""}
              </td>
              <td>
                <input type="number" class="labor-rate" data-code="${esc(ln.code)}"
                  min="0" step="0.01" value="${esc(ln.rate)}" style="width:5rem" />
              </td>
              <td class="muted">${esc(ln.unit)}</td>
              <td class="num">
                ${
                  qtyEditable
                    ? `<input type="number" class="labor-qty" data-code="${esc(ln.code)}"
                        min="0" step="0.01" value="${esc(ln.qty)}" style="width:6rem" />`
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
            Excel <strong>04 LABOR / SUPERVISION</strong> — stored in
            <code>estimate_labor_lines</code>.
            SF <strong>${num(d.total_sf, 0)}</strong>
            · drops <strong>${num(d.drops_ff, 0)} LF</strong> <span title="Sum of drop-kind grade beams on this estimate">(from drop beams)</span>
            · rebar <strong>${num(d.total_rebar_tons, 2)} ton</strong>
            · super <strong>${num(d.super_weeks, 2)} wk / ${num(d.super_days, 1)} days</strong>
            · refreshed <strong>${esc(refreshed)}</strong>
          </p>
        </div>
        <div style="display:flex;gap:0.5rem;align-items:center;flex-wrap:wrap">
          <div class="card stat" style="min-width:7rem;margin:0">
            <div class="label">Labor</div>
            <div class="value" style="font-size:1.1rem">${money(labor.total_labor_cost)}</div>
          </div>
          <div class="card stat" style="min-width:7rem;margin:0">
            <div class="label">Supervision</div>
            <div class="value" style="font-size:1.1rem">${money(labor.total_supervision_cost)}</div>
          </div>
          <div class="card stat" style="min-width:7rem;margin:0">
            <div class="label">Total / SF</div>
            <div class="value" style="font-size:1.1rem">${money(labor.total_cost)}</div>
            <div class="hint">${labor.cost_per_sf != null ? num(labor.cost_per_sf, 2) + " $/SF" : "—"}</div>
          </div>
          <button type="button" class="btn" id="btn-refresh-labor">Refresh from pours</button>
        </div>
      </div>
      ${groupTable("labor", "Slab labor")}
      ${groupTable("supervision", "Supervision")}
      <p style="color:var(--text-muted);font-size:0.8rem;margin:0.75rem 0 0">
        Toggle <strong>On</strong> and edit <strong>rate</strong>, then <strong>Save</strong>.
        Slab labor <strong>qty is from pours</strong> (not editable) — use <strong>Refresh from pours</strong> after SF/drops/rebar change.
        Supervision qty (e.g. foreman days) can be edited. Super days = SF ÷ 16,000 weeks × 7.
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
                ${ln.is_manual ? ` <span class="badge">manual</span>` : ""}
                ${ln.notes ? `<div class="muted">${esc(ln.notes)}</div>` : ""}
                <div class="muted" style="font-size:0.75rem">${esc(ln.formula || "")}</div>
              </td>
              <td>
                <input type="number" class="equip-days" data-code="${esc(ln.code)}"
                  min="0" step="0.1" value="${esc(ln.days_qty)}" style="width:5.5rem"
                  title="${group === "equipment" ? "Calendar days on rent" : "Quantity (CY, SF, …)"}" />
              </td>
              <td class="num muted" title="After Excel rental tiers (week/month caps)">${num(ln.billable_units, 1)}</td>
              <td>
                <input type="number" class="equip-rate" data-code="${esc(ln.code)}"
                  min="0" step="0.01" value="${esc(ln.rate)}" style="width:5rem" />
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
            Excel <strong>04 EQUIPMENT</strong> — stored in <code>estimate_equipment_lines</code>.
            Super days <strong>${num(d.super_days, 1)}</strong>
            → equip days <strong>${num(d.equip_days, 0)}</strong> (ladder)
            · pour CY <strong>${num(d.total_concrete_cy, 1)}</strong>
            · refreshed <strong>${esc(refreshed)}</strong>
          </p>
        </div>
        <div style="display:flex;gap:0.5rem;align-items:center;flex-wrap:wrap">
          <div class="card stat" style="min-width:7rem;margin:0">
            <div class="label">Fleet</div>
            <div class="value" style="font-size:1.1rem">${money(equip.total_equipment_cost)}</div>
          </div>
          <div class="card stat" style="min-width:7rem;margin:0">
            <div class="label">Contract</div>
            <div class="value" style="font-size:1.1rem">${money(equip.total_contract_cost)}</div>
          </div>
          <div class="card stat" style="min-width:7rem;margin:0">
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

const BAR_SIZES = [3, 4, 5, 6, 7, 8, 9, 10, 11];
const MIN_GB_ROWS = 5;

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
};

function barSizeOptions(selected) {
  return (
    `<option value="">—</option>` +
    BAR_SIZES.map(
      (s) =>
        `<option value="${s}" ${Number(selected) === s ? "selected" : ""}>#${s}</option>`
    ).join("")
  );
}

function emptyGbRow(i, kind = "grade_beam") {
  const prefix = (BEAM_KIND_META[kind] || BEAM_KIND_META.grade_beam).labelPrefix;
  return {
    label: `${prefix} ${i}`,
    width_in: "",
    height_in: "",
    length_lf: "",
    top_bars_count: "",
    top_bars_size: "",
    bottom_bars_count: "",
    bottom_bars_size: "",
    mid_bars_count: "",
    mid_bars_size: "",
    stirrup_size: "",
    stirrup_spacing_in: "",
    pt_cables_count: "",
    calc_rebar_lb: null,
    calc_pt_cable_lf: null,
    calc_concrete_cy: null,
    calc_poly_sf: null,
  };
}

function gbRowHtml(row, idx, showPt = true) {
  const ptCells = showPt
    ? `<td><input type="number" name="pt_cables_count" min="0" step="1" value="${esc(row.pt_cables_count ?? "")}" style="width:3rem" title="PT cables in this GB" /></td>
      <td class="num muted">${row.calc_pt_cable_lf != null ? num(row.calc_pt_cable_lf, 0) : "—"}</td>`
    : "";
  return `
    <tr data-gb-idx="${idx}">
      <td><input name="label" value="${esc(row.label || "")}" style="width:7rem" /></td>
      <td><input type="number" name="width_in" min="0" step="0.1" value="${esc(row.width_in ?? "")}" style="width:4rem" /></td>
      <td><input type="number" name="height_in" min="0" step="0.1" value="${esc(row.height_in ?? "")}" style="width:4rem" /></td>
      <td><input type="number" name="length_lf" min="0" step="0.1" value="${esc(row.length_lf ?? "")}" style="width:5rem" /></td>
      <td><input type="number" name="top_bars_count" min="0" step="1" value="${esc(row.top_bars_count ?? "")}" style="width:3rem" /></td>
      <td><select name="top_bars_size">${barSizeOptions(row.top_bars_size)}</select></td>
      <td><input type="number" name="bottom_bars_count" min="0" step="1" value="${esc(row.bottom_bars_count ?? "")}" style="width:3rem" /></td>
      <td><select name="bottom_bars_size">${barSizeOptions(row.bottom_bars_size)}</select></td>
      <td><input type="number" name="mid_bars_count" min="0" step="1" value="${esc(row.mid_bars_count ?? "")}" style="width:3rem" /></td>
      <td><select name="mid_bars_size">${barSizeOptions(row.mid_bars_size)}</select></td>
      <td><select name="stirrup_size">${barSizeOptions(row.stirrup_size)}</select></td>
      <td><input type="number" name="stirrup_spacing_in" min="0" step="0.5" value="${esc(row.stirrup_spacing_in ?? "")}" style="width:3.5rem" placeholder="in" /></td>
      ${ptCells}
      <td class="num muted gb-lb">${row.calc_rebar_lb != null ? num(row.calc_rebar_lb, 1) : "—"}</td>
      <td class="num muted">${row.calc_concrete_cy != null ? num(row.calc_concrete_cy, 2) : "—"}</td>
      <td class="num muted" title="((2×H)/12)×L sides only">${row.calc_poly_sf != null ? num(row.calc_poly_sf, 0) : "—"}</td>
    </tr>`;
}

async function openGradeBeamsModal(slab, kind = "grade_beam") {
  const meta = BEAM_KIND_META[kind] || BEAM_KIND_META.grade_beam;
  const showPt = !!meta.showPt;

  const backdrop = document.createElement("div");
  backdrop.className = "modal-backdrop";
  backdrop.innerHTML = `<div class="modal" style="width:min(1100px,100%)"><div class="loading">Loading ${esc(meta.title.toLowerCase())}…</div></div>`;
  document.body.appendChild(backdrop);

  let existing = [];
  try {
    existing = await Api.listGradeBeams(slab.id, kind);
  } catch (err) {
    toast(err.message, "err");
    backdrop.remove();
    return;
  }

  let rows = existing.map((b) => ({
    label: b.label,
    width_in: b.width_in,
    height_in: b.height_in,
    length_lf: b.length_lf,
    top_bars_count: b.top_bars_count,
    top_bars_size: b.top_bars_size,
    bottom_bars_count: b.bottom_bars_count,
    bottom_bars_size: b.bottom_bars_size,
    mid_bars_count: b.mid_bars_count,
    mid_bars_size: b.mid_bars_size,
    stirrup_size: b.stirrup_size,
    stirrup_spacing_in: b.stirrup_spacing_in,
    pt_cables_count: b.pt_cables_count,
    calc_rebar_lb: b.calc_rebar_lb,
    calc_pt_cable_lf: b.calc_pt_cable_lf,
    calc_concrete_cy: b.calc_concrete_cy,
    calc_poly_sf: b.calc_poly_sf,
  }));
  while (rows.length < MIN_GB_ROWS) {
    rows.push(emptyGbRow(rows.length + 1, kind));
  }

  function paint() {
    const totalGb = existing.reduce((a, b) => a + Number(b.calc_rebar_lb || 0), 0);
    const totalPt = existing.reduce((a, b) => a + Number(b.calc_pt_cable_lf || 0), 0);
    const totalCy = existing.reduce((a, b) => a + Number(b.calc_concrete_cy || 0), 0);
    const totalPoly = existing.reduce((a, b) => a + Number(b.calc_poly_sf || 0), 0);
    const ptHint = showPt
      ? (existing.length
          ? `· rebar <strong>${num(totalGb, 1)} lb</strong> · PT <strong>${num(totalPt, 0)} LF</strong> · <strong>${num(totalCy, 2)} CY</strong> · poly <strong>${num(totalPoly, 0)} SF</strong>`
          : "")
      : existing.length
        ? `· rebar <strong>${num(totalGb, 1)} lb</strong> · <strong>${num(totalCy, 2)} CY</strong> · poly <strong>${num(totalPoly, 0)} SF</strong>`
        : "";
    const ptHeads = showPt ? `<th>PT #</th><th>PT LF</th>` : "";
    $(".modal", backdrop).innerHTML = `
      <h2>${esc(meta.title)} — ${esc(slab.description || "Pour")}</h2>
      <p style="margin:-0.4rem 0 0.85rem;color:var(--text-muted);font-size:0.9rem">
        ${meta.hint} At least ${MIN_GB_ROWS} slots; blank rows ignored.
        CY = (W″ × H″ × L) / (144 × 27) × (1+waste).
        Poly wrap SF = ((2×H″) / 12) × L — two sides only (Excel; pour SF covers bottoms).
        Saving this kind leaves GBs / Exp / Drops of other kinds alone.
        ${ptHint}
      </p>
      <div class="table-wrap" style="max-height:55vh">
        <table class="data" id="gb-table">
          <thead>
            <tr>
              <th>Type / label</th>
              <th>W"</th>
              <th>H"</th>
              <th>L (ft)</th>
              <th>Top #</th>
              <th>Top sz</th>
              <th>Bot #</th>
              <th>Bot sz</th>
              <th>Mid #</th>
              <th>Mid sz</th>
              <th>Stirrup</th>
              <th>@ in</th>
              ${ptHeads}
              <th>rebar lb</th>
              <th>CY</th>
              <th>poly SF</th>
            </tr>
          </thead>
          <tbody>
            ${rows.map((r, i) => gbRowHtml(r, i, showPt)).join("")}
          </tbody>
        </table>
      </div>
      <div class="modal-actions" style="justify-content:space-between;margin-top:1rem">
        <button type="button" class="btn" id="gb-add-row">+ Add type</button>
        <div style="display:flex;gap:0.5rem">
          <button type="button" class="btn ghost" id="cancel">Cancel</button>
          <button type="button" class="btn primary" id="gb-save">Save ${esc(meta.short)}</button>
        </div>
      </div>`;

    $("#cancel", backdrop).onclick = () => backdrop.remove();
    $("#gb-add-row", backdrop).onclick = () => {
      rows = collectRows().concat([emptyGbRow(rows.length + 1, kind)]);
      paint();
    };
    $("#gb-save", backdrop).onclick = () => save();
  }

  function collectRows() {
    return $$("#gb-table tbody tr", backdrop).map((tr) => {
      const g = (n) => {
        const el = tr.querySelector(`[name="${n}"]`);
        return el ? el.value : "";
      };
      const n = (name) => {
        const v = g(name);
        return v === "" ? null : Number(v);
      };
      const pt = showPt ? n("pt_cables_count") : null;
      return {
        kind,
        label: g("label") || null,
        width_in: n("width_in"),
        height_in: n("height_in"),
        length_lf: n("length_lf"),
        top_bars_count: n("top_bars_count"),
        top_bars_size: n("top_bars_size"),
        bottom_bars_count: n("bottom_bars_count"),
        bottom_bars_size: n("bottom_bars_size"),
        mid_bars_count: n("mid_bars_count"),
        mid_bars_size: n("mid_bars_size"),
        stirrup_size: n("stirrup_size"),
        stirrup_spacing_in: n("stirrup_spacing_in"),
        pt_cables_count: pt != null ? Math.round(pt) : null,
      };
    });
  }

  async function save() {
    const beams = collectRows().filter(
      (r) =>
        r.length_lf != null &&
        r.length_lf > 0 &&
        r.width_in != null &&
        r.width_in > 0 &&
        r.height_in != null &&
        r.height_in > 0
    );
    try {
      const saved = await Api.replaceGradeBeams(slab.id, beams, kind);
      toast(`Saved ${saved.length} ${meta.title.toLowerCase()} type(s)`);
      backdrop.remove();
      render();
    } catch (err) {
      toast(err.message, "err");
    }
  }

  paint();
  backdrop.addEventListener("click", (e) => {
    if (e.target === backdrop) backdrop.remove();
  });
}

function openMonoSlabModal(estimate, existing = null) {
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
        Estimate: ${esc(estimate.name)} · calcs refresh on save
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
          <label>Drops</label>
          <div class="muted" style="font-size:0.8rem;padding:0.45rem 0">
            Entered as beams — use the <strong>Drops</strong> button on this pour.
          </div>
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
          <input type="number" name="slab_bar_spacing_in" min="0.1" step="0.5"
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
        await Api.createMonoSlab({ ...body, estimate_id: estimate.id });
        toast("Pour added · calcs refreshed");
      }
      backdrop.remove();
      render();
    } catch (err) {
      toast(err.message, "err");
    }
  };
}

async function renderMixes(root) {
  root.innerHTML = `<div class="loading">Loading mix designs…</div>`;
  const mixes = await Api.listMixes({ active_only: true });
  root.innerHTML = `
    <div class="page-header">
      <div>
        <h1>Mix designs</h1>
        <p>SC / ASH / Air-ASH matrix + 3000 integral color.</p>
      </div>
    </div>
    <div class="table-wrap">
      <table class="data">
        <thead><tr><th>Code</th><th>Name</th><th>PSI</th><th>Ash</th><th>Air</th><th>Unit cost</th></tr></thead>
        <tbody>
          ${mixes
            .map(
              (m) => `<tr>
              <td class="muted">${esc(m.code)}</td>
              <td><strong>${esc(m.name)}</strong></td>
              <td class="num">${m.strength_psi ?? "—"}</td>
              <td>${m.has_ash ? "✓" : ""}</td>
              <td>${m.has_air ? "✓" : ""}</td>
              <td class="num">${m.unit_cost != null ? money(m.unit_cost) : "—"}</td>
            </tr>`
            )
            .join("")}
        </tbody>
      </table>
    </div>`;
}

async function renderMaterials(root) {
  root.innerHTML = `<div class="loading">Loading materials…</div>`;
  const cats = await Api.materialCategories();
  let category = "";
  let q = "";

  async function load() {
    const rows = await Api.listMaterials({
      active_only: true,
      category: category || undefined,
      q: q || undefined,
    });
    $("#mat-body").innerHTML = `
      <div class="table-wrap">
        <table class="data">
          <thead><tr><th>Name</th><th>Category</th><th>Unit</th><th>Cost</th><th>Note</th></tr></thead>
          <tbody>
            ${rows
              .map(
                (m) => `<tr>
                <td><strong>${esc(m.name)}</strong></td>
                <td class="muted">${esc(m.category)}</td>
                <td>${esc(m.unit)}</td>
                <td class="num">${m.unit_cost != null ? money(m.unit_cost) : "—"}</td>
                <td class="muted">${esc(m.unit_note || "")}</td>
              </tr>`
              )
              .join("")}
          </tbody>
        </table>
      </div>
      <p class="muted" style="color:var(--text-muted);font-size:0.85rem">${rows.length} items</p>`;
  }

  root.innerHTML = `
    <div class="page-header">
      <div>
        <h1>Materials</h1>
        <p>Unit-price catalog from Pricing (New Current Worksheet).</p>
      </div>
    </div>
    <div class="toolbar">
      <input id="mat-q" placeholder="Search…" style="min-width:180px" />
      <select id="mat-cat">
        <option value="">All categories</option>
        ${cats.map((c) => `<option value="${esc(c)}">${esc(c)}</option>`).join("")}
      </select>
    </div>
    <div id="mat-body"></div>`;

  await load();
  $("#mat-cat").onchange = (e) => {
    category = e.target.value;
    load().catch((err) => toast(err.message, "err"));
  };
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
  const rows = await Api.listEquipment({ active_only: true });
  root.innerHTML = `
    <div class="page-header">
      <div>
        <h1>Equipment</h1>
        <p>Rental rates from Pricing EQUIPMENT RENTAL.</p>
      </div>
    </div>
    <div class="table-wrap">
      <table class="data">
        <thead><tr><th>Name</th><th>Category</th><th>Unit</th><th>Rate</th></tr></thead>
        <tbody>
          ${rows
            .map(
              (e) => `<tr>
              <td><strong>${esc(e.name)}</strong></td>
              <td class="muted">${esc(e.category)}</td>
              <td>${esc(e.unit)}</td>
              <td class="num">${money(e.unit_cost)}</td>
            </tr>`
            )
            .join("")}
        </tbody>
      </table>
    </div>`;
}

async function render() {
  const root = $("#app");
  try {
    if (state.route === "home") await renderHome(root);
    else if (state.route === "projects") await renderProjects(root);
    else if (state.route === "project") await renderProjectDetail(root);
    else if (state.route === "estimate") await renderEstimateDetail(root);
    else if (state.route === "estimators") await renderEstimators(root);
    else if (state.route === "mixes") await renderMixes(root);
    else if (state.route === "materials") await renderMaterials(root);
    else if (state.route === "equipment") await renderEquipment(root);
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
      (state.route === "estimate" && b.dataset.route === "projects");
    b.classList.toggle("active", active);
  });
}

function init() {
  $$(".nav button").forEach((btn) => {
    btn.addEventListener("click", () => setRoute(btn.dataset.route));
  });
  window.addEventListener("hashchange", () => {
    const p = parseHash();
    state.route = p.route;
    state.projectId = p.projectId;
    state.estimateId = p.estimateId;
    syncNavActive();
    render();
  });
  const p = parseHash();
  state.route = p.route;
  state.projectId = p.projectId;
  state.estimateId = p.estimateId;
  syncNavActive();
  checkHealth();
  render();
}

init();
