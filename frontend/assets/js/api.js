/**
 * API client.
 *
 * Same origin whenever a server is serving this page: FastAPI mounts /api
 * beside /assets, so "/api" is right on 8001, on `run.ps1 -Port 8002`, on the
 * office box — anywhere a browser got this file from a server. Only a page
 * opened straight from disk (file://) has no origin to speak of, and that is
 * the one case that still points at the dev host.
 *
 * Until 2026-09-04 any localhost port other than 8001 was ALSO sent to
 * 127.0.0.1:8001 — so `-Port 8002`, the natural move when 8001 is busy (which
 * run.ps1 refuses to share), rendered a page whose every write went to
 * whatever old process was still on 8001 (audit P2 #10). Exported so
 * frontend/tests/api-base.test.mjs can pin it without a browser.
 */
export function apiBaseFor(loc) {
  return loc.protocol === "file:" ? "http://127.0.0.1:8001/api" : "/api";
}

const API_BASE = apiBaseFor(location);

async function api(path, options = {}) {
  const opts = {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  };
  if (opts.body && typeof opts.body === "object") {
    opts.body = JSON.stringify(opts.body);
  }
  const res = await fetch(`${API_BASE}${path}`, opts);
  if (res.status === 204) return null;
  const text = await res.text();
  let data = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = text;
  }
  if (!res.ok) throw new Error(describeFailure(res.statusText, data));
  return data;
}

/**
 * The message a failed request throws. FastAPI's 422 is a list of {loc, msg};
 * until 2026-09-05 the toast showed only msg, so "Decimal input should be an
 * integer, float, string or Decimal object" never said WHICH cell — that was
 * the wall grid's "0 in every footing box" (the schemas now take a blank as a
 * zero; backend/tests/test_blank_cells_are_zero.py). Now body/rows/0/ftg_width_in
 * reads "row 1 ftg_width_in: …". Exported for frontend/tests/api-errors.test.mjs.
 */
export function describeFailure(statusText, data) {
  const detail = data?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map(describeOne).join("; ");
  return statusText || "Request failed";
}

const LOC_ROOTS = new Set(["body", "query", "path", "header"]);

function describeOne(d) {
  const msg = d?.msg || JSON.stringify(d);
  const loc = Array.isArray(d?.loc) ? d.loc.filter((p, i) => !(i === 0 && LOC_ROOTS.has(p))) : [];
  if (!loc.length) return msg;
  if (loc[0] === "rows" && Number.isInteger(loc[1])) {
    const rest = loc.slice(2).join(".");
    return `row ${loc[1] + 1}${rest ? ` ${rest}` : ""}: ${msg}`;
  }
  return `${loc.join(".")}: ${msg}`;
}

/** Query string from an object, dropping null/undefined/empty values. */
function qs(params = {}) {
  const q = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v != null && v !== "") q.set(k, v);
  });
  return q.toString();
}

