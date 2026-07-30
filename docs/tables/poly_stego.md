# Poly / Stego (vapor barrier) SF

Quantity for vapor barrier under mono slab pours (Poly, Stego Wrap, Yellow Guard, etc.).

## Formula

```
beam_poly_sf  = (2 × height_in / 12) × length_lf   # Excel AS = H*2/12 per LF
pour_poly_sf  = pour_SF + Σ beam_poly_sf   (all kinds: GB, Exp, Drop)
total_poly_sf = pour_poly_sf × (1 + waste_poly)
```

| Piece | Meaning |
|-------|---------|
| Pour SF | Slab plane (`mono_slabs.square_footage`) — already covers beam bottoms |
| Beam wrap | Two vertical sides only (`2×H`), inches → feet, × length (Excel 04-PT SOG) |
| waste_poly | System default **0.10** (10%) in `system_settings` |

SQL helper: `calc_poly_beam_sf(width_in, height_in, length_lf)`

## Stored columns

| Table | Column | Notes |
|-------|--------|--------|
| `grade_beams` | `calc_poly_sf` | Per type/row wrap SF |
| `mono_slabs` | `calc_poly_slab_sf` | Pour SF |
| `mono_slabs` | `calc_poly_gb_sf` | Sum of beam wraps |
| `mono_slabs` | `calc_poly_sf` | Total with waste |

## Migration

`sql/014_poly_stego_sf.sql` (create) · `sql/015_poly_sides_only.sql` (Excel sides-only fix + backfill)

## Not yet

- Roll → material (Stego 14×210, etc.) conversion
- Tape LF
- Cost / supplier pick
