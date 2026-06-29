# Personal Dashboard

A self-built personal dashboard that aggregates data from 15+ sources into a single interface, kept fresh by automated GitHub Actions pipelines running daily and hourly.

---

## What it does

The dashboard is a single-page web app (`docs/index.html`) that reads from a collection of JSON files updated by Python scrapers on a schedule. Each module is fully independent.

| Module | Description |
|---|---|
| **Media Hub** | Watchlist and game library synced from Notion, automatically enriched with TMDB/RAWG metadata — posters, ratings, genres, trailers, cast, and runtime. Tracks status (currently watching, backlog, history) across movies, series, anime, AAA games, indie games, and co-op titles, with a configurable 5-level opinion rating system |
| **Reading List** | Books and manga tracked via Notion with currently-reading and history-by-year views. Each entry carries an opinion rating, and the full reading history is browsable by year |
| **Events & Venues** | Aggregates live event listings from Bandsintown, Quicket, and Webtickets, combined with a curated venue database. All venues are geocoded via Google Places and Nominatim, with coordinates stored in an incremental location cache. Events are tagged by category (music, art, food, nightlife, etc.) and filterable by genre |
| **Google Calendar** | Syncs upcoming events from multiple Google Calendar IDs, surfacing birthdays, reminders, and personal events alongside the public event feed |
| **One Piece Cards** | Scrapes card availability and pricing across 4 online stores hourly, cross-referencing against a configurable missing-card list. Detects new listings, tracks price history over time, and sends targeted email alerts when cards of interest appear below a price threshold |
| **Release Radar** | Unified view of upcoming and recently released content: movies from TMDB (sorted by release date, filtered by region), new game releases from RAWG, IMAX showtimes enriched with TMDB poster/trailer data, and latest movie releases scraped from a release aggregator |
| **News** | Pulls and ranks articles from 20+ RSS/Atom feeds across 8 categories — Global, South Africa, Cape Town, Games, F1, Entertainment, Climbing, and local Events. An importance scoring system weighs sources and keywords to surface breaking or high-signal stories, with configurable thresholds and per-category age limits. Includes a live F1 Snapshot module with driver standings, constructor standings, race schedule, and race highlights |
| **YouTube** | Tracks latest uploads from configured channels using RSS feeds and yt-dlp, with chapter metadata support and a local channel ID cache. Presents videos grouped by channel series with thumbnails and publish times |
| **Game Hub** | A structured reference hub for tabletop and co-op game sessions — stores module notes, build loadouts, ability breakdowns, and strategy screenshots per campaign. Designed as a quick-reference companion during play sessions, with a manifest-driven layout that makes adding new game modules straightforward |
| **Game Lab** | An embedded sandbox for rapidly prototyping and testing browser-based game ideas. Ships with a few working examples (Snake, a sliding-tile puzzle, a DVD-logo bounce game) that serve as starting templates — new games can be dropped in as self-contained HTML/JS/CSS bundles and are automatically surfaced via a manifest |
| **Timeline** | A chronological photo and memory feed, driven by a date-stamped manifest. New entries are added by dropping images into the photos directory and updating the manifest — no database required |
| **Weather** | 7-day forecast with daily high/low temperatures and weather codes, pulled from the Open-Meteo API and rendered as a compact week-at-a-glance strip |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      GitHub Actions                          │
│   Daily (4am UTC)          Hourly                           │
│   ─────────────────        ───────                          │
│   News, media, events,     One Piece card checks            │
│   release radar, YouTube,  + email notification             │
│   reading list, digest                                      │
└────────────────┬────────────────────────────────────────────┘
                 │  commits JSON to repo
                 ▼
┌─────────────────────────────────────────────────────────────┐
│                  docs/data/  (JSON files)                    │
│  events/   media/   news/   release_radar/   one_piece/     │
│  youtube/  reading_list.json   metadata.json   ...          │
└────────────────┬────────────────────────────────────────────┘
                 │  loaded by browser fetch()
                 ▼
┌─────────────────────────────────────────────────────────────┐
│           docs/index.html + app.js + styles.css             │
│           Static dashboard — served anywhere                 │
│           (GitHub Pages, local HTTP server, etc.)            │
└─────────────────────────────────────────────────────────────┘
                 │  UI state persistence
                 ▼
