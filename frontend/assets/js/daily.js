/**
 * Daily reports from the field (sql/084, 2026-09-09).
 *
 * Two pages. `renderDaily` is the office's: the reports newest first with
 * filters, the totals by job and month, the whole report in a modal, and the
 * two pick-lists (jobs, foremen) the form offers. `renderReportForm` is the
 * form itself — the Jotform "S and S Daily Construction Report" rebuilt for a
 * phone, English and Spanish on a toggle — which a foreman signing in lands
 * on and sees nothing else of; the office opens it from the list and edits a
 * report through it.
 *
 * app.js hands the shared helpers over through initDaily; nothing here
 * reaches back into it. The Spanish is the Jotform form's own wording.
 */
import { Api } from "./api.js";

let d = null;

/** app.js calls this once with { state, $, $$, esc, toast, setRoute, canAct, render }. */
export function initDaily(deps) {
  d = deps;
}

const TRADES = ["foreman", "assistants", "rod_busters", "form_setters", "finishers", "laborers"];
const SUB_TRADES = ["finishers", "form_setters", "rod_busters", "laborers"];
const MAINT = ["fuel", "grease", "oil", "hydraulic", "tires"];

const WORDS = {
  en: {
    title: "Daily report",
    edit: "Edit daily report",
    date: "Date",
    job: "Job",
    foremen: "Foreman",
    crew: "Man power",
    workers: "Workers",
    hours: "Hours each",
    subs: "Sub labor",
    sub_name: "Sub name",
    work: "Work accomplished",
    delays: "Delays",
    safety: "Safety concerns",
    plan: "Plan for tomorrow",
    poured: "Concrete poured today?",
    yes: "Yes",
    no: "No",
    yards: "Yards poured",
    supplier: "Concrete supplier",
    what: "What was poured? (e.g. slab, columns)",
    tax: "Tax exempt",
    maint: "Maintenance performed",
    submit: "Send report",
    save: "Save",
    cancel: "Cancel",
    sent: "Report sent",
    another: "Another report",
    list: "Back to the list",
    pick: "Choose…",
    need_job: "Choose the job",
    need_foreman: "Choose the foreman",
    another_foreman: "+ Another foreman",
    mgmt: "Management notes",
    mgmt_hint: "seniors, management and admins only",
    o_title: "Concrete order",
    o_edit: "Edit concrete order",
    o_ordered_on: "Date ordered",
    o_supplier: "Concrete supplier",
    o_pour_date: "Date of pour",
    o_pour_time: "Time of pour",
    o_yards: "Yards ordered",
    o_mix: "Mix design (the supplier's mix number)",
    o_number: "Order number",
    o_by: "Ordered by",
    o_notes: "Notes",
    o_status: "Status",
    o_submit: "Send order",
    o_sent: "Order sent",
    o_another: "Another order",
    o_list: "Back to the orders",
    o_need_supplier: "Choose the supplier",
    o_need_yards: "Enter the yards",
    st_ordered: "Ordered",
    st_confirmed: "Confirmed",
    st_poured: "Poured",
    st_canceled: "Canceled",
    st_delivered: "Delivered",
    m_title: "Material order",
    m_edit: "Edit material order",
    m_kind: "What kind",
    m_supplier: "Supplier",
    m_description: "What (sizes, lengths, the shop drawing)",
    m_quantity: "Quantity",
    m_unit: "Unit",
    m_needed_by: "Needed on site by",
    m_delivered_on: "Delivered on",
    m_submit: "Send order",
    m_sent: "Order sent",
    m_another: "Another order",
    m_list: "Back to the orders",
    m_need_description: "Say what the material is",
    k_rebar: "Rebar",
    k_post_tension: "Post-tension",
    k_other: "Other",
    trades: {
      foreman: "Foreman",
      assistants: "Assistants",
      rod_busters: "Rod busters",
      form_setters: "Form setters",
      finishers: "Finishers",
      laborers: "Laborers",
    },
    maints: {
      fuel: "Checked fuel level",
      grease: "Grease machine",
      oil: "Check oil level",
      hydraulic: "Check hydraulic fluid level",
      tires: "Tire pressure",
    },
  },
  es: {
    title: "Reporte diario",
    edit: "Editar reporte",
    date: "Fecha",
    job: "Proyecto",
    foremen: "Mayordomo",
    crew: "Mano de obra",
    workers: "Trabajadores",
    hours: "Horas cada uno",
    subs: "Subcontratistas",
    sub_name: "Nombre del sub",
    work: "Trabajo realizado",
    delays: "Demoras",
    safety: "Preocupaciones de seguridad",
    plan: "Plan para mañana",
    poured: "¿Se coló concreto hoy?",
    yes: "Sí",
    no: "No",
    yards: "Yardas tiradas",
    supplier: "Proveedor de concreto",
    what: "¿Qué se tiró? (e.j. losa, columnas)",
    tax: "Exento de impuestos",
    maint: "Mantenimiento realizado",
    submit: "Enviar reporte",
    save: "Guardar",
    cancel: "Cancelar",
    sent: "Reporte enviado",
    another: "Otro reporte",
    list: "Volver a la lista",
    pick: "Elegir…",
    need_job: "Elija el proyecto",
    need_foreman: "Elija el mayordomo",
    another_foreman: "+ Otro mayordomo",
    mgmt: "Notas de gerencia",
    mgmt_hint: "solo estimadores senior, gerencia y administradores",
    o_title: "Pedido de concreto",
    o_edit: "Editar pedido",
    o_ordered_on: "Fecha del pedido",
    o_supplier: "Proveedor de concreto",
    o_pour_date: "Fecha del colado",
    o_pour_time: "Hora del colado",
    o_yards: "Yardas pedidas",
    o_mix: "Diseño de mezcla (el número del proveedor)",
    o_number: "Número de pedido",
    o_by: "Pedido por",
    o_notes: "Notas",
    o_status: "Estado",
    o_submit: "Enviar pedido",
    o_sent: "Pedido enviado",
    o_another: "Otro pedido",
    o_list: "Volver a los pedidos",
    o_need_supplier: "Elija el proveedor",
    o_need_yards: "Escriba las yardas",
    st_ordered: "Pedido",
    st_confirmed: "Confirmado",
    st_poured: "Colado",
    st_canceled: "Cancelado",
    st_delivered: "Entregado",
    m_title: "Pedido de material",
    m_edit: "Editar pedido de material",
    m_kind: "Qué tipo",
    m_supplier: "Proveedor",
    m_description: "Qué es (medidas, largos, el plano de taller)",
    m_quantity: "Cantidad",
    m_unit: "Unidad",
    m_needed_by: "Necesario en obra para el",
    m_delivered_on: "Entregado el",
    m_submit: "Enviar pedido",
    m_sent: "Pedido enviado",
    m_another: "Otro pedido",
    m_list: "Volver a los pedidos",
    m_need_description: "Diga qué material es",
    k_rebar: "Varilla",
    k_post_tension: "Postensado",
    k_other: "Otro",
    trades: {
      foreman: "Mayordomo",
      assistants: "Asistentes",
      rod_busters: "Fierreros",
      form_setters: "Carpinteros",
      finishers: "Acabadores",
      laborers: "Ayudantes",
    },
    maints: {
      fuel: "Revisó el combustible",
      grease: "Engrasado",
      oil: "Nivel de aceite",
      hydraulic: "Nivel hidráulico",
      tires: "Presión de llantas",
    },
  },
};

let lang = "en";
try {
  lang = localStorage.getItem("daily_lang") === "es" ? "es" : "en";
} catch {
  lang = "en";
}

/** A word by path: "work", or "trades.foreman". */
function word(path, which = lang) {
  const parts = path.split(".");
  let node = WORDS[which];
  for (const p of parts) node = node ? node[p] : undefined;
  if (node === undefined && which !== "en") return word(path, "en");
  return node === undefined ? path : node;
}

export function todayLocal() {
  const n = new Date();
  return [n.getFullYear(), String(n.getMonth() + 1).padStart(2, "0"), String(n.getDate()).padStart(2, "0")].join("-");
}

export function shiftDays(iso, days) {
  const t = new Date(iso + "T00:00:00");
  t.setDate(t.getDate() + days);
  return [t.getFullYear(), String(t.getMonth() + 1).padStart(2, "0"), String(t.getDate()).padStart(2, "0")].join("-");
}

