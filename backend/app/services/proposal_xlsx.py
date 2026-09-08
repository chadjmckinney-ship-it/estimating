"""
The proposal as an .xlsx on the bid form (sql/080).

Built cell for cell to the NEW FORM of 2026-08-28 as the Sherry Pointe
proposal of 2026-09-01 carries it: the letterhead, the header block, the
four drawings, the intro, a band and a header row over every section's
numbered lines, a SECTION TOTAL under each, the bullet blocks, the lump sum,
the terms and the acceptance page. Fonts, fills, borders, widths, row
heights and the page setup are the template's own, read off it with openpyxl.

Two things the form does on purpose, kept here on purpose:

  * UNIT PRICE and EXTENDED sit in F and G, and the print area stops at E.
    Section totals and the lump sum print; the rates behind them do not
    (Chad, 2026-08-28: a per-item number handed over before award is a
    number that gets used to beat us with later).
  * The money is live: G is `=C*F`, a section total is `=SUM(G..)`, the lump
    sum adds the section totals — so a rate tweaked in Excel still adds up.
"""

from __future__ import annotations

from decimal import Decimal
from io import BytesIO
from math import ceil
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.worksheet.page import PageMargins
from openpyxl.worksheet.properties import PageSetupProperties

# ------------------------------------------------------ the form's words ----
LETTERHEAD = (
    "S & S CONCRETE CONTRACTORS, INC.",
    "P.O. BOX 162147",
    "FORT WORTH, TX 76161-2147",
    "817-332-2253",
    "817-332-2254 - FAX",
)
PROPOSE = (
    "We propose hereby to furnish material and labor - complete in accordance "
    "with above specifications, for the sum of:"
)
GUARANTEE = (
    "All material is guaranteed to be as specified. All work to be completed in a "
    "workmanlike manner according to standard practices. Any alteration or deviation "
    "from above specifications involving extra cost will be executed only upon written "
    "orders, and will become an extra charge over and above the estimate. All "
    "agreements contingent upon strikes, accidents or delays beyond are our control. "
    "Owner to carry fire, tornado and other necessary insurance. Our workers are fully "
    "covered by Workman's Compensation Insurance."
)
WITHDRAW = "Note: This proposal may be withdrawn by us if not accepted within _30__ days."
ACCEPT = (
    "Acceptance of Proposal - The above prices, specifications and conditions are "
    "satisfactory and are hereby accepted. You are authorized to do the work as "
    "specified. Payment will be made as outlined above."
)
SIGNATURES = ("Date of Acceptance", "Customer Signature", "Authorized Signature, S & S Concrete Contractors, Inc.")
BLOCK_TITLES = {
    "alternates": "ALTERNATES",
    "equipment_rates": "ADDITIONAL EQUIPMENT RATES",
    "labor_rates": "ADDITIONAL LABOR RATES",
    "qualifications": "QUALIFICATIONS",
    "exclusions": "EXCLUSIONS",
}
BULLET_BLOCKS = ("alternates", "equipment_rates", "labor_rates", "qualifications", "exclusions")

# ------------------------------------------------------ the form's look ----
ARIAL = "Arial"
DARK, GREY, BLUE, NAVY, LIGHT, WHITE = "1C1C1C", "5C6570", "2754B2", "1C3F8A", "E8EEF8", "FFFFFF"
COLUMN_WIDTHS = {"A": 5.0, "B": 74.0, "C": 13.0, "D": 6.0, "E": 14.73, "F": 13.0, "G": 15.0}
THIN = Side(style="thin")
MEDIUM = Side(style="medium")
BOX = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
HEAD_BOX = Border(left=THIN, right=THIN, top=THIN, bottom=MEDIUM)
CENTER = Alignment(horizontal="center", vertical="center")
VCENTER = Alignment(vertical="center")
LEFT = Alignment(horizontal="left", vertical="center")
RIGHT = Alignment(horizontal="right", vertical="center")
WRAP_TOP = Alignment(vertical="top", wrap_text=True)
HEAD = Alignment(horizontal="center", vertical="top", wrap_text=True)
HEAD_LEFT = Alignment(vertical="top", wrap_text=True)
MONEY = '"$"#,##0.00'
MONEY0 = '"$"#,##0'


def _font(size: float, bold: bool = False, color: str = DARK) -> Font:
    return Font(name=ARIAL, size=size, bold=bold, color=color)


def _fill(rgb: str) -> PatternFill:
    return PatternFill(fill_type="solid", fgColor=rgb, bgColor=rgb)


def _height(text: str, size: float, base: float) -> float:
    """
    A row tall enough for wrapped text in column B — Excel does not re-fit
    rows on open, so the height has to be written. Characters a line holds
    and the height of a line, both read off the template's own rows.
    """
    per_line = {8: 100, 9: 92, 9.5: 85, 10: 80}.get(size, 85)
    lines = sum(max(1, ceil(len(part) / per_line)) for part in str(text or "").split("\n"))
    return max(base, round(lines * size * 1.32 + 4, 1))


