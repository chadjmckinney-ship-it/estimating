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
  const filters = { job_id: "", poured: false };
  let reports = [];

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
    reports = await Api.listDailyReports(p);
    paint();
  };

  const item = (r) => {
    const title = `${r.job_name} — ${(r.foremen || []).join(", ")}${r.concrete_poured ? ` — ${n1(r.yards_poured)} yd ${r.supplier || ""}` : ""}${r.work_accomplished ? `\n${r.work_accomplished}` : ""}`;
    const text = r.concrete_poured ? `${n1(r.yards_poured)} yd · ${r.job_name}` : `${r.job_name}${r.foremen && r.foremen.length ? ` · ${r.foremen[0]}` : ""}`;
    return `<div class="cal-item${r.concrete_poured ? " pour" : ""}" data-cal-report="${esc(r.id)}" title="${esc(title)}">${esc(text)}</div>`;
  };

  const paint = () => {
    const g = grid();
    const byDay = {};
    reports.forEach((r) => {
      (byDay[r.report_date] = byDay[r.report_date] || []).push(r);
    });
    const inMonth = reports.filter((r) => r.report_date.startsWith(g.first.slice(0, 7)));
    const pours = inMonth.filter((r) => r.concrete_poured);
    const yards = pours.reduce((s, r) => s + Number(r.yards_poured || 0), 0);
    $("#cal-title").textContent = new Date(year, month - 1, 1).toLocaleDateString(undefined, { month: "long", year: "numeric" });
    $("#cal-totals").innerHTML =
      `<strong>${inMonth.length}</strong> reports · <strong>${pours.length}</strong> pours · <strong>${n1(yards)}</strong> yards this month`;
    const cells = [];
    for (let i = 0; i < g.rows * 7; i += 1) {
      const iso = shiftDays(g.start, i);
      const other = !iso.startsWith(g.first.slice(0, 7));
      const items = byDay[iso] || [];
      cells.push(`<div class="cal-day${other ? " other" : ""}${iso === today ? " today" : ""}">
        <div class="d">${Number(iso.slice(8, 10))}</div>
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
