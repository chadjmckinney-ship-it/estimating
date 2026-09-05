# The front end: how it breaks silently, and the two guards

Written 2026-09-01, after a day lost to a bug that looked like a dead API.

## What happened

Chad: *"lol, think we crashed the api or database."* Then, later, a screenshot:
the shell rendering, "Loading…" in the main pane, "Checking API…" in the corner.

**The API was fine the whole time.** `/health` returned 200, every endpoint
answered, the estimate rolled up correctly, migrations were applied. The page
was dead for an entirely different reason:

```
SyntaxError: Unexpected identifier 'estimate'   app.js:1718:49
```

Line 1718 was an **HTML comment inside a template literal**, explaining a fix
made earlier that week:

```js
root.innerHTML = `
  ...
  <!-- Seeded from the SECTION, which is also what Apply writes to.
       These boxes used to be filled from `estimate.margin_pct` — the
       default a NEW section is created with — while the button PATCHed ... -->
```

A backtick inside a template literal **ends it**. The prose was fine as prose
and fatal as code.

## Why it survived a syntax check

`node --check app.js` passed. Repeatedly.

`index.html` loads the file with `type="module"`, and module parsing is not
script parsing. In the **script** grammar, Annex B allows `<!--` as an
HTML-like line comment — so `node --check` swallowed the `<!--` line and the
backticks happened to balance. In a **module**, `<!--` is not a comment, the
template literal is still open, and the file will not parse.

```
node --check app.js       →  passes    (script grammar)
cp app.js x.mjs; node --check x.mjs  →  SyntaxError  (module grammar — what runs)
```

**A check that does not use the grammar the browser uses is not a check.**

## Guard 1 — `frontend/check.mjs`

```
node frontend/check.mjs
```

Imports every file under `frontend/assets/js/` as a real ES module and reports
any `SyntaxError` with its line and column. A non-syntax error (no `document`)
is expected and ignored — the point is the parse. Exits 1 on failure.

Verified by reintroducing the bug in a copy: it fails with the same message the
browser gave.

**Run it before shipping any front-end file.** It is the only check that
matches how the page loads.

## The rule that prevents it

**Nothing inside a template literal may contain a backtick, or a `${` that is
not a real interpolation.** Prose about the code goes in a `//` comment outside
the literal, where it cannot terminate anything. The note above now lives above
`root.innerHTML = \``, unchanged in substance.

HTML comments inside a template are the specific trap, because they read as
inert. Two others in `app.js` (both about `step="any"`) are fine — they contain
no backticks — and are left alone.

---

## The second silent failure: drivers a schema drops

Found the same day, building the columns page.

`FormingDrivers` and `LaborDrivers` are Pydantic response models that name
their fields explicitly. `services/forming.py` and `services/labor.py` computed
`column_count`, `form_sf` and `chamfer_lf`, handed them back in the drivers
dict, and the schema **dropped all three on the way out**. The browser rendered
`num(undefined)` as `—`.

No error anywhere: 200 OK on every request, nothing in the console, and a card
that should read 7,716 SF reading a dash.

Walls had carried the same hole since sql/040 without anyone noticing — its
forming header fell through to the mono-slab branch and read
*"Perim 0 LF · drops 0 LF · SF 0"*, and its labor header said
*"04 LABOR / SUPERVISION"* on a 06-Walls section.

A third variant, same class: `load_stored_labor` rebuilds its driver dict **by
hand** from `estimate_labor_summary`, which carries the columns a mono slab
needs and nothing else. Even with the schemas fixed, every read after the first
lost the geometry again. Fixed by overlaying the live-computed geometry fields
onto the stored dict — additive only, so no stored cost or day can change.

### Adding a driver means touching three places

1. the service that computes it,
2. the response **schema** that names it,
3. for labor, the **stored-path** dict in `load_stored_labor` that reassembles
   it.

## Guard 2 — `backend/tests/test_columns_ui_contract.py`

A deliberately dumb list of key names, asserted against the four payloads the
section page fetches: `/column-types/totals`, `/column-types`,
`/sections/{id}/forming-materials`, `/sections/{id}/labor`,
`/sections/{id}/equipment`, `/sections/{id}/material-costs`.

It checks **nothing** about whether the numbers are right — `test_columns.py`
does that against the sheet. It checks that the fields `app.js` reaches for
exist, so renaming a driver breaks a test instead of blanking a card.

**If a card is added to a section page, add its driver to that file.**

---

## How the columns page was verified

Not by reading it. The container ran the API against `estimating_test` seeded
with the four LBJ column types, and Playwright (Chromium at
`/opt/pw-browsers/chromium`) loaded the real page, collected console errors,
and read every card back:

| | |
|---|---:|
| Columns | 68 |
| Form SF | 7,716 |
| Concrete CY | 128.27 |
| Steel lb | 47,417 |
| Chamfer LF | 4,368 |
| Super days | 17 |
| Cost | $172,301 |
| Cost / column | $2,534 |

Every one matches `test_columns.py`. Console clean apart from a missing
favicon.

**This is the pattern to repeat for the next assembly's screen.** A page that
has never been rendered has not been tested, and the two failures above both
produce a page that looks like something else is broken.
