"""
The 13-Miscellaneous tab as data (sql/078): the library, with quantities.

Nothing on any workbook in the folder is typed into this tab, so the golden
is an EXERCISE — the tab's 22 items at quantities chosen here, priced the way
the tab prices them: the LBJ Pricing sheet's mix 1 ($134, both the site and
the structural picker), its D22 and D24 bar ($0.60), 8.25% tax.

`tab_row` below is the tab, row by row, formula by formula — ROUNDUP and
ROUND where the tab has them, tax only where the tab remembers it. The app
keeps the yards' decimals and taxes everything it buys; those are the two
differences, and the test names them to the cent.
"""

from __future__ import annotations

import math
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal

from sqlalchemy import text

from app.models.estimate_section import EstimateSection
from app.services.misc import refresh_section_misc_calcs, seed_from_library

D = Decimal

# ---------------------------------------------------------------- prices ----
MIX_CODE = "3000-AIR-ASH"        # the tab's mix 1, "3,000 PSI 5sk /Ash and Air"
MIX_COST = D("134.00")           # Pricing F3 on LBJ — both pickers (E8 and Q8) read it
REBAR_NAME = "REBAR PIERS / PT slabs"
REBAR_COST = D("0.60")           # Pricing D22 and D24, the same number
TAX = D("0.0825")

SETTINGS = {
    "sales_tax_pct": "0.0825",
    "equip_fuel_maint_pct": "0.50",
}

SECTION = dict(
    kind="miscellaneous",
    name="13-Miscellaneous",
    unit="LS",
    margin_pct=D("0.18"),      # Summary!P59 — informational here; the sale is typed
    contingency_pct=D("0.00"),
    tax_exempt=None,
)

# The exercise: the tab's item code -> quantity.
QUANTITIES = {
    "1301": 10, "1302": 20, "1303": 4, "1304": 6,
    "1306": 1, "1307": 1, "1308": 1, "1309": 20, "1310": 2, "1311": 40,
    "1312": 4, "1313": 2, "1314": 1, "1315": 40, "1316": 100, "1317": 1, "1318": 1, "1319": 1,
    "1320": 2, "1321": 6, "1322": 12, "1323": 4,
}
TOTAL_SALE = D("88340.00")       # the sum of qty x the tab's unit sale, exactly

# What the APP reads. Set from the first run (2026-09-08) and held since.
GOLDEN_COST = D("78982.63")


def _ru(x: Decimal) -> Decimal:
    """Excel ROUNDUP(x, 0)."""
    return x.quantize(D("1"), rounding=ROUND_CEILING)


def _rd(x: Decimal) -> Decimal:
    """Excel ROUND(x, 0)."""
    return x.quantize(D("1"), rounding=ROUND_HALF_UP)


