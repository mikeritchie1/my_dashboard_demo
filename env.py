from __future__ import annotations


CONFIG = {
    "dashboard": {
        "DASHBOARD_TIMEZONE": "Africa/Johannesburg",
        "DASHBOARD_WEATHER_API_URL": "https://api.open-meteo.com/v1/forecast?latitude=-33.9249&longitude=18.4241&daily=weathercode,temperature_2m_max,temperature_2m_min&timezone=Africa%2FJohannesburg&forecast_days=7",
        "DASHBOARD_HOLIDAYS_API_URL_TEMPLATE": "https://date.nager.at/api/v3/publicholidays/{year}/ZA",
    },
    "scraping": {
        "NOTION_SPECIALS_PAGE_URL": "https://www.notion.so/Places-082fa9625a9f4f949d03a8d1517c76f8",
        "NOTION_WATCHLIST_PAGE_ID": "1d757df8191880aeb859c1402a2154c8",
        "NOTION_WATCHLIST_PAGE_URL": "https://www.notion.so/My-Watchlist-1d757df8191880aeb859c1402a2154c8",
        "SCRAPE_NOTION_API_BASE_URL": "https://api.notion.com/v1",
        "SCRAPE_TMDB_API_BASE_URL": "https://api.themoviedb.org/3",
        "SCRAPE_TMDB_IMAGE_BASE_URL": "https://image.tmdb.org/t/p/w342",
        "SCRAPE_TMDB_SITE_MOVIE_BASE_URL": "https://www.themoviedb.org/movie",
        "SCRAPE_TMDB_SITE_TV_BASE_URL": "https://www.themoviedb.org/tv",
        "SCRAPE_YOUTUBE_WATCH_BASE_URL": "https://www.youtube.com/watch?v=",
        "SCRAPE_QUICKET_EVENTS_URL_TEMPLATE": "https://www.quicket.co.za/events/{page}/",
        "SCRAPE_WEBTICKETS_CATEGORY_URL_TEMPLATE": "https://www.webtickets.co.za/v2/category.aspx?itemid=1184162&location=9&when=anytime&page={page}",
        "SCRAPE_WEBTICKETS_PAGE_PREFIX": "https://www.webtickets.co.za/v2/",
        "SCRAPE_NOMINATIM_SEARCH_URL": "https://nominatim.openstreetmap.org/search",
        "SCRAPE_GOOGLE_CALENDAR_API_BASE_URL": "https://www.googleapis.com/calendar/v3",
        "SCRAPE_GOOGLE_PLACES_SEARCH_URL": "https://places.googleapis.com/v1/places:searchText",
        "SCRAPE_RELEASES_SOURCE_URL": "https://pahe.ink/",
        "SCRAPE_TMDB_UPCOMING_API_URL": "https://api.themoviedb.org/3/movie/upcoming",
        "SCRAPE_TMDB_DISCOVER_API_URL": "https://api.themoviedb.org/3/discover/movie",
        "SCRAPE_RAWG_GAMES_API_URL": "https://api.rawg.io/api/games",
        "SCRAPE_RAWG_SITE_GAME_BASE_URL": "https://rawg.io/games",
        "SCRAPE_RELEASES_FETCH_LIMIT": "12",
        "SCRAPE_RELEASES_MAX_ITEMS": "50",
        "SCRAPE_COMING_SOON_FETCH_LIMIT": "50",
        "SCRAPE_COMING_SOON_MAX_ITEMS": "50",
        "SCRAPE_COMING_SOON_WINDOW_DAYS": "90",
        "SCRAPE_COMING_SOON_MAX_PAGES": "3",
        "SCRAPE_COMING_SOON_RELEASE_TYPES": "2|3",
        "SCRAPE_COMING_SOON_REGION": "ZA",
        "SCRAPE_GAME_RELEASES_FETCH_LIMIT": "50",
        "SCRAPE_GAME_RELEASES_MAX_ITEMS": "50",
        "SCRAPE_GAME_RELEASES_WINDOW_DAYS": "90",
        "SCRAPE_GAME_RELEASES_PAST_DAYS": "45",
        "SCRAPE_GAME_RELEASES_MAX_PAGES": "6",
        "SCRAPE_GAME_RELEASES_PLATFORMS": "",
        "SCRAPE_OP_KNIGHTLY_COLLECTION_URL": "https://www.knightlygaming.co.za/collections/one-piece-singles",
        "SCRAPE_OP_MARVELLOUS_COLLECTION_URL": "https://marvelloushobbies.com/one-piece-singles/",
        "SCRAPE_OP_MARVELLOUS_PRODUCTS_URL_TEMPLATE": "https://marvelloushobbies.com/wp-json/wc/store/v1/products?per_page=100&page={page}&category=36",
        "SCRAPE_OP_TANUKI_COLLECTION_URL": "https://tanukitrader.co.za/",
        "SCRAPE_OP_TANUKI_PRODUCTS_URL_TEMPLATE": "https://tanukitrader.co.za/wp-json/wc/store/v1/products?per_page=100&page={page}",
        "SCRAPE_OP_BIG_BANG_COLLECTION_URL": "https://bigbangshop.co.za/collections/one-piece-single-cards",
    },
}


def _flatten(values: dict) -> dict[str, str]:
    out: dict[str, str] = {}
    for value in values.values():
        if isinstance(value, dict):
            out.update(_flatten(value))
    for key, value in values.items():
        if not isinstance(value, dict):
            out[str(key)] = str(value)
    return out


ENV = _flatten(CONFIG)


def get(name: str, default: str = "") -> str:
    value = ENV.get(name, default)
    return str(value).strip()
