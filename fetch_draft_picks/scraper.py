"""scraper.py — Python scraping with Claude HTML fallback."""
import json
import time
import logging
from dataclasses import dataclass
from typing import Callable

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger("fetch_draft_picks.scraper")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    )
}


@dataclass
class Source:
    name: str
    url: str
    mode: str           # "current" or "future" or "news"
    parse_fn: Callable  # fn(html: str) -> list[dict]
    priority: int = 0   # lower = tried first


# Registry — populated at bottom of file
CURRENT_SOURCES: list[Source] = []
FUTURE_SOURCES:  list[Source] = []
NEWS_URLS: list[str] = []


def fetch_html(url: str, timeout: int = 20) -> str:
    """Fetch raw HTML via requests. Raises on HTTP error."""
    resp = requests.get(url, headers=HEADERS, timeout=timeout)
    resp.raise_for_status()
    return resp.text


def scrape_source(source: Source) -> dict:
    """Attempt Python scraping; return result dict with metadata."""
    t0 = time.time()
    try:
        html = fetch_html(source.url)
        picks = source.parse_fn(html)
        elapsed = round(time.time() - t0, 1)
        logger.info("[scraper] %-30s OK  (python)   %.1fs", source.name, elapsed)
        return {"source": source.name, "picks": picks, "method": "python",
                "elapsed": elapsed, "error": None}
    except Exception as e:
        elapsed = round(time.time() - t0, 1)
        logger.warning("[scraper] %-30s FAIL→fallback  error=%s", source.name, e)
        return {"source": source.name, "picks": None, "method": None,
                "elapsed": elapsed, "error": str(e)}


# ── Team helpers ──────────────────────────────────────────────────────────────

_TEAM_ABBR = {
    "Las Vegas Raiders": "LV", "New York Jets": "NYJ", "Arizona Cardinals": "ARI",
    "Tennessee Titans": "TEN", "New York Giants": "NYG", "Cleveland Browns": "CLE",
    "Washington Commanders": "WSH", "New Orleans Saints": "NO",
    "Chicago Bears": "CHI", "New England Patriots": "NE", "Jacksonville Jaguars": "JAX",
    "Los Angeles Rams": "LAR", "Atlanta Falcons": "ATL", "Carolina Panthers": "CAR",
    "Pittsburgh Steelers": "PIT", "Philadelphia Eagles": "PHI",
    "Dallas Cowboys": "DAL", "Indianapolis Colts": "IND", "Cincinnati Bengals": "CIN",
    "Miami Dolphins": "MIA", "Seattle Seahawks": "SEA", "Denver Broncos": "DEN",
    "Tampa Bay Buccaneers": "TB", "Green Bay Packers": "GB", "Minnesota Vikings": "MIN",
    "Los Angeles Chargers": "LAC", "Detroit Lions": "DET", "San Francisco 49ers": "SF",
    "Baltimore Ravens": "BAL", "Buffalo Bills": "BUF", "Kansas City Chiefs": "KC",
    "Houston Texans": "HOU",
}

# Reverse map: abbr → full name
_ABBR_TEAM = {v: k for k, v in _TEAM_ABBR.items()}

# Tankathon uses lowercase team codes in SVG filenames / CSS classes
_TANKATHON_SLUG = {
    "lv": "LV", "nyj": "NYJ", "ari": "ARI", "ten": "TEN", "nyg": "NYG",
    "cle": "CLE", "wsh": "WSH", "no": "NO", "chi": "CHI", "ne": "NE",
    "jax": "JAX", "lar": "LAR", "atl": "ATL", "car": "CAR", "pit": "PIT",
    "phi": "PHI", "dal": "DAL", "ind": "IND", "cin": "CIN", "mia": "MIA",
    "sea": "SEA", "den": "DEN", "tb": "TB", "gb": "GB", "min": "MIN",
    "lac": "LAC", "det": "DET", "sf": "SF", "bal": "BAL", "buf": "BUF",
    "kc": "KC", "hou": "HOU",
}


def _normalize_abbr(team_name: str) -> str:
    for full, abbr in _TEAM_ABBR.items():
        if full.lower() in team_name.lower() or abbr.lower() == team_name.lower():
            return abbr
    return team_name.upper()[:3]


def _round_for_overall(overall: int) -> int:
    thresholds = [32, 64, 96, 128, 160, 192, 224, 999]
    for i, t in enumerate(thresholds, 1):
        if overall <= t:
            return i
    return 7


