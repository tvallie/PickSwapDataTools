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
    use_playwright: bool = False


# Registry — populated at bottom of file
CURRENT_SOURCES: list[Source] = []
FUTURE_SOURCES:  list[Source] = []
NEWS_URLS: list[str] = []


def fetch_html(url: str, timeout: int = 20) -> str:
    """Fetch raw HTML via requests. Raises on HTTP error."""
    resp = requests.get(url, headers=HEADERS, timeout=timeout)
    resp.raise_for_status()
    return resp.text


def fetch_html_playwright(url: str) -> str:
    """Fetch rendered HTML via headless Chromium. Use for JS-heavy or WAF-protected sites."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent=HEADERS["User-Agent"],
            viewport={"width": 1280, "height": 900},
            locale="en-US",
        )
        page = ctx.new_page()
        page.goto(url, timeout=30000, wait_until="domcontentloaded")
        html = page.content()
        browser.close()
    return html


def scrape_source(source: Source) -> dict:
    """Attempt Python scraping; return result dict with metadata."""
    t0 = time.time()
    try:
        html = fetch_html_playwright(source.url) if source.use_playwright else fetch_html(source.url)
        picks = source.parse_fn(html)
        elapsed = round(time.time() - t0, 1)
        method = "playwright" if source.use_playwright else "python"
        logger.info("[scraper] %-30s OK  (%s)   %.1fs", source.name, method, elapsed)
        return {"source": source.name, "picks": picks, "method": method,
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



def _parse_si_current(html: str) -> list[dict]:
    """Parse SI draft order article — numbered list with optional (via ABBR) trade notes."""
    import re
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer"]):
        tag.decompose()
    lines = [l.strip() for l in soup.get_text(separator="\n").split("\n") if l.strip()]

    picks = []
    current_round = 0
    overall = 0
    for line in lines:
        round_m = re.fullmatch(r"Round\s+(\d+)", line)
        if round_m:
            current_round = int(round_m.group(1))
            continue
        if not current_round:
            continue
        pick_m = re.match(r"^(\d+)\.\s+(.+)$", line)
        if not pick_m:
            continue
        pick_num = int(pick_m.group(1))
        rest = pick_m.group(2).strip()
        # Extract "(via ABBR)" trade note if present
        via_m = re.search(r"\(via\s+([A-Z]{2,3})\)", rest)
        orig_abbr = via_m.group(1) if via_m else None
        team_name = re.sub(r"\s*\(via\s+[A-Z]{2,3}\)", "", rest).strip()
        abbr = _normalize_abbr(team_name)
        original_team = _ABBR_TEAM.get(orig_abbr, team_name) if orig_abbr else team_name
        overall = pick_num
        picks.append({
            "overall":       overall,
            "round":         current_round,
            "pick_in_round": _pick_in_round(overall),
            "team":          team_name,
            "abbr":          abbr,
            "is_comp":       pick_num > current_round * 32,
            "original_team": original_team,
        })

    if not picks:
        raise ValueError("No picks parsed from SI page")
    return picks


# ── Future pick parsers ───────────────────────────────────────────────────────


def _parse_realgm_future(html: str) -> list[dict]:
    """Parse RealGM future picks page — team sections with 'YEAR Xth Round: To ABBR' lines."""
    import re
    import datetime
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer"]):
        tag.decompose()
    lines = [l.strip() for l in soup.get_text(separator="\n").split("\n") if l.strip()]

    this_year = datetime.date.today().year
    picks = []
    current_team_abbr = None

    for line in lines:
        # Team section header: "Arizona Cardinals Draft Picks"
        team_m = re.match(r"^(.+?)\s+Draft Picks$", line)
        if team_m:
            current_team_abbr = _normalize_abbr(team_m.group(1))
            continue

        if not current_team_abbr:
            continue

        # Pick line: "2027 1st Round: To NYJ" or "2027 2nd Round: Own"
        pick_m = re.match(r"^(20\d{2})\s+(\d+)[a-z]+\s+Round:\s+(.+)$", line, re.IGNORECASE)
        if not pick_m:
            continue
        year = int(pick_m.group(1))
        round_ = int(pick_m.group(2))
        status = pick_m.group(3).strip()

        if year <= this_year:
            continue  # only future picks
        if status == "Own":
            continue  # not traded

        # "To ABBR" — this team's pick was traded to another team
        to_m = re.match(r"To\s+([A-Z]{2,3})(?:;|$)", status)
        if to_m:
            picks.append({
                "year":          year,
                "round":         round_,
                "original_abbr": current_team_abbr,
                "current_abbr":  to_m.group(1),
            })

    if not picks:
        raise ValueError("No future picks parsed from RealGM page")
    return picks


# ── Spotrac future picks parser ───────────────────────────────────────────────

def _parse_spotrac_year(html: str, year: int) -> list[dict]:
    """Parse one Spotrac /nfl/draft/picks/_/year/{year} page."""
    soup = BeautifulSoup(html, "html.parser")
    picks = []

    view_table = soup.find("div", id="view-table")
    if not view_table:
        raise ValueError(f"Spotrac {year}: div#view-table not found")

    round_num = 0
    for element in view_table.children:
        if not hasattr(element, "name"):
            continue
        if element.name == "header":
            h2 = element.find("h2")
            if h2:
                text = h2.get_text(strip=True)  # "Round 1", "Round 2", …
                import re as _re
                m = _re.search(r"\d+", text)
                if m:
                    round_num = int(m.group())
        elif element.name == "div" and round_num:
            table = element.find("table")
            if not table:
                continue
            for row in table.find_all("tr"):
                tds = row.find_all("td")
                if len(tds) < 3:
                    continue  # skip header rows

                # Current owner abbreviation — div.d-block inside td[1]
                abbr_div = tds[1].find("div", class_="d-block")
                if not abbr_div:
                    continue
                current_abbr = abbr_div.get_text(strip=True).upper()
                if not current_abbr or len(current_abbr) > 3:
                    continue

                # Trade chain — td[2] text; empty if not traded
                chain_text = tds[2].get_text(strip=True)
                if chain_text:
                    parts = [p.strip() for p in chain_text.split(">")]
                    original_abbr = parts[0].upper() if parts else current_abbr
                else:
                    original_abbr = current_abbr

                picks.append({
                    "year":          year,
                    "round":         round_num,
                    "original_abbr": original_abbr,
                    "current_abbr":  current_abbr,
                })

    if not picks:
        raise ValueError(f"Spotrac {year}: no picks parsed")
    return picks


def _parse_spotrac_future(html: str) -> list[dict]:
    """Parse Spotrac future picks for all relevant future years."""
    import datetime
    this_year = datetime.date.today().year
    future_years = range(this_year + 1, this_year + 3)  # e.g. 2027, 2028

    # html is already fetched for the first year — parse it
    first_year = future_years.start
    picks = _parse_spotrac_year(html, first_year)

    # Fetch remaining years internally
    for year in range(future_years.start + 1, future_years.stop):
        try:
            extra_html = fetch_html(
                f"https://www.spotrac.com/nfl/draft/picks/_/year/{year}"
            )
            picks += _parse_spotrac_year(extra_html, year)
        except Exception as e:
            logger.warning("[spotrac] Failed to fetch year %s: %s", year, e)

    return picks


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
    Source("espn-api",  "https://sports.core.api.espn.com/v2/sports/football/leagues/nfl/seasons/2026/draft/rounds", "current", _parse_espn_api_current,  priority=0),
    Source("tankathon", "https://www.tankathon.com/nfl/full_draft",                                                  "current", _parse_tankathon_current, priority=1),
    Source("si",        "https://www.si.com/nfl/updated-2026-nfl-draft-order-full-list-of-picks-all-seven-rounds",  "current", _parse_si_current,        priority=2, use_playwright=True),
]

FUTURE_SOURCES = [
    Source("spotrac", "https://www.spotrac.com/nfl/draft/picks/_/year/2027",                       "future", _parse_spotrac_future, priority=0),
    Source("realgm",  "https://football.realgm.com/analysis/3656/NFL-Future-Draft-Picks-By-Team", "future", _parse_realgm_future,  priority=1, use_playwright=True),
]

NEWS_URLS = [
    "https://profootballtalk.nbcsports.com",
    "https://www.nfl.com/news",
    "https://www.espn.com/nfl/",
]

# ── prosportstransactions.com helpers ─────────────────────────────────────────

# Nickname (team mascot) → abbreviation map for prosportstransactions.com pages.
# The site uses mascot nicknames in img alt attributes (e.g., "Falcons", "Rams").
_NICKNAME_ABBR: dict[str, str] = {
    "Raiders": "LV",  "Jets": "NYJ",   "Cardinals": "ARI", "Titans": "TEN",
    "Giants": "NYG",  "Browns": "CLE", "Commanders": "WSH","Saints": "NO",
    "Bears": "CHI",   "Patriots": "NE","Jaguars": "JAX",   "Rams": "LAR",
    "Falcons": "ATL", "Panthers": "CAR","Steelers": "PIT",  "Eagles": "PHI",
    "Cowboys": "DAL", "Colts": "IND",  "Bengals": "CIN",   "Dolphins": "MIA",
    "Seahawks": "SEA","Broncos": "DEN","Buccaneers": "TB", "Packers": "GB",
    "Vikings": "MIN", "Chargers": "LAC","Lions": "DET",    "49ers": "SF",
    "Ravens": "BAL",  "Bills": "BUF",  "Chiefs": "KC",     "Texans": "HOU",
}


def _nickname_abbr(nickname: str) -> str:
    """Map a team nickname to an abbreviation. Returns empty string if unknown."""
    return _NICKNAME_ABBR.get(nickname.strip(), "")


def _parse_prosports_trade_rows(html: str, pick_year: int) -> list[dict]:
    """
    Shared parse logic for prosportstransactions.com DraftTrades/Years/<year>.htm.

    Table structure (confirmed via inspection):
      - class="datatable center"
      - Round label rows: <td class="RoundLabel">Round N</td>
      - Trade rows: td[0]=round#, td[1]=current holder (img alt), td[2]=trade info
        td[2] contains: first img alt = previous holder; p.bodyCopySm = trade text
        The pick appears in <strong> within bodyCopySm, date as "on YYYY-MM-DD"

    Returns list of raw trade dicts with keys:
      year, round, overall, pick_in_round, date, from, to
    """
    import re
    soup = BeautifulSoup(html, "html.parser")
    results = []

    table = soup.find("table", {"class": "datatable"})
    if not table:
        logger.warning("[prosports-%s] no datatable found", pick_year)
        return results

    current_round = 0
    for row in table.find_all("tr"):
        # Round label rows
        label_td = row.find("td", class_="RoundLabel")
        if label_td:
            m = re.search(r"Round\s+(\d+)", label_td.get_text())
            if m:
                current_round = int(m.group(1))
            continue

        tds = row.find_all("td")
        if len(tds) < 3 or current_round == 0:
            continue

        # td[2] must have a p.bodyCopySm with a Traded entry about pick_year
        txn_td = tds[2]
        body = txn_td.find("p", class_="bodyCopySm")
        if not body:
            continue
        body_text = body.get_text(strip=True)
        if "Traded" not in body_text:
            continue
        if str(pick_year) not in body_text:
            continue
        # Skip conditional/unconfirmed entries
        if "conditional" in body_text.lower():
            continue

        # Current holder: td[1] first img alt
        to_img = tds[1].find("img")
        if not to_img:
            continue
        to_abbr = _nickname_abbr(to_img.get("alt", ""))
        if not to_abbr:
            continue

        # Previous holder: td[2] first img alt
        from_img = txn_td.find("img")
        if not from_img:
            continue
        from_abbr = _nickname_abbr(from_img.get("alt", ""))
        if not from_abbr or from_abbr == to_abbr:
            continue

        # Date: "on YYYY-MM-DD"
        date_m = re.search(r"on\s+(\d{4}-\d{2}-\d{2})", body_text)
        if not date_m:
            continue
        date_str = date_m.group(1)

        # Overall pick number: "#N-" in the strong tag, or 0 if not yet assigned
        strong = body.find("strong")
        overall = 0
        if strong:
            ovr_m = re.search(r"#(\d+)-", strong.get_text())
            if ovr_m:
                overall = int(ovr_m.group(1))

        results.append({
            "year":          pick_year,
            "round":         current_round,
            "overall":       overall,
            "pick_in_round": _pick_in_round(overall) if overall else 0,
            "date":          date_str,
            "from":          from_abbr,
            "to":            to_abbr,
        })

    logger.info("[prosports-%s] parsed %d trade entries", pick_year, len(results))
    return results


def _parse_prosports_current(html: str) -> list[dict]:
    """Parse prosportstransactions.com DraftTrades/Years/2026.htm.

    Returns list of dicts:
      {"overall": int, "round": int, "pick_in_round": int,
       "date": "YYYY-MM-DD", "from": "ABR", "to": "ABR"}
    """
    raw = _parse_prosports_trade_rows(html, 2026)
    return [
        {
            "overall":       e["overall"],
            "round":         e["round"],
            "pick_in_round": e["pick_in_round"],
            "date":          e["date"],
            "from":          e["from"],
            "to":            e["to"],
        }
        for e in raw
    ]


# ── History source registries ─────────────────────────────────────────────────

CURRENT_HISTORY_SOURCES = [
    Source(
        "prosportstransactions-current",
        "https://prosportstransactions.com/football/DraftTrades/Years/2026.htm",
        "history_current",
        _parse_prosports_current,
        priority=0,
        use_playwright=True,
    ),
]
