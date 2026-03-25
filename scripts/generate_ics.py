from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, date, time, timedelta
import re
from pathlib import Path
from typing import Iterable

import ssl
import requests
from requests.adapters import HTTPAdapter

from bs4 import BeautifulSoup
from icalendar import Calendar, Event
from zoneinfo import ZoneInfo


class CustomSSLAdapter(HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        ctx = ssl.create_default_context()
        ctx.set_ciphers("DEFAULT:@SECLEVEL=1")
        kwargs["ssl_context"] = ctx
        return super().init_poolmanager(*args, **kwargs)

session = requests.Session()
session.mount("https://", CustomSSLAdapter())

KST = ZoneInfo("Asia/Seoul")
YEAR = 2026

TEAMS = {
    "GY몬스터즈": "https://www.gameone.kr/club/info/schedule/table?club_idx=41381",
    "GY몬스터즈B": "https://www.gameone.kr/club/info/schedule/table?club_idx=44558",
}

slug_map = {
    "GY몬스터즈": "gymonsters_2026.ics",
    "GY몬스터즈B": "gymonstersB_2026.ics",
}

OUT_DIR = Path("docs")
OUT_DIR.mkdir(exist_ok=True)


@dataclass
class Game:
    league_year: int | None
    league: str | None
    away_team: str
    home_team: str
    game_date: date
    location: str | None
    description: str | None


def fetch_html(url: str) -> str:
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    }
    r = session.get(url, headers=headers, timeout=30)
    r.raise_for_status()
    return r.text


def parse_games(team_name: str, url: str) -> list[Game]:
    html = fetch_html(url)
    soup = BeautifulSoup(html, "lxml")

    rows = soup.select("table.game_table tr")[1:]

    games: list[Game] = []
    for row in rows:
        cols = row.select("td")

        date = cols[0].get_text(strip=True)
        parsed_date = parse_korean_datetime(date)

        league = cols[1].get_text(strip=True)
        location = cols[2].get_text(strip=True)
        
        teams = cols[3].select(".team_name")
        team1 = teams[0].get_text(strip=True)
        team2 = teams[1].get_text(strip=True)

        link = cols[4].select_one("a")["href"]

        # You should refine these based on actual column meanings
        description = f"https://www.gameone.kr/{link}"

        games.append(
            Game(
                league_year=YEAR,
                league=league,
                away_team=team1,
                home_team=team2,
                game_date=parsed_date,                
                location=location,
                description=description,
            )
        )

        games.sort(key=lambda x: x.game_date)
    return games


def make_uid(game: Game) -> str:
    raw = f"{game.away_team} vs {game.home_team}|{game.game_date.isoformat()}|{game.location}"
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
    return f"{digest}@gymonsters-ics"


def add_event(cal: Calendar, game: Game) -> None:
    ev = Event()
    ev.add("uid", make_uid(game))
    ev.add("summary", f"{game.away_team} vs {game.home_team} [{game.league_year} {game.league}]")

    ev.add("dtstart", game.game_date)
    ev.add("dtend", game.game_date+timedelta(hours=2))

    if game.location:
        ev.add("location", game.location)
    if game.description:
        ev.add("description", game.description)

    cal.add_component(ev)


def write_calendar(team_name: str, games: Iterable[Game]) -> None:
    cal = Calendar()
    cal.add("version", "2.0")
    cal.add("prodid", f"-//{team_name} Game Schedule//EN")
    for game in games:
        add_event(cal, game)

    path = OUT_DIR / slug_map[team_name]
    path.write_bytes(cal.to_ical())


def parse_korean_datetime(text: str, year: int = 2026):
    m = re.search(r"(\d{2})월(\d{2})일.*?(\d{2}):(\d{2})", text)
    if not m:
        return None

    month = int(m.group(1))
    day = int(m.group(2))
    hour = int(m.group(3))
    minute = int(m.group(4))

    return datetime(year, month, day, hour, minute)


def main() -> None:
    for team_name, url in TEAMS.items():
        games = parse_games(team_name, url)
        print(f"{team_name} games:", games)

        write_calendar(team_name, games)

    # # simple index stamp for sanity-checking deployments
    # stamp = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S %Z")
    # index_path = OUT_DIR / "index.html"
    # if not index_path.exists():
    #     index_path.write_text("<h1>GameOne ICS</h1>", encoding="utf-8")
    # with index_path.open("a", encoding="utf-8") as f:
    #     f.write(f"\n<!-- updated: {stamp} -->\n")


if __name__ == "__main__":
    main()