def tab_row(code: str, qty: int, *, exact: bool = False) -> dict[str, Decimal]:
    """
    The tab's row for this item at this quantity: (cy, lb, forms, concrete,
    steel, labor, super, equip, cost, sale).

    `exact=False` is the tab as it stands — its ROUNDUPs, its 3.145, its tax
    where it remembered it. `exact=True` is the same structure the way the
    app prices it: decimal yards, pi, every purchase taxed, the steel at
    lb/CY of the decimal yards. Two departures, both named in the test.
    """
    G = D(qty)
    M = MIX_COST
    R22 = REBAR_COST
    t = D("1") + TAX
    pi = D(str(math.pi)) if exact else D("3.145")
    ru = (lambda x: x) if exact else _ru
    rd = (lambda x: x) if exact else _rd
    # Blocks 1 and 2 forgot the tax on their concrete and steel; the app taxes them.
    t12 = t if exact else D("1")

    def round_base(dia, depth, steel_f, sale, labor, forms_pct, forms_each, sup_pct, equip_each, pours=True):
        o = ru((dia * D("0.5") * dia * D("0.5")) * pi / D("144") * depth / D("27") * G) if pours else D("0")
        p = dia * depth * steel_f * G
        k = G * sale
        q = k * forms_pct + G * forms_each
        return dict(cy=o, lb=p, forms=q * t12, concrete=o * M * t12, steel=p * R22 * t12,
                    labor=labor * G, sup=labor * G * sup_pct, equip=equip_each * G, sale=k)

    def block(L, W, H, lb_per_cy, sale, labor, forms_pct, face_rate, sup_pct, equip_each, *, lb_extra=D("0"), pours=True):
        walls = ru(L * W * H / D("3888") * D("1.15") * G) if pours else D("0")
        floor = ru((L / D("4")) * (L / D("4")) / D("27") * G) if pours else D("0")
        o = walls + floor
        p = rd(o * lb_per_cy) + lb_extra
        k = G * sale
        q = ru(k * forms_pct) + L * H / D("12") * face_rate * G
        return dict(cy=o, lb=p, forms=q * t12, concrete=o * M * t12, steel=rd(p * R22) * t12 if not exact else p * R22 * t12,
                    labor=labor * G, sup=labor * G * sup_pct, equip=equip_each * G, sale=k)

    def slab(sf, thk, sale, labor, forms_pct_sale, forms_pct_conc, sup_pct, equip_each, equip_pct_labor):
        o = sf * thk / D("324") * G
        n = o * D("0.01") * D("13232")
        r = o * M * t
        s = n * R22 * t
        k = G * sale
        q = sale * forms_pct_sale * G * (t if exact else D("1")) + r * forms_pct_conc
        lab = labor * G
        return dict(cy=o, lb=n, forms=q, concrete=r, steel=s, labor=lab, sup=lab * sup_pct,
                    equip=equip_each * G + lab * equip_pct_labor, sale=k)

    def box(L, W, Dp, lb_per_cy, sale, labor, forms_each, forms_pct_conc, sup_pct, equip_pct_labor, pours=True):
        o = L * W * Dp / D("46656") * G * D("1.2") if pours else D("0")
        r = o * M * t
        p = o * lb_per_cy
        s = p * R22 * t
        k = G * sale
        q = forms_each * G * (t if exact else D("1")) + r * forms_pct_conc * (t if not exact else D("1"))
        lab = labor * G
        return dict(cy=o, lb=p, forms=q, concrete=r, steel=s, labor=lab, sup=lab * sup_pct,
                    equip=lab * equip_pct_labor, sale=k)

    if code == "1301":
        row = round_base(D("24"), D("8"), D("0.95"), D("1150"), D("350"), D("0.1"), D("37.5"), D("0.2"), D("139"))
    elif code == "1302":
        row = round_base(D("12"), D("6"), D("0.95"), D("350"), D("120"), D("0.1"), D("37.5"), D("0.25"), D("8"))
    elif code == "1303":
        row = round_base(D("8"), D("2"), D("0"), D("300"), D("170"), D("0.1"), D("1"), D("0.25"), D("8"), pours=False)
    elif code == "1304":
        row = round_base(D("18"), D("3"), D("0"), D("150"), D("65"), D("0"), D("0"), D("0.25"), D("20"))
    elif code == "1306":
        row = block(D("48"), D("16"), D("72"), D("145"), D("18600"), D("6200"), D("0.15"), D("4.25"), D("0.1"), D("250"))
    elif code == "1307":
        # A service: the tab files $2,000 a pit under forms and takes 10% supervision on it.
        row = dict(cy=D("0"), lb=D("0"), forms=D("0"), concrete=D("0"), steel=D("0"),
                   labor=D("2000") * G, sup=D("200") * G, equip=D("0"), sale=D("2600") * G)
        if not exact:
            row["forms"], row["labor"] = row["labor"], D("0")
    elif code == "1308":
        row = block(D("15"), D("36"), D("36"), D("55"), D("2800"), D("650"), D("0.2"), D("0"), D("0.3"), D("15"))
    elif code == "1309":
        row = block(D("20"), D("0"), D("0"), D("55"), D("500"), D("150"), D("0.1"), D("0"), D("0.3"), D("50"))
    elif code == "1310":
        row = block(D("36"), D("12"), D("24"), D("55"), D("2500"), D("699"), D("0.1"), D("0"), D("0.3"), D("50"))
    elif code == "1311":
        # The tab adds L x 2.5 x 4 lb ONCE; the app carries 10 lb a unit.
        row = block(D("1"), D("12"), D("12"), D("55"), D("40"), D("16"), D("0.1"), D("0"), D("0.1"), D("3"),
                    lb_extra=(D("10") * G if exact else D("10")))
    elif code == "1312":
        row = slab(D("9"), D("28"), D("450"), D("150"), D("0.1"), D("0"), D("0.15"), D("0"), D("0.15"))
    elif code == "1313":
        row = slab(D("9"), D("24"), D("550"), D("185"), D("0.1"), D("0"), D("0.15"), D("55"), D("0"))
    elif code == "1314":
        row = slab(D("36"), D("12"), D("1150"), D("360"), D("0"), D("0.7"), D("0.15"), D("114.58"), D("0"))
    elif code == "1315":
        row = slab(D("2"), D("12"), D("43"), D("16"), D("0"), D("0.5"), D("0.1"), D("0"), D("0.1"))
    elif code == "1316":
        row = slab(D("1"), D("12"), D("38"), D("18"), D("0"), D("0.5"), D("0.05"), D("3.18"), D("0"))
    elif code == "1317":
        row = slab(D("4"), D("18"), D("350"), D("175"), D("0"), D("0.5"), D("0.15"), D("19.10"), D("0"))
    elif code == "1318":
        row = slab(D("50"), D("12"), D("1400"), D("500"), D("0"), D("0.5"), D("0.15"), D("159.15"), D("0"))
    elif code == "1319":
        row = slab(D("369"), D("12"), D("11050"), D("3700"), D("0"), D("0.7"), D("0.15"), D("1174.54"), D("0"))
    elif code == "1320":
        row = box(D("24"), D("24"), D("5"), D("0"), D("250"), D("150"), D("25"), D("0"), D("0.1"), D("0"), pours=False)
    elif code == "1321":
        row = box(D("60"), D("12"), D("12"), D("0"), D("125"), D("57"), D("8"), D("0"), D("0.1"), D("0.075"))
    elif code == "1322":
        row = box(D("36"), D("36"), D("6"), D("66.625"), D("110"), D("50"), D("5"), D("0"), D("0.1"), D("0"))
    elif code == "1323":
        # The tab's steel is a ratio of the concrete DOLLARS: R x 0.33 / 0.26 x 1.15 lb.
        row = box(D("60"), D("60"), D("4"), D("211.7"), D("550"), D("350"), D("0"), D("0.5"), D("0"), D("0"))
        if not exact:
            row["lb"] = row["concrete"] * D("0.33") / D("0.26") * D("1.15")
            row["steel"] = row["lb"] * R22 * t
    else:
        raise KeyError(code)

    row["cost"] = row["forms"] + row["concrete"] + row["steel"] + row["labor"] + row["sup"] + row["equip"]
    return row