┌──────────────────────────────────────────────────────────────┐
│         Cloudflare Worker + KV  (optional)                   │
│         Stores active tabs, scroll state across sessions     │
└──────────────────────────────────────────────────────────────┘
```

Key design decisions:
- **CI-driven data pipeline** — scrapers run in GitHub Actions and push updated JSON, keeping the frontend always in sync without a running server
- **Lightweight scraping layer** — all HTTP requests use Python's `urllib.request`, keeping the dependency surface minimal
- **Data as contract** — each module's JSON file is the agreed schema between scraper and UI, making modules fully independent
- **Incremental updates** — scrapers diff against a previous snapshot and only write what changed

---

## Tech stack

**Backend (scraping & automation)**
- Python 3.13
- GitHub Actions — daily + hourly scheduled workflows
- SMTP — email notifications for One Piece card alerts and daily digest

**Frontend**
- HTML5, CSS3, JavaScript
- Hosted on GitHub Pages

**APIs**
- [TMDB](https://www.themoviedb.org/documentation/api) — movie and TV metadata
- [RAWG](https://rawg.io/apidocs) — video game database
- [Notion API](https://developers.notion.com/) — user lists (watchlist, games, reading, specials)
- [Google Calendar API](https://developers.google.com/calendar) — calendar events
- [Google Places API](https://developers.google.com/maps/documentation/places) — venue geocoding
- [Open-Meteo](https://open-meteo.com/) — weather
- [Nominatim](https://nominatim.org/) — fallback geocoding

**Infrastructure**
- GitHub Pages — static hosting
- Cloudflare Workers + KV — optional state persistence

---

## Project layout

```
my-dashboard/
├── docs/                        # Dashboard (served as the site)
│   ├── index.html
│   ├── app.js
│   ├── styles.css
│   └── data/                    # JSON data files read by the dashboard
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
├── tests/                       # Integration and scraper tests
├── env.py                       # Non-secret configuration constants
├── secrets.env.example          # Template for required secrets
├── requirements.txt             # Python dependencies
└── run_local_dashboard_update.py  # Local runner (calls module wrappers)
```

---

## Local setup

**Prerequisites:** Python 3.11+ (3.13 recommended)

```powershell
# 1. Clone the repo
git clone <repo-url>
cd my-dashboard

# 2. Create and activate a virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1       # Windows PowerShell
# source .venv/bin/activate        # Linux / macOS

# 3. Install dependencies
pip install -r requirements.txt

# 4. Copy secrets template and fill in your API keys
cp secrets.env.example secrets.env
# Edit secrets.env with your keys

# 5. Serve the dashboard
python -m http.server 8080
# Open http://localhost:8080/docs/
```

The dashboard ships with pre-populated demo data — you can browse it immediately without running any scrapers.

---

## Running scrapers locally

```powershell
# Run everything
python run_local_dashboard_update.py all

# Run individual modules
python run_local_dashboard_update.py news
python run_local_dashboard_update.py media
python run_local_dashboard_update.py events
python run_local_dashboard_update.py releases
python run_local_dashboard_update.py youtube
python run_local_dashboard_update.py reading
```

Module wrappers support `--hard`, `--source`, `--limit`, and `--max-pages` flags — see the service scripts for details.

---

## Secrets

All secrets are read from environment variables or a local `secrets.env` file (git-ignored). Copy `secrets.env.example` to get started:

| Variable | Used by |
|---|---|
| `NOTION_TOKEN` | Media watchlist, games, reading list, specials |
| `TMDB_BEARER_TOKEN` / `TMDB_API_KEY` | Movie/TV metadata and IMAX showtimes |
| `RAWG_API_KEY` | Game library and release radar |
| `GOOGLE_API_KEY` | Google Calendar events |
| `GOOGLE_PLACES_API_KEY` | Venue geocoding |
| `GOOGLE_CALENDAR_IDS` | Comma-separated calendar IDs to sync |
| `SCRAPE_OP_MISSING_CARDS_DRIVE_URL` | Google Drive link for One Piece missing-card list |
| `SMTP_*` / `EMAIL_*` | Email notifications (daily digest, card alerts) |

In CI, these are stored as GitHub repository secrets and injected as environment variables by the workflow.

---

## Automation

### Daily workflow (4am UTC)

Runs: news, media, events, release radar, YouTube scrapers, reading list, daily digest email.

### Hourly workflow

Runs: One Piece card scrapers across all configured stores. If new stock appears for cards on the missing list and priced below a threshold, an email alert is sent.

Both workflows commit any changed data back to the repo, so the GitHub Pages site is always up to date.

---

## Cloudflare Worker (optional)

The `cloudflare-state-worker/` directory contains a Cloudflare Worker that persists dashboard UI state (active tab, filters) in Cloudflare KV, so your position is remembered across page reloads.

See [`docs/cloudflare-state-setup.md`](docs/cloudflare-state-setup.md) for setup instructions.
