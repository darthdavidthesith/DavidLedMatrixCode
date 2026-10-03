"""Hardware-free tests of installed odds ticker cycle and refresh contracts."""

import ast
import logging
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from src.common.scroll_helper import ScrollHelper


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def methods():
    path = ROOT / "plugin-repos/odds-ticker/manager.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    plugin = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "OddsTickerPlugin")
    names = {"is_cycle_complete", "get_dynamic_duration_cap", "get_display_duration", "_perform_update", "update"}
    selected = [node for node in plugin.body if isinstance(node, ast.FunctionDef) and node.name in names]
    namespace = {"time": time, "logger": logging.getLogger(__name__)}
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(path), "exec"), namespace)
    return namespace


@pytest.mark.parametrize("loop", [False, True])
def test_completion_depends_on_distance_not_elapsed_time(methods, loop):
    helper = ScrollHelper(128, 32)
    helper.total_scroll_width = 20000
    instance = SimpleNamespace(supports_dynamic_duration=lambda: True, scroll_helper=helper,
                               loop=loop, _display_start_time=0, dynamic_duration=720)
    assert methods["is_cycle_complete"](instance) is False
    helper.scroll_complete = True
    assert methods["is_cycle_complete"](instance) is True


def test_fixed_duration_is_preserved(methods):
    instance = SimpleNamespace(supports_dynamic_duration=lambda: False, display_duration=45)
    assert methods["is_cycle_complete"](instance) is True
    assert methods["get_display_duration"](instance) == 45


def test_dynamic_slot_uses_minimum_and_requests_no_cap(methods):
    instance = SimpleNamespace(supports_dynamic_duration=lambda: True, min_duration=30)
    assert methods["get_display_duration"](instance) == 30
    assert methods["get_dynamic_duration_cap"](instance) == float("inf")


@pytest.mark.parametrize("new_width", [20000, 3000])
def test_live_refresh_preserves_distance_and_position(methods, new_width):
    helper = ScrollHelper(128, 32)
    helper.scroll_position = 5000
    helper.total_distance_scrolled = 5000
    helper.total_scroll_width = 20000

    def rebuild():
        helper.reset_scroll()
        helper.total_scroll_width = new_width

    instance = SimpleNamespace(
        _get_current_update_interval=lambda: 60, last_update=0,
        _update_lock=threading.Lock(), _config_generation=0,
        odds_ticker_config={}, loop=True, scroll_helper=helper,
        enabled_leagues=["nfl"], show_favorite_teams_only=False,
        _fetch_upcoming_games=lambda: [{"status_state": "in", "away_team": "A", "home_team": "B"}],
        _create_ticker_image=rebuild, games_data=[],
    )
    methods["_perform_update"](instance, preserve_scroll=True)
    assert helper.scroll_position == min(5000, new_width)
    assert helper.total_distance_scrolled == min(5000, new_width)
    assert helper.scroll_complete is (new_width <= 5000)


def test_controller_update_defers_progress_preserving_refresh(methods):
    display = Mock()
    display.is_currently_scrolling.return_value = True
    instance = SimpleNamespace(is_enabled=True, display_manager=display, _deferred_refresh=Mock())
    methods["update"](instance)
    display.defer_update.assert_called_once_with(instance._deferred_refresh, priority=1)


@pytest.mark.parametrize("plugin_cap,global_cap,expected", [
    (float("inf"), 720, float("inf")),
    (900, 720, 720),
    (None, 720, 720),
])
def test_controller_honors_uncapped_request_without_changing_other_caps(plugin_cap, global_cap, expected):
    path = ROOT / "src/display_controller.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    decision = next(node for node in ast.walk(tree) if isinstance(node, ast.If)
                    and ast.unparse(node.test) == "plugin_cap == float('inf')")
    namespace = {"plugin_cap": plugin_cap, "cap_candidates": [
        cap for cap in (plugin_cap, global_cap) if cap is not None and cap > 0
    ], "DEFAULT_DYNAMIC_DURATION_CAP": 600}
    exec(compile(ast.Module(body=[decision], type_ignores=[]), str(path), "exec"), namespace)
    assert namespace["chosen_cap"] == expected