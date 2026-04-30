# Dashboard + Scrapers

This project now has:
- `services/` for scraper/service code
- `dashboard/` for frontend files
- `data/` as the single source of runtime data (no duplicate copies)

## Structure

- [services/events](C:/Users/mjrit/OneDrive/Desktop/one-piece-scraper/services/events): events and specials scrapers
- [services/media](C:/Users/mjrit/OneDrive/Desktop/one-piece-scraper/services/media): media/watchlist scraper
- [services/one_piece](C:/Users/mjrit/OneDrive/Desktop/one-piece-scraper/services/one_piece): One Piece card scraping and change detection
- [services/release_radar](C:/Users/mjrit/OneDrive/Desktop/one-piece-scraper/services/release_radar): release/coming-soon scrapers
- [dashboard/index.html](C:/Users/mjrit/OneDrive/Desktop/one-piece-scraper/dashboard/index.html): dashboard page
- [dashboard/app.js](C:/Users/mjrit/OneDrive/Desktop/one-piece-scraper/dashboard/app.js): dashboard logic
- [dashboard/styles.css](C:/Users/mjrit/OneDrive/Desktop/one-piece-scraper/dashboard/styles.css): dashboard styles
- [data/events](C:/Users/mjrit/OneDrive/Desktop/one-piece-scraper/data/events): events + specials JSON
- [data/media](C:/Users/mjrit/OneDrive/Desktop/one-piece-scraper/data/media): media/watchlist JSON + caches
- [data/one_piece](C:/Users/mjrit/OneDrive/Desktop/one-piece-scraper/data/one_piece): One Piece CSV/JSON
- [data/release_radar](C:/Users/mjrit/OneDrive/Desktop/one-piece-scraper/data/release_radar): release JSON
- [data/metadata.json](C:/Users/mjrit/OneDrive/Desktop/one-piece-scraper/data/metadata.json): last scrape timestamp
- [tests](C:/Users/mjrit/OneDrive/Desktop/one-piece-scraper/tests): manual test scripts

## Config

All configuration is in [env.py](C:/Users/mjrit/OneDrive/Desktop/one-piece-scraper/env.py).
Scrapers import variables directly from that file.

## Run

Run all scraper groups:

```powershell
python run_local_dashboard_update.py all
```

Run one group:

```powershell
python run_local_dashboard_update.py media
python run_local_dashboard_update.py events
python run_local_dashboard_update.py cards
```

Serve dashboard:

```powershell
python -m http.server 8080
```

Open:

`http://localhost:8080/dashboard/`

## Notes

- There is no data mirroring to dashboard anymore.
- Dashboard reads directly from `../data/...` paths.
- `.md` and `.txt` report outputs were removed where unused.
