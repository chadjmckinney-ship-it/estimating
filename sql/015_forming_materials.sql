-- Forming / lumber takeoff settings (Excel 04 LUMBER AND ACCESS)
-- Apply: psql -d estimating -f sql/015_forming_materials.sql

BEGIN;

INSERT INTO system_settings (key, value, description)
VALUES
    (
        'form_percent',
        '0.50'::jsonb,
        'Excel W65 “% of forming” — multiplies perimeter-driven lumber (2x4/2x6/2x10/ply). LBJ used 0.50; template default 0.70.'
    ),
    (
        'form_waste',
        '0.00'::jsonb,
        'Optional waste on forming material extended cost (decimal). Excel uses Y44 markup separately; leave 0 for qty-only.'
    )
ON CONFLICT (key) DO NOTHING;

COMMIT;
