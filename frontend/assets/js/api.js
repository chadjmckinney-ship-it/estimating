/** API client — same origin when served by FastAPI, else localhost:8001 */
const API_BASE = (() => {
  if (location.port === "8001" || location.hostname === "127.0.0.1" || location.hostname === "localhost") {
    // When opened as file:// or different port, hit the API host
    if (location.protocol === "file:" || location.port !== "8001") {
      return "http://127.0.0.1:8001/api";
    }
  }
  return "/api";
})();

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
  if (!res.ok) {
    const detail = data?.detail;
    const msg =
      typeof detail === "string"
        ? detail
        : Array.isArray(detail)
          ? detail.map((d) => d.msg || JSON.stringify(d)).join("; ")
          : res.statusText || "Request failed";
    throw new Error(msg);
  }
  return data;
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
  deleteEstimate: (id) => api(`/estimates/${id}`, { method: "DELETE" }),
  // Rewrite pours + stored takeoffs from current inputs (after settings changes)
  recalcEstimate: (id) => api(`/estimates/${id}/recalc`, { method: "POST" }),
  // Company defaults
  listSettings: (prefix) =>
    api(`/system-settings${prefix ? "?prefix=" + encodeURIComponent(prefix) : ""}`),
  updateSetting: (key, value) =>
    api(`/system-settings/${encodeURIComponent(key)}`, { method: "PATCH", body: { value } }),
  recalcAllEstimates: () => api("/system-settings/recalc-all", { method: "POST" }),
  // Mono slabs
  listMonoSlabs: (estimateId) =>
    api(`/mono-slabs?estimate_id=${encodeURIComponent(estimateId)}`),
  monoSlabTotals: (estimateId) =>
    api(`/mono-slabs/totals?estimate_id=${encodeURIComponent(estimateId)}`),
  createMonoSlab: (body) => api("/mono-slabs", { method: "POST", body }),
  updateMonoSlab: (id, body) => api(`/mono-slabs/${id}`, { method: "PATCH", body }),
  deleteMonoSlab: (id) => api(`/mono-slabs/${id}`, { method: "DELETE" }),
  recalcMonoSlab: (id) => api(`/mono-slabs/${id}/recalc`, { method: "POST" }),
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
  listBeamTypes: (estimateId, kind = null) => {
    const q = kind ? `?kind=${encodeURIComponent(kind)}` : "";
    return api(`/estimates/${estimateId}/beam-types${q}`);
  },
  createBeamType: (estimateId, body) =>
    api(`/estimates/${estimateId}/beam-types`, { method: "POST", body }),
  updateBeamType: (typeId, body) =>
    api(`/beam-types/${typeId}`, { method: "PATCH", body }),
  deleteBeamType: (typeId, force = false) =>
    api(`/beam-types/${typeId}${force ? "?force=true" : ""}`, { method: "DELETE" }),
  beamTypeUsage: (typeId) => api(`/beam-types/${typeId}/usage`),
  // Forming / lumber takeoff (stored on estimate; refresh recalculates from pours)
  formingMaterials: (estimateId) =>
    api(`/estimates/${estimateId}/forming-materials`),
  refreshFormingMaterials: (estimateId) =>
    api(`/estimates/${estimateId}/forming-materials/refresh`, { method: "POST" }),
  setFormPercent: (estimateId, form_percent) =>
    api(`/estimates/${estimateId}/forming-materials/form-percent`, {
      method: "PUT",
      body: { form_percent },
    }),
  // Labor + supervision
  laborMaterials: (estimateId) => api(`/estimates/${estimateId}/labor`),
  refreshLabor: (estimateId) =>
    api(`/estimates/${estimateId}/labor/refresh`, { method: "POST" }),
  patchLaborLine: (estimateId, code, body) =>
    api(`/estimates/${estimateId}/labor/lines/${encodeURIComponent(code)}`, {
      method: "PATCH",
      body,
    }),
  // Estimate equipment (day fleet + pumping)
  estimateEquipment: (estimateId) => api(`/estimates/${estimateId}/equipment`),
  refreshEstimateEquipment: (estimateId) =>
    api(`/estimates/${estimateId}/equipment/refresh`, { method: "POST" }),
  patchEstimateEquipmentLine: (estimateId, code, body) =>
    api(`/estimates/${estimateId}/equipment/lines/${encodeURIComponent(code)}`, {
      method: "PATCH",
      body,
    }),
  // Catalogs
  listMixes: (params = {}) => {
    const q = new URLSearchParams(params).toString();
    return api(`/mix-designs${q ? "?" + q : ""}`);
  },
  listMaterials: (params = {}) => {
    const q = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v != null && v !== "") q.set(k, v);
    });
    const s = q.toString();
    return api(`/materials${s ? "?" + s : ""}`);
  },
  materialCategories: () => api("/materials/meta/categories"),
  listEquipment: (params = {}) => {
    const q = new URLSearchParams(params).toString();
    return api(`/equipment${q ? "?" + q : ""}`);
  },
};
