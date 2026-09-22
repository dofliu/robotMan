"""五個畫面的瀏覽器視覺驗證（PUB-C0 的「browser visual verification + dedicated UI tests」）。

每個測試：實際載入頁面、操作、讀回畫面上的數字與後端 API 對照、以 CDP 取當前幀存檔、
斷言 console 與 page error 為零。跑在 README 的 production 路徑（後端直接供應 build 出的 dist）。

    python3 -X utf8 -m pytest frontend/e2e -p no:cacheprovider -q
"""

from __future__ import annotations

import re
import time

import pytest

from conftest import png_distinct_colors

TABS = ("分析模式", "即時互動", "三機同步比較", "RL 訓練")
CONTROLLERS = ("track", "raibert", "rl")


def _click_tab(page, label: str) -> None:
    page.get_by_role("button", name=label, exact=True).first.click()


def _body(page) -> str:
    return page.inner_text("body")


def _click_button_containing(page, text: str) -> None:
    """以 DOM click 觸發：three.js 每幀重繪時，Playwright 的 actionability 等待會卡住（實測），
    evaluate 不受影響。找不到按鈕就失敗。"""
    found = page.evaluate(
        "(t) => { const b = [...document.querySelectorAll('button')].find(b => b.textContent.includes(t));"
        " if (!b) return false; b.click(); return true; }", text)
    assert found, f"找不到含「{text}」的按鈕"


def _wait_text(page, pattern: str, timeout_s: float = 20.0) -> re.Match:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        m = re.search(pattern, _body(page))
        if m:
            return m
        time.sleep(0.25)
    raise AssertionError(f"畫面上找不到 /{pattern}/；目前內容開頭：{_body(page)[:400]!r}")


# ---------------------------------------------------------------- 1. 分析模式


def test_analysis_view_renders_summary_cards_chart_and_scene(page, api):
    pg, log = page
    _click_tab(pg, "分析模式")
    for label in ("模型總質量", "平均功率（簡化估計）", "CoT（估計）"):
        _wait_text(pg, re.escape(label))
    # 結果要真的算出來：總質量欄位是數字，不是「—」
    m = _wait_text(pg, r"模型總質量\s*\n?\s*([0-9]+\.[0-9])\s*\n?\s*kg")
    assert float(m.group(1)) > 10.0
    for chart_tab in ("關節扭矩", "關節角度", "解析 GRF"):
        assert pg.get_by_role("button", name=chart_tab, exact=True).count() >= 1, f"缺圖表分頁 {chart_tab}"
    deadline = time.time() + 20
    while pg.locator("canvas").count() < 2 and time.time() < deadline:
        time.sleep(0.25)
    assert pg.locator("canvas").count() >= 2, "分析模式應有 3D 場景與圖表兩個 canvas"
    shot = log.screenshot("analysis")
    assert png_distinct_colors(shot) > 50, "分析模式截圖近乎單色，3D 場景或圖表沒有畫出來"
    log.assert_clean()


# ---------------------------------------------------------------- 2. 即時互動（含 Trace 記錄）


def test_live_view_streams_telemetry_and_records_a_trace(page, api):
    pg, log = page
    _click_tab(pg, "即時互動")
    pg.wait_for_selector("[data-testid=intervention-status]", timeout=20_000)
    _wait_text(pg, r"站立平衡")
    t1 = float(_wait_text(pg, r"t = ([0-9]+\.[0-9]{2}) s").group(1))
    time.sleep(1.0)
    t2 = float(_wait_text(pg, r"t = ([0-9]+\.[0-9]{2}) s").group(1))
    assert t2 > t1, f"模擬時間沒有前進：{t1} → {t2}（WebSocket 沒串流）"
    assert "控制器決策日誌" in _body(pg)

    before = {t["run_id"] for t in api("/api/traces")["traces"]}
    _click_button_containing(pg, "Trace 記錄（500 Hz）")   # Disclosure 預設收合
    _wait_text(pg, r"● 開始記錄 Trace")
    _click_button_containing(pg, "● 開始記錄 Trace")
    _wait_text(pg, r"■ 停止並保存 Trace")
    time.sleep(1.5)
    _click_button_containing(pg, "■ 停止並保存 Trace")
    _wait_text(pg, r"run-[0-9a-z\-]+", timeout_s=20.0)
    after = api("/api/traces")["traces"]
    new = [t for t in after if t["run_id"] not in before]
    assert len(new) == 1, f"錄完後 /api/traces 應多一筆，實得 {len(new)}"
    assert new[0]["label"].startswith("live-"), new[0]
    assert new[0]["sample_count"] >= 500, new[0]   # ≥ 1 s @ 500 Hz
    pytest.trace_run_id = new[0]["run_id"]  # type: ignore[attr-defined]
    shot = log.screenshot("live")
    assert png_distinct_colors(shot) > 50
    log.assert_clean()


