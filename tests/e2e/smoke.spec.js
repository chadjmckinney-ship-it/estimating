import { expect, test } from "@playwright/test";

/**
 * READ-ONLY smoke tests. These run against the live `estimating` database, so
 * they must never click Save, Apply, Refresh, Recalculate or Delete. Loading
 * pages and opening dialogs is fine; anything that writes is not.
 *
 * The point of these is the console-error assertion: a template-literal typo or
 * a field the API stopped returning shows up as a runtime error that renders a
 * blank card, which no amount of static checking catches.
 *
 * Since sections (sql/033-034) the pours, the beam schedule and the three
 * line-set cards all live on a SECTION page, and /api/mono-slabs lists by
 * section, not by estimate. This spec was written before that and sat unrun
 * on this box until 2026-09-05 (no browsers installed); the first run failed
 * five of seven on a 422 from the old by-estimate lookup. It now finds a mono
 * slab section with pours and opens that.
 */

/** Collect console errors and page exceptions for the life of a page. */
function watchErrors(page) {
  const errors = [];
  page.on("console", (m) => {
    if (m.type() === "error") errors.push(`console: ${m.text()}`);
  });
  page.on("pageerror", (e) => errors.push(`pageerror: ${e.message}`));
  return errors;
}

async function getJson(request, path, label) {
  const res = await request.get(path);
  expect(res.ok(), `GET ${path} (${label}) should succeed`).toBeTruthy();
  return res.json();
}

/**
 * A section of the given kind that actually has takeoff rows, read from the
 * API so no UUID is hard-coded. Picking the newest estimate is not enough —
 * an empty section renders "No mono slabs yet" instead of the table, and every
 * column assertion below would fail for a reason that has nothing to do with
 * the code under test.
 */
async function sectionWithRows(request, kind, rowsPath) {
  const estimates = await getJson(request, "/api/estimates", "estimates");
  for (const e of estimates) {
    const sections = await getJson(
      request,
      `/api/estimates/${encodeURIComponent(e.id)}/sections`,
      `sections of ${e.name}`
    );
    for (const s of sections) {
      if (s.kind !== kind) continue;
      const rows = await getJson(
        request,
        `${rowsPath}?section_id=${encodeURIComponent(s.id)}`,
        `${kind} rows of ${s.name}`
      );
      if (rows.length > 0) return s.id;
    }
  }
  test.skip(true, `no ${kind} section has any rows to render`);
  return null;
}

const monoSlabSectionWithPours = (request) =>
  sectionWithRows(request, "mono_slab", "/api/mono-slabs");
const wallsSectionWithRuns = (request) =>
  sectionWithRows(request, "walls_footings", "/api/wall-runs");

test("dashboard renders with no console errors", async ({ page }) => {
  const errors = watchErrors(page);
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Estimating" })).toBeVisible();
  // Stat cards are driven by six parallel API calls; a failure blanks them.
  await expect(page.locator(".card.stat").first()).toBeVisible();
  expect(errors).toEqual([]);
});

test("projects list renders", async ({ page }) => {
  const errors = watchErrors(page);
  await page.goto("/#projects");
  await expect(page.getByRole("heading", { name: "Projects" })).toBeVisible();
  expect(errors).toEqual([]);
});

test("mono slab section shows the Slab mat column and Recalculate", async ({
  page,
  request,
}) => {
  const errors = watchErrors(page);
  const id = await monoSlabSectionWithPours(request);
  await page.goto(`/#section/${id}`);

  // Slab mat column — added with the bar-size/spacing feature.
  await expect(
    page.getByRole("columnheader", { name: "Slab mat" })
  ).toBeVisible();
  // Recalculate button — added with the system_settings propagation work.
  await expect(
    page.getByRole("button", { name: "Recalculate" })
  ).toBeVisible();
  // Header stat cards, including the Slab mat tile.
  await expect(page.locator(".card.stat").filter({ hasText: "Slab mat" })).toBeVisible();

  expect(errors).toEqual([]);
});