def _qty(value: Any) -> tuple[Any, str]:
    """A whole quantity as an integer with no decimals; anything else to three."""
    if value is None:
        return None, "General"
    d = Decimal(str(value))
    if d == d.to_integral_value():
        return int(d), "#,##0"
    return float(d), "#,##0.###"


class _Sheet:
    """A cursor down the sheet: one row at a time, each with its height."""

    def __init__(self, ws):
        self.ws = ws
        self.r = 0

    def row(self, height: float | None = None) -> int:
        self.r += 1
        if height is not None:
            self.ws.row_dimensions[self.r].height = height
        return self.r

    def put(self, col: str, value: Any, *, font: Font, fill: PatternFill | None = None,
            align: Alignment | None = None, border: Border | None = None, fmt: str | None = None):
        c = self.ws[f"{col}{self.r}"]
        c.value = value
        c.font = font
        if fill is not None:
            c.fill = fill
        if align is not None:
            c.alignment = align
        if border is not None:
            c.border = border
        if fmt is not None:
            c.number_format = fmt
        return c

    def band(self, rgb: str, cols: str = "ABCDE") -> None:
        for col in cols:
            self.ws[f"{col}{self.r}"].fill = _fill(rgb)

    def title(self, text: str) -> None:
        """A section or block title: bold white on the form's blue band."""
        self.row(20.0)
        self.band(BLUE)
        self.put("B", text, font=_font(11, True, WHITE), fill=_fill(BLUE), align=VCENTER)