def _pick_in_round(overall: int) -> int:
    return ((overall - 1) % 32) + 1


# ── Current pick parsers ──────────────────────────────────────────────────────

def _parse_tankathon_current(html: str) -> list[dict]:
    """Parse Tankathon full draft page — div/span layout with SVG team slugs."""
    soup = BeautifulSoup(html, "html.parser")
    picks = []

    # Each pick row is a <tr> inside #draft-board or similar table,
    # or a div with class containing pick number. Inspect both patterns.
    rows = soup.select("tr.pick-row, div.pick-row, div[class*='pick']")

    if not rows:
        # Fallback: look for any table rows with team logo img
        rows = soup.select("table tr")

    overall = 0
    for row in rows:
        # Try to extract team from SVG src slug or img alt
        img = row.find("img")
        if not img:
            continue
        src = img.get("src", "") or img.get("data-src", "")
        alt = img.get("alt", "")

        abbr = None
        # SVG path like ".../nfl/lv.svg" or ".../nfl/500/scoreboard/lv.png"
        for part in src.lower().replace("/", " ").split():
            slug = part.replace(".svg", "").replace(".png", "")
            if slug in _TANKATHON_SLUG:
                abbr = _TANKATHON_SLUG[slug]
                break

        if abbr is None and alt:
            abbr = _normalize_abbr(alt)
        if abbr is None:
            continue

        overall += 1
        team = _ABBR_TEAM.get(abbr, abbr)
        picks.append({
            "overall": overall,
            "round": _round_for_overall(overall),
            "pick_in_round": _pick_in_round(overall),
            "team": team,
            "abbr": abbr,
            "is_comp": False,
            "original_team": team,
        })

    if not picks:
        raise ValueError("No picks parsed from Tankathon current page")
    return picks


def _parse_espn_current(html: str) -> list[dict]:
    raise NotImplementedError("ESPN current: JS-rendered, use Claude fallback")


def _parse_nfldraftbuzz_current(html: str) -> list[dict]:
    raise NotImplementedError("NFLDraftBuzz current: blocked, use Claude fallback")


def _parse_pfr_current(html: str) -> list[dict]:
    """Parse Pro-Football-Reference draft table."""
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", {"id": "drafts"})
    if not table:
        raise ValueError("PFR draft table not found")
    picks = []
    for row in table.select("tbody tr:not(.thead)"):
        cells = row.find_all("td")
        if len(cells) < 4:
            continue
        try:
            overall = int(row.find("td", {"data-stat": "pick_overall"}).get_text(strip=True))
        except (AttributeError, ValueError):
            continue
        team_td = row.find("td", {"data-stat": "team"})
        if not team_td:
            continue
        team_name = team_td.get_text(strip=True)
        abbr = _normalize_abbr(team_name)
        picks.append({
            "overall": overall,
            "round": _round_for_overall(overall),
            "pick_in_round": _pick_in_round(overall),
            "team": team_name,
            "abbr": abbr,
            "is_comp": False,
            "original_team": team_name,
        })
    if not picks:
        raise ValueError("No picks parsed from PFR page")
    return picks


def _parse_nflmockdb_current(html: str) -> list[dict]:
    raise NotImplementedError("NFLMockDB current: JS-rendered, use Claude fallback")


def _parse_si_current(html: str) -> list[dict]:
    raise NotImplementedError("SI current: JS-rendered, use Claude fallback")


def _parse_prosportstrans_current(html: str) -> list[dict]:
    raise NotImplementedError("ProSportsTrans: use Claude fallback")


# ── Future pick parsers ───────────────────────────────────────────────────────

def _parse_tankathon_future(html: str) -> list[dict]:
    """Parse Tankathon future picks page — team-class divs with pick rows."""
    soup = BeautifulSoup(html, "html.parser")
    picks = []

    # Tankathon organizes future picks by current owner (team sections)
    # Each section has a team class like .BUF, .MIA etc. and contains pick rows
    for team_div in soup.select("div[class]"):
        classes = team_div.get("class", [])
        current_abbr = None
        for cls in classes:
            if cls.upper() in _ABBR_TEAM:
                current_abbr = cls.upper()
                break
        if not current_abbr:
            continue

        # Each pick row within the section lists year, round, original team
        for row in team_div.select("div.pick-row, tr.pick-row, div[class*='future']"):
            text = row.get_text(" ", strip=True)
            # Look for patterns like "2027 Round 1" or "Round 2 2027"
            import re
            year_m = re.search(r"20(2[5-9]|3\d)", text)
            round_m = re.search(r"[Rr]ound\s*(\d)", text)
            orig_m = re.search(r"\b([A-Z]{2,3})\b", text)
            if not (year_m and round_m):
                continue
            year = int(year_m.group())
            round_ = int(round_m.group(1))
            orig_abbr = orig_m.group(1) if orig_m else current_abbr
            picks.append({
                "year": year, "round": round_,
                "original_abbr": orig_abbr,
                "current_abbr": current_abbr,
            })

    if not picks:
        raise ValueError("No future picks parsed from Tankathon")
    return picks


