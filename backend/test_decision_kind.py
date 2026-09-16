"""決策日誌的 kind 欄位：每條 entry 都帶穩定識別，且前端分類表涵蓋後端每個 key。"""

import re
from pathlib import Path

from controller import BalanceController

BACKEND = Path(__file__).parent
FRONTEND_LIVE_VIEW = BACKEND.parent / "frontend" / "src" / "LiveView.tsx"


def _bare_controller() -> BalanceController:
    # decide() 只用 t、_decide_last、decisions；不需要 MuJoCo model。
    controller = object.__new__(BalanceController)
    controller.t = 0.0
    controller._decide_last = {}
    controller.decisions = []
    return controller


def test_decide_records_kind_alongside_text_and_level():
    controller = _bare_controller()
    controller.decide("hip", "🫁 髖策略介入：+10 Nm", "strategy", 1.0)
    controller.t = 0.3
    controller.decide("hip", "🫁 髖策略介入：+12 Nm", "strategy", 1.0)  # 節流：不寫入
    controller.t = 1.5
    controller.decide("fall", "💥 跌倒！", "fall", 0)
    assert controller.decisions == [
        {"t": 0.0, "text": "🫁 髖策略介入：+10 Nm", "level": "strategy", "kind": "hip"},
        {"t": 1.5, "text": "💥 跌倒！", "level": "fall", "kind": "fall"},
    ]


def _backend_decide_keys() -> set[str]:
    keys: set[str] = set()
    for path in BACKEND.glob("*.py"):
        if path.name.startswith("test_"):
            continue
        text = path.read_text(encoding="utf-8")
        keys.update(re.findall(r'\.decide\(\s*"([a-z_]+)"', text))
        keys.update(re.findall(r'"kind":\s*"([a-z_]+)"', text))
    return keys


def _frontend_kind_categories() -> set[str]:
    text = FRONTEND_LIVE_VIEW.read_text(encoding="utf-8")
    block = re.search(r"const KIND_CATEGORY[^{]*\{(.*?)\n\};", text, re.S)
    assert block, "LiveView.tsx must define KIND_CATEGORY"
    return set(re.findall(r"\b([a-z_]+):\s*\"", block.group(1)))


def test_every_backend_decision_kind_has_a_frontend_category():
    backend_keys = _backend_decide_keys()
    assert {"hip", "ankle", "td", "raibert", "fall", "push_cmd", "mode", "reset"} <= backend_keys
    missing = backend_keys - _frontend_kind_categories()
    assert not missing, f"decision kinds without a frontend category: {sorted(missing)}"