export function day(iso) {
  if (!iso) return "—";
  return new Date(iso + "T00:00:00").toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

function n1(v) {
  if (v == null || v === "") return "—";
  const x = Number(v);
  if (Number.isNaN(x)) return "—";
  return x.toLocaleString(undefined, { maximumFractionDigits: 1 });
}

function monthLabel(ym) {
  const [y, m] = ym.split("-");
  return new Date(Number(y), Number(m) - 1, 1).toLocaleDateString(undefined, { month: "short", year: "numeric" });
}

// ---------------------------------------------------------- the office --

export async function renderDaily(root) {
  const { $, $$, esc, toast, setRoute, canAct } = d;
  root.innerHTML = `<div class="loading">Loading daily reports…</div>`;
  let meta = await Api.dailyReportMeta();
  const filters = { job_id: "", foreman: "", range: "60", date_from: "", date_to: "", poured: false, q: "" };
  let reports = [];
  let summary = [];
  let showLists = false;

  const params = () => {
    const p = {};
    if (filters.job_id) p.job_id = filters.job_id;
    if (filters.foreman) p.foreman = filters.foreman;
    if (filters.range === "custom") {
      if (filters.date_from) p.date_from = filters.date_from;
      if (filters.date_to) p.date_to = filters.date_to;
    } else if (filters.range === "year") {
      p.date_from = todayLocal().slice(0, 4) + "-01-01";
    } else if (filters.range !== "all") {
      p.date_from = shiftDays(todayLocal(), -Number(filters.range));
    }
    return p;
  };

  const load = async () => {
    const p = params();
    const listParams = { ...p, limit: 2000 };
    if (filters.poured) listParams.poured = "true";
    if (filters.q) listParams.q = filters.q;
    [reports, summary] = await Promise.all([Api.listDailyReports(listParams), Api.dailyReportSummary(p)]);
    paint();
  };

  const totals = () => {
    const t = { reports: reports.length, pours: 0, yards: 0, man_hours: 0, sub_man_hours: 0 };
    reports.forEach((r) => {
      if (r.concrete_poured) t.pours += 1;
      t.yards += Number(r.yards_poured || 0);
      t.man_hours += Number(r.man_hours || 0);
      t.sub_man_hours += Number(r.sub_man_hours || 0);
    });
    return t;
  };

  const clamp =
    "display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;font-size:0.8rem;max-width:26rem";

  const table = () => {
    if (!reports.length) return `<div class="empty">No daily reports match.</div>`;
    return `<div class="table-wrap"><table class="data">
      <thead><tr>
        <th>Date</th><th>Job</th><th>Foreman</th><th class="num">Crew</th><th class="num">Subs</th><th>Pour</th><th>Work accomplished</th><th></th>
      </tr></thead>
      <tbody>${reports
        .map(
          (r) => `<tr data-report="${esc(r.id)}" class="clickable">
          <td style="white-space:nowrap">${esc(day(r.report_date))}${r.source === "jotform" ? ` <span class="muted" title="Imported from Jotform" style="font-size:0.7rem">JF</span>` : ""}</td>
          <td><strong>${esc(r.job_name)}</strong></td>
          <td>${esc((r.foremen || []).join(", ") || "—")}</td>
          <td class="num" title="workers · man-hours">${r.workers || 0} · ${n1(r.man_hours)} h</td>
          <td class="num" title="sub workers · man-hours">${r.sub_workers ? `${r.sub_workers} · ${n1(r.sub_man_hours)} h` : "—"}</td>
          <td style="white-space:nowrap">${
            r.concrete_poured
              ? `<span class="badge ok">${n1(r.yards_poured)} yd</span>${r.supplier ? ` <span class="muted">${esc(r.supplier)}</span>` : ""}`
              : `<span class="muted">—</span>`
          }</td>
          <td><div class="muted" style="${clamp}" title="${esc(r.work_accomplished || "")}">${esc(r.work_accomplished || "")}</div></td>
          <td style="white-space:nowrap">
            <button type="button" class="btn ghost" data-view="${esc(r.id)}">View</button>
            ${canAct("estimator") ? `<button type="button" class="btn ghost" data-edit="${esc(r.id)}">Edit</button>` : ""}
          </td>
        </tr>`
        )
        .join("")}</tbody></table></div>`;
  };

  const summaryTable = () => {
    if (!summary.length) return "";
    return `<details style="margin-bottom:1rem"><summary style="cursor:pointer;color:var(--text-muted)">By job and month (${summary.length})</summary>
      <div class="table-wrap" style="margin-top:0.5rem"><table class="data">
      <thead><tr><th>Job</th><th>Month</th><th class="num">Reports</th><th class="num">Pours</th><th class="num">Yards</th><th class="num">Man-hours</th><th class="num">Sub man-hours</th></tr></thead>
      <tbody>${summary
        .map(
          (s) => `<tr><td>${esc(s.job_name)}</td><td>${esc(monthLabel(s.month))}</td><td class="num">${s.reports}</td><td class="num">${s.pours}</td>
          <td class="num">${n1(s.yards)}</td><td class="num">${n1(s.man_hours)}</td><td class="num">${n1(s.sub_man_hours)}</td></tr>`
        )
        .join("")}</tbody></table></div></details>`;
  };

  const listsPanel = () => {
    if (!showLists) return "";
    const rows = (items, kind) =>
      items
        .map(
          (x) => `<tr>
          <td>${esc(x.name)}${kind === "job" && x.project_name ? ` <span class="muted">→ ${esc(x.project_name)}</span>` : ""}</td>
          <td class="num">${x.reports}</td><td class="muted" style="white-space:nowrap">${esc(day(x.last_report))}</td>
          <td><label style="display:flex;align-items:center;gap:0.4rem"><input type="checkbox" data-${kind}-active="${x.id}"${x.is_active ? " checked" : ""} /> on the form</label></td>
          <td>${canAct("senior_estimator") ? `<button type="button" class="btn danger ghost" data-del-${kind}="${x.id}">Delete</button>` : ""}</td>
        </tr>`
        )
        .join("");
    return `<div class="grid" style="grid-template-columns:repeat(auto-fit,minmax(320px,1fr));margin-bottom:1rem">
      <div class="card"><h3 style="margin:0 0 0.5rem">Jobs on the form</h3>
        <div class="table-wrap"><table class="data"><thead><tr><th>Job</th><th class="num">Reports</th><th>Last</th><th></th><th></th></tr></thead><tbody>${rows(meta.jobs, "job")}</tbody></table></div>
        <form id="add-job" class="toolbar" style="margin:0.6rem 0 0"><input name="name" placeholder="New job name" required maxlength="200" style="flex:1" /><button class="btn primary" type="submit">Add</button></form>
      </div>
      <div class="card"><h3 style="margin:0 0 0.5rem">Foremen on the form</h3>
        <div class="table-wrap"><table class="data"><thead><tr><th>Foreman</th><th class="num">Reports</th><th>Last</th><th></th><th></th></tr></thead><tbody>${rows(meta.foremen, "foreman")}</tbody></table></div>
        <form id="add-foreman" class="toolbar" style="margin:0.6rem 0 0"><input name="name" placeholder="New foreman" required maxlength="200" style="flex:1" /><button class="btn primary" type="submit">Add</button></form>
      </div>
    </div>`;
  };

  const paint = () => {
    const t = totals();
    $("#daily-counts").innerHTML =
      `<strong>${t.reports}</strong> reports · <strong>${t.pours}</strong> pours · <strong>${n1(t.yards)}</strong> yards · ` +
      `<strong>${n1(t.man_hours)}</strong> crew man-hours · <strong>${n1(t.sub_man_hours)}</strong> sub man-hours`;
    $("#daily-lists").innerHTML = listsPanel();
    $("#daily-body").innerHTML = summaryTable() + table();
    wire();
  };

  const wire = () => {
    $$("[data-view]", root).forEach((btn) => {
      btn.onclick = () => {
        const r = reports.find((x) => x.id === btn.dataset.view);
        if (r) openReportModal(r, { onChanged: load });
      };
    });
    $$("[data-edit]", root).forEach((btn) => {
      btn.onclick = () => setRoute("report", { reportId: btn.dataset.edit });
    });
    $$("tr[data-report]", root).forEach((tr) => {
      tr.ondblclick = () => {
        const r = reports.find((x) => x.id === tr.dataset.report);
        if (r) openReportModal(r, { onChanged: load });
      };
    });
    $$("[data-job-active]", root).forEach((box) => {
      box.onchange = async () => {
        try {
          await Api.updateFieldJob(box.dataset.jobActive, { is_active: box.checked });
          meta = await Api.dailyReportMeta();
          paint();
        } catch (err) {
          toast(err.message, "err");
        }
      };
    });
    $$("[data-foreman-active]", root).forEach((box) => {
      box.onchange = async () => {
        try {
          await Api.updateFieldForeman(box.dataset.foremanActive, { is_active: box.checked });
          meta = await Api.dailyReportMeta();
          paint();
        } catch (err) {
          toast(err.message, "err");
        }
      };
    });
    const refresh = async () => {
      meta = await Api.dailyReportMeta();
      await load();
    };
    $$("[data-del-job]", root).forEach((btn) => {
      btn.onclick = () => {
        const job = meta.jobs.find((j) => String(j.id) === btn.dataset.delJob);
        if (!job) return;
        if (!job.reports) {
          if (!confirm(`Delete the job "${job.name}"?`)) return;
          Api.deleteFieldJob(job.id).then(refresh).catch((err) => toast(err.message, "err"));
          return;
        }
        openMoveDeleteModal({ kind: "job", item: job, others: meta.jobs.filter((j) => j.id !== job.id), onDone: refresh });
      };
    });
    $$("[data-del-foreman]", root).forEach((btn) => {
      btn.onclick = () => {
        const f = meta.foremen.find((x) => String(x.id) === btn.dataset.delForeman);
        if (!f) return;
        if (!f.reports) {
          if (!confirm(`Delete the foreman "${f.name}"?`)) return;
          Api.deleteFieldForeman(f.id).then(refresh).catch((err) => toast(err.message, "err"));
          return;
        }
        openMoveDeleteModal({ kind: "foreman", item: f, others: meta.foremen.filter((x) => x.id !== f.id), onDone: refresh });
      };
    });
    const addJob = $("#add-job", root);
    if (addJob) {
      addJob.onsubmit = async (e) => {
        e.preventDefault();
        try {
          await Api.createFieldJob({ name: String(new FormData(e.target).get("name")).trim() });
          meta = await Api.dailyReportMeta();
          paint();
        } catch (err) {
          toast(err.message, "err");
        }
      };
    }
    const addForeman = $("#add-foreman", root);
    if (addForeman) {
      addForeman.onsubmit = async (e) => {
        e.preventDefault();
        try {
          await Api.createFieldForeman({ name: String(new FormData(e.target).get("name")).trim() });
          meta = await Api.dailyReportMeta();
          paint();
        } catch (err) {
          toast(err.message, "err");
        }
      };
    }
  };

  const jobOptions = () =>
    `<option value="">All jobs</option>` +
    meta.jobs
      .map((j) => `<option value="${j.id}">${esc(j.name)}${j.is_active ? "" : " (off the form)"}</option>`)
      .join("");
  const foremanOptions = () =>
    `<option value="">Any foreman</option>` + meta.foremen.map((f) => `<option value="${esc(f.name)}">${esc(f.name)}</option>`).join("");

  root.innerHTML = `
    <div class="page-header">
      <div>
        <h1>Daily reports</h1>
        <p id="daily-counts"></p>
      </div>
      <div class="toolbar" style="margin:0">
        ${canAct("estimator") ? `<button class="btn ghost" id="btn-lists">Jobs &amp; foremen</button>` : ""}
        ${canAct("estimator") ? `<button class="btn primary" id="btn-new-report">+ New report</button>` : ""}
      </div>
    </div>
    <div class="toolbar">
      <select id="daily-job">${jobOptions()}</select>
      <select id="daily-foreman">${foremanOptions()}</select>
      <select id="daily-range">
        <option value="30">Last 30 days</option>
        <option value="60" selected>Last 60 days</option>
        <option value="180">Last 6 months</option>
        <option value="year">This year</option>
        <option value="all">All time</option>
        <option value="custom">Between dates…</option>
      </select>
      <span id="daily-custom" class="hidden"><input type="date" id="daily-from" /> – <input type="date" id="daily-to" /></span>
      <label style="display:flex;align-items:center;gap:0.35rem"><input type="checkbox" id="daily-poured" /> Pours only</label>
      <input id="daily-q" placeholder="Search the reports…" style="min-width:200px" />
    </div>
    <div id="daily-lists"></div>
    <div id="daily-body"><div class="loading">Loading…</div></div>
  `;

  $("#daily-job").onchange = (e) => {
    filters.job_id = e.target.value;
    load();
  };
  $("#daily-foreman").onchange = (e) => {
    filters.foreman = e.target.value;
    load();
  };
  $("#daily-range").onchange = (e) => {
    filters.range = e.target.value;
    $("#daily-custom").classList.toggle("hidden", filters.range !== "custom");
    if (filters.range !== "custom") load();
  };
  $("#daily-from").onchange = (e) => {
    filters.date_from = e.target.value;
    load();
  };
  $("#daily-to").onchange = (e) => {
    filters.date_to = e.target.value;
    load();
  };
  $("#daily-poured").onchange = (e) => {
    filters.poured = e.target.checked;
    load();
  };
  let timer;
  $("#daily-q").oninput = (e) => {
    clearTimeout(timer);
    timer = setTimeout(() => {
      filters.q = e.target.value.trim();
      load();
    }, 250);
  };
  const lists = $("#btn-lists");
  if (lists) {
    lists.onclick = () => {
      showLists = !showLists;
      paint();
    };
  }
  const fresh = $("#btn-new-report");
  if (fresh) fresh.onclick = () => setRoute("report");
  await load();
}

/** The whole report, read-only, with Edit and Delete for the office. The dashboard opens it too. */
export function openReportModal(r, { onChanged } = {}) {
  const { $, esc, toast, setRoute, canAct } = d;
  const backdrop = document.createElement("div");
  backdrop.className = "modal-backdrop";
  const text = (label, v) =>
    v ? `<div class="field full"><label>${label}</label><div style="white-space:pre-wrap">${esc(v)}</div></div>` : "";
  const crewRows = (r.crew || [])
    .map(
      (c) => `<tr><td>${esc(word("trades." + c.trade, "en"))}</td><td class="num">${c.workers}</td><td class="num">${n1(c.hours)}</td><td class="num">${n1(c.man_hours)}</td></tr>`
    )
    .join("");
  const subRows = (r.subs || [])
    .map(
      (s) => `<tr><td>${esc(s.sub_name)} <span class="muted">${esc(word("trades." + s.trade, "en"))}</span></td><td class="num">${s.workers}</td><td class="num">${n1(s.hours)}</td><td class="num">${n1(s.man_hours)}</td></tr>`
    )
    .join("");
  backdrop.innerHTML = `
    <div class="modal" style="width:min(760px,100%)">
      <h2 style="margin-bottom:0.2rem">${esc(r.job_name)} — ${esc(day(r.report_date))}</h2>
      <p class="muted" style="margin-top:0">${esc((r.foremen || []).join(", ") || "no foreman named")} ·
        ${r.source === "jotform" ? "imported from Jotform" : `filed in the app${r.submitted_by_name ? ` by ${esc(r.submitted_by_name)}` : ""}`}
        · ${esc(new Date(r.submitted_at).toLocaleString())}</p>
      <div class="form-grid" style="grid-template-columns:1fr 1fr">
        <div class="field"><label>Man power</label>
          ${crewRows ? `<table class="data"><thead><tr><th></th><th class="num">Workers</th><th class="num">Hours</th><th class="num">Man-hours</th></tr></thead><tbody>${crewRows}</tbody>
            <tfoot><tr><td>Total</td><td class="num">${r.workers}</td><td></td><td class="num">${n1(r.man_hours)}</td></tr></tfoot></table>` : `<div class="muted">—</div>`}
        </div>
        <div class="field"><label>Sub labor</label>
          ${subRows ? `<table class="data"><thead><tr><th></th><th class="num">Workers</th><th class="num">Hours</th><th class="num">Man-hours</th></tr></thead><tbody>${subRows}</tbody>
            <tfoot><tr><td>Total</td><td class="num">${r.sub_workers}</td><td></td><td class="num">${n1(r.sub_man_hours)}</td></tr></tfoot></table>` : `<div class="muted">—</div>`}
        </div>
        <div class="field full"><label>Concrete</label>
          ${
            r.concrete_poured
              ? `<div><span class="badge ok">${n1(r.yards_poured)} yards</span> ${esc(r.supplier || "")}${r.what_poured ? ` — ${esc(r.what_poured)}` : ""}${r.tax_exempt ? ` <span class="badge info">tax exempt</span>` : ""}</div>`
              : `<div class="muted">No pour</div>`
          }
        </div>
        ${text("Work accomplished", r.work_accomplished)}
        ${text("Delays", r.delays)}
        ${text("Safety concerns", r.safety_concerns)}
        ${text("Plan for tomorrow", r.plan_tomorrow)}
        ${text("Comments", r.comments)}
        <div class="field full"><label>Maintenance performed</label>
          <div class="chips">${(r.maintenance || []).map((k) => `<span class="chip">${esc(word("maints." + k, "en"))}</span>`).join("") || `<span class="muted">—</span>`}</div>
        </div>
        ${r.signature_url ? `<div class="field full"><a href="${esc(r.signature_url)}" target="_blank" rel="noopener">signature ↗</a></div>` : ""}
        ${canAct("senior_estimator") && r.management_notes ? text("Management notes", r.management_notes) : ""}
      </div>
      <div class="modal-actions">
        ${canAct("senior_estimator") ? `<button type="button" class="btn danger ghost" id="rep-delete">Delete</button>` : ""}
        <button type="button" class="btn ghost" id="rep-close">Close</button>
        ${canAct("estimator") ? `<button type="button" class="btn primary" id="rep-edit">Edit</button>` : ""}
      </div>
    </div>`;
  document.body.appendChild(backdrop);
  $("#rep-close", backdrop).onclick = () => backdrop.remove();
  backdrop.addEventListener("click", (e) => {
    if (e.target === backdrop) backdrop.remove();
  });
  const edit = $("#rep-edit", backdrop);
  if (edit) {
    edit.onclick = () => {
      backdrop.remove();
      setRoute("report", { reportId: r.id });
    };
  }
  const del = $("#rep-delete", backdrop);
  if (del) {
    del.onclick = async () => {
      if (!confirm(`Delete the ${day(r.report_date)} report for ${r.job_name}?`)) return;
      try {
        await Api.deleteDailyReport(r.id);
        toast("Report deleted");
        backdrop.remove();
        if (onChanged) onChanged();
      } catch (err) {
        toast(err.message, "err");
      }
    };
  }
}

// ------------------------------------------------------------ the form --

export async function renderReportForm(root) {
  const { $, $$, esc, toast, setRoute, state, canAct } = d;
  root.innerHTML = `<div class="loading">Loading…</div>`;
  const meta = await Api.dailyReportMeta();
  const existing = state.reportId ? await Api.getDailyReport(state.reportId) : null;
  const field = !!state.user && state.user.role === "foreman";

  // A foreman's own name, preselected when it is on the list.
  const me = ((state.user && state.user.full_name) || "").trim().toLowerCase();
  const mine = field
    ? meta.foremen.find((f) => {
        const short = f.name.toLowerCase().split("(")[0].trim();
        return f.is_active && (f.name.toLowerCase() === me || (short && me.startsWith(short)));
      })
    : null;
  const chosenNames = existing ? existing.foremen : mine ? [mine.name] : [];
  const chosenForemen = new Set(chosenNames.map((n) => n.toLowerCase()));
  const crewBy = {};
  (existing ? existing.crew : []).forEach((c) => {
    crewBy[c.trade] = c;
  });
  const subsBy = {};
  (existing ? existing.subs : []).forEach((s) => {
    if (!subsBy[s.trade]) subsBy[s.trade] = s;
  });

  const jobs = meta.jobs.filter((j) => j.is_active || (existing && j.id === existing.job_id));
  const foremen = meta.foremen.filter((f) => f.is_active || chosenForemen.has(f.name.toLowerCase()));
  const suppliers = meta.suppliers.slice();
  if (existing && existing.supplier && !suppliers.some((s) => s.toLowerCase() === existing.supplier.toLowerCase())) {
    suppliers.push(existing.supplier);
  }
  const poured = existing ? existing.concrete_poured : false;

  // Chad, 2026-09-09: "make foreman a dropdown". One select; "+ Another foreman"
  // adds a second, since the Jotform field allowed several and some reports carry four.
  const foremanSelect = (value) =>
    `<select name="foremen" class="foreman-pick">
      <option value="" data-w="pick">${esc(word("pick"))}</option>
      ${foremen
        .map((f) => `<option value="${esc(f.name)}"${value && f.name.toLowerCase() === value.toLowerCase() ? " selected" : ""}>${esc(f.name)}</option>`)
        .join("")}
    </select>`;

  root.innerHTML = `
    <form id="report-form" class="report-form card">
      <div style="display:flex;flex-wrap:wrap;justify-content:space-between;align-items:center;gap:0.5rem;margin-bottom:0.6rem">
        <h2 style="margin:0" data-w="${existing ? "edit" : "title"}">${esc(word(existing ? "edit" : "title"))}</h2>
        <div class="lang-toggle">
          <button type="button" data-lang="en"${lang === "en" ? ' class="active"' : ""}>English</button>
          <button type="button" data-lang="es"${lang === "es" ? ' class="active"' : ""}>Español</button>
        </div>
      </div>

      <div class="field"><label data-w="date">${esc(word("date"))}</label>
        <input type="date" name="report_date" required value="${esc(existing ? existing.report_date : todayLocal())}" /></div>

      <div class="field"><label data-w="job">${esc(word("job"))}</label>
        <select name="job_id" required>
          <option value="" data-w="pick">${esc(word("pick"))}</option>
          ${jobs.map((j) => `<option value="${j.id}"${existing && existing.job_id === j.id ? " selected" : ""}>${esc(j.name)}</option>`).join("")}
        </select></div>

      <div class="field"><label data-w="foremen">${esc(word("foremen"))}</label>
        <div id="foremen-picks" style="display:grid;gap:0.4rem">
          ${(chosenNames.length ? chosenNames : [""]).map((name) => foremanSelect(name)).join("")}
        </div>
        <a href="#" id="foreman-more" data-w="another_foreman" style="font-size:0.9rem;margin-top:0.3rem">${esc(word("another_foreman"))}</a>
      </div>

      <div class="field"><label data-w="crew">${esc(word("crew"))}</label>
        <div class="grid-3 head"><span></span><span data-w="workers">${esc(word("workers"))}</span><span data-w="hours">${esc(word("hours"))}</span></div>
        ${TRADES.map(
          (t) => `<div class="grid-3">
            <span class="row-label" data-w="trades.${t}">${esc(word("trades." + t))}</span>
            <input type="number" inputmode="numeric" min="0" max="999" step="1" name="crew_workers_${t}" value="${crewBy[t] ? crewBy[t].workers : ""}" />
            <input type="number" inputmode="decimal" min="0" max="24" step="0.5" name="crew_hours_${t}" value="${crewBy[t] ? n1(crewBy[t].hours).replace(",", "") : ""}" />
          </div>`
        ).join("")}
      </div>

      <div class="field"><label data-w="subs">${esc(word("subs"))}</label>
        <div class="grid-4 head"><span></span><span data-w="sub_name">${esc(word("sub_name"))}</span><span data-w="workers">${esc(word("workers"))}</span><span data-w="hours">${esc(word("hours"))}</span></div>
        ${SUB_TRADES.map(
          (t) => `<div class="grid-4">
            <span class="row-label" data-w="trades.${t}">${esc(word("trades." + t))}</span>
            <input type="text" name="sub_name_${t}" maxlength="200" value="${esc(subsBy[t] ? subsBy[t].sub_name : "")}" />
            <input type="number" inputmode="numeric" min="0" max="999" step="1" name="sub_workers_${t}" value="${subsBy[t] ? subsBy[t].workers : ""}" />
            <input type="number" inputmode="decimal" min="0" max="24" step="0.5" name="sub_hours_${t}" value="${subsBy[t] ? n1(subsBy[t].hours).replace(",", "") : ""}" />
          </div>`
        ).join("")}
      </div>

      <div class="field"><label data-w="work">${esc(word("work"))}</label>
        <textarea name="work_accomplished" rows="4">${esc(existing ? existing.work_accomplished || "" : "")}</textarea></div>
      <div class="field"><label data-w="delays">${esc(word("delays"))}</label>
        <textarea name="delays" rows="2">${esc(existing ? existing.delays || "" : "")}</textarea></div>
      <div class="field"><label data-w="safety">${esc(word("safety"))}</label>
        <textarea name="safety_concerns" rows="2">${esc(existing ? existing.safety_concerns || "" : "")}</textarea></div>
      <div class="field"><label data-w="plan">${esc(word("plan"))}</label>
        <textarea name="plan_tomorrow" rows="3">${esc(existing ? existing.plan_tomorrow || "" : "")}</textarea></div>

      <div class="field"><label data-w="poured">${esc(word("poured"))}</label>
        <div class="choices row">
          <label><input type="radio" name="concrete_poured" value="yes"${poured ? " checked" : ""} /> <span data-w="yes">${esc(word("yes"))}</span></label>
          <label><input type="radio" name="concrete_poured" value="no"${poured ? "" : " checked"} /> <span data-w="no">${esc(word("no"))}</span></label>
        </div></div>
      <div id="pour-block" class="${poured ? "" : "hidden"}">
        <div class="field"><label data-w="yards">${esc(word("yards"))}</label>
          <input type="number" inputmode="decimal" min="0" step="0.5" name="yards_poured" value="${existing && existing.yards_poured != null ? esc(String(existing.yards_poured)) : ""}" /></div>
        <div class="field"><label data-w="supplier">${esc(word("supplier"))}</label>
          <select name="supplier"><option value="" data-w="pick">${esc(word("pick"))}</option>
            ${suppliers.map((s) => `<option value="${esc(s)}"${existing && existing.supplier && existing.supplier.toLowerCase() === s.toLowerCase() ? " selected" : ""}>${esc(s)}</option>`).join("")}
          </select></div>
        <div class="field"><label data-w="what">${esc(word("what"))}</label>
          <textarea name="what_poured" rows="2">${esc(existing ? existing.what_poured || "" : "")}</textarea></div>
        <div class="field"><label data-w="tax">${esc(word("tax"))}</label>
          <div class="choices row">
            <label><input type="radio" name="tax_exempt" value="yes"${existing && existing.tax_exempt === true ? " checked" : ""} /> <span data-w="yes">${esc(word("yes"))}</span></label>
            <label><input type="radio" name="tax_exempt" value="no"${existing && existing.tax_exempt === false ? " checked" : ""} /> <span data-w="no">${esc(word("no"))}</span></label>
          </div></div>
      </div>

      <div class="field"><label data-w="maint">${esc(word("maint"))}</label>
        <div class="choices">
          ${MAINT.map(
            (k) => `<label><input type="checkbox" name="maintenance" value="${k}"${existing && (existing.maintenance || []).includes(k) ? " checked" : ""} /> <span data-w="maints.${k}">${esc(word("maints." + k))}</span></label>`
          ).join("")}
        </div></div>

      ${
        canAct("senior_estimator")
          ? `<div class="field"><label><span data-w="mgmt">${esc(word("mgmt"))}</span> <span class="muted" data-w="mgmt_hint">(${esc(word("mgmt_hint"))})</span></label>
        <textarea name="management_notes" rows="3">${esc(existing ? existing.management_notes || "" : "")}</textarea></div>`
          : ""
      }
      <div id="report-error" class="error-banner hidden"></div>
      <div class="modal-actions" style="flex-direction:column;gap:0.5rem">
        <button type="submit" class="btn primary big" data-w="${existing ? "save" : "submit"}">${esc(word(existing ? "save" : "submit"))}</button>
        ${existing || !field ? `<button type="button" class="btn ghost big" id="report-cancel" data-w="cancel">${esc(word("cancel"))}</button>` : ""}
      </div>
    </form>`;

  const form = $("#report-form", root);

  const relabel = () => {
    $$("[data-w]", form).forEach((el) => {
      el.textContent = word(el.dataset.w);
    });
    $$("[data-lang]", form).forEach((b) => b.classList.toggle("active", b.dataset.lang === lang));
  };
  $$("[data-lang]", form).forEach((b) => {
    b.onclick = () => {
      lang = b.dataset.lang;
      try {
        localStorage.setItem("daily_lang", lang);
      } catch {
        // a private window; the choice lasts the page
      }
      relabel();
    };
  });

  // A worker count typed with no hours beside it is a day: eight.
  TRADES.forEach((t) => {
    form[`crew_workers_${t}`].oninput = (e) => {
      const hours = form[`crew_hours_${t}`];
      if (Number(e.target.value) > 0 && !hours.value) hours.value = "8";
    };
  });
  SUB_TRADES.forEach((t) => {
    form[`sub_workers_${t}`].oninput = (e) => {
      const hours = form[`sub_hours_${t}`];
      if (Number(e.target.value) > 0 && !hours.value) hours.value = "8";
    };
  });
  $$("input[name=concrete_poured]", form).forEach((r) => {
    r.onchange = () => $("#pour-block", form).classList.toggle("hidden", form.concrete_poured.value !== "yes");
  });

  $("#foreman-more", form).onclick = (e) => {
    e.preventDefault();
    const picks = $("#foremen-picks", form);
    if (picks.querySelectorAll("select").length >= 4) return;
    picks.insertAdjacentHTML("beforeend", foremanSelect(""));
    picks.lastElementChild.focus();
  };

  const cancel = $("#report-cancel", form);
  if (cancel) cancel.onclick = () => setRoute(field ? "report" : "daily");

  const payload = () => {
    const fd = new FormData(form);
    const str = (name) => String(fd.get(name) || "").trim();
    const pouredNow = fd.get("concrete_poured") === "yes";
    const tax = fd.get("tax_exempt");
    return {
      report_date: str("report_date"),
      job_id: Number(fd.get("job_id")),
      foremen: fd.getAll("foremen").map(String).filter(Boolean),
      work_accomplished: str("work_accomplished"),
      delays: str("delays"),
      plan_tomorrow: str("plan_tomorrow"),
      safety_concerns: str("safety_concerns"),
      concrete_poured: pouredNow,
      yards_poured: pouredNow ? str("yards_poured") : "",
      supplier: pouredNow ? str("supplier") : "",
      what_poured: pouredNow ? str("what_poured") : "",
      tax_exempt: pouredNow && tax ? tax === "yes" : null,
      maintenance: fd.getAll("maintenance").map(String),
      // Seniors and above only (sql/085); anyone else never has the box, and the API would refuse the key.
      ...(canAct("senior_estimator") ? { management_notes: str("management_notes") } : {}),
      crew: TRADES.map((t) => ({ trade: t, workers: str(`crew_workers_${t}`), hours: str(`crew_hours_${t}`) })).filter(
        (r) => r.workers || r.hours
      ),
      subs: SUB_TRADES.map((t) => ({
        trade: t,
        sub_name: str(`sub_name_${t}`),
        workers: str(`sub_workers_${t}`),
        hours: str(`sub_hours_${t}`),
      })).filter((r) => r.sub_name || r.workers || r.hours),
    };
  };

  form.onsubmit = async (e) => {
    e.preventDefault();
    const err = $("#report-error", form);
    err.classList.add("hidden");
    const body = payload();
    if (!body.job_id) {
      err.textContent = word("need_job");
      err.classList.remove("hidden");
      return;
    }
    if (!body.foremen.length) {
      err.textContent = word("need_foreman");
      err.classList.remove("hidden");
      return;
    }
    const btn = form.querySelector("button[type=submit]");
    btn.disabled = true;
    try {
      if (existing) {
        await Api.updateDailyReport(existing.id, body);
        toast("Report saved");
        setRoute("daily");
        return;
      }
      await Api.createDailyReport(body);
      root.innerHTML = `
        <div class="report-form card" style="text-align:center">
          <h2 style="margin-top:0">✓ ${esc(word("sent"))}</h2>
          <p class="muted">${esc(body.report_date)}</p>
          <div class="modal-actions" style="flex-direction:column;gap:0.5rem">
            <button type="button" class="btn primary big" id="report-again">${esc(word("another"))}</button>
            ${!field && canAct("user") ? `<button type="button" class="btn ghost big" id="report-list">${esc(word("list"))}</button>` : ""}
          </div>
        </div>`;
      $("#report-again", root).onclick = () => renderReportForm(root);
      const back = $("#report-list", root);
      if (back) back.onclick = () => setRoute("daily");
    } catch (error) {
      err.textContent = error.message;
      err.classList.remove("hidden");
      btn.disabled = false;
    }
  };
}

// ---------------------------------------------------------- the calendar --

/** A month of reports, a cell a day, the pours marked with their yards. Chad, 2026-09-09: "can we add a calender view?" */
export async function renderCalendar(root) {
  const { $, $$, esc, toast } = d;
  root.innerHTML = `<div class="loading">Loading the calendar…</div>`;
  const meta = await Api.dailyReportMeta();
  const today = todayLocal();
  let year = Number(today.slice(0, 4));
  let month = Number(today.slice(5, 7)); // 1–12
  const filters = { job_id: "", poured: false, show: "both" };
  let reports = [];
  let orders = [];
  let materials = [];

  const pad = (n) => String(n).padStart(2, "0");
  const grid = () => {
    const first = `${year}-${pad(month)}-01`;
    const days = new Date(year, month, 0).getDate();
    const lead = new Date(year, month - 1, 1).getDay(); // 0 = Sunday
    const rows = Math.ceil((lead + days) / 7);
    const start = shiftDays(first, -lead);
    return { first, days, start, end: shiftDays(start, rows * 7 - 1), rows };
  };

  const load = async () => {
    const g = grid();
    const p = { date_from: g.start, date_to: g.end, limit: 2000 };
    if (filters.job_id) p.job_id = filters.job_id;
    if (filters.poured) p.poured = "true";
    const op = { date_from: g.start, date_to: g.end, limit: 2000 };
    if (filters.job_id) op.job_id = filters.job_id;
    [reports, orders, materials] = await Promise.all([
      ["orders", "deliveries"].includes(filters.show) ? Promise.resolve([]) : Api.listDailyReports(p),
      ["reports", "deliveries"].includes(filters.show) ? Promise.resolve([]) : Api.listConcreteOrders(op),
      ["reports", "orders"].includes(filters.show) ? Promise.resolve([]) : Api.listMaterialOrders(op),
    ]);
    orders = orders.filter((o) => o.status !== "canceled");
    materials = materials.filter((m) => m.status !== "canceled" && m.needed_by);
    paint();
  };

  const orderItem = (o) => {
    const when = o.pour_time ? clock(o.pour_time) + " · " : "";
    const title = `Ordered: ${n1(o.yards)} yd ${o.supplier}${o.mix ? " " + o.mix : ""} — ${o.job_name}${o.pour_time ? " at " + clock(o.pour_time) : ""}${o.order_number ? " — #" + o.order_number : ""}${o.ordered_by ? " — by " + o.ordered_by : ""} (${o.status})`;
    return `<div class="cal-item order${o.status === "poured" ? " done" : ""}" data-cal-order="${esc(o.id)}" title="${esc(title)}">${esc(when)}${esc(n1(o.yards))} yd · ${esc(o.job_name)}</div>`;
  };

  const item = (r) => {
    const title = `${r.job_name} — ${(r.foremen || []).join(", ")}${r.concrete_poured ? ` — ${n1(r.yards_poured)} yd ${r.supplier || ""}` : ""}${r.work_accomplished ? `\n${r.work_accomplished}` : ""}`;
    const text = r.concrete_poured ? `${n1(r.yards_poured)} yd · ${r.job_name}` : `${r.job_name}${r.foremen && r.foremen.length ? ` · ${r.foremen[0]}` : ""}`;
    return `<div class="cal-item${r.concrete_poured ? " pour" : ""}" data-cal-report="${esc(r.id)}" title="${esc(title)}">${esc(text)}</div>`;
  };

  const deliveryItem = (m) => {
    const qty = m.quantity != null ? `${n1(m.quantity)} ${m.unit || ""}`.trim() : "";
    const title = `Delivery: ${word("k_" + m.kind, "en")} — ${m.job_name} — ${m.description}${qty ? " — " + qty : ""} — ${m.supplier}${m.order_number ? " — #" + m.order_number : ""} (${m.status})`;
    return `<div class="cal-item delivery${m.status === "delivered" ? " done" : ""}" data-cal-delivery="${esc(m.id)}" title="${esc(title)}">${esc(word("k_" + m.kind, "en"))} · ${esc(m.job_name)}${qty ? ` · ${esc(qty)}` : ""}</div>`;
  };

  const paint = () => {
    const g = grid();
    const byDay = {};
    reports.forEach((r) => {
      (byDay[r.report_date] = byDay[r.report_date] || []).push(r);
    });
    const ordersByDay = {};
    orders.forEach((o) => {
      (ordersByDay[o.pour_date] = ordersByDay[o.pour_date] || []).push(o);
    });
    const ordered = orders.filter((o) => o.pour_date.startsWith(g.first.slice(0, 7)));
    const orderedYards = ordered.reduce((s, o) => s + Number(o.yards || 0), 0);
    const materialsByDay = {};
    materials.forEach((m) => {
      (materialsByDay[m.needed_by] = materialsByDay[m.needed_by] || []).push(m);
    });
    const dueThisMonth = materials.filter((m) => m.needed_by.startsWith(g.first.slice(0, 7))).length;
    const inMonth = reports.filter((r) => r.report_date.startsWith(g.first.slice(0, 7)));
    const pours = inMonth.filter((r) => r.concrete_poured);
    const yards = pours.reduce((s, r) => s + Number(r.yards_poured || 0), 0);
    $("#cal-title").textContent = new Date(year, month - 1, 1).toLocaleDateString(undefined, { month: "long", year: "numeric" });
    $("#cal-totals").innerHTML =
      `<strong>${inMonth.length}</strong> reports · <strong>${pours.length}</strong> pours · <strong>${n1(yards)}</strong> yards this month` +
      (filters.show === "reports" ? "" : ` · <strong>${ordered.length}</strong> orders · <strong>${n1(orderedYards)}</strong> yards ordered`) +
      (["reports", "orders"].includes(filters.show) ? "" : ` · <strong>${dueThisMonth}</strong> deliveries`);
    const cells = [];
    for (let i = 0; i < g.rows * 7; i += 1) {
      const iso = shiftDays(g.start, i);
      const other = !iso.startsWith(g.first.slice(0, 7));
      const items = byDay[iso] || [];
      const dayOrders = ordersByDay[iso] || [];
      const dayDeliveries = materialsByDay[iso] || [];
      cells.push(`<div class="cal-day${other ? " other" : ""}${iso === today ? " today" : ""}">
        <div class="d">${Number(iso.slice(8, 10))}</div>
        ${dayOrders.map(orderItem).join("")}
        ${dayDeliveries.map(deliveryItem).join("")}
        ${items.map(item).join("")}
      </div>`);
    }
    $("#cal-grid").innerHTML =
      ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].map((w) => `<div class="cal-head">${w}</div>`).join("") + cells.join("");
    $$("[data-cal-report]", root).forEach((el) => {
      el.onclick = () => {
        const r = reports.find((x) => x.id === el.dataset.calReport);
        if (r) openReportModal(r, { onChanged: load });
      };
    });
    $$("[data-cal-order]", root).forEach((el) => {
      el.onclick = () => {
        const o = orders.find((x) => x.id === el.dataset.calOrder);
        if (o) openOrderModal(o, { onChanged: load });
      };
    });
    $$("[data-cal-delivery]", root).forEach((el) => {
      el.onclick = () => {
        const m = materials.find((x) => x.id === el.dataset.calDelivery);
        if (m) openMaterialOrderModal(m, { onChanged: load });
      };
    });
  };

  root.innerHTML = `
    <div class="page-header">
      <div>
        <h1>Calendar</h1>
        <p id="cal-totals"></p>
      </div>
      <div class="toolbar" style="margin:0">
        <button type="button" class="btn ghost" id="cal-prev" title="Previous month">‹</button>
        <strong id="cal-title" style="min-width:11rem;text-align:center"></strong>
        <button type="button" class="btn ghost" id="cal-next" title="Next month">›</button>
        <button type="button" class="btn ghost" id="cal-today">Today</button>
      </div>
    </div>
    <div class="toolbar">
      <select id="cal-job"><option value="">All jobs</option>${meta.jobs
        .map((j) => `<option value="${j.id}">${esc(j.name)}${j.is_active ? "" : " (off the form)"}</option>`)
        .join("")}</select>
      <label style="display:flex;align-items:center;gap:0.35rem"><input type="checkbox" id="cal-poured" /> Pours only</label>
      <select id="cal-show" title="Reports on the day they were filed, orders on the day of the pour">
        <option value="both">Everything</option>
        <option value="reports">Reports only</option>
        <option value="orders">Concrete orders only</option>
        <option value="deliveries">Deliveries only</option>
      </select>
      <span class="muted" style="font-size:0.8rem"><span class="cal-key order"></span> ordered pour &nbsp; <span class="cal-key pour"></span> reported pour &nbsp; <span class="cal-key delivery"></span> delivery</span>
    </div>
    <div id="cal-grid" class="cal-grid"></div>
  `;
  $("#cal-prev").onclick = () => {
    month -= 1;
    if (month < 1) {
      month = 12;
      year -= 1;
    }
    load().catch((err) => toast(err.message, "err"));
  };
  $("#cal-next").onclick = () => {
    month += 1;
    if (month > 12) {
      month = 1;
      year += 1;
    }
    load().catch((err) => toast(err.message, "err"));
  };
  $("#cal-today").onclick = () => {
    year = Number(today.slice(0, 4));
    month = Number(today.slice(5, 7));
    load().catch((err) => toast(err.message, "err"));
  };
  $("#cal-job").onchange = (e) => {
    filters.job_id = e.target.value;
    load().catch((err) => toast(err.message, "err"));
  };
  $("#cal-poured").onchange = (e) => {
    filters.poured = e.target.checked;
    load().catch((err) => toast(err.message, "err"));
  };
  $("#cal-show").onchange = (e) => {
    filters.show = e.target.value;
    load().catch((err) => toast(err.message, "err"));
  };
  await load();
}

