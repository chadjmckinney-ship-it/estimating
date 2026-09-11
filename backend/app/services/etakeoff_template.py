"""
eTakeoff Dimension item-tree templates (.itt): a bid code on every measurable item.

Chad, 2026-09-10: "we can build a bidcode file that I can import and them
assign to each item... then there is no way to screw it up... I wonder if you
can read my template file with all the prebuilt items" — and, on the plan,
"yes". See docs/specs/etakeoff-bid-codes.md.

The template (`Rev Template.itt`) is Dimension's Quantity Worksheet tree in a
line-per-field text format::

    INodeLink {
     ItemNode {
      BrkdnCode("05 MonoSlab Wrap Bld 1")
      ...
      BidCode("")
     }
     INodeLink { ItemNode { ... } ... }
    }

`recode()` reads it, decides a code for every item that can be measured, and
writes the file back with ONLY the BidCode values changed — every other byte,
the CRLF line endings included, is the office's. The codes follow the families
already in Chad's projects (MonoSlabBld1Pour01, MonoSlabIntGBBld1Pour01,
Footings-F01, WallSec01, PavingHeavyDuty, ...) and fill the gaps in the same
style. `bid_code_rows()` is the two-column list Dimension's Standard Bid Code
List pastes; `review()` is the change list Chad reads before importing.

Nothing here touches the database: this is a file in, three files out.
"""

from __future__ import annotations

import csv
import io
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field

# ------------------------------------------------------------ the file format


@dataclass(slots=True)
class Node:
    name: str
    arg: str | None = None
    children: list["Node"] = field(default_factory=list)
    parent: "Node | None" = None
    val_start: int = -1   # offset of the value's first character in the source
    val_end: int = -1     # offset past its last character
    quoted: bool = False

    def get(self, name: str, default: str = "") -> str:
        for c in self.children:
            if c.name == name:
                return c.arg if c.arg is not None else default
        return default

    def child(self, name: str) -> "Node | None":
        for c in self.children:
            if c.name == name:
                return c
        return None


_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def parse(text: str) -> Node:
    """The tree, with every field's value span recorded so it can be rewritten in place."""
    root = Node("ROOT")
    cur = root
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c in " \t\r\n":
            i += 1
            continue
        if c == "}":
            cur = cur.parent or root
            i += 1
            continue
        m = _IDENT.match(text, i)
        if not m:
            i += 1
            continue
        name, i = m.group(0), m.end()
        while i < n and text[i] in " \t":
            i += 1
        if i < n and text[i] == "{":
            node = Node(name, parent=cur)
            cur.children.append(node)
            cur = node
            i += 1
            continue
        if i < n and text[i] == "(":
            i += 1
            if i < n and text[i] == '"':
                i += 1
                start = i
                buf: list[str] = []
                while i < n:
                    ch = text[i]
                    if ch == "\\" and i + 1 < n:
                        buf.append(text[i + 1])
                        i += 2
                        continue
                    if ch == '"':
                        break
                    buf.append(ch)
                    i += 1
                end = i
                i += 1
                while i < n and text[i] != ")":
                    i += 1
                i += 1
                cur.children.append(Node(name, "".join(buf), parent=cur, val_start=start, val_end=end, quoted=True))
            else:
                start = i
                while i < n and text[i] != ")":
                    i += 1
                cur.children.append(Node(name, text[start:i], parent=cur, val_start=start, val_end=i, quoted=False))
                i += 1
            continue
        cur.children.append(Node(name, parent=cur))
    return root


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def trace_name(trace: str) -> str:
    """The trace's name, the twelfth field of Dimension's comma-packed trace string."""
    parts = trace.split(",") if trace else []
    return parts[11].strip() if len(parts) > 11 else ""


# ----------------------------------------------------------------- the items


@dataclass
class Item:
    node: Node
    path: tuple[str, ...]
    label: str
    desc: str
    trace: str
    dtype: str
    fmla: str
    layer: str
    has_children: bool
    old_code: str
    new_code: str = ""
    status: str = ""            # kept | added | changed | cleared | skipped
    notes: list[str] = field(default_factory=list)

    @property
    def where(self) -> str:
        return " > ".join(self.path)

    @property
    def top(self) -> str:
        return self.path[0]


