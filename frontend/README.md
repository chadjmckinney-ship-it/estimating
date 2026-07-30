# Estimating Web UI

Browser interface for the S&S estimating system. Served by the FastAPI backend (no Node/Flutter build required).

## Run

```bash
cd ~/Estimate_Projects/backend
../.venv/bin/uvicorn app.main:app --reload --host 127.0.0.1 --port 8001
```

Open: **http://127.0.0.1:8001/**

## What’s included

| Page | Features |
|------|----------|
| Dashboard | Counts + recent projects |
| Projects | List, search, filter status, create/edit (Notion-shaped fields) |
| Project detail | Bid header + estimates list + create estimate |
| Estimate detail | **Mono slab pours** — enter SF/thickness/PT/mix, live CY & rebar calcs |
| Estimators | List + add |
| Mix designs | SC / ASH / Air-ASH catalog |
| Materials | Browse / filter / search unit costs |
| Equipment | Rental rates |

## Stack

- Static HTML + CSS + ES modules (no bundler)
- Talks to `/api/*` on the same host
- Dark industrial theme (concrete gray + orange accent)

## Later

- Flutter Web can replace this SPA when you want a mobile-class UI
- Mono Slab quantity screens attach to an **estimate** (next product step)