// ------------------------------------------------- deleting a list entry --

/**
 * A job with reports must say where they go; a foreman may leave the name as
 * typed on the reports, or move them to another. Chad, 2026-09-09: "let me
 * delete jobs and foreman".
 */
function openMoveDeleteModal({ kind, item, others, onDone }) {
  const { $, esc, toast } = d;
  const isJob = kind === "job";
  const backdrop = document.createElement("div");
  backdrop.className = "modal-backdrop";
  backdrop.innerHTML = `
    <div class="modal">
      <h2>Delete ${esc(item.name)}</h2>
      <p class="muted" style="color:var(--text-muted)">${item.reports} report${item.reports === 1 ? "" : "s"} ${
        isJob ? `${item.reports === 1 ? "is" : "are"} on this job` : `${item.reports === 1 ? "names" : "name"} this foreman`
      }.</p>
      <div class="field">
        <label>${isJob ? "Move them to" : "Move them to another foreman"}</label>
        <select id="mv-target">
          ${isJob ? `<option value="">Choose…</option>` : `<option value="">Leave the name as typed on them</option>`}
          ${others.map((o) => `<option value="${o.id}">${esc(o.name)}${o.is_active ? "" : " (off the form)"}</option>`).join("")}
        </select>
      </div>
      <div class="modal-actions">
        <button type="button" class="btn ghost" id="mv-cancel">Cancel</button>
        <button type="button" class="btn danger" id="mv-go">Delete</button>
      </div>
    </div>`;
  document.body.appendChild(backdrop);
  $("#mv-cancel", backdrop).onclick = () => backdrop.remove();
  backdrop.addEventListener("click", (e) => {
    if (e.target === backdrop) backdrop.remove();
  });
  $("#mv-go", backdrop).onclick = async () => {
    const target = $("#mv-target", backdrop).value;
    if (isJob && !target) {
      toast("Choose the job the reports move to", "err");
      return;
    }
    try {
      const res = isJob ? await Api.deleteFieldJob(item.id, target) : await Api.deleteFieldForeman(item.id, target);
      toast(`${item.name} deleted${res.moved ? `, ${res.moved} report${res.moved === 1 ? "" : "s"} moved` : ""}`);
      backdrop.remove();
      if (onDone) onDone();
    } catch (err) {
      toast(err.message, "err");
    }
  };
}