def _tab_on_the_tab(code: str, qty: int) -> dict[str, Decimal]:
    """The slab and box families tax inline; a row's cost is the tab's X."""
    return tab_row(code, qty)


def price_the_catalog(db) -> dict:
    mix_id = db.execute(
        text("UPDATE mix_designs SET unit_cost = :c WHERE code = :k RETURNING id"),
        {"c": MIX_COST, "k": MIX_CODE},
    ).scalar()
    assert mix_id is not None, f"no mix design {MIX_CODE} in the catalog"
    found = db.execute(
        text("UPDATE materials SET unit_cost = :c WHERE name = :n RETURNING id"),
        {"c": REBAR_COST, "n": REBAR_NAME},
    ).scalar()
    assert found is not None, f"no catalog material named {REBAR_NAME!r}"
    for key, value in SETTINGS.items():
        db.execute(
            text("INSERT INTO system_settings (key, value) VALUES (:k, to_jsonb(CAST(:v AS text))) "
                 "ON CONFLICT (key) DO UPDATE SET value = excluded.value"),
            {"k": key, "v": value},
        )
    db.flush()
    return {"mix_id": int(mix_id)}


def build_section(db, estimate, ids: dict, *, quantities: dict | None = None) -> EstimateSection:
    section = EstimateSection(estimate_id=estimate.id, **SECTION)
    db.add(section)
    db.flush()
    seed_from_library(db, section)
    q = QUANTITIES if quantities is None else quantities
    for code, qty in q.items():
        n = db.execute(
            text("UPDATE misc_items SET qty = :q, mix_design_id = :m WHERE section_id = :s AND code = :c"),
            {"q": qty, "m": ids["mix_id"], "s": str(section.id), "c": code},
        ).rowcount
        assert n == 1, f"library item {code} not on the section"
    db.expire_all()
    refresh_section_misc_calcs(db, section)
    db.flush()
    return section


def build(db, estimate, *, quantities: dict | None = None) -> EstimateSection:
    priced = price_the_catalog(db)
    from app.services.price_book import pull_prices

    pull_prices(db, estimate.id)
    return build_section(db, estimate, priced, quantities=quantities)