def _parse_overthecap_future(html: str) -> list[dict]:
    raise NotImplementedError("OverTheCap future: use Claude fallback")


def _parse_nfltraderumors_future(html: str) -> list[dict]:
    raise NotImplementedError("NFLTradeRumors future: use Claude fallback")


def _parse_realgm_future(html: str) -> list[dict]:
    raise NotImplementedError("RealGM future: use Claude fallback")


# ── ESPN Core API parser ──────────────────────────────────────────────────────

def _parse_espn_api_current(json_text: str) -> list[dict]:
    """Parse ESPN Core API /draft/rounds response — returns all 257 picks with trade info."""
    import re

    data = json.loads(json_text)

    # Build ESPN team-id → {abbr, name} lookup via site API
    try:
        teams_resp = requests.get(
            "https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams?limit=40",
            headers=HEADERS,
            timeout=20,
        )
        teams_resp.raise_for_status()
        team_lookup: dict[str, dict] = {}
        for entry in teams_resp.json()["sports"][0]["leagues"][0]["teams"]:
            t = entry["team"]
            team_lookup[t["id"]] = {"abbr": t["abbreviation"], "name": t["displayName"]}
    except Exception as e:
        raise ValueError(f"ESPN team lookup failed: {e}") from e

    picks = []
    for round_data in data.get("items", []):
        round_num = round_data["number"]
        for pick_data in round_data.get("picks", []):
            team_ref = pick_data.get("team", {}).get("$ref", "")
            m = re.search(r"/teams/(\d+)", team_ref)
            if not m:
                continue
            team_info = team_lookup.get(m.group(1), {"abbr": "UNK", "name": "Unknown"})

            traded     = pick_data.get("traded", False)
            trade_note = pick_data.get("tradeNote", "")

            # Extract original team abbreviation from trade note ("From ATL", "From MIN through JAX")
            original_name = team_info["name"]
            if traded and trade_note:
                orig_m = re.match(r"From\s+([A-Z]{2,3})", trade_note)
                if orig_m:
                    orig_abbr = orig_m.group(1)
                    original_name = _ABBR_TEAM.get(orig_abbr, team_info["name"])

            picks.append({
                "overall":       pick_data["overall"],
                "round":         round_num,
                "pick_in_round": pick_data["pick"],
                "team":          team_info["name"],
                "abbr":          team_info["abbr"],
                "is_comp":       pick_data["pick"] > 32,
                "original_team": original_name,
            })

    if not picks:
        raise ValueError("No picks parsed from ESPN API response")
    return sorted(picks, key=lambda p: p["overall"])


# ── News fetch ────────────────────────────────────────────────────────────────

def _fetch_news_snippets(urls: list[str], max_per_site: int = 5) -> list[str]:
    """Fetch recent headlines from news sites. Returns plaintext snippets."""
    snippets = []
    for url in urls:
        try:
            html = fetch_html(url)
            soup = BeautifulSoup(html, "html.parser")
            for tag in soup.find_all(["h2", "h3"])[:max_per_site]:
                text = tag.get_text(strip=True)
                if text:
                    snippets.append(f"[{url}] {text}")
        except Exception as e:
            logger.warning("[news] Failed to fetch %s: %s", url, e)
    return snippets


def fetch_news_snippets(urls: list[str], max_per_site: int = 5) -> list[str]:
    """Public wrapper — see _fetch_news_snippets."""
    return _fetch_news_snippets(urls, max_per_site)


# ── Claude HTML fallback ──────────────────────────────────────────────────────