// ----------------------------------------------------- concrete orders --
//
// Chad, 2026-09-09: "another section under daily reports... 'concrete orders'
// basically like a daily report.. Date ordered, dropdown for job, concrete
// supplier, date of pour, Time of pour, Yards ordered, mix design, order
// number, ordered by. then the list and calender." The mix is the supplier's
// own number, typed. The job and supplier lists are the daily report's.

const ORDER_STATUSES = ["ordered", "confirmed", "poured", "canceled"];

/** "07:00:00" → "7:00 AM". */
function clock(t) {
  if (!t) return "";
  const [h, m] = String(t).split(":").map(Number);
  const suffix = h >= 12 ? "PM" : "AM";
  const hour = h % 12 === 0 ? 12 : h % 12;
  return `${hour}:${String(m).padStart(2, "0")} ${suffix}`;
}

function statusBadgeFor(status) {
  const cls = status === "poured" ? "ok" : status === "confirmed" ? "info" : status === "canceled" ? "" : "warn";
  return `<span class="badge ${cls}">${esc(word("st_" + status, "en"))}</span>`;
}

function esc(s) {
  return d.esc(s);
}

export async function renderOrders(root) {
  const { $, $$, toast, setRoute, canAct } = d;
  root.innerHTML = `<div class="loading">Loading concrete orders…</div>`;
  const meta = await Api.dailyReportMeta();
  const filters = { job_id: "", supplier: "", status: "open", range: "week", date_from: "", date_to: "", q: "" };
  let orders = [];

  const params = () => {
    const p = { limit: 2000 };
    if (filters.job_id) p.job_id = filters.job_id;
    if (filters.supplier) p.supplier = filters.supplier;
    if (filters.q) p.q = filters.q;
    if (filters.status !== "open" && filters.status !== "all") p.status = filters.status;
    if (filters.range === "custom") {
      if (filters.date_from) p.date_from = filters.date_from;
      if (filters.date_to) p.date_to = filters.date_to;
    } else if (filters.range === "week") {
      p.date_from = shiftDays(todayLocal(), -7);
    } else if (filters.range === "month") {
      p.date_from = shiftDays(todayLocal(), -30);
    }
    return p;
  };

  const load = async () => {
    orders = await Api.listConcreteOrders(params());
    if (filters.status === "open") orders = orders.filter((o) => o.status === "ordered" || o.status === "confirmed");
    paint();
  };

  const table = () => {
    if (!orders.length) return `<div class="empty">No concrete orders match.</div>`;
    const today = todayLocal();
    return `<div class="table-wrap"><table class="data">
      <thead><tr>
        <th>Pour</th><th>Job</th><th>Supplier</th><th class="num">Yards</th><th>Mix</th><th>Order #</th><th>Ordered</th><th>Status</th><th></th>
      </tr></thead>
      <tbody>${orders
        .map(
          (o) => `<tr data-order="${esc(o.id)}" class="clickable">
          <td style="white-space:nowrap">${o.pour_date === today ? `<span class="badge accent">today</span> ` : ""}${esc(day(o.pour_date))}${o.pour_time ? ` <span class="muted">${esc(clock(o.pour_time))}</span>` : ""}</td>
          <td><strong>${esc(o.job_name)}</strong></td>
          <td>${esc(o.supplier)}</td>
          <td class="num">${esc(n1(o.yards))}</td>
          <td class="muted">${esc(o.mix || "—")}</td>
          <td class="muted">${esc(o.order_number || "—")}</td>
          <td class="muted" style="white-space:nowrap" title="${esc(o.ordered_by || "")}">${esc(day(o.ordered_on))}${o.ordered_by ? ` · ${esc(o.ordered_by)}` : ""}</td>
          <td>${
            canAct("estimator")
              ? `<select data-order-status="${esc(o.id)}">${ORDER_STATUSES.map((s) => `<option value="${s}"${o.status === s ? " selected" : ""}>${esc(word("st_" + s, "en"))}</option>`).join("")}</select>`
              : statusBadgeFor(o.status)
          }</td>
          <td style="white-space:nowrap">
            <button type="button" class="btn ghost" data-view-order="${esc(o.id)}">View</button>
            ${canAct("estimator") ? `<button type="button" class="btn ghost" data-edit-order="${esc(o.id)}">Edit</button>` : ""}
          </td>
        </tr>`
        )
        .join("")}</tbody></table></div>`;
  };

  const paint = () => {
    const yards = orders.reduce((s, o) => s + Number(o.yards || 0), 0);
    $("#orders-counts").innerHTML = `<strong>${orders.length}</strong> orders · <strong>${n1(yards)}</strong> yards`;
    $("#orders-body").innerHTML = table();
    $$("[data-view-order]", root).forEach((btn) => {
      btn.onclick = () => {
        const o = orders.find((x) => x.id === btn.dataset.viewOrder);
        if (o) openOrderModal(o, { onChanged: load });
      };
    });
    $$("[data-edit-order]", root).forEach((btn) => {
      btn.onclick = () => setRoute("order", { orderId: btn.dataset.editOrder });
    });
    $$("[data-order-status]", root).forEach((sel) => {
      sel.onchange = async () => {
        try {
          const updated = await Api.updateConcreteOrder(sel.dataset.orderStatus, { status: sel.value });
          toast(`${updated.job_name} ${day(updated.pour_date)}: ${word("st_" + updated.status, "en")}`);
          load();
        } catch (err) {
          toast(err.message, "err");
          load();
        }
      };
    });
  };

  root.innerHTML = `
    <div class="page-header">
      <div>
        <h1>Concrete orders</h1>
        <p id="orders-counts"></p>
      </div>
      ${canAct("estimator") ? `<button class="btn primary" id="btn-new-order">+ New order</button>` : ""}
    </div>
    <div class="toolbar">
      <select id="orders-job"><option value="">All jobs</option>${meta.jobs
        .map((j) => `<option value="${j.id}">${esc(j.name)}${j.is_active ? "" : " (off the form)"}</option>`)
        .join("")}</select>
      <select id="orders-supplier"><option value="">Any supplier</option>${meta.suppliers.map((s) => `<option value="${esc(s)}">${esc(s)}</option>`).join("")}</select>
      <select id="orders-status">
        <option value="open">Ordered + confirmed</option>
        <option value="all">All statuses</option>
        ${ORDER_STATUSES.map((s) => `<option value="${s}">${esc(word("st_" + s, "en"))}</option>`).join("")}
      </select>
      <select id="orders-range">
        <option value="week" selected>Last 7 days and ahead</option>
        <option value="month">Last 30 days and ahead</option>
        <option value="all">All time</option>
        <option value="custom">Between dates…</option>
      </select>
      <span id="orders-custom" class="hidden"><input type="date" id="orders-from" /> – <input type="date" id="orders-to" /></span>
      <input id="orders-q" placeholder="Search job / supplier / mix / order # / notes…" style="min-width:220px" />
    </div>
    <div id="orders-body"><div class="loading">Loading…</div></div>
  `;
  $("#orders-job").onchange = (e) => {
    filters.job_id = e.target.value;
    load();
  };
  $("#orders-supplier").onchange = (e) => {
    filters.supplier = e.target.value;
    load();
  };
  $("#orders-status").onchange = (e) => {
    filters.status = e.target.value;
    load();
  };
  $("#orders-range").onchange = (e) => {
    filters.range = e.target.value;
    $("#orders-custom").classList.toggle("hidden", filters.range !== "custom");
    if (filters.range !== "custom") load();
  };
  $("#orders-from").onchange = (e) => {
    filters.date_from = e.target.value;
    load();
  };
  $("#orders-to").onchange = (e) => {
    filters.date_to = e.target.value;
    load();
  };
  let timer;
  $("#orders-q").oninput = (e) => {
    clearTimeout(timer);
    timer = setTimeout(() => {
      filters.q = e.target.value.trim();
      load();
    }, 250);
  };
  const fresh = $("#btn-new-order");
  if (fresh) fresh.onclick = () => setRoute("order");
  await load();
}

