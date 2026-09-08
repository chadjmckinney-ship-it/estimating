-- 073_grade_beams.sql
--
-- Grade beams and continuous footings: the workbook's 02-Gd Beams tab as a
-- section of its own, and 02-Cont Footings as a second kind on the same
-- engine.
--
-- Chad, 2026-09-07: "most spread footings have a weld plate.. so I think we
-- need a section for spread footings and one for continuous footings.. we
-- can do cont footings when we do grade beams" — and, asked whether the two
-- sell per face foot the way the sheet's C40 does: "we use LF for both of
-- those."
--
-- The tab is the SEPARATELY POURED beam — formed on both faces and poured
-- before the slab — which the vault has held apart from the monolithic beam
-- on the mono slab since 2026-08-02 ("the two methods do not share a cost
-- model"). One row per beam type: mix, length, width, height, top, bottom
-- and mid bars, stirrups at a spacing, L bars, pilasters. Steel and concrete
-- by the tab's formulas; forming, place and finish, wreck, and rub and patch
-- per face foot of ONE face; tie steel per ton; excavation per CY of a
-- trench as deep as it is wide plus the beam itself; backfill per CY of
-- trench; the lumber block, the supervision block and the equipment ladder
-- the walls tab already reproduces. On the LBJ workbook the tab is empty;
-- the Pearl Landing Podium estimate carries both tabs with money on them,
-- and they are the goldens (tests/grade_beams_fixture.py).
--
-- 02-Cont Footings is the same tab with four cells typed differently:
-- carton forms and the durrock retainer switched on, wall ties and camlocks
-- zeroed. Those are the second kind's defaults; everything else is shared.

-- The kind.
ALTER TABLE estimate_sections DROP CONSTRAINT IF EXISTS estimate_sections_kind_check;
ALTER TABLE estimate_sections
    ADD CONSTRAINT estimate_sections_kind_check CHECK (kind IN (
        'mono_slab', 'paving', 'sidewalk', 'piers', 'grade_beams', 'cont_footings',
        'walls_footings', 'spot_footings', 'columns', 'slabs', 'cip_deck',
        'slab_on_deck', 'panels', 'miscellaneous'
    ));

-- One row per beam type — the tab's row 10, sixth takeoff shape.
CREATE TABLE IF NOT EXISTS beam_runs (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    section_id          uuid NOT NULL REFERENCES estimate_sections (id) ON DELETE CASCADE,
    label               text,
    description         text,
    mix_design_id       integer REFERENCES mix_designs (id) ON DELETE SET NULL,

    length_ft           numeric(12, 3) NOT NULL DEFAULT 0,
    width_in            numeric(8, 3)  NOT NULL DEFAULT 0,
    height_in           numeric(8, 3)  NOT NULL DEFAULT 0,

    top_bars_count      integer NOT NULL DEFAULT 0,
    top_bars_size       smallint REFERENCES bar_weights (bar_size),
    bottom_bars_count   integer NOT NULL DEFAULT 0,
    bottom_bars_size    smallint REFERENCES bar_weights (bar_size),
    mid_bars_count      integer NOT NULL DEFAULT 0,
    mid_bars_size       smallint REFERENCES bar_weights (bar_size),
    stirrup_size        smallint REFERENCES bar_weights (bar_size),
    stirrup_spacing_in  numeric(8, 3),
    l_bars_size         smallint REFERENCES bar_weights (bar_size),
    l_bars_spacing_in   numeric(8, 3),
    l_bars_length_ft    numeric(8, 3),

    pilaster_count      integer NOT NULL DEFAULT 0,
    pilaster_length_in  numeric(8, 3),
    pilaster_width_in   numeric(8, 3),

    notes               text,
    sort_order          integer NOT NULL DEFAULT 0,

    calc_total_rebar_lb       numeric(14, 3),
    calc_concrete_cy    numeric(14, 4),
    calc_contact_ff     numeric(14, 3),
    calc_face_ff        numeric(14, 3),
    calc_pilaster_ff    numeric(14, 3),
    calc_excavate_cy    numeric(14, 3),
    calc_backfill_cy    numeric(14, 3),

    calc_direct_cost    numeric(14, 2),
    calc_allocated_cost numeric(14, 2),
    calc_equip_fuel     numeric(14, 2),
    calc_tax            numeric(14, 2),
    calc_cost           numeric(14, 2),
    calc_sale           numeric(14, 2),
    calc_cost_per_unit  numeric(14, 4),
    calc_sale_per_unit  numeric(14, 4),

    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),
    updated_by          uuid REFERENCES estimators (id) ON DELETE SET NULL,

    CONSTRAINT beam_runs_length_ft_check          CHECK (length_ft >= 0),
    CONSTRAINT beam_runs_width_in_check           CHECK (width_in >= 0),
    CONSTRAINT beam_runs_height_in_check          CHECK (height_in >= 0),
    CONSTRAINT beam_runs_top_bars_count_check     CHECK (top_bars_count >= 0),
    CONSTRAINT beam_runs_bottom_bars_count_check  CHECK (bottom_bars_count >= 0),
    CONSTRAINT beam_runs_mid_bars_count_check     CHECK (mid_bars_count >= 0),
    CONSTRAINT beam_runs_pilaster_count_check     CHECK (pilaster_count >= 0)
);
CREATE INDEX IF NOT EXISTS beam_runs_section_id_idx    ON beam_runs (section_id);
CREATE INDEX IF NOT EXISTS beam_runs_mix_design_id_idx ON beam_runs (mix_design_id);
CREATE INDEX IF NOT EXISTS beam_runs_updated_by_idx    ON beam_runs (updated_by);

