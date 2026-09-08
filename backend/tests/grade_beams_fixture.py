"""
02-Gd Beams and 02-Cont Footings on the Pearl Landing Podium estimate, rebuilt
as data (sql/073).

One beam type on each tab: 24" x 30", three #6 top and bottom, #3 stirrups at
12", mix 8 at $170. The beams tab runs 1,248 LF of it — 3,120 face feet, 240
CY, 17,020 lb — for $112,207.97 cost and $134,649.56 sale; the continuous
footings tab 184 LF for $17,047.88 and $20,457.46. Both sell per LF here
(Chad, 2026-09-07: "we use LF for both of those"); the sheet sells per face
foot, and that figure sits beside the LF one on the totals.

Prices are stated HERE, the way walls_fixture.py does it.

## What the sheet says, and where this deliberately differs

  * **THE TAB'S TAX CELL READS "200".** U39 is the EXEMPT cell; both tabs
    hold the number 200 in it instead of Y or N, so every `IF(U39="N", 1 +
    tax, 1)` on concrete and steel takes the no-tax branch while the lumber
    column's `IF(U39="Y", ..., x (1 + tax))` taxes everything. The app taxes
    concrete and steel on a taxable job. Named per tab below.
  * **ACCESSORIES AT THE CATALOG'S $0.04/lb** where the tab types $0.02
    (V80). Prices live in the catalog (sql/044); the tab's typed-over cell
    does not. Named per tab.
  * **CONCRETE HAUL-OFF IS NOT TAXED** — a service, the rule every other
    assembly follows (sql/036) — where this tab taxes its whole lumber
    column. Named per tab.
  * **CARTON FORMS AND THE DURROCK RETAINER ARE TAXED** — they are
    materials — where the tab's O58 and O59 multiply LF by rate and stop.
    $154.46 on the footings tab; nothing on the beams tab, which typed n.
  * **FUEL AND TAX ON MISCELLANEOUS.** The one equipment line the sheet
    leaves without `x (1 + tax + fuel)`; here it is an ordinary rental, as
    on walls and spot footings.
  * **BAR WEIGHT** is the catalog's: 1.502 lb/ft for a #6 where the tab
    reads 1.5019, and 0.376 for a #3 stirrup where the tab's own stirrup
    constant works out to 0.3763. A few pounds either way.
  * **CAMLOCKS at $0.859375** — the tab's V71 reads Pricing!Q4, which is the
    2x4 price, and that is what the bid paid. Stated as the bid did.
  * **FORM RENTAL** is on the rentals card and OFF: the tab rents 30% of the
    contact feet (K60) at a rate cell (G60) that is blank on both jobs.
  * **KEYWAY, WATER STOP and the SLAB DOWELS** are lines the tab carries and
    zeroes by formula; here they exist and start OFF.
  * The **STIRRUP-SPACING QUIRK** — `IF(P10 = 0, 0, ...)` zeroes every pound
    of steel on a row with no stirrup spacing — is not reproduced. Neither
    row here trips it.

Rounding across pieces each stated to the cent may leave a cent.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import text

from app.models.beam_run import BeamRun
from app.models.estimate_section import EstimateSection
from app.services.beams import refresh_beam_run_calcs

# ---------------------------------------------------------------- prices ----
MIX_CODE = "5000-ASH"            # the sheet's mix 8, "5,000 PSI / Ash no Air"
MIX_COST = Decimal("170.00")     # G51 on the beams tab, G48 on the footings tab

MATERIAL_PRICES = {
    "REBAR GRADE BEAM": Decimal("0.6500"),   # G52
    "ACCESSORIES": Decimal("0.0400"),        # the catalog; the tab types 0.02 (V80)
    "2 x 2 x 30 Stakes": Decimal("24.00"),   # V55
    "16p NAILS DUPLEX": Decimal("45.00"),    # V56
    "8p DUPLEX": Decimal("68.20"),           # V57
    "6p NAILS": Decimal("68.20"),            # V58
    "CHAMFER": Decimal("0.2500"),            # V61
    "WALL TIES": Decimal("45.00"),           # V62
    "CAMLOCKS": Decimal("0.859375"),         # V71 = Pricing!Q4 — the 2x4 price, as bid
    "TURNBUCKLES": Decimal("1.4453"),        # V72 = Pricing!Q5 (qty 0 on both tabs)
    "CONCRETE HAUL OFF": Decimal("250.00"),  # V77
}

EQUIPMENT_PRICES = {
    "MINI EXCAVATOR": Decimal("475.00"),     # G79
    "SKID STEER": Decimal("325.00"),         # G80 — Pricing!D35 on this job
    "TOWER LIGHT w/ GENERATOR": Decimal("100.00"),   # G81
}

SETTINGS = {
    "sales_tax_pct": "0.0825",
    "equip_fuel_maint_pct": "0.50",
    "labor_super_day_rate": "425",
    "labor_foreman_day_rate": "250",
    "labor_expense_day_rate": "100",
    "labor_pm_day_rate": "200",
    "labor_super_days_per_week": "7",
    "equip_skytrack_day_rate": "425",        # G78
    "equip_vault_day_rate": "50",            # G82
    "equip_misc_day_rate": "35",             # G83
    "waste_poly": "0.10",
}

# The rates the tab types, set on the section. All but form_percent are the
# assembly's own values (sql/073); stated here so the golden does not move
# with the assembly table.
SECTION_RATES = {
    "labor_pilasters_ff": "8",       # E62
    "labor_forming_sf": "4",         # E63
    "labor_place_finish_sf": "4",    # E64
    "labor_wreck_sf": "1",           # E65
    "labor_rub_patch_sf": "0.25",    # E66
    "labor_tie_steel_ton": "450",    # E67
    "labor_excavate_cy": "4",        # E68
    "labor_backfill_cy": "8",        # E69
    "concrete_pump_cy": "20",        # G85
    "haul_off_cy": "6",              # G89
    "carton_forms_lf": "3.75",       # G58
    "durrock_retainer_lf": "2.75",   # G59
    "form_percent": "0",             # T48 — the Podium job types 0 where the template says 0.5
}

BEAMS = dict(
    kind="grade_beams",
    name="02-Gd Beams",
    unit="LF",
    margin_pct=Decimal("0.20"),      # M40
    contingency_pct=Decimal("0.00"),
    tax_exempt=None,
    waste_concrete=Decimal("0.04"),  # K48
    waste_rebar=Decimal("0.10"),     # K52
)
FOOTINGS = dict(BEAMS, kind="cont_footings", name="02-Cont Footings")

# ---------------------------------------------------------------- takeoff ---
# The one beam type on each tab (row 10): label, length, width, height,
# top bars (count, size), bottom bars (count, size), stirrups (size, spacing).
BEAM_ROW = dict(
    label="GB", width_in=Decimal("24"), height_in=Decimal("30"),
    top_bars_count=3, top_bars_size=6, bottom_bars_count=3, bottom_bars_size=6,
    stirrup_size=3, stirrup_spacing_in=Decimal("12"),
)
BEAMS_LF = Decimal("1248")        # F10 on 02-Gd Beams
FOOTINGS_LF = Decimal("184")      # F10 on 02-Cont Footings

BEAMS_SUPER_DAYS = Decimal("5")       # E73; foreman, expense and PM follow it (E74:E76)
FOOTINGS_SUPER_DAYS = Decimal("0.2")  # E73 on the footings tab

# ------------------------------------------------------------ the sheets ----
BEAMS_SHEET = {
    "length_lf": Decimal("1248"),          # F36
    "face_ff": Decimal("3120"),            # BB36 = I63
    "contact_ff": Decimal("6240"),         # BA36 = L60
    "steel_lb": Decimal("17019.8378"),     # W36
    "concrete_cy": Decimal("240.3556"),    # X36
    "excavate_cy": Decimal("529"),         # I68
    "backfill_cy": Decimal("289"),         # I69
    "concrete_cost": Decimal("40860.4444"),   # O51, untaxed by the 200 quirk
    "steel_cost": Decimal("11062.8946"),      # O52, untaxed likewise
    "labor": Decimal("37117.4635"),           # O71
    "supervision": Decimal("4875.00"),        # M74 + O76
    "equipment": Decimal("6632.8125"),        # M80
    "pump": Decimal("4807.1111"),             # O85
    "haul_off": Decimal("1442.1333"),         # O89
    "lumber": Decimal("5410.1110"),           # X90
    "total_cost": Decimal("112207.9704"),     # U40
    "total_sale": Decimal("134649.5645"),     # E40
    "sale_per_ff": Decimal("43.1569"),        # C40
}
FOOTINGS_SHEET = {
    "length_lf": Decimal("184"),
    "face_ff": Decimal("460"),
    "contact_ff": Decimal("920"),
    "steel_lb": Decimal("2509.3351"),
    "concrete_cy": Decimal("35.4370"),
    "excavate_cy": Decimal("78"),
    "backfill_cy": Decimal("43"),
    "concrete_cost": Decimal("6024.2963"),
    "steel_cost": Decimal("1631.0678"),
    "carton_forms": Decimal("759.00"),        # O58: 184 x 1.1 x 3.75
    "durrock_retainer": Decimal("1113.20"),   # O59: 184 x 2 x 1.1 x 2.75
    "labor": Decimal("5475.6004"),
    "supervision": Decimal("195.00"),         # M74 (155) + O76 (40)
    "equipment": Decimal("442.1875"),
    "pump": Decimal("708.7407"),
    "haul_off": Decimal("212.6222"),
    "lumber": Decimal("486.1698"),
    "total_cost": Decimal("17047.8847"),
    "total_sale": Decimal("20457.4616"),
    "sale_per_ff": Decimal("44.4727"),
}

# What the APP reads — each sheet plus every difference named in the module
# docstring. Set from the first run (2026-09-07) and held since.
BEAMS_GOLDEN_COST = Decimal("116902.23")
FOOTINGS_GOLDEN_COST = Decimal("17889.47")


def price_the_catalog(db) -> dict:
    """Bid prices for the life of this test. Rolled back with everything else."""
    mid = db.execute(
        text("UPDATE mix_designs SET unit_cost = :c WHERE code = :k RETURNING id"),
        {"c": MIX_COST, "k": MIX_CODE},
    ).scalar()
    assert mid is not None, f"no mix design {MIX_CODE} in the catalog"
    for name, cost in MATERIAL_PRICES.items():
        found = db.execute(
            text("UPDATE materials SET unit_cost = :c WHERE name = :n RETURNING id"),
            {"c": cost, "n": name},
        ).scalar()
        assert found is not None, f"no catalog material named {name!r}"
    for name, cost in EQUIPMENT_PRICES.items():
        db.execute(text("UPDATE equipment SET unit_cost = :c WHERE name = :n"), {"c": cost, "n": name})
    for key, value in SETTINGS.items():
        db.execute(
            text("INSERT INTO system_settings (key, value) VALUES (:k, to_jsonb(CAST(:v AS text))) "
                 "ON CONFLICT (key) DO UPDATE SET value = excluded.value"),
            {"k": key, "v": value},
        )
    db.flush()
    return {"mix_id": int(mid)}


def build_section(db, estimate, ids: dict, *, footings: bool = False, sheet_mode: bool = False) -> EstimateSection:
    section = EstimateSection(estimate_id=estimate.id, **(FOOTINGS if footings else BEAMS))
    db.add(section)
    db.flush()
    for key, value in SECTION_RATES.items():
        db.execute(
            text("INSERT INTO section_rates (section_id, key, value, note) VALUES (:s, :k, :v, :n) "
                 "ON CONFLICT (section_id, key) DO UPDATE SET value = excluded.value"),
            {"s": str(section.id), "k": key, "v": value, "n": section.name},
        )
    run = BeamRun(
        section_id=section.id, sort_order=10, mix_design_id=ids["mix_id"],
        length_ft=FOOTINGS_LF if footings else BEAMS_LF, **BEAM_ROW,
    )
    db.add(run)
    db.flush()
    refresh_beam_run_calcs(db, run, section, sheet_mode=sheet_mode)
    db.flush()
    return section


def type_the_supervision(db, section_id, *, footings: bool = False) -> None:
    """The tab's E73, and the three lines that read it (E74:E76) — entered, not derived."""
    from app.services.labor import update_labor_line

    days = FOOTINGS_SUPER_DAYS if footings else BEAMS_SUPER_DAYS
    for code in ("superintendent", "foreman", "expense", "pm"):
        update_labor_line(db, section_id, code, qty=days, mark_manual=True)


def switch_off_the_cartons(db, section_id) -> None:
    """The Podium beams tab types n for carton forms and the durrock retainer (F58, F59)."""
    from app.services.forming import set_forming_line_enabled

    for code in ("carton_forms", "durrock_retainer"):
        set_forming_line_enabled(db, section_id, code, False)


def build(db, estimate, *, sheet_mode: bool = False) -> EstimateSection:
    """The beams tab, priced and taken off; the line sets are the caller's."""
    priced = price_the_catalog(db)
    from app.services.price_book import pull_prices

    pull_prices(db, estimate.id)
    return build_section(db, estimate, priced, sheet_mode=sheet_mode)


def build_footings(db, estimate, *, sheet_mode: bool = False) -> EstimateSection:
    priced = price_the_catalog(db)
    from app.services.price_book import pull_prices

    pull_prices(db, estimate.id)
    return build_section(db, estimate, priced, footings=True, sheet_mode=sheet_mode)
