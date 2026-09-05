# The rebar question, and two bugs it flushed out — 2026-09-01

Chad went looking for a rebar quote field because **he could not see how much
money was in rebar**. There was no number for it anywhere in the app, so he
typed into the quote box to find out. That is the origin of everything below.

The fix is the per-material breakdown on the section stat cards
(`/api/sections/{id}/material-costs`), which now shows the dollars next to the
pounds. It found two real bugs within minutes of going live.

---

## The answer he was after: steel on this job

| Section | Pounds | Rate | Cost | Rate source |
|---|---:|---:|---:|---|
| Piers | 73,771 | $0.75 | $55,328.59 | `piers` assembly rate |
| 10-Paving | 150,387 | $0.60 | $90,231.97 | REBAR PIERS / PT slabs |
| Walls & Footings | 33,728 | $0.65 | $21,923.42 | REBAR GRADE BEAM |
| Mono slab | 21,945 | $0.60 | $13,166.99 | REBAR PIERS / PT slabs |
| **All four** | **279,831 lb** | **$0.6456** | **$180,650.97** | |

Paving is not in this contract. **Contract steel: 129,445 lb / 64.7 tons /
$90,419.00.**

**Open question — three rates on one job.** Piers $0.75, walls $0.65, slab and
paving $0.60. Some spread is legitimate (bar size, fabrication), but 25 cents
between piers and slab is worth resolving with the fabricator. If contract
steel all belonged at $0.60 it would be **$18,443 less**.

---

## 1. The $0.65 rebar "quote" — RESOLVED

The exploratory entry landed as **$0.65 with unit `LS`** — sixty-five cents,
total, for 21,944.977 lb of steel.

| | |
|---|---|
| Steel at catalog $0.60/lb | $13,166.99 |
| As entered | $0.65 |
| Understated cost | $14,252.58 (incl. $1,086.24 tax) |
| Understated sale | $16,390.48 |

The app accepted it, spread it across the pours, stamped a baseline against
21,944.977 lb and rendered a green "quoted · current" badge. A lump working out
to $0.00003/lb had a clean bill of health.

**Resolved:** Chad cleared the quote. The slab is back on the catalog rate at
**$671,712.66 / $772,469.56** — the reconciled workbook figure exactly.

### Prevention shipped

The **Priced per** dropdown defaulted to `LS — lump sum` on every kind, so an
unquoted card sat on the one shape where a *rate* typed into the amount box
becomes a catastrophe. Reordered default-first:

    rebar     LB, TON, CWT, LS
    pt        SF, LS
    drilling  LS            (the only unit a drilling quote takes)

A server-side sanity check on absurd lump rates was offered and declined — the
money on the stat cards is the check now.

---

## 2. The stale job total — FIXED

`refresh_estimate_totals` rolls sections up by reading `estimate_sections` in
**raw SQL**, while every caller arrives having just written
`section.calc_total_cost` through the **ORM**. `app/db.py` builds sessions
`autoflush=False`, so the SELECT ran against the pre-edit row and the job total
came out **one edit behind on every write path**.

Proven live twice. After the margin change:

    sum of the four sections   $3,038,292.46
    estimate.calc_total_sale   $3,029,168.56   ← $9,123.90 behind

A recalc of **10-Paving** — a section nobody had touched — then moved the job
total by exactly the *piers* margin change, because the rollup finally saw the
committed row.

**Fix:** `db.flush()` at the top of `refresh_estimate_totals`. One line, at the
one place that reads the table, not at the five call sites.

### Why no test caught it

`tests/conftest.py` built its session at SQLAlchemy's default `autoflush=True`.
Every call site got a free flush under test and none on the server. **A harness
more forgiving than production certifies bugs.**

Pinned by `tests/test_estimate_rollup.py`, which opens its own
production-shaped session (`autoflush=False`, same connection, same rollback)
and drives the rollup the way a request does. Verified to fail without the fix.

---

## 3. The margin box read the wrong object — FIXED

On the section page, **Apply markup** correctly PATCHed the *section*, but the
Margin % and Conting % inputs were seeded from `estimate.margin_pct` — the
default a *new* section is created with. Two consequences:

* a section at 18% displayed the job's 15% and **sprang back after every
  successful save**, so the margin looked unchangeable (it wasn't — the saves
  were landing);
* pressing Apply *without touching the box* silently overwrote the section's
  real markup with the job default. On paving that is 3 points on $1.4M —
  roughly **$42,000 of sale, one button press, no warning**.

Both inputs now read the section, fall back to the job default only when the
section has none, and the row says "this section only · job default is X%" when
they differ. Header shows one decimal so 17.5% stops rendering as 18%.

---

## 4. STILL OPEN: another instance of bug #2

Flipping `conftest.py` to `autoflush=False` — the real fix for the divergence —
**fails five tests in `test_piers.py`**. The pier section prices **$7,263.67
light** ($289,940.85 against an expected $297,204.52).

Same shape, different service: something in the piers takeoff → labor →
equipment → costing chain reads a table in raw SQL after an unflushed ORM write.
Not yet run down.

The conftest change was reverted so the suite stays green, and the reason is
written into the `db` fixture docstring so the next person finds it rather than
rediscovering it. **This is the next thing to look at.**

---

## Live LBJ state, end of session

| Section | Margin | Cost | Sale |
|---|---|---:|---:|
| Piers | 18% | $304,130.10 | $358,873.52 |
| Mono slab on grade | 15% | $671,712.66 | $772,469.56 |
| 10-Paving | 18% | $1,404,380.20 | $1,657,168.64 |
| 06-Walls & Footings | 15% | $207,012.35 | $238,064.21 |
| **Estimate** | | **$2,587,235.31** | **$3,026,575.93** |

The mono slab figure is the reconciled workbook number exactly. Header agrees
with the sum of sections to the penny.

**Net effect of the entire session on the bid: cost unchanged, sale +$9,123.90,
all of it the piers margin going 15% → 18%.** Every other movement during the
day was entered and then reverted. No code change moved a price — the breakdown
only reads, the flush changes *when* the rollup reads rather than what anything
costs, and the card, margin-box and dropdown fixes are display.

Tests: **322** green.