test("pour form has bar size + spacing and no Drops input", async ({
  page,
  request,
}) => {
  const errors = watchErrors(page);
  const id = await monoSlabSectionWithPours(request);
  await page.goto(`/#section/${id}`);

  const edit = page.locator("button.btn-edit-slab").first();
  await expect(edit).toBeVisible();
  await edit.click(); // opens a modal; does not write

  const modal = page.locator(".modal-backdrop .modal");
  await expect(modal).toBeVisible();

  await expect(modal.locator('select[name="slab_bar_size"]')).toBeVisible();
  await expect(modal.locator('input[name="slab_bar_spacing_in"]')).toBeVisible();
  // drops_ff was retired in sql/022 — no input, and no leftover label either.
  // Drops are entered via the pour's Drops button, not this form.
  await expect(modal.locator('input[name="drops_ff"]')).toHaveCount(0);
  await expect(modal).not.toContainText("Drops");

  // Close without saving.
  await modal.getByRole("button", { name: "Cancel" }).click();
  await expect(modal).toBeHidden();

  expect(errors).toEqual([]);
});

test("beam modal shows the estimate schedule and per-pour lengths", async ({
  page,
  request,
}) => {
  const errors = watchErrors(page);
  const id = await monoSlabSectionWithPours(request);
  await page.goto(`/#section/${id}`);

  // The GBs button on the first pour that has one.
  const gbButton = page.locator('button.btn-gb[data-kind="grade_beam"]').first();
  await expect(gbButton).toBeVisible();
  await gbButton.click(); // opens a modal; does not write

  const modal = page.locator(".modal-backdrop .modal");
  await expect(modal).toBeVisible();

  // Half 1: the estimate's shared schedule (sql/025)
  await expect(modal.locator("#type-table")).toBeVisible();
  await expect(modal).toContainText("schedule for this estimate");
  await expect(modal).toContainText("changes every pour that uses it");
  // Half 2: lengths for this pour only
  await expect(modal.locator("#usage-table")).toBeVisible();
  await expect(modal.locator("input.usage-lf").first()).toBeVisible();

  await modal.getByRole("button", { name: "Close" }).click();
  await expect(modal).toBeHidden();
  expect(errors).toEqual([]);
});

test("forming, labor and equipment cards render", async ({ page, request }) => {
  const errors = watchErrors(page);
  const id = await monoSlabSectionWithPours(request);
  await page.goto(`/#section/${id}`);

  for (const sel of ["#forming-materials", "#labor-supervision", "#estimate-equipment"]) {
    const card = page.locator(sel);
    await expect(card).toBeVisible();
    // "Could not load" is the catch(() => null) fallback — means the fetch failed.
    await expect(card).not.toContainText("Could not load");
  }
  expect(errors).toEqual([]);
});

test("mono slab section has a beam schedule listing types", async ({
  page,
  request,
}) => {
  const errors = watchErrors(page);
  const id = await monoSlabSectionWithPours(request);
  await page.goto(`/#section/${id}`);

  const card = page.locator("#beam-schedule");
  await expect(card).toBeVisible();
  await expect(card).not.toContainText("Could not load");
  // Types are estimate-level and shared — the warning must be stated.
  await expect(card).toContainText("changes every pour that uses it");
  // At least one type row, with its usage rolled up.
  await expect(card.locator("tr[data-beam-type]").first()).toBeVisible();
  await expect(page.getByRole("button", { name: "+ Add type" })).toBeVisible();

  // The editor opens and warns when the type is in use (no save).
  await card.locator("button.btn-edit-type").first().click();
  const modal = page.locator(".modal-backdrop .modal");
  await expect(modal).toBeVisible();
  await expect(modal.locator('input[name="label"]')).toBeVisible();
  await expect(modal.locator('input[name="width_in"]')).toBeVisible();
  await modal.getByRole("button", { name: "Cancel" }).click();
  await expect(modal).toBeHidden();

  expect(errors).toEqual([]);
});

