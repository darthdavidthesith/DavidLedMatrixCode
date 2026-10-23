"""Regressions for granular scrolling duration and upcoming-card diagnostics."""

import logging
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))

from game_renderer import GameRenderer
from manager import BasketballScoreboardPlugin as Plugin


def plugin_for_scroll(mode_type="upcoming"):
    plugin = Plugin.__new__(Plugin)
    plugin.is_enabled = True
    plugin.logger = logging.getLogger("basketball-scroll-test")
    plugin.config = {"nba": {"dynamic_duration": {"enabled": False}}}
    plugin._current_display_league = None
    plugin._current_display_mode_type = None
    plugin._current_active_display_mode = None
    plugin._display_mode_settings = {"nba": {mode_type: "scroll"}}
    plugin._league_registry = {
        "nba": {"enabled": True, "managers": {mode_type: object()}},
    }
    display = SimpleNamespace(
        scroll_helper=SimpleNamespace(dynamic_duration_enabled=True),
        get_dynamic_duration=lambda: 600,
    )
    plugin._scroll_manager = Mock()
    plugin._scroll_manager.get_scroll_display.return_value = display
    plugin._scroll_manager.is_complete.return_value = False
    plugin._display_scroll_mode = Mock(return_value=True)
    plugin._dynamic_cycle_complete = False
    return plugin


@pytest.mark.parametrize("mode_type", ["recent", "upcoming", "live"])
def test_scroll_context_and_duration_reach_controller(mode_type):
    plugin = plugin_for_scroll(mode_type)
    assert plugin._display_league_mode("nba", mode_type, False)
    assert plugin._current_display_league == "nba"
    assert plugin._current_display_mode_type == mode_type
    assert plugin._current_active_display_mode == f"nba_{mode_type}"
    assert plugin.supports_dynamic_duration()
    assert plugin.get_cycle_duration(f"nba_{mode_type}") == 600
    assert not plugin.is_cycle_complete()
    plugin._scroll_manager.is_complete.return_value = True
    assert plugin.is_cycle_complete()
    plugin._scroll_manager.is_complete.assert_called_with(mode_type)


def test_explicit_scroll_dynamic_opt_out_is_preserved():
    plugin = plugin_for_scroll()
    plugin._display_league_mode("nba", "upcoming", False)
    display = plugin._scroll_manager.get_scroll_display.return_value
    display.scroll_helper.dynamic_duration_enabled = False
    assert not plugin.supports_dynamic_duration()


def test_explicit_mode_duration_still_wins():
    plugin = plugin_for_scroll()
    plugin.config["nba"]["mode_durations"] = {"upcoming_mode_duration": 120}
    plugin._display_league_mode("nba", "upcoming", False)
    assert plugin.get_cycle_duration("nba_upcoming") == 120


def test_switch_mode_does_not_use_another_modes_scroll_state():
    plugin = plugin_for_scroll()
    plugin._current_display_league = "nba"
    plugin._current_display_mode_type = "recent"
    assert not plugin.supports_dynamic_duration()
    plugin._scroll_manager.get_scroll_display.assert_not_called()


def test_upcoming_card_draws_date_time_and_logs_only_three_samples(caplog):
    renderer = GameRenderer(128, 32, {}, custom_logger=logging.getLogger("nba-card-test"))
    renderer._load_and_resize_logo = Mock(
        return_value=Image.new("RGBA", (20, 20), (0, 0, 255, 255))
    )
    draw_text = Mock(wraps=renderer._draw_text_with_outline)
    renderer._draw_text_with_outline = draw_text
    game = {
        "id": "nba-upcoming",
        "league": "nba",
        "away_abbr": "NY",
        "home_abbr": "BOS",
        "game_date": "10/23",
        "game_time": "7:30PM",
        "start_time_utc": "2026-10-23T23:30:00+00:00",
    }
    with caplog.at_level(logging.INFO, logger="nba-card-test"):
        image = renderer.render_game_card(game, "upcoming")
        for _ in range(4):
            renderer.render_game_card(game, "upcoming")
    drawn = {call.args[1]: call.args[2] for call in draw_text.call_args_list}
    assert {"VS", "Oct 23", "7:30PM"} <= drawn.keys()
    for text in ("Oct 23", "7:30PM"):
        x, y = drawn[text]
        assert 0 <= x < image.width
        assert 0 <= y < image.height
    messages = [r.message for r in caplog.records if "[NBA Upcoming Scroll]" in r.message]
    assert len(messages) == 3
    assert "game_date='10/23' game_time='7:30PM'" in messages[0]
    assert "formatted_date='Oct 23' formatted_time='7:30PM'" in messages[0]