def items(root: Node) -> list[Item]:
    out: list[Item] = []

    def walk(link: Node, path: tuple[str, ...]) -> None:
        node = link.child("ItemNode")
        if node is None:
            return
        p = path + (node.get("BrkdnCode"),)
        kids = [c for c in link.children if c.name == "INodeLink"]
        out.append(Item(
            node=node, path=p, label=node.get("BrkdnCode"), desc=node.get("Desc"),
            trace=trace_name(node.get("Trace")), dtype=node.get("DataType"), fmla=node.get("Fmla"),
            layer=node.get("Layer"), has_children=bool(kids), old_code=node.get("BidCode"),
        ))
        for k in kids:
            walk(k, p)

    for c in root.children:
        if c.name == "INodeLink":
            walk(c, ())
    return out


def measurable(it: Item) -> bool:
    """An item a measurement can land on: not a breakdown header, not a hand-typed
    number, not a formula without a trace, not an item with neither a type nor a trace."""
    if len(it.path) == 1:
        return False
    if it.dtype == "N":
        return False
    if it.dtype == "F" and not it.trace:
        return False
    if not it.dtype and not it.trace:
        return False
    return True


# ------------------------------------------------------------------ the codes

# Chad's mono slab roles, as the items are labelled (2026-09-10: "IntRB is
# interior rebar beam, TKND is thickened beam").
ROLES = {
    "INT GB": "IntGB", "INT RB": "IntRB", "INT TKND": "TKND", "DROPS": "Drop", "DROP": "Drop",
    "EXPOSED GB": "EXP", "STEMWALL": "Stem", "BRICKLEDGE": "Brick",
}
ROLE_WORDS = {
    "IntGB": "interior grade beam", "IntRB": "interior rebar beam", "TKND": "thickened beam", "Drop": "drop beam",
    "EXP": "exposed grade beam", "Stem": "stem wall", "Brick": "brickledge", "Keyway": "keyway",
}
PAVING_NAMES = {
    "HEAVY DUTY/FIRELANE": "HeavyDuty", "HEAVY DUTY/FIRELANE PAVERS": "HeavyDutyPavers",
    "HEAVY DUTY/FIRELANE STAMPED": "HeavyDutyStamped", "LIGHT DUTY": "LightDuty",
    "LIGHT DUTY PAVER BASE": "LightDutyPavers", "LIGHT DUTY STAMPED": "LightDutyStamped",
    "MEDIUM DUTY": "MediumDuty", "MEDIUM DUTY PAVER BASE": "MediumDutyPavers", "MEDIUM DUTY STAMPED": "MediumDutyStamped",
    "CURB & GUTTER": "CurbGutter", "DOWEL TO EXISTING": "Dowel", "DUMPSTER PAD": "DumpsterPad",
    "DUMPSTER PAD APRON": "DumpsterApron", "MONO CURB": "MonoCurb", "TURN LANE/DECEL LANE": "TurnLane",
    "MEDIAN AREA": "Median", "CURB": "Curb", "APPROACH": "Approach", "DEMO": "Demo", "FIRELANE": "Firelane",
    "PARKING": "Parking",
}
SIDEWALK_NAMES = {
    "ADA RAMPS BLDG": "ADARampsBldg", "ADA RAMPS CITY": "ADARampsCity", "CITY WALKS": "CityWalks",
    "DECO WALKS": "DecoWalks", "ON SITE WALKS": "OnSiteWalks", "STAIR TREAD": "StairTread", "PAVER BASE": "PaverBase",
    "STAMPED AND STAINED SIDEWALK": "StampedStained", "STANDARD BROOM FINISH": "Broom",
}
KEEP_CAPS = {"ADA", "CMU", "GB", "RB", "EXP", "TKND", "SOG", "LF", "CIP", "ROW", "INT", "PC", "CY", "SF", "HVAC"}


def norm(label: str) -> str:
    """A label as a code fragment: letters, digits and hyphens, words run together,
    a bare single digit padded to two ("Wall 1" -> Wall01, "C1" -> C01, "18 x 36" -> 18x36,
    "60/24/20" -> 60-24-20)."""
    s = label.replace("&", " ").replace("'s", "").replace("'", "").replace("#", "No").replace("/", "-")
    s = re.sub(r"[^A-Za-z0-9\- ]", " ", s)
    out: list[str] = []
    for w in s.split():
        if w.lower() == "x":
            out.append("x")
            continue
        if re.fullmatch(r"\d", w):
            w = "0" + w
        m = re.fullmatch(r"([A-Za-z]+)(\d)", w)
        if m:
            w = m.group(1) + "0" + m.group(2)
        if w.isupper() and (w in KEEP_CAPS or not w.isalpha()):
            out.append(w)
        elif w.isupper() and len(w) > 1:
            out.append(w[0] + w[1:].lower())
        else:
            out.append(w[0].upper() + w[1:])
    return "".join(out)