test("walls section draws each type as a wall line over its footing line", async ({
  page,
  request,
}) => {
  // The two-line grid of 2026-09-05: every record is a `tr.has-sub` with a
  // `tr.sub-line` under it, the header stacks both labels, and each footing
  // box carries its own tag on the line. Nothing here is clicked.
  const errors = watchErrors(page);
  const id = await wallsSectionWithRuns(request);
  await page.goto(`/#section/${id}`);

  const card = page.locator("#wall-runs");
  await expect(card).toBeVisible();
  const wallLines = card.locator("tbody tr.has-sub");
  const footingLines = card.locator("tbody tr.sub-line");
  await expect(wallLines.first()).toBeVisible();
  expect(await footingLines.count()).toBe(await wallLines.count());
  await expect(card.locator("thead th .sub-label").first()).toHaveText("Footing");
  await expect(footingLines.first().locator(".sub-text")).toContainText("footing");
  // The footing's two mats (sql/059), each tagged where it is typed.
  for (const tag of ['W"', 'T"', 'bot sp"', "bot #", 'top sp"', "top #"]) {
    await expect(footingLines.first().locator(".sub-tag", { hasText: tag }).first()).toBeVisible();
  }
  // Each footing can name its own mix on its line (sql/062)...
  await expect(
    footingLines.first().locator('select[data-f="footing_mix_design_id"]')
  ).toBeVisible();
  // ...and the section's footing mix (the sheet's R8) has its own select
  // above the grid since 2026-09-05; blank there means each footing follows
  // its wall.
  const ftgMix = page.locator("select#sec-footing-mix");
  await expect(ftgMix).toBeVisible();
  await expect(ftgMix.locator("option").first()).toHaveText("follows the wall's mix");
  expect(await ftgMix.locator("option").count()).toBeGreaterThan(1);
  expect(errors).toEqual([]);
});

/**
 * The unload guard follows the grid that is on the page (audit P3, batch 3).
 *
 * wireGrid used to add a `beforeunload` listener on every render and never
 * remove it, so a grid you had dirtied and then navigated away from — inside
 * the app, by hash — still asked "Leave site?" when the tab closed. Nothing
 * here is saved: a cell is typed into and the tab is closed.
 */
test("a dirty grid still on the page asks before the tab closes", async ({ page, request }) => {
  const errors = watchErrors(page);
  const id = await wallsSectionWithRuns(request);
  await page.goto(`/#section/${id}`);
  const card = page.locator("#wall-runs");
  await expect(card).toBeVisible();
  const cell = card.locator("tbody input").first();
  await cell.click();
  await cell.press("End");
  await cell.type("1");
  await expect(card.locator("tbody tr.dirty").first()).toBeVisible();
  const dialog = page.waitForEvent("dialog", { timeout: 2000 }).catch(() => null);
  await page.close({ runBeforeUnload: true });
  const d = await dialog;
  expect(d && d.type()).toBe("beforeunload");
  await d.accept();
  expect(errors).toEqual([]);
});

test("a dirty grid you navigated away from does not ask when the tab closes", async ({
  page,
  request,
}) => {
  const errors = watchErrors(page);
  const id = await wallsSectionWithRuns(request);
  await page.goto(`/#section/${id}`);
  const card = page.locator("#wall-runs");
  await expect(card).toBeVisible();
  const cell = card.locator("tbody input").first();
  await cell.click();
  await cell.press("End");
  await cell.type("1");
  await expect(card.locator("tbody tr.dirty").first()).toBeVisible();
  // The app's own navigation: the grid is gone, and so should its guard be.
  await page.evaluate(() => {
    location.hash = "#projects";
  });
  await expect(page.getByRole("heading", { name: "Projects" })).toBeVisible();
  await expect(page.locator("#wall-runs")).toHaveCount(0);
  const dialog = page.waitForEvent("dialog", { timeout: 2000 }).catch(() => null);
  await page.close({ runBeforeUnload: true });
  expect(await dialog).toBeNull();
  expect(errors).toEqual([]);
});
