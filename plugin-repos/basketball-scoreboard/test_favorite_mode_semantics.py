#!/usr/bin/env python3
"""Check the basketball favorite-only and league-window selection semantics."""

import logging
import sys
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

plugin_dir = Path(__file__).parent
sys.path.insert(0, str(plugin_dir))

import sports  # noqa: E402


def _game(game_id, away, home, days_ago=0, days_out=0, final=False, upcoming=False):
    return {
        "id": game_id,
        "away_abbr": away,
        "home_abbr": home,
        "start_time_utc": datetime.now(timezone.utc) + timedelta(
            days=days_out or -days_ago
        ),
        "is_final": final,
        "is_upcoming": upcoming,
    }


def _make(cls, favorites, favorite_only):
    probe_class = type(
        "SelectionProbe",
        (cls,),
        {
            "_extract_game_details": lambda self, event: dict(event),
            "_fetch_data": lambda self: {"events": []},
        },
    )
    obj = probe_class.__new__(probe_class)
    obj.favorite_teams = favorites
    obj.show_favorite_teams_only = favorite_only
    obj.upcoming_games_to_show = 3
    obj.recent_games_to_show = 3
    obj.other_games_min_quality = "any"
    obj.other_games_divisions = []
    obj._team_rankings_cache = {}
    obj._division_team_ids = {}
    obj._division_loaded_at = 0.0
    obj.logger = logging.getLogger("favorite_mode_semantics")
    return obj


def main():
    failures = []

    upcoming = [
        _game("cha-next", "NYK", "CHA", days_out=1, upcoming=True),
        _game("cha-later", "CHA", "BOS", days_out=2, upcoming=True),
        _game("other-one", "LAL", "DEN", days_out=1, upcoming=True),
        _game("other-two", "MIA", "ORL", days_out=2, upcoming=True),
    ]
    strict_upcoming = _make(sports.SportsUpcoming, ["CHA"], True)
    strict_upcoming = strict_upcoming._select_games_for_display(upcoming, ["CHA"])
    if [game["id"] for game in strict_upcoming] != ["cha-next"]:
        failures.append("strict upcoming mode did not select only the next favorite game")

    league_upcoming = _make(sports.SportsUpcoming, ["CHA"], False)
    league_upcoming = league_upcoming._filtered_or_all(upcoming)
    league_upcoming = sorted(
        league_upcoming, key=lambda game: game["start_time_utc"]
    )
    if [game["id"] for game in league_upcoming] != [
        "cha-next", "other-one", "cha-later", "other-two"
    ]:
        failures.append("league upcoming mode did not retain the full window")

    recent = [
        _game("cha-last", "CHA", "ATL", days_ago=1, final=True),
        _game("cha-older", "CHA", "BKN", days_ago=2, final=True),
        _game("other-final", "LAL", "DEN", days_ago=1, final=True),
    ]
    strict_recent = _make(sports.SportsRecent, ["CHA"], True)
    strict_recent = strict_recent._select_recent_games_for_display(recent, ["CHA"])
    if [game["id"] for game in strict_recent] != ["cha-last"]:
        failures.append("strict recent mode did not select only the latest favorite game")

    if failures:
        for failure in failures:
            print("FAIL:", failure)
        return 1
    print("PASS: strict favorite mode selects one game and league mode retains the window")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