def _iso(value: Any) -> str:
    if value is None or value == "":
        return ""
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def build_workbook(p: dict[str, Any]) -> bytes:
    """The proposal read (services.proposals.proposal_read) as the form, in bytes."""
    wb = Workbook()
    ws = wb.active
    ws.title = "PROPOSAL"
    for col, width in COLUMN_WIDTHS.items():
        ws.column_dimensions[col].width = width
    ws.sheet_view.showGridLines = False
    s = _Sheet(ws)

    # Letterhead, merged across the print width.
    for i, line in enumerate(LETTERHEAD):
        r = s.row(22.0 if i == 0 else 14.05)
        ws.merge_cells(f"A{r}:E{r}")
        s.put("A", line, font=_font(16, True, NAVY) if i == 0 else _font(9, color=GREY), align=CENTER)
    s.row(22.0)
    s.band(BLUE)
    s.put("B", "PROPOSAL", font=_font(14, True, WHITE), fill=_fill(BLUE), align=LEFT)
    s.row(10.0)

    # The header block, one line each, zebra-striped the way the form is.
    header = [
        ("SUBMITTED TO", p.get("submitted_to")),
        ("ATTN", p.get("attn")),
        ("EMAIL", p.get("email")),
        ("DATE", _iso(p.get("proposal_date"))),
        ("JOB", p.get("job_label")),
        ("LOCATION", p.get("location")),
    ]
    if p.get("phone"):
        header.insert(3, ("PHONE", p.get("phone")))
    for i, (label, value) in enumerate(header):
        s.row(16.0)
        s.put("B", f"{label}     {value or ''}", font=_font(10), fill=_fill(LIGHT if i % 2 else WHITE), align=VCENTER)
    s.row(8.0)

    # Drawings supplied.
    s.row(16.0)
    s.put("B", "DRAWINGS SUPPLIED", font=_font(9, True, WHITE), fill=_fill(NAVY), align=VCENTER)
    s.put("C", "DATE OF PLANS", font=_font(9, True, WHITE), fill=_fill(NAVY), align=CENTER)
    for d in p.get("drawings") or []:
        s.row(16.2)
        firm = d.get("firm") or ""
        s.put("B", f"{d.get('discipline', '')}:   {firm}", font=_font(9), fill=_fill(LIGHT), border=BOX, align=HEAD_LEFT)
        s.put("C", _iso(d.get("plan_date")), font=_font(9), fill=_fill(LIGHT), border=BOX, align=CENTER)
    s.row(10.0)

    intro = p.get("intro") or ""
    s.row(_height(intro, 10, 32.4))
    s.put("B", intro, font=_font(10), align=WRAP_TOP)
    s.row(8.0)

    # The sections: a band, a header row, the numbered lines, a total.
    n = 0
    total_cells: list[str] = []
    for sec in p.get("sections") or []:
        s.title(str(sec.get("title") or "").upper())
        s.row(18.0)
        for col, text, align in (("A", "#", HEAD), ("B", "DESCRIPTION", HEAD_LEFT), ("C", "QTY", HEAD),
                                 ("D", "UNIT", HEAD), ("E", "STATUS", HEAD)):
            s.put(col, text, font=_font(8, True, WHITE), fill=_fill(NAVY), align=align, border=HEAD_BOX)
        s.put("F", "UNIT PRICE", font=_font(8, True, GREY), align=VCENTER)
        s.put("G", "EXTENDED", font=_font(8, True, GREY), align=VCENTER)

        first = last = None
        for ln in sec.get("lines") or []:
            n += 1
            desc = ln.get("description") or ""
            r = s.row(_height(desc, 9.5, 18.2))
            first = first or r
            last = r
            s.put("A", n, font=_font(9, color=GREY), align=CENTER, border=BOX)
            s.put("B", desc, font=_font(9.5), align=WRAP_TOP, border=BOX)
            qty, qfmt = _qty(ln.get("qty"))
            s.put("C", qty, font=_font(10), align=CENTER, border=BOX, fmt=qfmt)
            s.put("D", ln.get("unit") or None, font=_font(9), align=CENTER, border=BOX)
            s.put("E", ln.get("status") or "INCLUDED", font=_font(8, True), align=CENTER, border=BOX)
            included = (ln.get("status") or "INCLUDED") == "INCLUDED"
            price = ln.get("unit_price")
            if included and price is not None:
                s.put("F", float(Decimal(str(price))), font=_font(10), align=VCENTER, fmt=MONEY)
                if qty is not None:
                    s.put("G", f"=C{r}*F{r}", font=_font(10), align=VCENTER, fmt=MONEY0)
        s.row(18.0)
        s.put("D", "SECTION TOTAL", font=_font(8, True, WHITE), fill=_fill(NAVY), align=RIGHT)
        formula = f"=SUM(G{first}:G{last})" if first is not None else 0
        s.put("E", formula, font=_font(11, True, WHITE), fill=_fill(NAVY), align=CENTER, border=BOX, fmt=MONEY0)
        total_cells.append(f"E{s.r}")
        s.row(12.0)

    # The bullet blocks.
    items = p.get("items") or {}
    for block in BULLET_BLOCKS:
        rows = items.get(block) or []
        if not rows:
            continue
        s.title(BLOCK_TITLES[block])
        for it in rows:
            text = it.get("text") if isinstance(it, dict) else str(it)
            s.row(_height(text, 9.5, 18.2))
            s.put("A", "•", font=_font(10, True, BLUE), align=CENTER)
            s.put("B", text, font=_font(9.5), align=WRAP_TOP)
        s.row(10.0)

    # The sum.
    s.row(_height(PROPOSE, 10, 32.4))
    s.put("B", PROPOSE, font=_font(10, True), align=WRAP_TOP)
    s.row(6.0)
    s.row(24.0)
    s.put("D", "TOTAL", font=_font(12, True, WHITE), fill=_fill(BLUE), align=RIGHT)
    lump = "=" + "+".join(total_cells) if total_cells else 0
    s.put("E", lump, font=_font(14, True, WHITE), fill=_fill(BLUE), align=CENTER, border=BOX, fmt=MONEY0)
    s.row(15.0)

    # Terms, numbered.
    terms = items.get("terms") or []
    if terms:
        s.title("TERMS AND CONDITIONS")
        for i, it in enumerate(terms):
            text = it.get("text") if isinstance(it, dict) else str(it)
            s.row(_height(text, 9.5, 18.2))
            s.put("A", i + 1, font=_font(10, True, BLUE), align=CENTER)
            s.put("B", text, font=_font(9.5), align=WRAP_TOP)
        s.row(10.0)

    # Acceptance.
    s.title("ACCEPTANCE")
    payment = f"Payment to be made as follows:  {p.get('payment_terms') or ''}"
    s.row(_height(payment, 10, 32.4))
    s.put("B", payment, font=_font(10, True), align=WRAP_TOP)
    s.row(6.0)
    s.row(_height(GUARANTEE, 9.5, 98.4))
    s.put("B", GUARANTEE, font=_font(9.5), align=WRAP_TOP)
    s.row(4.0)
    s.row(17.2)
    s.put("B", WITHDRAW, font=_font(9), align=WRAP_TOP)
    s.row(8.0)
    s.row(_height(ACCEPT, 10, 45.6))
    s.put("B", ACCEPT, font=_font(10), align=WRAP_TOP)
    s.row(12.0)
    for label in SIGNATURES:
        s.row(14.0)
        s.put("B", label, font=_font(8, color=GREY), align=VCENTER)
        s.row(22.0)
        s.row(10.0)

    # The page: letter, portrait, one page wide, prices off the print.
    ws.print_area = f"A1:E{s.r}"
    ws.page_setup.orientation = "portrait"
    ws.page_setup.paperSize = ws.PAPERSIZE_LETTER
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)
    ws.page_margins = PageMargins(left=0.7, right=0.7, top=0.75, bottom=0.75, header=0.3, footer=0.3)
    ws.oddFooter.center.text = "Page &P of &N"
    ws.oddFooter.right.text = "CONFIDENTIAL"

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
