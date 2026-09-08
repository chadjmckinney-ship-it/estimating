-- 080_proposals.sql
--
-- The proposal: the estimate pushed onto the bid form. Chad, 2026-09-08: "ok,
-- proposal? here is the latest proposal form we are using" — Sherry Pointe
-- Apts 26-102 on the NEW FORM of 2026-08-28 — and, on the proposal, "build
-- it". docs/specs/proposal-spec.md.
--
-- The form: a header (submitted to, attention, email, date, job, location,
-- the four drawings with their plan dates), numbered lines under section
-- titles — number, description, quantity, unit and status printed; unit
-- price and extended held in F and G outside the print area, so only the
-- section totals and the lump sum print — then the standing blocks
-- (alternates, equipment rates, labor rates, qualifications, exclusions),
-- the terms, and the acceptance page.
--
-- Five tables. `proposals` is one per estimate: the header and a revision
-- counter (the file is the playbook's `<Job> - Proposal - <#> - <date>_<NN>`).
-- `proposal_sections` and `proposal_lines` are the body; a line remembers the
-- takeoff row it was seeded from, so a refresh pulls fresh quantities and
-- prices onto it and leaves the rewritten description alone. `proposal_items`
-- are the bullet blocks and the terms on THIS proposal. `proposal_library` is
-- the company's standing text every new proposal copies, seeded here from the
-- Sherry Pointe form as Chad uses it today, less the job-specific sales tax
-- deduction.
--
-- The takeoff is untouched: an excluded line is a proposal status with its
-- quantity kept, and the row behind it still prices.

CREATE TABLE IF NOT EXISTS proposal_library (
    id          serial PRIMARY KEY,
    block       text NOT NULL CHECK (block IN (
                    'alternates', 'equipment_rates', 'labor_rates',
                    'qualifications', 'exclusions', 'terms')),
    sort_order  integer NOT NULL DEFAULT 0,
    text        text NOT NULL,
    updated_by  uuid REFERENCES estimators (id) ON DELETE SET NULL,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS proposal_library_block_idx      ON proposal_library (block, sort_order);
CREATE INDEX IF NOT EXISTS proposal_library_updated_by_idx ON proposal_library (updated_by);

COMMENT ON TABLE proposal_library IS
    'The company''s standing proposal text (sql/080): the bullet blocks and the terms every new '
    'proposal copies. Edited under Settings; a proposal already made keeps its own copy.';

CREATE TABLE IF NOT EXISTS proposals (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    estimate_id     uuid NOT NULL UNIQUE REFERENCES estimates (id) ON DELETE CASCADE,
    rev             integer NOT NULL DEFAULT 1 CHECK (rev >= 1),
    proposal_date   date NOT NULL DEFAULT CURRENT_DATE,
    -- The header block, as the form prints it. Seeded from the project (the
    -- GC, the job and number, the location) and typed over freely.
    submitted_to    text,
    attn            text,
    email           text,
    phone           text,
    job_label       text,
    location        text,
    intro           text NOT NULL DEFAULT
        'We are pleased to submit a proposal for labor, material, and equipment as detailed herein to construct the items below.',
    payment_terms   text NOT NULL DEFAULT 'PER CONTRACT AGREEMENT OR UPON COMPLETION',
    -- The four drawings: [{discipline, firm, plan_date}], in the form's order.
    drawings        jsonb NOT NULL DEFAULT '[]'::jsonb,
    notes           text,
    updated_by      uuid REFERENCES estimators (id) ON DELETE SET NULL,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS proposals_updated_by_idx ON proposals (updated_by);

COMMENT ON TABLE proposals IS
    'One proposal per estimate (sql/080): the bid form''s header and revision counter. The '
    'sections, lines and standing text hang off it; the .xlsx is built from all of them.';
COMMENT ON COLUMN proposals.rev IS
    'The playbook''s revision counter, _01 upward per job; the file name carries it. Typed, '
    'never bumped by a download.';

CREATE TABLE IF NOT EXISTS proposal_sections (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    proposal_id  uuid NOT NULL REFERENCES proposals (id) ON DELETE CASCADE,
    -- The estimate section this one was seeded from, if any; the tie-out
    -- card reads its sale. NULL for a section typed by hand.
    section_id   uuid REFERENCES estimate_sections (id) ON DELETE SET NULL,
    title        text NOT NULL DEFAULT '',
    sort_order   integer NOT NULL DEFAULT 0,
    updated_by   uuid REFERENCES estimators (id) ON DELETE SET NULL,
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS proposal_sections_proposal_idx   ON proposal_sections (proposal_id, sort_order);
CREATE INDEX IF NOT EXISTS proposal_sections_section_idx    ON proposal_sections (section_id);
CREATE INDEX IF NOT EXISTS proposal_sections_updated_by_idx ON proposal_sections (updated_by);

CREATE TABLE IF NOT EXISTS proposal_lines (
    id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    proposal_section_id  uuid NOT NULL REFERENCES proposal_sections (id) ON DELETE CASCADE,
    sort_order           integer NOT NULL DEFAULT 0,
    description          text NOT NULL DEFAULT '',
    qty                  numeric(14, 3),
    unit                 text,
    status               text NOT NULL DEFAULT 'INCLUDED' CHECK (status IN ('INCLUDED', 'EXCLUDED')),
    -- Four places, the way a sale divided by a quantity comes out; the form
    -- shows it to the cent and the extended is C x F.
    unit_price           numeric(14, 4),
    -- Where the line came from: the takeoff table and row a refresh re-reads.
    -- NULL on a line typed by hand (haul-off, certified payroll, pumping).
    source_table         text,
    source_id            uuid,
    source_missing       boolean NOT NULL DEFAULT false,
    notes                text,
    updated_by           uuid REFERENCES estimators (id) ON DELETE SET NULL,
    created_at           timestamptz NOT NULL DEFAULT now(),
    updated_at           timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS proposal_lines_section_idx    ON proposal_lines (proposal_section_id, sort_order);
CREATE INDEX IF NOT EXISTS proposal_lines_updated_by_idx ON proposal_lines (updated_by);

COMMENT ON COLUMN proposal_lines.status IS
    'INCLUDED prices; EXCLUDED keeps the line and its quantity on the form and contributes '
    'nothing — measured and excluded, not missed.';
COMMENT ON COLUMN proposal_lines.source_missing IS
    'Set by a refresh when the takeoff row behind the line is gone or at no quantity. The '
    'line stays until someone deletes it.';

CREATE TABLE IF NOT EXISTS proposal_items (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    proposal_id  uuid NOT NULL REFERENCES proposals (id) ON DELETE CASCADE,
    block        text NOT NULL CHECK (block IN (
                     'alternates', 'equipment_rates', 'labor_rates',
                     'qualifications', 'exclusions', 'terms')),
    sort_order   integer NOT NULL DEFAULT 0,
    text         text NOT NULL,
    updated_by   uuid REFERENCES estimators (id) ON DELETE SET NULL,
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS proposal_items_proposal_idx   ON proposal_items (proposal_id, block, sort_order);
CREATE INDEX IF NOT EXISTS proposal_items_updated_by_idx ON proposal_items (updated_by);

-- The standing text, from the Sherry Pointe form (2026-09-01_02) as Chad
-- uses it today. The one job-specific alternate on that form — the material
-- sales tax deduction with its dollar figure — is left off.
INSERT INTO proposal_library (block, sort_order, text) VALUES
    ('alternates', 10, 'Pipe Bollards (install and fill only, bollards supplied by others) - $250.00 EA'),
    ('alternates', 20, 'Light Bollard (12" dia x 24" deep) - $250.00 EA'),
    ('alternates', 30, 'Pumping of paving per setup - ADD $4,000.00 minimum or $16.00 per YD'),
    ('alternates', 40, 'Additional 1" thickness added to onsite pavement in lieu of Lime Stabilization - ADD $1.15 per SF'),
    ('alternates', 50, 'Single Phase CIP transformer pads, approx 44" x 56" - $1,200.00 EA'),
    ('alternates', 60, 'Three Phase 750 kva transformer pads, approx 96" x 114" - $3,400.00 EA'),
    ('alternates', 70, 'Site Retaining Walls - EXCLUDED'),
    ('alternates', 80, 'Transformer Pads - EXCLUDED'),
    ('equipment_rates', 10, 'Water Pump 2" Electric - $175.00 / day'),
    ('equipment_rates', 20, 'Light Tower - $290.00 / day'),
    ('equipment_rates', 30, 'Roto Hammer / Grinder / Cutoff Saw - $175.00 / day'),
    ('equipment_rates', 40, 'Plate Compactor - $150.00 / day'),
    ('equipment_rates', 50, 'Jumping Jack Compactor - $165.00 / day'),
    ('equipment_rates', 60, 'Truck & Trailer - $175.00 / hr'),
    ('equipment_rates', 70, 'Dump Truck - $175.00 / hr'),
    ('equipment_rates', 80, 'Bobcat / Skidloader - $620.00 / day'),
    ('equipment_rates', 90, 'Backhoe / Mini Excavator - $820.00 / day'),
    ('labor_rates', 10, 'Laborers - $36.00 / hr'),
    ('labor_rates', 20, 'Form setters, finishers and equipment operators - $46.00 / hr'),
    ('labor_rates', 30, 'Supervision - $200.00 / hr'),
    ('qualifications', 10, 'Grade + or - 0.10'),
    ('qualifications', 20, 'Broomed finished concrete at sidewalks and paving'),
    ('qualifications', 30, 'Expansion joints on paving every 200 ft. Control joints on paving every 15''.'),
    ('qualifications', 40, 'Any spoils are stockpiled only up to 100'' from where created'),
    ('qualifications', 50, 'Clean-up to your dumpsters'),
    ('qualifications', 60, 'Rock excavation is cost and labor plus 20% markup'),
    ('qualifications', 70, 'Two inches of sand (cushion sand) only.'),
    ('qualifications', 80, 'Not responsible for existing conditions of which could be damaged in construction'),
    ('exclusions', 10, 'Any item not specifically included is excluded.'),
    ('exclusions', 20, 'Embedded materials (anchor bolts, pipe bollards, angles, hold downs, etc.)'),
    ('exclusions', 30, 'Concrete pumping at paving'),
    ('exclusions', 40, 'Concrete colors (integral or cast on), concrete stains and decorative concrete finishes'),
    ('exclusions', 50, 'Site retaining walls not listed above'),
    ('exclusions', 60, 'Backfilling of walls w/ onsite spoils'),
    ('exclusions', 70, 'Gravel Backfill'),
    ('exclusions', 80, 'Radon Mitigation System, Associated Pits'),
    ('terms', 10, 'General Contractor is responsible for including this proposal into all future contracts. Acceptance of the below pricing is an acceptance to the scope as defined below and will supersede any conflicting details and notes specified in the plans and project documents. Please understand that there are pending and continuous price increases in the materials needed for our work, including, but not limited to, ready mix concrete, lumber, rebar, and post tension cable. We will provide applicable data or other support to demonstrate any cost increase in these and other materials required for our work. Because of the continuous increase in the cost of materials, be advised that any delay in the project schedule could cause an increase in our material costs and a directly related increase in our pricing'),
    ('terms', 20, 'Allowing S & S Concrete Contractors Inc. to commence work or Customer’s signature on this Proposal will constitute acceptance by Customer of this Proposal. It is understood that the parties may enter into a more comprehensive Subcontract; however, this Proposal including these Terms and Conditions shall be incorporated into any such subsequent Subcontract. In the event of any conflict between the terms of this Proposal and any other document, writing, agreement or source, the terms of this Proposal shall govern.'),
    ('terms', 30, 'The pricing in this proposal will be acceptable for thirty (30) days, unless otherwise agreed upon in writing. S & S Concrete Contractors Inc. will not bear the risk of any increases in pricing, including applicable sales tax, after thirty (30) days. After thirty (30) days, any increase in price will be paid by contractor or owner including applicable sales tax and markup.'),
    ('terms', 40, 'In no event will S & S Concrete Contractors, Inc be responsible for any failure or delay in performance of its obligations hereunder arising out of without limitations or caused by, directly or indirectly, forces beyond its control , due to Covid-19 or other disease decisions made by Local or Federal Government.'),
    ('terms', 50, 'This Proposal, including without limitation the price and scope, may not be modified except by a written change order signed by both S & S Concrete and Customer. S & S Concrete shall have no obligation to perform any additional work until a change order is signed by both S & S Concrete and Customer. Costs for work associated with approved change orders shall be billed during the same billing period they are incurred, regardless of whether Customer has fully processed a change order.'),
    ('terms', 60, 'An event of "force majeure" is an event which is beyond the reasonable control of S & S Concrete Contractors, Inc., such as a: (a) riot, war, invasion, acts of terrorism, civil war, rebellion, revolution, insurrection of military or usurped power, secession of states, requisition or compulsory acquisition by any government or competent authority; (b) earthquake, flood, fire or other physical natural disaster, severe weather conditions or acts of god; (c) epidemic, pandemic, quarantine or civil commotion; (d) strike on a national level or industrial dispute at a national level, or strike or industrial dispute which affect an essential portion of S & S Concrete Contractors, Inc''s performance of the contract; (e) acts by other subcontractors that impede S & S Concrete Contractors, Inc''s ability to perform the work, (f) general lack of availability of raw materials or other supplies, and (g) a manufacturer’s delay in supplying the product. S & S Concrete Contractors, Inc is not responsible for any failure to perform its obligations under the Contract if it is prevented or delayed in performing those obligations by an event of force majeure. Where there is an event of force majeure, S & S Concrete Contractors must promptly notify Contractor giving full particulars of the event of force majeure and the reasons for the event of force majeure from preventing S & S Concrete Contractors from or delaying S & S Concrete Contractors in performing its obligations under the contract and S & S Concrete Contractors must use its reasonable efforts to mitigate the effect of the event of force majeure upon its performance of the contract and to fulfill its incurred by Contractor due to the event of force majeure.');