_FALLBACK_PROMPT_CURRENT = """\
Extract the 2026 NFL draft pick order from the following webpage text.
Return ONLY a JSON array where each element has:
  overall (int), round (int), pick_in_round (int),
  team (string, full name), abbr (string, 2-3 letter code),
  is_comp (bool), original_team (string, full name before any trade).
Include all picks. If a pick was traded, set original_team to the team that originally owned it.

Webpage text:
{text}
"""

_FALLBACK_PROMPT_FUTURE = """\
Extract future traded NFL draft picks from the following webpage text.
Return ONLY a JSON array where each element has:
  year (int), round (int), original_abbr (string), current_abbr (string).
Only include picks where ownership has changed (traded picks).

Webpage text:
{text}
"""


def _html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    return " ".join(soup.get_text(separator=" ").split())[:12000]


def scrape_with_claude_fallback(source: Source) -> dict:
    """Fetch HTML and use Claude Haiku to extract structured pick data."""
    import anthropic
    t0 = time.time()
    try:
        html = fetch_html(source.url)
        text = _html_to_text(html)
        prompt_template = (
            _FALLBACK_PROMPT_CURRENT if source.mode == "current"
            else _FALLBACK_PROMPT_FUTURE
        )
        prompt = prompt_template.format(text=text)
        client = anthropic.Anthropic()
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=8192,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        picks = json.loads(raw)
        elapsed = round(time.time() - t0, 1)
        logger.info("[scraper] %-30s OK  (claude-haiku)   %.1fs", source.name, elapsed)
        return {"source": source.name, "picks": picks, "method": "claude-haiku",
                "elapsed": elapsed, "error": None}
    except Exception as e:
        elapsed = round(time.time() - t0, 1)
        logger.error("[scraper] %-30s FAIL (claude fallback also failed): %s", source.name, e)
        return {"source": source.name, "picks": None, "method": "claude-haiku",
                "elapsed": elapsed, "error": str(e)}


def scrape_all_sources(sources: list[Source]) -> list[dict]:
    """Scrape all sources; fall back to Claude if Python parsing fails."""
    results = []
    for source in sorted(sources, key=lambda s: s.priority):
        result = scrape_source(source)
        if result["picks"] is None:
            print(f"  Python scraping failed for {source.name}, trying Claude fallback...")
            result = scrape_with_claude_fallback(source)
        results.append(result)
    return results


# ── Source registry ───────────────────────────────────────────────────────────

CURRENT_SOURCES = [
    Source("espn-api",       "https://sports.core.api.espn.com/v2/sports/football/leagues/nfl/seasons/2026/draft/rounds", "current", _parse_espn_api_current,      priority=0),
    Source("tankathon",      "https://www.tankathon.com/nfl/full_draft",                                                  "current", _parse_tankathon_current,     priority=1),
    Source("espn",           "https://www.espn.com/nfl/draft/rounds/_/season/2026",                                      "current", _parse_espn_current,          priority=2),
    Source("nfldraftbuzz",   "https://www.nfldraftbuzz.com/DraftOrder/2026",                                              "current", _parse_nfldraftbuzz_current,  priority=3),
    Source("prosportstrans", "https://prosportstransactions.com/football/DraftTrades/Years/2026.htm",                     "current", _parse_prosportstrans_current, priority=4),
    Source("si",             "https://www.si.com/nfl/updated-2026-nfl-draft-order-full-list-of-picks-all-seven-rounds",  "current", _parse_si_current,             priority=5),
    Source("nflmockdraftdb", "https://www.nflmockdraftdatabase.com/draft-order/2026-nfl-draft-order",                    "current", _parse_nflmockdb_current,     priority=6),
    Source("pro-football-ref", "https://www.pro-football-reference.com/years/2026/draft.htm",                            "current", _parse_pfr_current,           priority=7),
]

FUTURE_SOURCES = [
    Source("overthecap",       "https://overthecap.com/draft",                                          "future", _parse_overthecap_future,    priority=0),
    Source("tankathon-future", "https://www.tankathon.com/picks/future_picks",                          "future", _parse_tankathon_future,     priority=1),
    Source("nfltraderumors",   "https://www.nfltraderumors.co/future-draft-picks",                      "future", _parse_nfltraderumors_future, priority=2),
    Source("realgm",           "https://football.realgm.com/analysis/3656/NFL-Future-Draft-Picks-By-Team", "future", _parse_realgm_future,    priority=3),
]

NEWS_URLS = [
    "https://profootballtalk.nbcsports.com",
    "https://www.nfl.com/news",
    "https://www.espn.com/nfl/",
]