COMMENT ON TABLE beam_runs IS
    'Separately poured grade beams and continuous footings (sql/073): one row per beam type, the 02-Gd Beams tab''s row 10. Not the mono slab''s beams, which are monolithic and live on estimate_beam_types.';
COMMENT ON COLUMN beam_runs.calc_face_ff IS
    'Form feet on ONE face: L x H/12 — what forming, place and finish, wreck, and rub and patch are priced per (the tab''s BB and I63).';
COMMENT ON COLUMN beam_runs.calc_contact_ff IS
    'Both faces: L x H/12 x 2 — what wall ties and form rental run off (the tab''s BA).';
COMMENT ON COLUMN beam_runs.calc_excavate_cy IS
    'The tab''s FT: ROUND(L x H/12 x H/12 / 27 + concrete CY) — a trench as deep as it is wide, plus the beam.';
COMMENT ON COLUMN beam_runs.calc_backfill_cy IS
    'The tab''s FV: ROUND(L x H/12 x H/12 / 27) — the trench.';

-- The tab's rates, for both kinds. The workbook's own numbers: the LBJ
-- template where it types one, the Podium job where the template is blank.
INSERT INTO assembly_rates (kind, key, value, note)
SELECT k.kind, r.key, r.value, r.note
  FROM (VALUES ('grade_beams'), ('cont_footings')) AS k(kind)
 CROSS JOIN (VALUES
    ('labor_pilasters_ff',      8,     '02-Gd Beams E62 — pilaster forming, per face foot of pilaster'),
    ('labor_forming_sf',        4,     '02-Gd Beams E63 — per face foot, one face'),
    ('labor_place_finish_sf',   4,     '02-Gd Beams E64'),
    ('labor_wreck_sf',          1,     '02-Gd Beams E65'),
    ('labor_rub_patch_sf',      0.25,  '02-Gd Beams E66'),
    ('labor_tie_steel_ton',     450,   '02-Gd Beams E67'),
    ('labor_excavate_cy',       4,     '02-Gd Beams E68 — the walls tab digs at 12'),
    ('labor_backfill_cy',       8,     '02-Gd Beams E69'),
    ('concrete_pump_cy',        20,    '02-Gd Beams G85 — the walls tab pumps at 10'),
    ('haul_off_cy',             6,     '02-Gd Beams G89 — per CY of concrete, automatic on this tab'),
    ('waterproofing_sf',        5.25,  '02-Gd Beams G86'),
    ('saw_cutting_lf',          2.5,   '02-Gd Beams G87'),
    ('misc_contract_ls',        500,   '02-Gd Beams G88'),
    ('carton_forms_lf',         3.75,  '02-Gd Beams G58 — per LF of beam, with its waste'),
    ('durrock_retainer_lf',     2.75,  '02-Gd Beams G59 — per LF, both sides'),
    ('carton_forms_waste',      0.10,  '02-Gd Beams K57 — on carton forms and the retainer'),
    ('form_percent',            0.5,   '02-Gd Beams T48 on the LBJ template (the Podium job types 0)'),
    ('form_rental_percent',     0.3,   '02-Gd Beams K60 — the share of contact feet rented'),
    ('waste_concrete',          0.04,  '02-Gd Beams K48'),
    ('waste_rebar',             0.10,  '02-Gd Beams K52'),
    ('pilaster_steel_pct',      0.03,  '02-Gd Beams W10 — pilaster steel as 3% of its volume, in lb')
 ) AS r(key, value, note)
ON CONFLICT (kind, key) DO NOTHING;

-- The price sheets: the two kinds' monetary rates on every existing job, at
-- the assembly value, so nothing reads unpriced until the next pull.
INSERT INTO estimate_prices
    (estimate_id, kind, scope, ref_key, label, unit, category, catalog_value, value)
SELECT e.id, 'assembly_rate', a.kind, a.key, k.label, k.unit, a.kind || ' rates', a.value, a.value
  FROM estimates e
 CROSS JOIN assembly_rates a
  JOIN (VALUES
          ('labor_pilasters_ff',    'Pilaster labor',        'FF'),
          ('labor_forming_sf',      'Forming labor',         'SF'),
          ('labor_place_finish_sf', 'Place & finish labor',  'SF'),
          ('labor_wreck_sf',        'Wreck & clean labor',   'SF'),
          ('labor_rub_patch_sf',    'Rub & patch labor',     'SF'),
          ('labor_tie_steel_ton',   'Tie steel labor',       'TON'),
          ('labor_excavate_cy',     'Excavate labor',        'CY'),
          ('labor_backfill_cy',     'Backfill labor',        'CY'),
          ('concrete_pump_cy',      'Concrete pump',         'CY'),
          ('haul_off_cy',           'Haul off',              'CY'),
          ('waterproofing_sf',      'Waterproofing',         'SF'),
          ('saw_cutting_lf',        'Saw cutting',           'LF'),
          ('misc_contract_ls',      'Miscellaneous contract','LS'),
          ('carton_forms_lf',       'Carton forms (beams)',  'LF'),
          ('durrock_retainer_lf',   'Durrock retainer',      'LF')
       ) AS k(key, label, unit) ON k.key = a.key
 WHERE a.kind IN ('grade_beams', 'cont_footings')
   AND EXISTS (SELECT 1 FROM estimate_prices p WHERE p.estimate_id = e.id)
ON CONFLICT DO NOTHING;