export const Api = {
  health: () => fetch(API_BASE.replace(/\/api$/, "") + "/health").then((r) => r.json()),
  // Estimators
  listEstimators: (params = {}) => {
    const q = new URLSearchParams(params).toString();
    return api(`/estimators${q ? "?" + q : ""}`);
  },
  createEstimator: (body) => api("/estimators", { method: "POST", body }),
  updateEstimator: (id, body) => api(`/estimators/${id}`, { method: "PATCH", body }),
  // Projects
  listProjects: (params = {}) => {
    const q = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v != null && v !== "") q.set(k, v);
    });
    const s = q.toString();
    return api(`/projects${s ? "?" + s : ""}`);
  },
  getProject: (id) => api(`/projects/${id}`),
  createProject: (body) => api("/projects", { method: "POST", body }),
  updateProject: (id, body) => api(`/projects/${id}`, { method: "PATCH", body }),
  projectTypes: () => api("/projects/meta/project-types"),
  projectStatuses: () => api("/projects/meta/statuses"),
  // Estimates
  listEstimates: (params = {}) => {
    const q = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v != null && v !== "") q.set(k, v);
    });
    const s = q.toString();
    return api(`/estimates${s ? "?" + s : ""}`);
  },
  createEstimate: (body) => api("/estimates", { method: "POST", body }),
  updateEstimate: (id, body) => api(`/estimates/${id}`, { method: "PATCH", body }),
  getEstimate: (id) => api(`/estimates/${id}`),
  // Sections — the assemblies of a job (sql/033-034). An estimate is a rollup;
  // the work, the rates and the markup all live on a section.
  listSections: (estimateId) => api(`/estimates/${estimateId}/sections`),
  createSection: (estimateId, body) =>
    api(`/estimates/${estimateId}/sections`, { method: "POST", body }),
  getSection: (sectionId) => api(`/sections/${sectionId}`),
  updateSection: (sectionId, body) =>
    api(`/sections/${sectionId}`, { method: "PATCH", body }),
  deleteSection: (sectionId, force = false) =>
    api(`/sections/${sectionId}${force ? "?force=true" : ""}`, { method: "DELETE" }),
  recalcSection: (sectionId) =>
    api(`/sections/${sectionId}/recalc`, { method: "POST" }),
  sectionKinds: () => api("/sections/meta/kinds"),
  // The dollars behind the quantity cards — concrete, steel, poly, drilling,
  // each with the rate it was priced at. One endpoint for every assembly.
  sectionMaterialCosts: (sectionId) => api(`/sections/${sectionId}/material-costs`),
  // Quotes on a section (sql/039). A real supplier number replacing one the app
  // computed — drilling, rebar, PT. Writing one re-costs the section, so the
  // caller re-renders off the response rather than patching the DOM.
  listSectionQuotes: (sectionId) => api(`/sections/${sectionId}/quotes`),
  putSectionQuote: (sectionId, kind, body) =>
    api(`/sections/${sectionId}/quotes/${kind}`, { method: "PUT", body }),
  deleteSectionQuote: (sectionId, kind) =>
    api(`/sections/${sectionId}/quotes/${kind}`, { method: "DELETE" }),
  // Vapor barrier is named on the section rather than matched by name (sql/030)
  setVaporBarrier: (sectionId, vapor_barrier_material_id) =>
    api(`/sections/${sectionId}`, { method: "PATCH", body: { vapor_barrier_material_id } }),
  // Seam tape, priced off the barrier's roll count (sql/031)
  setVaporTape: (sectionId, vapor_tape_material_id) =>
    api(`/sections/${sectionId}`, { method: "PATCH", body: { vapor_tape_material_id } }),
  deleteEstimate: (id) => api(`/estimates/${id}`, { method: "DELETE" }),
  // Rewrite pours + stored takeoffs from current inputs (after settings changes)
  recalcEstimate: (id) => api(`/estimates/${id}/recalc`, { method: "POST" }),
  // The job's price sheet (sql/048): what THIS estimate pays for each mix and
  // material, pulled from the master list when the estimate was created and
  // edited per job from there.
  getPriceSheet: (estimateId) => api(`/estimates/${estimateId}/prices`),
  pullPriceSheet: (estimateId, dryRun = false) =>
    api(`/estimates/${estimateId}/prices/pull${dryRun ? "?dry_run=true" : ""}`, { method: "POST" }),
  updatePrice: (estimateId, priceId, body) =>
    api(`/estimates/${estimateId}/prices/${priceId}`, { method: "PATCH", body }),
  // Company defaults
  // Rates set on ONE section (sql/055). The GET reports the whole ladder —
  // section, job, assembly, company, default — so the screen can say where a
  // number came from rather than just what it is. DELETE removes the override
  // and lets the ladder below take over again.
  sectionRates: (sectionId) =>
    api(`/sections/${encodeURIComponent(sectionId)}/rates`),
  setSectionRate: (sectionId, key, value, note) =>
    api(`/sections/${encodeURIComponent(sectionId)}/rates/${encodeURIComponent(key)}`, {
      method: "PUT",
      body: { value, note: note || null },
    }),
  clearSectionRate: (sectionId, key) =>
    api(`/sections/${encodeURIComponent(sectionId)}/rates/${encodeURIComponent(key)}`, {
      method: "DELETE",
    }),

  // Company settings. Every row carries its own metadata since sql/053 —
  // price or rule, label, unit, group, and what a change rewrites — so the
  // screen never holds a second copy of that taxonomy. Sending `null` clears
  // a key back to UNSET, which is not the same as zero.
  listSettings: (prefix) =>
    api(`/system-settings${prefix ? "?prefix=" + encodeURIComponent(prefix) : ""}`),
  updateSetting: (key, value) =>
    api(`/system-settings/${encodeURIComponent(key)}`, { method: "PATCH", body: { value } }),
  // Push catalog / default changes into the open estimates. Final and archived
  // ones are left at their bid numbers unless include_frozen is set.
  recalcAllEstimates: (includeFrozen = false) =>
    api(`/system-settings/recalc-all${includeFrozen ? "?include_frozen=true" : ""}`, {
      method: "POST",
    }),
  // Mono slabs
  listMonoSlabs: (sectionId) =>
    api(`/mono-slabs?section_id=${encodeURIComponent(sectionId)}`),
  monoSlabTotals: (sectionId) =>
    api(`/mono-slabs/totals?section_id=${encodeURIComponent(sectionId)}`),
  createMonoSlab: (body) => api("/mono-slabs", { method: "POST", body }),
  updateMonoSlab: (id, body) => api(`/mono-slabs/${id}`, { method: "PATCH", body }),
  deleteMonoSlab: (id) => api(`/mono-slabs/${id}`, { method: "DELETE" }),
  recalcMonoSlab: (id) => api(`/mono-slabs/${id}/recalc`, { method: "POST" }),
  // Save a whole grid of pours in one request. Paving is entered as a table,
  // and the section's forming, labor and equipment all key off the totals —
  // so a save per field would re-run all three on every keystroke.
  // Piers — one row is a GROUP of identical shafts, and the section is
  // measured in EA rather than SF (sql/037).
  listPierGroups: (sectionId) =>
    api(`/pier-groups?section_id=${encodeURIComponent(sectionId)}`),
  pierTotals: (sectionId) =>
    api(`/pier-groups/totals?section_id=${encodeURIComponent(sectionId)}`),
  deletePierGroup: (id) => api(`/pier-groups/${id}`, { method: "DELETE" }),
  // Walls — one row is a wall type AND the footing under it, measured in FORM
  // FEET (sql/040). Form feet is one face, not both; see the column spec.
  listWallRuns: (sectionId) =>
    api(`/wall-runs?section_id=${encodeURIComponent(sectionId)}`),
  wallTotals: (sectionId) =>
    api(`/wall-runs/totals?section_id=${encodeURIComponent(sectionId)}`),
  deleteWallRun: (id) => api(`/wall-runs/${id}`, { method: "DELETE" }),
  bulkSaveWallRuns: (sectionId, rows, deleteMissing = false) =>
    api("/wall-runs/bulk", {
      method: "PUT",
      body: { section_id: sectionId, rows, delete_missing: deleteMissing },
    }),
  // Columns — the fourth takeoff shape: a TYPE and how many of it (sql/045).
  // There is no area and no run; the row is a schedule entry with a count, and
  // the section allocates by form contact SF.
  listColumnTypes: (sectionId) =>
    api(`/column-types?section_id=${encodeURIComponent(sectionId)}`),
  columnTotals: (sectionId) =>
    api(`/column-types/totals?section_id=${encodeURIComponent(sectionId)}`),
  deleteColumnType: (id) => api(`/column-types/${id}`, { method: "DELETE" }),
  bulkSaveColumnTypes: (sectionId, rows, deleteMissing = false) =>
    api("/column-types/bulk", {
      method: "PUT",
      body: { section_id: sectionId, rows, delete_missing: deleteMissing },
    }),

  // The CIP elevated deck — the fifth takeoff shape: a LEVEL (sql/052). An
  // area, a thickness, two mats and the grade beams running through it. The
  // beams are a nested list on the row, so the grid sends them with it.
  listDeckLevels: (sectionId) =>
    api(`/deck-levels?section_id=${encodeURIComponent(sectionId)}`),
  deckTotals: (sectionId) =>
    api(`/deck-levels/totals?section_id=${encodeURIComponent(sectionId)}`),
  deleteDeckLevel: (id) => api(`/deck-levels/${id}`, { method: "DELETE" }),
  bulkSaveDeckLevels: (sectionId, rows, deleteMissing = false) =>
    api("/deck-levels/bulk", {
      method: "PUT",
      body: { section_id: sectionId, rows, delete_missing: deleteMissing },
    }),

  pierDrillRates: () => api("/pier-groups/drill-rates"),
  bulkSavePierGroups: (sectionId, rows, deleteMissing = false) =>
    api("/pier-groups/bulk", {
      method: "PUT",
      body: { section_id: sectionId, rows, delete_missing: deleteMissing },
    }),

  bulkSaveMonoSlabs: (sectionId, rows, deleteMissing = false) =>
    api("/mono-slabs/bulk", {
      method: "PUT",
      body: { section_id: sectionId, rows, delete_missing: deleteMissing },
    }),
  // Grade beams / exposed GBs / drops (per mono slab pour; Excel 04)
  listGradeBeams: (monoSlabId, kind = null) => {
    const q = new URLSearchParams({ mono_slab_id: monoSlabId });
    if (kind) q.set("kind", kind);
    return api(`/grade-beams?${q}`);
  },
  replaceGradeBeams: (monoSlabId, beams, kind = "grade_beam") =>
    api(`/mono-slabs/${monoSlabId}/grade-beams`, {
      method: "PUT",
      body: { kind, beams },
    }),
  // Beam types — the per-estimate schedule a pour's lengths point at
  listBeamTypes: (sectionId, kind = null) => {
    const q = kind ? `?kind=${encodeURIComponent(kind)}` : "";
    return api(`/sections/${sectionId}/beam-types${q}`);
  },
  createBeamType: (sectionId, body) =>
    api(`/sections/${sectionId}/beam-types`, { method: "POST", body }),
  updateBeamType: (typeId, body) =>
    api(`/beam-types/${typeId}`, { method: "PATCH", body }),
  // The whole schedule in one request: one recalc, one commit (audit P3).
  saveBeamTypes: (sectionId, rows) =>
    api(`/sections/${sectionId}/beam-types/bulk`, { method: "PUT", body: { rows } }),
  deleteBeamType: (typeId, force = false) =>
    api(`/beam-types/${typeId}${force ? "?force=true" : ""}`, { method: "DELETE" }),
  beamTypeUsage: (typeId) => api(`/beam-types/${typeId}/usage`),
  // Rules for one JOB (sql/055's estimate_rules). Rules only — a price is
  // frozen on the price sheet and is edited there.
  estimateRules: (estimateId) => api(`/estimates/${estimateId}/rules`),
  setEstimateRule: (estimateId, key, value, note) =>
    api(`/estimates/${estimateId}/rules/${encodeURIComponent(key)}`, {
      method: "PUT",
      body: { value, note },
    }),
  clearEstimateRule: (estimateId, key) =>
    api(`/estimates/${estimateId}/rules/${encodeURIComponent(key)}`, {
      method: "DELETE",
    }),
  // Forming / lumber takeoff (stored on estimate; refresh recalculates from pours)
  formingMaterials: (sectionId) =>
    api(`/sections/${sectionId}/forming-materials`),
  refreshFormingMaterials: (sectionId) =>
    api(`/sections/${sectionId}/forming-materials/refresh`, { method: "POST" }),
  // Include / exclude one lumber line (sql/056). Unchecking is how you answer
  // "RESHORING — forming" without inventing a price for it.
  toggleFormingLine: (sectionId, code, enabled) =>
    api(
      `/sections/${sectionId}/forming-materials/lines/${encodeURIComponent(code)}`,
      { method: "PATCH", body: { enabled } }
    ),
  setFormPercent: (sectionId, form_percent) =>
    api(`/sections/${sectionId}/forming-materials/form-percent`, {
      method: "PUT",
      body: { form_percent },
    }),
  // Labor + supervision
  laborMaterials: (sectionId) => api(`/sections/${sectionId}/labor`),
  refreshLabor: (sectionId) =>
    api(`/sections/${sectionId}/labor/refresh`, { method: "POST" }),
  patchLaborLine: (sectionId, code, body) =>
    api(`/sections/${sectionId}/labor/lines/${encodeURIComponent(code)}`, {
      method: "PATCH",
      body,
    }),
  // Estimate equipment (day fleet + pumping)
  estimateEquipment: (sectionId) => api(`/sections/${sectionId}/equipment`),
  refreshEstimateEquipment: (sectionId) =>
    api(`/sections/${sectionId}/equipment/refresh`, { method: "POST" }),
  patchEstimateEquipmentLine: (sectionId, code, body) =>
    api(`/sections/${sectionId}/equipment/lines/${encodeURIComponent(code)}`, {
      method: "PATCH",
      body,
    }),
  // Catalogs
  //
  // Editing a price here does NOT reprice stored estimates: each job carries
  // its own price sheet (sql/048) and costing reads that. A change lands on a
  // job when the job pulls its sheet (the price-sheet screen's Pull);
  // recalcAllEstimates() only recalculates with what each sheet already holds.
  listMixes: (params = {}) => {
    const q = qs(params);
    return api(`/mix-designs${q ? "?" + q : ""}`);
  },
  // The bar catalog (sql/066): the sizes every grid's pick-list offers and
  // the only sizes the database accepts.
  listBarSizes: () => api("/bar-sizes"),
  createMix: (body) => api("/mix-designs", { method: "POST", body }),
  updateMix: (id, body) => api(`/mix-designs/${id}`, { method: "PATCH", body }),
  deactivateMix: (id) => api(`/mix-designs/${id}`, { method: "DELETE" }),
  // Per-supplier $/CY behind a mix. A mix with no unit_cost of its own costs at
  // the cheapest quote here.
  listConcreteSuppliers: (params = {}) => {
    const q = qs(params);
    return api(`/concrete-suppliers${q ? "?" + q : ""}`);
  },
  createConcreteSupplier: (body) => api("/concrete-suppliers", { method: "POST", body }),
  updateConcreteSupplier: (id, body) =>
    api(`/concrete-suppliers/${id}`, { method: "PATCH", body }),
  listMaterials: (params = {}) => {
    const q = qs(params);
    return api(`/materials${q ? "?" + q : ""}`);
  },
  materialCategories: () => api("/materials/meta/categories"),
  createMaterial: (body) => api("/materials", { method: "POST", body }),
  updateMaterial: (id, body) => api(`/materials/${id}`, { method: "PATCH", body }),
  deactivateMaterial: (id) => api(`/materials/${id}`, { method: "DELETE" }),
  listEquipment: (params = {}) => {
    const q = qs(params);
    return api(`/equipment${q ? "?" + q : ""}`);
  },
  equipmentCategories: () => api("/equipment/meta/categories"),
  createEquipment: (body) => api("/equipment", { method: "POST", body }),
  updateEquipment: (id, body) => api(`/equipment/${id}`, { method: "PATCH", body }),
  deactivateEquipment: (id) => api(`/equipment/${id}`, { method: "DELETE" }),
};