/** The whole order, read-only, with Edit and Delete for the roles that may. */
export function openOrderModal(o, { onChanged } = {}) {
  const { $, toast, setRoute, canAct } = d;
  const backdrop = document.createElement("div");
  backdrop.className = "modal-backdrop";
  const row = (label, v) => (v ? `<div class="field"><label>${label}</label><div>${esc(v)}</div></div>` : "");
  backdrop.innerHTML = `
    <div class="modal" style="width:min(640px,100%)">
      <h2 style="margin-bottom:0.2rem">${esc(o.job_name)} — ${esc(day(o.pour_date))}${o.pour_time ? ` at ${esc(clock(o.pour_time))}` : ""}</h2>
      <p class="muted" style="margin-top:0">${statusBadgeFor(o.status)} &nbsp; ordered ${esc(day(o.ordered_on))}${o.ordered_by ? ` by ${esc(o.ordered_by)}` : ""}${o.created_by_name && o.created_by_name !== o.ordered_by ? ` <span class="muted">(filed by ${esc(o.created_by_name)})</span>` : ""}</p>
      <div class="form-grid" style="grid-template-columns:1fr 1fr">
        ${row("Yards", n1(o.yards))}
        ${row("Supplier", o.supplier)}
        ${row("Mix", o.mix)}
        ${row("Order number", o.order_number)}
        ${o.notes ? `<div class="field full"><label>Notes</label><div style="white-space:pre-wrap">${esc(o.notes)}</div></div>` : ""}
      </div>
      <div class="modal-actions">
        ${canAct("senior_estimator") ? `<button type="button" class="btn danger ghost" id="ord-delete">Delete</button>` : ""}
        <button type="button" class="btn ghost" id="ord-close">Close</button>
        ${canAct("estimator") ? `<button type="button" class="btn primary" id="ord-edit">Edit</button>` : ""}
      </div>
    </div>`;
  document.body.appendChild(backdrop);
  $("#ord-close", backdrop).onclick = () => backdrop.remove();
  backdrop.addEventListener("click", (e) => {
    if (e.target === backdrop) backdrop.remove();
  });
  const edit = $("#ord-edit", backdrop);
  if (edit) {
    edit.onclick = () => {
      backdrop.remove();
      setRoute("order", { orderId: o.id });
    };
  }
  const del = $("#ord-delete", backdrop);
  if (del) {
    del.onclick = async () => {
      if (!confirm(`Delete the ${day(o.pour_date)} order for ${o.job_name} (${n1(o.yards)} yd)?`)) return;
      try {
        await Api.deleteConcreteOrder(o.id);
        toast("Order deleted");
        backdrop.remove();
        if (onChanged) onChanged();
      } catch (err) {
        toast(err.message, "err");
      }
    };
  }
}

