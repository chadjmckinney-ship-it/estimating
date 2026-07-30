import { expect, test } from "@playwright/test";

/**
 * READ-ONLY smoke tests. These run against the live `estimating` database, so
 * they must never click Save, Apply, Refresh, Recalculate or Delete. Loading
 * pages and opening dialogs is fine; anything that writes is not.
 *
 * The point of these is the console-error assertion: a template-literal typo or
 * a field the API stopped returning shows up as a runtime error that renders a
 * blank card, which no amount of static checking catches.
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

/**
 * An estimate that actually has pours, read from the API so no UUID is
 * hard-coded. Picking the newest estimate is not enough — an empty one renders
 * "No mono slabs yet" instead of the table, and every column assertion below
 * would fail for a reason that has nothing to do with the code under test.
 */
async function estimateWithPours(request) {
  const res = await request.get("/api/estimates");
  expect(res.ok(), "GET /api/estimates should succeed").toBeTruthy();
  const rows = await res.json();
  for (const e of rows) {
    const slabs = await request.get(
      `/api/mono-slabs?estimate_id=${encodeURIComponent(e.id)}`
    );
    expect(slabs.ok(), `GET /api/mono-slabs for ${e.name} should succeed`).toBeTruthy();
    if ((await slabs.json()).length > 0) return e.id;
  }
  test.skip(true, "no estimate has any mono slab pours to render");
  return null;
}

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

test("estimate detail shows the Slab mat column and Recalculate", async ({
  page,
  request,
}) => {
  const errors = watchErrors(page);
  const id = await estimateWithPours(request);
  await page.goto(`/#estimate/${id}`);

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
  const id = await estimateWithPours(request);
  await page.goto(`/#estimate/${id}`);

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
  const id = await estimateWithPours(request);
  await page.goto(`/#estimate/${id}`);

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
  const id = await estimateWithPours(request);
  await page.goto(`/#estimate/${id}`);

  for (const sel of ["#forming-materials", "#labor-supervision", "#estimate-equipment"]) {
    const card = page.locator(sel);
    await expect(card).toBeVisible();
    // "Could not load" is the catch(() => null) fallback — means the fetch failed.
    await expect(card).not.toContainText("Could not load");
  }
  expect(errors).toEqual([]);
});

test("estimate has a beam schedule section listing types", async ({
  page,
  request,
}) => {
  const errors = watchErrors(page);
  const id = await estimateWithPours(request);
  await page.goto(`/#estimate/${id}`);

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
