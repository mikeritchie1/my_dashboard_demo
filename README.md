# Personal Dashboard

A self-built personal dashboard that pulls data from 15+ sources into a single interface, kept up to date by GitHub Actions pipelines running daily and hourly.

---

## What it does

The dashboard is a single-page app (`docs/index.html`) that reads from JSON files updated by Python scrapers on a schedule. Each module is fully independent.

| Module | Description |
|---|---|
| **Media Hub** | Movies, series, anime, and games synced from Notion, enriched with TMDB/RAWG metadata (posters, ratings, genres). Tracks watchlist, backlog, and history with a personal rating system |
| **Reading List** | Books and manga tracked via Notion, with currently-reading and year-by-year history views |
| **Events & Venues** | Live event listings from Bandsintown, Quicket, and Webtickets, combined with a curated venue database. Venues are geocoded and events tagged by category and genre |
| **Google Calendar** | Upcoming personal calendar events pulled across multiple Google Calendar IDs |
| **One Piece Cards** | Hourly scrape of card availability and pricing across 4 stores. Cross-references a configurable missing-card list, tracks price history, and sends email alerts for new stock below a set threshold |
| **Release Radar** | Upcoming and recent movies (TMDB), new game releases (RAWG), IMAX showtimes, and latest releases aggregated into a single view |
| **News** | Ranked articles from 20+ RSS/Atom feeds across 8 categories. An importance scoring system surfaces breaking stories, with a dedicated F1 Snapshot showing live standings, race schedule, and results |
| **YouTube** | Latest uploads from configured channels, grouped by series with thumbnail previews |
| **Game Hub** | A reference companion for tabletop/co-op game sessions - stores build loadouts, module notes, and ability breakdowns per campaign |
| **Game Lab** | A sandbox for quickly building and testing browser game ideas. New games drop in as self-contained HTML/JS/CSS bundles and are picked up automatically via a manifest |
| **Timeline** | Chronological photo and memory feed driven by a date-stamped manifest |
| **Weather** | 7-day forecast with daily high/low temperatures via Open-Meteo |

---

## Architecture

```
GitHub Actions (daily + hourly)
        |
        | commits updated JSON
        v
docs/data/  (JSON files per module)
        |
        | loaded by the frontend
        v
docs/index.html + app.js + styles.css
        |
        | UI state (tabs, filters)
        v
Cloudflare Worker + KV  (optional)
```

Key decisions:
- Scrapers run in CI and push updated JSON, so the site is always in sync
- Each module's JSON file is the contract between scraper and frontend, keeping them fully decoupled
- Scrapers diff against a previous snapshot and only write what changed

---

## Tech stack

**Backend**
- Python 3.13
- GitHub Actions - daily and hourly scheduled workflows
- SMTP - email notifications for card alerts and daily digest

**Frontend**
- HTML5, CSS3, JavaScript
- Hosted on GitHub Pages

**APIs**
- [TMDB](https://www.themoviedb.org/documentation/api) - movie and TV metadata
- [RAWG](https://rawg.io/apidocs) - video game database
- [Notion API](https://developers.notion.com/) - user lists (watchlist, games, reading, specials)
- [Google Calendar API](https://developers.google.com/calendar) - calendar events
- [Google Places API](https://developers.google.com/maps/documentation/places) - venue geocoding
- [Open-Meteo](https://open-meteo.com/) - weather
- [Nominatim](https://nominatim.org/) - fallback geocoding

**Infrastructure**
- GitHub Pages
- Cloudflare Workers + KV

---

## Project layout

```
my-dashboard/
├── docs/                        # Dashboard (served as the site)
│   ├── index.html
│   ├── app.js
│   ├── styles.css
│   └── data/                    # JSON data files
│       ├── events/
│       ├── media/
│       ├── news/
│       ├── one_piece/
│       ├── release_radar/
│       ├── youtube/
│       ├── game_hub/
│       ├── game_lab/
│       ├── timeline/
│       └── reading_list.json
├── services/                    # Python scrapers
│   ├── common/                  # Shared utilities (Notion client, secrets)
│   ├── events/                  # Bandsintown, Quicket, Webtickets, Google Calendar
│   ├── media/                   # TMDB/RAWG watchlist enrichment
│   ├── one_piece/               # 4 store scrapers + card matching + notifications
│   ├── release_radar/           # Pahe, TMDB upcoming, RAWG games, IMAX
│   ├── youtube/                 # Channel scrapers
│   ├── daily_digest/            # Email digest
│   └── scrape_*.py              # Module-level entry points
├── cloudflare-state-worker/     # Cloudflare Worker for state persistence
├── tests/
├── env.py                       # Non-secret config constants
├── secrets.env.example          # Template for required secrets
├── requirements.txt
└── run_local_dashboard_update.py
```

---

## Local setup

**Prerequisites:** Python 3.11+

```powershell
git clone <repo-url>
cd my-dashboard

python -m venv .venv
.\.venv\Scripts\Activate.ps1       # Windows
# source .venv/bin/activate        # Linux / macOS

pip install -r requirements.txt

cp secrets.env.example secrets.env
# fill in your API keys

python -m http.server 8080
# open http://localhost:8080/docs/
```

The repo ships with pre-populated demo data so you can browse the dashboard straight away.

---

## Running scrapers locally

```powershell
python run_local_dashboard_update.py all

# or individual modules
python run_local_dashboard_update.py news
python run_local_dashboard_update.py media
python run_local_dashboard_update.py events
python run_local_dashboard_update.py releases
python run_local_dashboard_update.py youtube
python run_local_dashboard_update.py reading
```

Wrappers support `--hard`, `--source`, `--limit`, and `--max-pages` flags - see the service scripts for details.

---

## Secrets

Secrets are read from environment variables or a local `secrets.env` file (git-ignored). Copy `secrets.env.example` to get started:

| Variable | Used by |
|---|---|
| `NOTION_TOKEN` | Media watchlist, games, reading list, specials |
| `TMDB_BEARER_TOKEN` / `TMDB_API_KEY` | Movie/TV metadata and IMAX showtimes |
| `RAWG_API_KEY` | Game library and release radar |
| `GOOGLE_API_KEY` | Google Calendar events |
| `GOOGLE_PLACES_API_KEY` | Venue geocoding |
| `GOOGLE_CALENDAR_IDS` | Comma-separated calendar IDs to sync |
| `SCRAPE_OP_MISSING_CARDS_DRIVE_URL` | Google Drive link for the One Piece missing-card list |
| `SMTP_*` / `EMAIL_*` | Email notifications (daily digest, card alerts) |

In CI these are stored as GitHub repository secrets.

---

## Automation

**Daily (4am UTC):** news, media, events, release radar, YouTube, reading list, daily digest email.

**Hourly:** One Piece card scrapers across all configured stores. Sends an email alert if new stock appears for cards on the missing list below the configured price threshold.

Both workflows commit updated data back to the repo so the site stays current.

---

## Cloudflare Worker (optional)

The `cloudflare-state-worker/` directory contains a Cloudflare Worker that persists dashboard UI state (active tab, filters) in Cloudflare KV, so your position is remembered across page reloads.

See [`docs/cloudflare-state-setup.md`](docs/cloudflare-state-setup.md) for setup instructions.