/** The order form: a phone-sized page, English and Spanish, for the field and the office alike. */
export async function renderOrderForm(root) {
  const { $, $$, toast, setRoute, state, canAct } = d;
  root.innerHTML = `<div class="loading">Loading…</div>`;
  const meta = await Api.dailyReportMeta();
  const existing = state.orderId ? await Api.getConcreteOrder(state.orderId) : null;
  const field = !!state.user && state.user.role === "foreman";
  const jobs = meta.jobs.filter((j) => j.is_active || (existing && j.id === existing.job_id));
  const suppliers = meta.suppliers.slice();
  if (existing && existing.supplier && !suppliers.some((s) => s.toLowerCase() === existing.supplier.toLowerCase())) {
    suppliers.push(existing.supplier);
  }
  const me = (state.user && state.user.full_name) || "";

  root.innerHTML = `
    <form id="order-form" class="report-form card">
      <div style="display:flex;flex-wrap:wrap;justify-content:space-between;align-items:center;gap:0.5rem;margin-bottom:0.6rem">
        <h2 style="margin:0" data-w="${existing ? "o_edit" : "o_title"}">${esc(word(existing ? "o_edit" : "o_title"))}</h2>
        <div class="lang-toggle">
          <button type="button" data-lang="en"${lang === "en" ? ' class="active"' : ""}>English</button>
          <button type="button" data-lang="es"${lang === "es" ? ' class="active"' : ""}>Español</button>
        </div>
      </div>
      <div class="field"><label data-w="o_ordered_on">${esc(word("o_ordered_on"))}</label>
        <input type="date" name="ordered_on" required value="${esc(existing ? existing.ordered_on : todayLocal())}" /></div>
      <div class="field"><label data-w="job">${esc(word("job"))}</label>
        <select name="job_id" required>
          <option value="" data-w="pick">${esc(word("pick"))}</option>
          ${jobs.map((j) => `<option value="${j.id}"${existing && existing.job_id === j.id ? " selected" : ""}>${esc(j.name)}</option>`).join("")}
        </select></div>
      <div class="field"><label data-w="o_supplier">${esc(word("o_supplier"))}</label>
        <select name="supplier" required>
          <option value="" data-w="pick">${esc(word("pick"))}</option>
          ${suppliers.map((s) => `<option value="${esc(s)}"${existing && existing.supplier && existing.supplier.toLowerCase() === s.toLowerCase() ? " selected" : ""}>${esc(s)}</option>`).join("")}
        </select></div>
      <div class="grid-3" style="grid-template-columns:1fr 1fr">
        <div class="field"><label data-w="o_pour_date">${esc(word("o_pour_date"))}</label>
          <input type="date" name="pour_date" required value="${esc(existing ? existing.pour_date : "")}" /></div>
        <div class="field"><label data-w="o_pour_time">${esc(word("o_pour_time"))}</label>
          <input type="time" name="pour_time" value="${esc(existing && existing.pour_time ? String(existing.pour_time).slice(0, 5) : "")}" /></div>
      </div>
      <div class="field"><label data-w="o_yards">${esc(word("o_yards"))}</label>
        <input type="number" inputmode="decimal" min="0.5" step="0.5" name="yards" required value="${existing ? esc(String(existing.yards)) : ""}" /></div>
      <div class="field"><label data-w="o_mix">${esc(word("o_mix"))}</label>
        <input type="text" name="mix" maxlength="200" value="${esc(existing ? existing.mix || "" : "")}" /></div>
      <div class="field"><label data-w="o_number">${esc(word("o_number"))}</label>
        <input type="text" name="order_number" maxlength="100" value="${esc(existing ? existing.order_number || "" : "")}" /></div>
      <div class="field"><label data-w="o_by">${esc(word("o_by"))}</label>
        <input type="text" name="ordered_by" maxlength="200" value="${esc(existing ? existing.ordered_by || "" : me)}" /></div>
      <div class="field"><label data-w="o_notes">${esc(word("o_notes"))}</label>
        <textarea name="notes" rows="2">${esc(existing ? existing.notes || "" : "")}</textarea></div>
      ${
        existing && canAct("estimator")
          ? `<div class="field"><label data-w="o_status">${esc(word("o_status"))}</label>
        <select name="status">${ORDER_STATUSES.map((s) => `<option value="${s}"${existing.status === s ? " selected" : ""} data-w="st_${s}">${esc(word("st_" + s))}</option>`).join("")}</select></div>`
          : ""
      }
      <div id="order-error" class="error-banner hidden"></div>
      <div class="modal-actions" style="flex-direction:column;gap:0.5rem">
        <button type="submit" class="btn primary big" data-w="${existing ? "save" : "o_submit"}">${esc(word(existing ? "save" : "o_submit"))}</button>
        ${existing || !field ? `<button type="button" class="btn ghost big" id="order-cancel" data-w="cancel">${esc(word("cancel"))}</button>` : ""}
      </div>
    </form>`;

  const form = $("#order-form", root);
  const relabel = () => {
    $$("[data-w]", form).forEach((el) => {
      el.textContent = word(el.dataset.w);
    });
    $$("[data-lang]", form).forEach((b) => b.classList.toggle("active", b.dataset.lang === lang));
  };
  $$("[data-lang]", form).forEach((b) => {
    b.onclick = () => {
      lang = b.dataset.lang;
      try {
        localStorage.setItem("daily_lang", lang);
      } catch {
        // a private window; the choice lasts the page
      }
      relabel();
    };
  });
  const cancel = $("#order-cancel", form);
  if (cancel) cancel.onclick = () => setRoute(field ? "order" : "orders");

  form.onsubmit = async (e) => {
    e.preventDefault();
    const err = $("#order-error", form);
    err.classList.add("hidden");
    const fd = new FormData(form);
    const str = (name) => String(fd.get(name) || "").trim();
    const body = {
      ordered_on: str("ordered_on"),
      job_id: Number(fd.get("job_id")),
      supplier: str("supplier"),
      pour_date: str("pour_date"),
      pour_time: str("pour_time"),
      yards: str("yards"),
      mix: str("mix"),
      order_number: str("order_number"),
      ordered_by: str("ordered_by"),
      notes: str("notes"),
      ...(existing && canAct("estimator") ? { status: str("status") } : {}),
    };
    if (!body.job_id) {
      err.textContent = word("need_job");
      err.classList.remove("hidden");
      return;
    }
    if (!body.supplier) {
      err.textContent = word("o_need_supplier");
      err.classList.remove("hidden");
      return;
    }
    if (!Number(body.yards)) {
      err.textContent = word("o_need_yards");
      err.classList.remove("hidden");
      return;
    }
    const btn = form.querySelector("button[type=submit]");
    btn.disabled = true;
    try {
      if (existing) {
        await Api.updateConcreteOrder(existing.id, body);
        toast("Order saved");
        setRoute("orders");
        return;
      }
      await Api.createConcreteOrder(body);
      root.innerHTML = `
        <div class="report-form card" style="text-align:center">
          <h2 style="margin-top:0">✓ ${esc(word("o_sent"))}</h2>
          <p class="muted">${esc(day(body.pour_date))}${body.pour_time ? ` · ${esc(clock(body.pour_time))}` : ""} · ${esc(n1(body.yards))} yd</p>
          <div class="modal-actions" style="flex-direction:column;gap:0.5rem">
            <button type="button" class="btn primary big" id="order-again">${esc(word("o_another"))}</button>
            ${!field ? `<button type="button" class="btn ghost big" id="order-list">${esc(word("o_list"))}</button>` : ""}
          </div>
        </div>`;
      $("#order-again", root).onclick = () => renderOrderForm(root);
      const back = $("#order-list", root);
      if (back) back.onclick = () => setRoute("orders");
    } catch (error) {
      err.textContent = error.message;
      err.classList.remove("hidden");
      btn.disabled = false;
    }
  };
}

