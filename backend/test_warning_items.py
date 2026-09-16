"""meta.warning_items 與 meta.warnings 的一對一契約。

warning_items 是給前端分類與縮短用的結構化版本；它不取代 warnings，
每一條 detail 就是 warnings 裡同一位置的同一條文字。
"""

import json
import re

import pytest

from config_schema import GaitParams, Obstacle, SimRequest, default_robot
from simulator import run_simulation

SEVERITIES = {"blocking", "warning", "caution", "info"}
SCOPES = {"stats", "actuator", "gait", "scene", "stability"}
KNOWN_CODES = {
    "STATS_WINDOW_FULL_FALLBACK",
    "COT_UNAVAILABLE",
    "ACTUATOR_PEAK_OVER_MOTOR_PEAK",
    "ACTUATOR_RMS_OVER_RATED",
    "ACTUATOR_PEAK_OVER_RATED",
    "ACTUATOR_SPEED_OVER_RATED",
    "GEARBOX_PEAK_OVER_RATED",
    "IK_REACH_CLAMPED",
    "OBSTACLE_NOT_PASSABLE",
    "ZMP_UNAVAILABLE",
    "ZMP_SCREEN_NOT_PASSED",
    "ZMP_MARGIN_LOW",
    "RUN_MODE_ZMP_INDICATIVE_ONLY",
}
EMOJI_SEVERITY = {"⛔": "blocking", "⚠️": "warning", "🔶": "caution", "ℹ️": "info"}


def _assert_items_mirror_warnings(out: dict) -> list[dict]:
    meta = out["meta"]
    items = meta["warning_items"]
    assert [item["detail"] for item in items] == meta["warnings"]
    actuator_groups = set(meta["summary"]["groups"])
    for item in items:
        assert set(item) == {
            "code", "severity", "scope", "group", "title", "detail", "value", "limit", "unit",
        }
        assert item["code"] in KNOWN_CODES
        assert re.fullmatch(r"[A-Z0-9_]+", item["code"])
        assert item["severity"] in SEVERITIES
        assert item["scope"] in SCOPES
        assert item["title"] and len(item["title"]) < len(item["detail"])
        # 嚴重度必須與文字開頭的符號一致，前端才能不解析文字就上色。
        leading = item["detail"][:2] if item["detail"].startswith(("⚠️", "ℹ️")) else item["detail"][:1]
        assert EMOJI_SEVERITY[leading] == item["severity"], item
        if item["scope"] == "actuator":
            assert item["group"] in actuator_groups
            assert item["value"] is not None and item["limit"] is not None and item["unit"]
        else:
            assert item["group"] is None
    json.dumps(items, ensure_ascii=False, allow_nan=False)
    return items


@pytest.fixture(scope="module")
def default_walk() -> dict:
    return run_simulation(SimRequest(
        robot=default_robot(),
        gait=GaitParams(speed=1.2, step_length=0.5, duration=3.0),
        obstacles=[],
    ))


def test_warning_items_mirror_warnings_one_to_one(default_walk):
    items = _assert_items_mirror_warnings(default_walk)
    assert items, "the default walk is expected to trip at least one screen"


def test_actuator_items_carry_at_most_one_torque_verdict_per_group(default_walk):
    torque_codes = {
        "ACTUATOR_PEAK_OVER_MOTOR_PEAK", "ACTUATOR_RMS_OVER_RATED", "ACTUATOR_PEAK_OVER_RATED",
    }
    per_group: dict[str, int] = {}
    for item in default_walk["meta"]["warning_items"]:
        if item["code"] in torque_codes:
            per_group[item["group"]] = per_group.get(item["group"], 0) + 1
    assert per_group, "default walk should exceed at least one torque threshold"
    assert all(count == 1 for count in per_group.values()), per_group


def test_actuator_item_values_match_summary_groups(default_walk):
    groups = default_walk["meta"]["summary"]["groups"]
    for item in default_walk["meta"]["warning_items"]:
        if item["scope"] != "actuator":
            continue
        stats = groups[item["group"]]
        expected = {
            "ACTUATOR_PEAK_OVER_MOTOR_PEAK": stats["peak_vs_peak_pct"],
            "ACTUATOR_RMS_OVER_RATED": stats["rms_util_pct"],
            "ACTUATOR_PEAK_OVER_RATED": stats["peak_util_pct"],
            "ACTUATOR_SPEED_OVER_RATED": stats["peak_speed_rpm"],
            "GEARBOX_PEAK_OVER_RATED": stats["gearbox_util_pct"],
        }[item["code"]]
        assert item["value"] == pytest.approx(expected, abs=1.0)
        assert item["value"] > item["limit"] or item["code"] == "ACTUATOR_SPEED_OVER_RATED"


def test_blocked_obstacle_yields_scene_and_stats_items():
    out = run_simulation(SimRequest(
        robot=default_robot(),
        gait=GaitParams(speed=0.7, step_length=0.35, duration=2.0),
        obstacles=[Obstacle(x=0.1, height=0.5, depth=0.3)],
    ))
    items = _assert_items_mirror_warnings(out)
    codes = {item["code"]: item for item in items}
    assert codes["OBSTACLE_NOT_PASSABLE"]["scope"] == "scene"
    assert codes["OBSTACLE_NOT_PASSABLE"]["severity"] == "blocking"
    assert codes["COT_UNAVAILABLE"]["scope"] == "stats"


def test_run_mode_adds_info_item_and_stays_json_safe():
    out = run_simulation(SimRequest(
        robot=default_robot(),
        gait=GaitParams(mode="run", speed=2.6, step_length=0.85, duty=0.38, clearance=0.12, duration=2.0),
        obstacles=[],
    ))
    items = _assert_items_mirror_warnings(out)
    info = [item for item in items if item["code"] == "RUN_MODE_ZMP_INDICATIVE_ONLY"]
    assert len(info) == 1 and info[0]["severity"] == "info"
    json.dumps(out, ensure_ascii=False, allow_nan=False)