# ---------------------------------------------------------------- 3. 三機同步比較


def test_compare_view_runs_three_isolated_plants_in_lockstep(page, api):
    pg, log = page
    _click_tab(pg, "三機同步比較")
    for c in CONTROLLERS:
        pg.wait_for_selector(f"[data-testid=compare-canvas-{c}]", timeout=30_000)
    _wait_text(pg, r"DEVELOPMENT_COMPARISON_ONLY", timeout_s=30.0)
    _wait_text(pg, r"相同輸入、三個獨立 plant", timeout_s=30.0)
    pg.get_by_role("button", name="三機開始行走").click()
    time.sleep(2.5)
    skew = _wait_text(pg, r"time skew ([0-9]+\.[0-9]{6}) s", timeout_s=15.0)
    assert float(skew.group(1)) == 0.0, f"三機時間偏移不為零：{skew.group(1)}"
    _wait_text(pg, r"plant sha256:[0-9a-f]{8,}", timeout_s=15.0)
    _wait_text(pg, r"行走|跌倒|停止中", timeout_s=15.0)
    shot = log.screenshot("compare")
    assert png_distinct_colors(shot) > 50
    log.assert_clean()


# ---------------------------------------------------------------- 4. Dynamic Trace


def test_trace_view_lists_and_plots_the_recorded_trace(page, api):
    pg, log = page
    run_id = getattr(pytest, "trace_run_id", None)
    traces = api("/api/traces")["traces"]
    assert traces, "後端沒有任何 trace；test_live_view 應先錄一筆"
    run_id = run_id or traces[0]["run_id"]
    _click_tab(pg, "分析模式")
    _click_tab(pg, "Dynamic Trace")
    pg.wait_for_selector("select", timeout=20_000)
    select = pg.locator("select").first
    options = select.locator("option").all_inner_texts()
    assert len(options) == len(traces), f"下拉選單 {len(options)} 筆，API {len(traces)} 筆"
    select.select_option(value=run_id)
    m = _wait_text(pg, r"([0-9]+) Hz ｜ ([0-9]+) samples", timeout_s=20.0)
    assert m.group(1) == "500"
    listed = next(t for t in traces if t["run_id"] == run_id)
    assert int(m.group(2)) == listed["sample_count"], f"畫面 {m.group(2)} samples，API {listed['sample_count']}"
    assert pg.locator("canvas, svg").count() >= 1, "Dynamic Trace 沒有畫出圖"
    shot = log.screenshot("trace")
    assert png_distinct_colors(shot) > 50
    log.assert_clean()


# ---------------------------------------------------------------- 5. RL 訓練


def test_training_view_lists_every_versioned_profile_read_only(page, api):
    pg, log = page
    _click_tab(pg, "RL 訓練")
    _wait_text(pg, r"NOT PHYSICALLY VALIDATED")
    inventory = api("/api/training/profiles")
    profiles = inventory["profiles"]
    assert len(profiles) >= 1
    # 家族群組是收合的 Disclosure：各群組標頭上的「N 個 profile」加總要等於 API 的總數
    counts = [int(n) for n in re.findall(r"([0-9]+) 個 profile", _body(pg))]
    assert sum(counts) == len(profiles), f"群組標頭加總 {sum(counts)}，API {len(profiles)}"
    # 每個群組切換一次、再切換一次，兩個狀態的內容聯集必須涵蓋每個 profile_id（table 以 title 屬性帶完整 id）
    headers = pg.get_by_role("button", name=re.compile(r"[0-9]+ 個 profile"))
    seen = pg.content()
    for _ in range(2):
        for i in range(headers.count()):
            headers.nth(i).click()
        time.sleep(0.3)
        seen += pg.content()
    missing = [p["profile_id"] for p in profiles if p["profile_id"] not in seen]
    assert not missing, f"頁面上找不到這些 profile：{missing}"
    assert "不會啟動訓練" in _body(pg)
    shot = log.screenshot("training")
    assert png_distinct_colors(shot) > 20
    log.assert_clean()


# ---------------------------------------------------------------- 6. 全站：每個分頁零 console error、favicon 有回應


def test_every_tab_loads_without_console_errors_and_favicon_resolves(page, api, server):
    pg, log = page
    for label in TABS:
        _click_tab(pg, label)
        time.sleep(0.6)
    import urllib.request
    with urllib.request.urlopen(f"{server}/favicon.svg", timeout=10) as resp:
        assert resp.status == 200
        assert "svg" in resp.headers.get("content-type", "")
    log.assert_clean()
