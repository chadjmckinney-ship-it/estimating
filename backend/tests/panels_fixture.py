"""
The 12-PANELS tab Chad seeded on 2026-09-08, rebuilt as data (sql/077).

workbooks/Downloads/Trammel Crow - LBJ Estimate.xlsm, 12-PANELS: twelve panel
types, three of each — all 7.25" on mix 5 (4,000 psi ash and air, $155),
29 or 30 ft long (one 18 ft), top elevations 26 to 35 ft on a bottom at -4
(one 26 on 20), each with one 10 x 3 opening, #4 at 12" both ways in two
mats, #5 verticals at 12" in two mats, two #5 edge bars and two #5 corner
bars. 36 panels, 30,024 SF, 673.57 CY, 124,024 lb; $411,101.45 cost,
$485,099.71 sale at 18%, $13.69/SF. Only the twelve rows, the mix slot and
the forty superintendent days are typed on that tab; every rate is the
template's.

Prices are stated HERE, from the tab and its Pricing sheet.

## What the tab says, and where this deliberately differs

  * **THE OPENING BRACKET IS CLOSED.** The tab's opening term adds
    `count x length` as bare pounds — a copy of the edge-bar term with its
    bracket dropped. Closed, it is one more set of edge bars: **+2,384 lb**
    with its tie labor and accessories.
  * **THE OPENINGS ARE FORMED.** Each opening's perimeter joins the formed
    perimeter the 2x4, the 2x8, the stakes and the chamfer run off. The tab
    carries no opening lumber at all (Chad, 2026-09-08: "short on rebar and
    lumber for the openings"). **+936 LF** of blockout.
  * **THE 2x10 COUNTS THE PANELS.** The tab's S70 is D52, the sum of the
    type LENGTHS: 347 LF on a 36-panel job. Per bottom LF here: 1,041.
  * **FUEL AND TAX ON MISCELLANEOUS**, the one equipment line the sheet
    leaves without the uplift; here it is an ordinary rental, as everywhere.
    **+$366.98.**
  * **BAR WEIGHT** is the catalog's (#4 0.668, #5 1.043) where the tab's
    constant (10.7028) makes them 0.6689 and 1.0452: about 0.2% lighter.
  * **LUMBER PRICES TO FOUR PLACES** on the catalog where the tab carries
    eight: pennies.
  * **QUANTITIES TO THREE PLACES** on the bond breaker: a third of a dollar.

Rounding across pieces each stated to the cent may leave a cent.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import text

from app.models.estimate_section import EstimateSection
from app.models.panel_type import PanelType
from app.services.panels import refresh_panel_type_calcs

# ---------------------------------------------------------------- prices ----
MIX_CODE = "4000-AIR-ASH"        # the tab's mix 5, "4,000 PSI /Ash and Air"
MIX_COST = Decimal("155.00")     # F68 = Pricing!J3

# The tab's Pricing sheet carries the lumber to eight places (0.859375); the
# catalog holds four. Both are here so the reconciliation can name the cents.
TAB_LUMBER = {
    "2 X 4  X 16'": Decimal("0.859375"),
    "2 X 6 X 16'": Decimal("1.4453125"),
    "2 X 8 X 16'": Decimal("1.171875"),
    "2 X 10 X 16'": Decimal("1.09375"),
}

MATERIAL_PRICES = {
    "REBAR GRADE BEAM": Decimal("0.6500"),        # F69 = Pricing!D23
    "2 X 4  X 16'": Decimal("0.8594"),            # U67 = Pricing!Q4
    "2 X 6 X 16'": Decimal("1.4453"),             # U68
    "2 X 8 X 16'": Decimal("1.1719"),             # U69
    "2 X 10 X 16'": Decimal("1.0938"),            # U70
    "2 x 2 x 30 Stakes": Decimal("24.00"),        # U72 (the catalog name carries a trailing space)
    "16p NAILS DUPLEX": Decimal("68.20"),         # U73
    "8p DUPLEX": Decimal("68.20"),                # U74
    "6p NAILS": Decimal("68.20"),                 # U75
    "CHAMFER": Decimal("0.25"),                   # U78
    "PATCH MATERIAL": Decimal("45.00"),           # U89 — Pave Crete
    'METAL CHAIRS 2.5"': Decimal("45.00"),        # U92 — panel chairs
    "ACCESSORIES": Decimal("0.0400"),             # U94 — the tab types the catalog's number
    "LIFT INSERT": Decimal("12.00"),              # U95
    "BRACE INSERTS": Decimal("8.00"),             # U96
    "SLAB CURE": Decimal("567.50"),               # U100
    "BOND BREAKER": Decimal("635.00"),            # U101
}

EQUIPMENT_PRICES = {
    "SkyTrack": Decimal("425.00"),           # F92 — the tab reads the BACK HOE row, same 425
    "MINI EXCAVATOR": Decimal("425.00"),     # F93 — typed; the catalog says 475
    "TRENCHER": Decimal("325.00"),           # F94, no days
    "SKID STEER": Decimal("325.00"),         # F95
    "COMPACTOR": Decimal("125.00"),          # F96 — typed; the catalog says 200
}

SETTINGS = {
    "sales_tax_pct": "0.0825",               # V55
    "equip_fuel_maint_pct": "0.50",          # I94
    "labor_super_day_rate": "350",           # F88
    "labor_foreman_day_rate": "250",         # F89
    "labor_expense_day_rate": "100",         # F90
    "labor_pm_day_rate": "200",              # no PM on this tab
    "labor_super_days_per_week": "7",
    "equip_misc_day_rate": "35",             # F97
    "out_of_town_day_rate": "250",           # F104, no days
}

# The tab's rates, set on the section — the assembly's own values (sql/077),
# stated here so the golden does not move with the assembly table.
SECTION_RATES = {
    "labor_brick_ledge_lf": "1.5",           # D79
    "labor_forming_sf": "0.35",              # D80
    "labor_place_finish_sf": "0.65",         # D81
    "labor_wreck_sf": "0.25",                # D82
    "labor_rub_patch_sf": "0.85",            # D83
    "labor_tie_steel_ton": "450",            # D84
    "labor_backfill_cy": "8",                # D85
    "backfill_width_ft": "6.5",              # H85
    "backfill_depth_ft": "2",                # G85
    "labor_super_sf_per_week": "0",
    "labor_super_days_per_week": "7",
    "form_percent": "0.4",                   # S66
    "form_rental_percent": "0",              # J77
    "carton_forms_waste": "0.1",             # J75
    "corner_bar_ft": "4",                    # U
    "panel_2x8_thick_in": "6",               # AV / AW
    "lumber_2x10_per_lf": "1",               # S70, counted
    "stakes_lf_per_bundle": "100",           # S72
    "nails_16p_per_sf": "1800",              # S73
    "nails_8p_factor": "0.6",                # S74
    "patch_sf_per_bag": "250",               # S89
    "chairs_sf_per_bag": "6000",             # S92
    "lift_inserts_per_panel": "8",           # S95
    "brace_inserts_per_panel": "3",          # S96
    "cure_sf_per_gal": "300",                # S100
    "bond_breaker_sf_per_gal": "200",        # S101
    "carton_forms_lf": "1",                  # F75
    "durrock_retainer_lf": "1.8",            # F76
    "form_rental_contact_ft": "0.65",        # F77
    "concrete_pump_cy": "20",                # D99
    "panel_engineering_ea": "90",            # D100
    "waterproofing_sf": "0",                 # D101
    "saw_cutting_lf": "0",                   # D102
    "haul_off_cy": "6",                      # F103
}

SECTION = dict(
    kind="panels",
    name="12-Panels",
    unit="SF",
    margin_pct=Decimal("0.18"),      # L56 = Summary!P59
    contingency_pct=Decimal("0.00"), # Summary!P60
    tax_exempt=None,                 # inherits the project; LBJ is taxable
    waste_concrete=Decimal("0.04"),  # J66
    waste_rebar=Decimal("0.05"),     # J69
)

SUPER_DAYS = Decimal("40")           # D88, typed

# ---------------------------------------------------------------- takeoff ---
# The steel schedule every type shares: #4 at 12" x 2 mats horizontal, #5 at
# 12" x 2 mats vertical, 2 #5 edge bars, 2 #5 corner bars.
STEEL = dict(
    horiz_spacing_in=Decimal("12"), horiz_size=4, horiz_mats=2,
    vert_spacing_in=Decimal("12"), vert_size=5, vert_mats=2,
    edge_bar_count=2, edge_bar_size=5, corner_bar_count=2, corner_bar_size=5,
)
THICKNESS_IN = Decimal("7.25")
OPENING = (Decimal("10"), Decimal("3"))      # I x J, one per panel

# label, qty, length ft, top el, bot el — the tab's rows 10-21
TYPES = [
    ("P1", 3, 29, 26, -4),
    ("P2", 3, 30, 26, -4),
    ("P3", 3, 30, 30, -4),
    ("P4", 3, 30, 29, -4),
    ("P5", 3, 30, 35, -4),
    ("P6", 3, 30, 11, -4),
    ("P7", 3, 18, 26, 20),
    ("P8", 3, 30, 26, -4),
    ("P9", 3, 30, 26, -4),
    ("P10", 3, 30, 26, -4),
    ("P11", 3, 30, 26, -4),
    ("P12", 3, 30, 26, -4),
]

# ------------------------------------------------------------ the sheet ----
SHEET = {
    "panels": 36,                              # AS52 / H53
    "types": 12,                               # AI52
    "total_sf": Decimal("30024"),              # AR52 / H80
    "sum_of_lengths": Decimal("347"),          # D52 — what the tab's 2x10 reads
    "perimeter_lf": Decimal("4104"),           # AT52
    "bottom_lf": Decimal("1041"),              # AU52
    "concrete_cy": Decimal("673.5733"),        # AP52 / K68
    "steel_lb": Decimal("124024.1580"),        # AQ52 / K69
    "lb_per_sf": Decimal("4.1308"),            # R58
    "u10_steel_each": Decimal("3592.0715"),    # U10 — P1, the tab's own bracket
    "v10_cy_each": Decimal("19.5481"),         # V10 — P1
    "x10_cost_each": Decimal("9377.5009"),     # X10 — P1
    "super_days": Decimal("40"),               # D88
    "equip_days": Decimal("60"),               # D93 — the ladder off 40
    "concrete_cost": Decimal("113017.1857"),   # N68, with tax
    "steel_cost": Decimal("87266.4982"),       # N69, with tax
    "carton": Decimal("1239.5708"),            # N75, with tax
    "durrock": Decimal("4462.4547"),           # N76, with tax
    "labor": Decimal("94965.6133"),            # N86
    "supervision": Decimal("28000"),           # L89
    "equipment": Decimal("37660.50"),          # L94, with fuel and tax
    "contract": Decimal("14551.4667"),         # SUM(N99:O104)
    "lumber": Decimal("29938.1563"),           # W105, with tax
    "lumber_2x4_lf": Decimal("1641.6"),        # S67
    "lumber_2x6_lf": Decimal("2082"),          # S68
    "lumber_2x8_lf": Decimal("1641.6"),        # S69
    "stakes_bundles": Decimal("6.5664"),       # S72
    "chamfer_lf": Decimal("8208"),             # S78
    "bond_breaker_drums": Decimal("2.7295"),   # S101
    "total_cost": Decimal("411101.4456"),      # T56
    "total_sale": Decimal("485099.7058"),      # D56
    "cost_per_sf": Decimal("13.6924"),         # I56
    "sale_per_sf": Decimal("16.1571"),         # B56
}

# What the APP reads — the sheet plus every difference named in the module
# docstring. Set from the first run (2026-09-08) and held since.
GOLDEN_COST = Decimal("415746.83")


def _price_material(db, name: str, cost: Decimal) -> int:
    # trim(): the catalog spells one stake bundle with a trailing space.
    mid = db.execute(
        text("UPDATE materials SET unit_cost = :c WHERE trim(name) = trim(:n) RETURNING id"),
        {"c": cost, "n": name},
    ).scalar()
    assert mid is not None, f"no catalog material named {name!r}"
    return int(mid)


def price_the_catalog(db) -> dict:
    """Bid prices for the life of this test. Rolled back with everything else."""
    mix_id = db.execute(
        text("UPDATE mix_designs SET unit_cost = :c WHERE code = :k RETURNING id"),
        {"c": MIX_COST, "k": MIX_CODE},
    ).scalar()
    assert mix_id is not None, f"no mix design {MIX_CODE} in the catalog"
    ids = {name: _price_material(db, name, cost) for name, cost in MATERIAL_PRICES.items()}
    for name, cost in EQUIPMENT_PRICES.items():
        found = db.execute(
            text("UPDATE equipment SET unit_cost = :c WHERE name = :n RETURNING id"),
            {"c": cost, "n": name},
        ).scalar()
        assert found is not None, f"no equipment named {name!r}"
    for key, value in SETTINGS.items():
        db.execute(
            text("INSERT INTO system_settings (key, value) VALUES (:k, to_jsonb(CAST(:v AS text))) "
                 "ON CONFLICT (key) DO UPDATE SET value = excluded.value"),
            {"k": key, "v": value},
        )
    db.flush()
    return {"mix_id": int(mix_id), **ids}


def build_section(db, estimate, ids: dict, *, sheet_mode: bool = False) -> EstimateSection:
    section = EstimateSection(estimate_id=estimate.id, **SECTION)
    db.add(section)
    db.flush()
    for key, value in SECTION_RATES.items():
        db.execute(
            text("INSERT INTO section_rates (section_id, key, value, note) VALUES (:s, :k, :v, '12-PANELS') "
                 "ON CONFLICT (section_id, key) DO UPDATE SET value = excluded.value"),
            {"s": str(section.id), "k": key, "v": value},
        )
    for order, (label, qty, length, top, bot) in enumerate(TYPES):
        row = PanelType(
            section_id=section.id,
            label=label,
            qty=qty,
            mix_design_id=ids["mix_id"],
            length_ft=Decimal(length),
            thickness_in=THICKNESS_IN,
            top_el_ft=Decimal(top),
            bot_el_ft=Decimal(bot),
            open1_len_ft=OPENING[0],
            open1_wide_ft=OPENING[1],
            sort_order=order * 10,
            **STEEL,
        )
        db.add(row)
        db.flush()
        refresh_panel_type_calcs(db, row, section, sheet_mode=sheet_mode)
    db.flush()
    return section


def type_the_supervision(db, section_id) -> None:
    """
    Panels TYPE their days — 40 on LBJ (12 D88). The foreman (D89 = D88) and
    the expense (D90) follow the superintendent on the next labor refresh.

    Run this AFTER the labor and equipment refreshes: typing the days moves
    the rental ladder on the NEXT refresh, the order test_piers uses.
    """
    from app.services.labor import update_labor_line

    update_labor_line(db, section_id, "superintendent", qty=SUPER_DAYS, mark_manual=True)


def build(db, estimate, *, sheet_mode: bool = False) -> EstimateSection:
    priced = price_the_catalog(db)
    # Pull the sheet AFTER pricing the catalog (sql/048), so this section
    # prices from an estimate sheet the way every real estimate does.
    from app.services.price_book import pull_prices

    pull_prices(db, estimate.id)
    return build_section(db, estimate, priced, sheet_mode=sheet_mode)