// ----------------------------------------------------- material orders --
//
// Chad, 2026-09-09: "like concrete orders.. but materials.. mostly to track
// post tension and rebar for projects.. so actually concrete orders should
// be there too". The two sit together in the Orders group; this is the
// material side: rebar, post-tension or other, what it is in words, a
// quantity and unit, needed on site by, delivered on.

const MATERIAL_KINDS = ["rebar", "post_tension", "other"];
const MATERIAL_STATUSES = ["ordered", "confirmed", "delivered", "canceled"];

function materialStatusBadge(status) {
  const cls = status === "delivered" ? "ok" : status === "confirmed" ? "info" : status === "canceled" ? "" : "warn";
  return `<span class="badge ${cls}">${esc(word("st_" + status, "en"))}</span>`;
}

function qtyText(m) {
  if (m.quantity == null) return "";
  return `${n1(m.quantity)} ${m.unit || ""}`.trim();
}

export async function renderMaterialOrders(root) {
  const { $, $$, toast, setRoute, canAct } = d;
  root.innerHTML = `<div class="loading">Loading material orders…</div>`;
  const [daily, meta] = await Promise.all([Api.dailyReportMeta(), Api.materialOrderMeta()]);
  const filters = { kind: "", job_id: "", supplier: "", status: "open", range: "all", date_from: "", date_to: "", q: "" };
  let orders = [];
  let summary = [];
  let showByJob = false;

  const params = () => {
    const p = { limit: 2000 };
    if (filters.kind) p.kind = filters.kind;
    if (filters.job_id) p.job_id = filters.job_id;
    if (filters.supplier) p.supplier = filters.supplier;
    if (filters.q) p.q = filters.q;
    if (filters.status !== "open" && filters.status !== "all") p.status = filters.status;
    if (filters.range === "custom") {
      if (filters.date_from) p.date_from = filters.date_from;
      if (filters.date_to) p.date_to = filters.date_to;
    } else if (filters.range === "month") {
      p.date_from = shiftDays(todayLocal(), -30);
    }
    return p;
  };

  const load = async () => {
    const sp = {};
    if (filters.job_id) sp.job_id = filters.job_id;
    if (filters.kind) sp.kind = filters.kind;
    [orders, summary] = await Promise.all([Api.listMaterialOrders(params()), Api.materialOrderSummary(sp)]);
    if (filters.status === "open") orders = orders.filter((o) => o.status === "ordered" || o.status === "confirmed");
    paint();
  };

  const totals = () => {
    const byUnit = {};
    orders.forEach((o) => {
      if (o.quantity == null) return;
      const u = o.unit || "—";
      byUnit[u] = (byUnit[u] || 0) + Number(o.quantity);
    });
    return Object.entries(byUnit)
      .map(([u, q]) => `<strong>${n1(q)}</strong> ${esc(u)}`)
      .join(" · ");
  };

  const table = () => {
    if (!orders.length) return `<div class="empty">No material orders match.</div>`;
    const today = todayLocal();
    return `<div class="table-wrap"><table class="data">
      <thead><tr>
        <th>Needed</th><th>Kind</th><th>Job</th><th>What</th><th class="num">Qty</th><th>Supplier</th><th>Order #</th><th>Ordered</th><th>Status</th><th></th>
      </tr></thead>
      <tbody>${orders
        .map(
          (o) => `<tr data-morder="${esc(o.id)}" class="clickable">
          <td style="white-space:nowrap">${o.needed_by === today ? `<span class="badge accent">today</span> ` : ""}${o.needed_by && o.needed_by < today && o.status !== "delivered" && o.status !== "canceled" ? `<span class="badge warn">late</span> ` : ""}${esc(day(o.needed_by))}</td>
          <td>${esc(word("k_" + o.kind, "en"))}</td>
          <td><strong>${esc(o.job_name)}</strong></td>
          <td><div class="muted" style="display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;font-size:0.85rem;max-width:24rem" title="${esc(o.description)}">${esc(o.description)}</div></td>
          <td class="num">${esc(qtyText(o) || "—")}</td>
          <td>${esc(o.supplier)}</td>
          <td class="muted">${esc(o.order_number || "—")}</td>
          <td class="muted" style="white-space:nowrap" title="${esc(o.ordered_by || "")}">${esc(day(o.ordered_on))}${o.ordered_by ? ` · ${esc(o.ordered_by)}` : ""}</td>
          <td>${
            canAct("estimator")
              ? `<select data-morder-status="${esc(o.id)}">${MATERIAL_STATUSES.map((s) => `<option value="${s}"${o.status === s ? " selected" : ""}>${esc(word("st_" + s, "en"))}</option>`).join("")}</select>`
              : materialStatusBadge(o.status)
          }</td>
          <td style="white-space:nowrap">
            <button type="button" class="btn ghost" data-view-morder="${esc(o.id)}">View</button>
            ${canAct("estimator") ? `<button type="button" class="btn ghost" data-edit-morder="${esc(o.id)}">Edit</button>` : ""}
          </td>
        </tr>`
        )
        .join("")}</tbody></table></div>`;
  };

  const byJob = () => {
    if (!showByJob) return "";
    if (!summary.length) return `<div class="card" style="margin-bottom:1rem"><div class="empty">Nothing ordered yet.</div></div>`;
    return `<div class="card" style="margin-bottom:1rem"><h3 style="margin:0 0 0.5rem">By job <span class="muted">(canceled left out)</span></h3>
      <div class="table-wrap"><table class="data"><thead><tr><th>Job</th><th>Kind</th><th class="num">Orders</th><th class="num">Quantity</th></tr></thead>
      <tbody>${summary
        .map((s) => `<tr><td>${esc(s.job_name)}</td><td>${esc(word("k_" + s.kind, "en"))}</td><td class="num">${s.orders}</td><td class="num">${esc(n1(s.quantity))} ${esc(s.unit || "")}</td></tr>`)
        .join("")}</tbody></table></div></div>`;
  };

  const paint = () => {
    $("#morders-counts").innerHTML = `<strong>${orders.length}</strong> orders${orders.length ? " · " + totals() : ""}`;
    $("#morders-byjob").innerHTML = byJob();
    $("#morders-body").innerHTML = table();
    $$("[data-view-morder]", root).forEach((btn) => {
      btn.onclick = () => {
        const o = orders.find((x) => x.id === btn.dataset.viewMorder);
        if (o) openMaterialOrderModal(o, { onChanged: load });
      };
    });
    $$("[data-edit-morder]", root).forEach((btn) => {
      btn.onclick = () => setRoute("material-order", { materialOrderId: btn.dataset.editMorder });
    });
    $$("[data-morder-status]", root).forEach((sel) => {
      sel.onchange = async () => {
        try {
          const updated = await Api.updateMaterialOrder(sel.dataset.morderStatus, { status: sel.value });
          toast(`${updated.job_name}: ${word("st_" + updated.status, "en")}`);
          load();
        } catch (err) {
          toast(err.message, "err");
          load();
        }
      };
    });
  };

  root.innerHTML = `
    <div class="page-header">
      <div>
        <h1>Material orders</h1>
        <p id="morders-counts"></p>
      </div>
      <div class="toolbar" style="margin:0">
        <button class="btn ghost" id="btn-byjob">By job</button>
        ${canAct("estimator") ? `<button class="btn primary" id="btn-new-morder">+ New order</button>` : ""}
      </div>
    </div>
    <div class="toolbar">
      <select id="morders-kind"><option value="">All kinds</option>${MATERIAL_KINDS.map((k) => `<option value="${k}">${esc(word("k_" + k, "en"))}</option>`).join("")}</select>
      <select id="morders-job"><option value="">All jobs</option>${daily.jobs
        .map((j) => `<option value="${j.id}">${esc(j.name)}${j.is_active ? "" : " (off the form)"}</option>`)
        .join("")}</select>
      <select id="morders-supplier"><option value="">Any supplier</option>${meta.suppliers.map((s) => `<option value="${esc(s)}">${esc(s)}</option>`).join("")}</select>
      <select id="morders-status">
        <option value="open">Ordered + confirmed</option>
        <option value="all">All statuses</option>
        ${MATERIAL_STATUSES.map((s) => `<option value="${s}">${esc(word("st_" + s, "en"))}</option>`).join("")}
      </select>
      <select id="morders-range">
        <option value="all" selected>All dates</option>
        <option value="month">Needed in the last 30 days and ahead</option>
        <option value="custom">Needed between dates…</option>
      </select>
      <span id="morders-custom" class="hidden"><input type="date" id="morders-from" /> – <input type="date" id="morders-to" /></span>
      <input id="morders-q" placeholder="Search job / supplier / what / order # / notes…" style="min-width:220px" />
    </div>
    <div id="morders-byjob"></div>
    <div id="morders-body"><div class="loading">Loading…</div></div>
  `;
  $("#morders-kind").onchange = (e) => {
    filters.kind = e.target.value;
    load();
  };
  $("#morders-job").onchange = (e) => {
    filters.job_id = e.target.value;
    load();
  };
  $("#morders-supplier").onchange = (e) => {
    filters.supplier = e.target.value;
    load();
  };
  $("#morders-status").onchange = (e) => {
    filters.status = e.target.value;
    load();
  };
  $("#morders-range").onchange = (e) => {
    filters.range = e.target.value;
    $("#morders-custom").classList.toggle("hidden", filters.range !== "custom");
    if (filters.range !== "custom") load();
  };
  $("#morders-from").onchange = (e) => {
    filters.date_from = e.target.value;
    load();
  };
  $("#morders-to").onchange = (e) => {
    filters.date_to = e.target.value;
    load();
  };
  let timer;
  $("#morders-q").oninput = (e) => {
    clearTimeout(timer);
    timer = setTimeout(() => {
      filters.q = e.target.value.trim();
      load();
    }, 250);
  };
  $("#btn-byjob").onclick = () => {
    showByJob = !showByJob;
    paint();
  };
  const fresh = $("#btn-new-morder");
  if (fresh) fresh.onclick = () => setRoute("material-order");
  await load();
}