def _compact(desc: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", desc.replace("#", "No").replace("'s", ""))


_WRAP = re.compile(r"Bld\s*(\d+)", re.I)
_DEPTH = re.compile(r'^(\d+)\s*"?\s*(Drop|Exposed\s*GB)s?$', re.I)
_POUR = re.compile(r"^Bld\s*(\d+)\s*Pour\s*(\d+|Leav\w*)$", re.I)
_TYPE = re.compile(r"^Bld\s*Type\s*(\d+)$", re.I)
_SEC = re.compile(r"Sec\s*(\d+)", re.I)
_FTG = re.compile(r"F(\d+)", re.I)
_PIER = re.compile(r"^P\s*(\d+)$", re.I)


def _family(top: str) -> str:
    t = top.upper()
    if "MONOSLAB WRAP" in t or "MONO SLAB WRAP" in t:
        return "wrap"
    if "GARDEN" in t:
        return "garden"
    if "GARAGE FOOTING" in t:
        return "garage_footings"
    if "FOOTING" in t:
        return "footings"
    if "GARAGE WALL" in t:
        return "garage_walls"
    if "WALL" in t:
        return "walls"
    if "GARAGE SOG" in t:
        return "garage_sog"
    if "ROW PAVING" in t:
        return "row_paving"
    if "PAVING" in t:
        return "paving"
    if "COURTYARD" in t:
        return "courtyard"
    if "SIDEWALK" in t:
        return "sidewalk"
    if "CIP DECK" in t:
        return "cip_deck"
    if "METAL DECK" in t or "SLAB ON DECK" in t:
        return "deck"
    if "COL" in t:
        return "columns"
    if "PIER" in t:
        return "piers"
    if "MISC" in t:
        return "misc"
    return "other"


def _named(table: dict[str, str], label: str) -> str:
    return table.get(label.strip().upper()) or norm(label)


def code_for(it: Item) -> str | None:
    """The code an item should carry, or None when it is not something a measurement lands on."""
    if not measurable(it):
        return None
    fam = _family(it.top)
    sub = it.path[1:]
    label = it.label.strip()

    if fam in ("wrap", "garden"):
        if fam == "wrap":
            m = _WRAP.search(it.top)
            bld = int(m.group(1)) if m else 0
            first = sub[0]
            pm = _POUR.match(first.strip())
            if pm:
                pour = "LO" if pm.group(2)[:4].upper() == "LEAV" else f"{int(pm.group(2)):02d}"
                scope = f"Bld{bld}Pour{pour}"
                if int(pm.group(1)) != bld:
                    it.notes.append(f"the pour is labelled for building {int(pm.group(1))} under the building {bld} breakdown")
            elif first.strip().upper() == "KEYWAY":
                return f"MonoSlabKeywayBld{bld}"
            else:
                it.notes.append("not a pour label; coded from the label")
                scope = f"{norm(first)}Bld{bld}"
        else:
            first = sub[0]
            tm = _TYPE.match(first.strip())
            if tm:
                scope = f"Type{int(tm.group(1)):02d}"
            elif first.strip().upper() == "KEYWAY":
                return "MonoSlabKeywayGarden"
            else:
                # A building type with a name instead of a number (Clubhouse, Trash
                # Enclosure): the same family, the name as the type.
                if len(sub) == 1:
                    it.notes.append("a named building type; coded from its name")
                scope = f"Type{norm(first)}"
        if len(sub) == 1:
            return f"MonoSlab{scope}"
        role = ROLES.get(label.upper())
        if role is None:
            # The depth-coded drops and exposed beams: `06" Drop`, `24" Exposed GB`
            # (MonoSlab06DropBld2Pour01, MonoSlab24EXPBld2Pour01 in the projects).
            dm = _DEPTH.match(label)
            if dm:
                role = f"{int(dm.group(1)):02d}" + ("Drop" if dm.group(2).upper().startswith("DROP") else "EXP")
            else:
                it.notes.append("no standard role for this label; coded from the label")
                role = norm(label)
        return f"MonoSlab{role}{scope}"

    if fam == "footings":
        m = _FTG.search(label)
        return f"Footings-F{int(m.group(1)):02d}" if m else f"Footings-{norm(label)}"
    if fam == "garage_footings":
        m = _FTG.search(label)
        return f"GarageFooting-F{int(m.group(1)):02d}" if m else f"GarageFooting-{norm(label)}"
    if fam == "walls":
        m = _SEC.search(label)
        return f"WallSec{int(m.group(1)):02d}" if m else f"Wall{norm(label)}"
    if fam == "garage_walls":
        m = _SEC.search(label)
        return f"GarageWallSec{int(m.group(1)):02d}" if m else f"GarageWall{norm(label)}"
    if fam == "piers":
        m = _PIER.match(label)
        return f"PierP{int(m.group(1)):02d}" if m else f"Pier{norm(label)}"
    if fam == "columns":
        return "Column" + "".join(norm(x) for x in sub)
    if fam == "deck":
        return "Deck" + "".join(norm(x) for x in sub)
    if fam == "cip_deck":
        return "CIPDeck" + "".join(norm(x) for x in sub)
    if fam in ("paving", "row_paving"):
        prefix = "Paving" if fam == "paving" else "ROWPaving"
        return prefix + "".join(_named(PAVING_NAMES, x) for x in sub)
    if fam in ("sidewalk", "courtyard"):
        prefix = "Sidewalk" if fam == "sidewalk" else "Courtyard"
        return prefix + "".join(_named(SIDEWALK_NAMES, x) for x in sub)
    if fam == "garage_sog":
        group = sub[0].strip().upper() if len(sub) > 1 else ""
        if group == "COLUMNS":
            return "GarageSOGCol" + norm(label)
        if group == "GRADE BEAMS":
            base = norm(label)
            if base.upper().startswith("GB"):
                base = base[2:] or base
            return "GarageSOGGB" + base + (f"-{_compact(it.desc)}" if it.desc else "")
        if group == "PIER CAPS":
            return "GarageSOGPierCap" + norm(label)
        if group == "PIERS":
            return "GarageSOGPier" + norm(label)
        if group == "WALLS":
            if sub[1].startswith("?"):
                it.notes.append("the wall has no name in the template")
                return "GarageSOGWallUnnamed" + "".join(norm(x) for x in sub[2:])
            base = "".join(norm(x) for x in sub[1:])
            if base.startswith("Wall"):
                base = base[4:]
            return "GarageSOGWall" + base
        return "GarageSOG" + "".join(norm(x) for x in sub)
    if fam == "misc":
        base = "".join(norm(x) for x in sub)
        if base.upper().startswith("MISC"):
            base = base[4:]
        return "Misc" + base
    it.notes.append("no family for this breakdown; coded from its labels")
    return norm(it.top) + "".join(norm(x) for x in sub)


# --------------------------------------------------------------- the layers

BEAM_ROLES = {"IntGB", "IntRB", "TKND", "Drop", "EXP"}
WALL_ROLES = {"Stem", "Brick"}


def expected_layer(it: Item) -> str | None:
    """The default layer an item's family uses in the template, or None where there is no convention.
    Chad, 2026-09-10: "there is a lot I need to straighten up in it.. like the layers"."""
    fam = _family(it.top)
    if fam in ("wrap", "garden"):
        if len(it.path) == 2:
            return "04 Slab" if it.label.strip().upper() != "KEYWAY" else None
        role = ROLES.get(it.label.strip().upper())
        if role is None and _DEPTH.match(it.label.strip()):
            role = "Drop" if "DROP" in it.label.upper() else "EXP"
        if role in BEAM_ROLES:
            return "04 GradeBeams"
        if role in WALL_ROLES:
            return "04 Walls"
        return None
    if fam in ("footings", "garage_footings"):
        return "04 Footings"
    if fam in ("walls", "garage_walls"):
        return "04 Walls"
    if fam == "piers":
        return "01 piers"
    if fam == "columns":
        return "03 Columns"
    if fam in ("paving", "row_paving"):
        return "03 Paving"
    if fam in ("sidewalk", "courtyard"):
        return "10 SIDEWALK"
    if fam == "garage_sog" and len(it.path) > 2:
        return {"COLUMNS": "03 Columns", "GRADE BEAMS": "04 GradeBeams", "PIERS": "01 piers"}.get(it.path[1].strip().upper())
    return None


# -------------------------------------------------------------- the assignment


def _numbers(s: str) -> list[str]:
    return re.findall(r"\d+", s)


def assign(its: list[Item]) -> None:
    """Decide every item's code and status, and note what a person should look at."""
    for it in its:
        code = code_for(it)
        if code is None:
            it.new_code = ""
            it.status = "cleared" if it.old_code else "skipped"
            if len(it.path) == 1 and it.trace:
                it.notes.append(f"a breakdown header carrying the trace {it.trace!r}")
            if len(it.path) > 1 and not it.dtype and not it.trace and not it.has_children:
                it.notes.append("no type and no trace: nothing can be measured onto it")
            continue
        it.new_code = code
        if not it.old_code:
            it.status = "added"
        elif it.old_code == code:
            it.status = "kept"
        else:
            it.status = "changed"
        # A trace that names a different numbered sibling ("F16 Footings" on the F15 trace).
        if it.trace and it.trace.strip().upper() != it.label.strip().upper():
            ln, tn = [int(x) for x in _numbers(it.label)], [int(x) for x in _numbers(it.trace)]
            same_shape = re.sub(r"\s+", " ", re.sub(r"\d+", "#", it.label.strip().upper())) == \
                re.sub(r"\s+", " ", re.sub(r"\d+", "#", it.trace.strip().upper()))
            if ln and tn and ln != tn and same_shape:
                it.notes.append(f"the trace is {it.trace!r}")
        want = expected_layer(it)
        if want and it.layer and it.layer != want:
            it.notes.append(f"default layer is {it.layer!r}; the family uses {want!r}")

    # Codes must be unique: a second item on the same code is a template defect.
    # The garage family lives under 09 (09 GARAGE SOG, 09 Garage Footings), so
    # when the template carries both a 06 and a 09 "Garage Walls" the 09 one
    # keeps the clean codes and the 06 twin is the one marked to delete.
    def rank(i: int) -> tuple[int, int]:
        it = its[i]
        return (0 if _family(it.top) == "garage_walls" and it.top.strip().startswith("09") else 1, i)

    seen: dict[str, Item] = {}
    for i in sorted(range(len(its)), key=rank):
        it = its[i]
        if not it.new_code:
            continue
        if it.new_code in seen:
            first = seen[it.new_code]
            n = 2
            while f"{it.new_code}-DUP{n}" in seen:
                n += 1
            dup = f"{it.new_code}-DUP{n}"
            it.notes.append(f"duplicate of {first.where!r}; delete one of them")
            it.new_code = dup
            it.status = "added" if not it.old_code else ("kept" if it.old_code == dup else "changed")
            seen[dup] = it
        else:
            seen[it.new_code] = it


# ------------------------------------------------------------------ the result


@dataclass
class Recoded:
    text: str
    items: list[Item]

    @property
    def counts(self) -> Counter:
        return Counter(it.status for it in self.items)

    def coded(self) -> list[Item]:
        return [it for it in self.items if it.new_code]

    def bid_code_rows(self) -> list[tuple[str, str]]:
        """(code, description) in the template's order, one row per code — the two columns
        Dimension's Standard Bid Code List pastes, without a header row."""
        rows: list[tuple[str, str]] = []
        for it in self.coded():
            desc = it.where
            if it.desc:
                desc += f" — {it.desc}"
            role = next((w for k, w in ROLE_WORDS.items() if it.new_code.startswith("MonoSlab" + k)), None)
            if role:
                desc += f" ({role})"
            rows.append((it.new_code, desc))
        return rows

    def bid_code_csv(self) -> str:
        buf = io.StringIO()
        w = csv.writer(buf, lineterminator="\r\n")
        for code, desc in self.bid_code_rows():
            w.writerow([code, desc])
        return buf.getvalue()

    def defects(self) -> list[Item]:
        """Items with a note a person should read — the layer notes are counted, not listed."""
        return [it for it in self.items if any(not n.startswith("default layer") for n in it.notes)]

    def layer_notes(self) -> list[str]:
        """One line per breakdown, layer and expected layer: '103 items under X sit on Sidewalks; the family uses 04 GradeBeams'."""
        counts: Counter = Counter()
        for it in self.items:
            if any(n.startswith("default layer") for n in it.notes):
                counts[(it.top, it.layer, expected_layer(it))] += 1
        return [f"{v} items under '{top}' default to the {layer!r} layer; the family uses {want!r}"
                for (top, layer, want), v in sorted(counts.items(), key=lambda kv: (kv[0][0], kv[0][1] or ""))]

    def layer_rows(self) -> list[Item]:
        return [it for it in self.items if any(n.startswith("default layer") for n in it.notes)]

    def described(self) -> list[Item]:
        return [it for it in self.items if it.desc]

    def review(self, name: str = "Rev Template.itt") -> str:
        c = self.counts
        fams = Counter(_family(it.top) for it in self.coded())
        lines = [
            f"# {name}: the bid codes",
            "",
            f"Items {len(self.items)}; coded {len(self.coded())} — kept {c.get('kept', 0)}, added {c.get('added', 0)}, "
            f"changed {c.get('changed', 0)}; cleared {c.get('cleared', 0)}; not measurable {c.get('skipped', 0)}.",
            "",
            "Families: " + ", ".join(f"{k} {v}" for k, v in sorted(fams.items())) + ".",
            "",
            "Roles on a mono slab: " + "; ".join(f"`{k}` {v}" for k, v in ROLE_WORDS.items()) + "; `PourLO` the leave-outs.",
            "",
            "## Look at these",
            "",
        ]
        tops = [it for it in self.items if len(it.path) == 1]
        twins = defaultdict(list)
        for t in tops:
            twins[re.sub(r"^\d+\s*", "", t.label).strip().upper()].append(t.label)
        twin_of: dict[str, set[str]] = {}
        for v in twins.values():
            if len(v) > 1:
                lines.append(f"- Two breakdowns carry the same codes: {' and '.join(repr(x) for x in v)}. Keep one.")
                for x in v:
                    twin_of[x] = {y for y in v if y != x}
        for it in self.defects():
            notes = [n for n in it.notes if not n.startswith("default layer")]
            # an item duplicated only because its whole breakdown is a twin is covered by the line above
            notes = [n for n in notes if not (n.startswith("duplicate of '") and any(n.startswith(f"duplicate of '{t} > ") for t in twin_of.get(it.top, ())))]
            if not notes:
                continue
            lines.append(f"- `{it.where}`" + (f" [{it.old_code} → {it.new_code}]" if it.new_code != it.old_code else "") + ": " + "; ".join(notes))
        for ln in self.layer_notes():
            lines.append(f"- {ln}")
        lines += ["", "## Layers to straighten", "",
                  "Items whose default layer is not the one their family uses. A blank layer is not listed.", "",
                  "| Item | Layer | The family uses |", "|---|---|---|"]
        for it in self.layer_rows():
            lines.append(f"| {it.where} | {it.layer} | {expected_layer(it)} |")
        lines += ["", "## Descriptions", "", "Every item that carries one, so the stale ones are in one list.", "",
                  "| Item | Description |", "|---|---|"]
        for it in self.described():
            lines.append(f"| {it.where} | {it.desc} |")
        lines += ["", "## Changed", "", "| Item | Was | Now |", "|---|---|---|"]
        for it in self.items:
            if it.status in ("changed", "cleared"):
                lines.append(f"| {it.where} | `{it.old_code}` | `{it.new_code}` |" if it.new_code else f"| {it.where} | `{it.old_code}` | (cleared) |")
        lines += ["", "## Every item", "", "| Item | Type | Trace | Code | Status |", "|---|---|---|---|---|"]
        for it in self.items:
            lines.append(f"| {it.where} | {it.dtype or ''} | {it.trace} | `{it.new_code}` | {it.status} |")
        return "\n".join(lines) + "\n"


def recode(text: str) -> Recoded:
    """The template with every measurable item coded; nothing else in the file changes."""
    root = parse(text)
    its = items(root)
    assign(its)
    edits: list[tuple[int, int, str]] = []
    for it in its:
        if it.new_code == it.old_code:
            continue
        bc = it.node.child("BidCode")
        if bc is None or not bc.quoted:
            it.notes.append("the item has no BidCode field to write; add the code by hand")
            continue
        edits.append((bc.val_start, bc.val_end, _escape(it.new_code)))
    out = text
    for start, end, value in sorted(edits, reverse=True):
        out = out[:start] + value + out[end:]
    return Recoded(text=out, items=its)


def mask_bid_codes(text: str) -> str:
    """The file with every BidCode value blanked — what must not change between in and out."""
    return re.sub(r'BidCode\("(?:[^"\\]|\\.)*"\)', 'BidCode("")', text)