/** The whole material order, read-only, with Edit and Delete for the roles that may. */
export function openMaterialOrderModal(m, { onChanged } = {}) {
  const { $, toast, setRoute, canAct } = d;
  const backdrop = document.createElement("div");
  backdrop.className = "modal-backdrop";
  const row = (label, v) => (v ? `<div class="field"><label>${label}</label><div>${esc(v)}</div></div>` : "");
  backdrop.innerHTML = `
    <div class="modal" style="width:min(640px,100%)">
      <h2 style="margin-bottom:0.2rem">${esc(word("k_" + m.kind, "en"))} — ${esc(m.job_name)}</h2>
      <p class="muted" style="margin-top:0">${materialStatusBadge(m.status)} &nbsp; ordered ${esc(day(m.ordered_on))}${m.ordered_by ? ` by ${esc(m.ordered_by)}` : ""}${m.created_by_name && m.created_by_name !== m.ordered_by ? ` <span class="muted">(filed by ${esc(m.created_by_name)})</span>` : ""}</p>
      <div class="form-grid" style="grid-template-columns:1fr 1fr">
        <div class="field full"><label>What</label><div style="white-space:pre-wrap">${esc(m.description)}</div></div>
        ${row("Quantity", qtyText(m))}
        ${row("Supplier", m.supplier)}
        ${row("Needed on site by", m.needed_by ? day(m.needed_by) : "")}
        ${row("Delivered on", m.delivered_on ? day(m.delivered_on) : "")}
        ${row("Order number", m.order_number)}
        ${m.notes ? `<div class="field full"><label>Notes</label><div style="white-space:pre-wrap">${esc(m.notes)}</div></div>` : ""}
      </div>
      <div class="modal-actions">
        ${canAct("senior_estimator") ? `<button type="button" class="btn danger ghost" id="mord-delete">Delete</button>` : ""}
        <button type="button" class="btn ghost" id="mord-close">Close</button>
        ${canAct("estimator") ? `<button type="button" class="btn primary" id="mord-edit">Edit</button>` : ""}
      </div>
    </div>`;
  document.body.appendChild(backdrop);
  $("#mord-close", backdrop).onclick = () => backdrop.remove();
  backdrop.addEventListener("click", (e) => {
    if (e.target === backdrop) backdrop.remove();
  });
  const edit = $("#mord-edit", backdrop);
  if (edit) {
    edit.onclick = () => {
      backdrop.remove();
      setRoute("material-order", { materialOrderId: m.id });
    };
  }
  const del = $("#mord-delete", backdrop);
  if (del) {
    del.onclick = async () => {
      if (!confirm(`Delete the ${word("k_" + m.kind, "en").toLowerCase()} order for ${m.job_name}?`)) return;
      try {
        await Api.deleteMaterialOrder(m.id);
        toast("Order deleted");
        backdrop.remove();
        if (onChanged) onChanged();
      } catch (err) {
        toast(err.message, "err");
      }
    };
  }
}

/** The material order form: the phone page, English and Spanish, the kind chosen first. */
export async function renderMaterialOrderForm(root) {
  const { $, $$, toast, setRoute, state, canAct } = d;
  root.innerHTML = `<div class="loading">Loading…</div>`;
  const [daily, meta] = await Promise.all([Api.dailyReportMeta(), Api.materialOrderMeta()]);
  const existing = state.materialOrderId ? await Api.getMaterialOrder(state.materialOrderId) : null;
  const field = !!state.user && state.user.role === "foreman";
  const jobs = daily.jobs.filter((j) => j.is_active || (existing && j.id === existing.job_id));
  const me = (state.user && state.user.full_name) || "";

  root.innerHTML = `
    <form id="morder-form" class="report-form card">
      <div style="display:flex;flex-wrap:wrap;justify-content:space-between;align-items:center;gap:0.5rem;margin-bottom:0.6rem">
        <h2 style="margin:0" data-w="${existing ? "m_edit" : "m_title"}">${esc(word(existing ? "m_edit" : "m_title"))}</h2>
        <div class="lang-toggle">
          <button type="button" data-lang="en"${lang === "en" ? ' class="active"' : ""}>English</button>
          <button type="button" data-lang="es"${lang === "es" ? ' class="active"' : ""}>Español</button>
        </div>
      </div>
      <div class="field"><label data-w="m_kind">${esc(word("m_kind"))}</label>
        <select name="kind" required>${MATERIAL_KINDS.map((k) => `<option value="${k}"${(existing ? existing.kind : "rebar") === k ? " selected" : ""} data-w="k_${k}">${esc(word("k_" + k))}</option>`).join("")}</select></div>
      <div class="field"><label data-w="o_ordered_on">${esc(word("o_ordered_on"))}</label>
        <input type="date" name="ordered_on" required value="${esc(existing ? existing.ordered_on : todayLocal())}" /></div>
      <div class="field"><label data-w="job">${esc(word("job"))}</label>
        <select name="job_id" required>
          <option value="" data-w="pick">${esc(word("pick"))}</option>
          ${jobs.map((j) => `<option value="${j.id}"${existing && existing.job_id === j.id ? " selected" : ""}>${esc(j.name)}</option>`).join("")}
        </select></div>
      <div class="field"><label data-w="m_supplier">${esc(word("m_supplier"))}</label>
        <input type="text" name="supplier" list="morder-suppliers" required maxlength="200" value="${esc(existing ? existing.supplier : "")}" />
        <datalist id="morder-suppliers">${meta.suppliers.map((s) => `<option value="${esc(s)}"></option>`).join("")}</datalist></div>
      <div class="field"><label data-w="m_description">${esc(word("m_description"))}</label>
        <textarea name="description" rows="3" required maxlength="2000">${esc(existing ? existing.description : "")}</textarea></div>
      <div class="grid-3" style="grid-template-columns:1fr 1fr">
        <div class="field"><label data-w="m_quantity">${esc(word("m_quantity"))}</label>
          <input type="number" inputmode="decimal" min="0" step="0.01" name="quantity" value="${existing && existing.quantity != null ? esc(String(existing.quantity)) : ""}" /></div>
        <div class="field"><label data-w="m_unit">${esc(word("m_unit"))}</label>
          <input type="text" name="unit" list="morder-units" maxlength="20" value="${esc(existing ? existing.unit || "" : "")}" />
          <datalist id="morder-units">${meta.units.map((u) => `<option value="${esc(u)}"></option>`).join("")}</datalist></div>
      </div>
      <div class="grid-3" style="grid-template-columns:1fr 1fr">
        <div class="field"><label data-w="m_needed_by">${esc(word("m_needed_by"))}</label>
          <input type="date" name="needed_by" value="${esc(existing ? existing.needed_by || "" : "")}" /></div>
        ${existing ? `<div class="field"><label data-w="m_delivered_on">${esc(word("m_delivered_on"))}</label>
          <input type="date" name="delivered_on" value="${esc(existing.delivered_on || "")}" /></div>` : "<div></div>"}
      </div>
      <div class="field"><label data-w="o_number">${esc(word("o_number"))}</label>
        <input type="text" name="order_number" maxlength="100" value="${esc(existing ? existing.order_number || "" : "")}" /></div>
      <div class="field"><label data-w="o_by">${esc(word("o_by"))}</label>
        <input type="text" name="ordered_by" maxlength="200" value="${esc(existing ? existing.ordered_by || "" : me)}" /></div>
      <div class="field"><label data-w="o_notes">${esc(word("o_notes"))}</label>
        <textarea name="notes" rows="2">${esc(existing ? existing.notes || "" : "")}</textarea></div>
      ${
        existing && canAct("estimator")
          ? `<div class="field"><label data-w="o_status">${esc(word("o_status"))}</label>
        <select name="status">${MATERIAL_STATUSES.map((s) => `<option value="${s}"${existing.status === s ? " selected" : ""} data-w="st_${s}">${esc(word("st_" + s))}</option>`).join("")}</select></div>`
          : ""
      }
      <div id="morder-error" class="error-banner hidden"></div>
      <div class="modal-actions" style="flex-direction:column;gap:0.5rem">
        <button type="submit" class="btn primary big" data-w="${existing ? "save" : "m_submit"}">${esc(word(existing ? "save" : "m_submit"))}</button>
        ${existing || !field ? `<button type="button" class="btn ghost big" id="morder-cancel" data-w="cancel">${esc(word("cancel"))}</button>` : ""}
      </div>
    </form>`;

  const form = $("#morder-form", root);
  const relabel = () => {
    $$("[data-w]", form).forEach((el) => {
      el.textContent = word(el.dataset.w);
    });
    $$("[data-lang]", form).forEach((b) => b.classList.toggle("active", b.dataset.lang === lang));
  };
  $$("[data-lang]", form).forEach((b) => {
    b.onclick = () => {
      lang = b.dataset.lang;
      try {
        localStorage.setItem("daily_lang", lang);
      } catch {
        // a private window; the choice lasts the page
      }
      relabel();
    };
  });
  const cancel = $("#morder-cancel", form);
  if (cancel) cancel.onclick = () => setRoute(field ? "material-order" : "material-orders");

  form.onsubmit = async (e) => {
    e.preventDefault();
    const err = $("#morder-error", form);
    err.classList.add("hidden");
    const fd = new FormData(form);
    const str = (name) => String(fd.get(name) || "").trim();
    const body = {
      kind: str("kind"),
      ordered_on: str("ordered_on"),
      job_id: Number(fd.get("job_id")),
      supplier: str("supplier"),
      description: str("description"),
      quantity: str("quantity"),
      unit: str("unit"),
      needed_by: str("needed_by"),
      order_number: str("order_number"),
      ordered_by: str("ordered_by"),
      notes: str("notes"),
      ...(existing ? { delivered_on: str("delivered_on") } : {}),
      ...(existing && canAct("estimator") ? { status: str("status") } : {}),
    };
    if (!body.job_id) {
      err.textContent = word("need_job");
      err.classList.remove("hidden");
      return;
    }
    if (!body.supplier) {
      err.textContent = word("o_need_supplier");
      err.classList.remove("hidden");
      return;
    }
    if (!body.description) {
      err.textContent = word("m_need_description");
      err.classList.remove("hidden");
      return;
    }
    const btn = form.querySelector("button[type=submit]");
    btn.disabled = true;
    try {
      if (existing) {
        await Api.updateMaterialOrder(existing.id, body);
        toast("Order saved");
        setRoute("material-orders");
        return;
      }
      await Api.createMaterialOrder(body);
      root.innerHTML = `
        <div class="report-form card" style="text-align:center">
          <h2 style="margin-top:0">✓ ${esc(word("m_sent"))}</h2>
          <p class="muted">${esc(word("k_" + body.kind))} · ${esc(body.description.slice(0, 60))}${body.needed_by ? ` · ${esc(day(body.needed_by))}` : ""}</p>
          <div class="modal-actions" style="flex-direction:column;gap:0.5rem">
            <button type="button" class="btn primary big" id="morder-again">${esc(word("m_another"))}</button>
            ${!field ? `<button type="button" class="btn ghost big" id="morder-list">${esc(word("m_list"))}</button>` : ""}
          </div>
        </div>`;
      $("#morder-again", root).onclick = () => renderMaterialOrderForm(root);
      const back = $("#morder-list", root);
      if (back) back.onclick = () => setRoute("material-orders");
    } catch (error) {
      err.textContent = error.message;
      err.classList.remove("hidden");
      btn.disabled = false;
    }
  };
}
