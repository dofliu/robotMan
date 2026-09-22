"""瀏覽器視覺驗證的共用 fixture：build 前端、起後端（production 路徑：後端直接供應 dist）、開 Chromium。

執行：python3 -X utf8 -m pytest frontend/e2e -p no:cacheprovider -q

fail-closed：缺 Node、build 失敗、後端起不來、Chromium 缺——都是失敗，不是 skip。
（skip-if-absent 是 fail-open，這個專案在 2026-09-19 已經踩過一次。）
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
FRONTEND = REPO / "frontend"
BACKEND = REPO / "backend"
ARTIFACTS = Path(__file__).resolve().parent / "artifacts"
VIEWPORT = {"width": 1440, "height": 1100}


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_http(url: str, timeout_s: float) -> None:
    deadline = time.time() + timeout_s
    last = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:
                if resp.status == 200:
                    return
        except Exception as exc:  # noqa: BLE001 - 等待期間任何錯誤都重試
            last = exc
        time.sleep(0.25)
    raise RuntimeError(f"{url} 在 {timeout_s:.0f} s 內沒有回 200：{last!r}")


@pytest.fixture(scope="session")
def frontend_dist() -> Path:
    """每次都重新 build，驗證的是目前的原始碼，不是上次留下的 dist。"""
    result = subprocess.run(["npm", "run", "build"], cwd=FRONTEND, capture_output=True, text=True, timeout=600)
    assert result.returncode == 0, f"npm run build 失敗：\n{result.stdout[-2000:]}\n{result.stderr[-2000:]}"
    dist = FRONTEND / "dist"
    assert (dist / "index.html").exists(), "build 後沒有 dist/index.html"
    return dist


@pytest.fixture(scope="session")
def server(frontend_dist: Path):
    """以 uvicorn 起 backend/main.py 的 app（與 README 的 production 路徑同一個 app 物件、同樣掛 dist）。"""
    port = _free_port()
    env = {**os.environ, "PYTHONUTF8": "1"}
    proc = subprocess.Popen(
        [sys.executable, "-X", "utf8", "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", str(port),
         "--log-level", "warning"],
        cwd=BACKEND, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    base = f"http://127.0.0.1:{port}"
    try:
        _wait_http(f"{base}/api/defaults", 90.0)
        _wait_http(f"{base}/", 30.0)
    except Exception:
        proc.terminate()
        out = proc.communicate(timeout=10)[0]
        raise RuntimeError(f"後端起不來：\n{out[-3000:]}")
    yield base
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()


@pytest.fixture(scope="session")
def api(server: str):
    def get(path: str):
        with urllib.request.urlopen(f"{server}{path}", timeout=10) as resp:
            assert resp.status == 200, f"{path} -> {resp.status}"
            return json.loads(resp.read().decode("utf-8"))
    return get


CHROMIUM_CANDIDATES = (
    os.environ.get("ROBOTMAN_CHROMIUM", ""),
    "/opt/pw-browsers/chromium",
)


@pytest.fixture(scope="session")
def browser():
    """先用 Playwright 自帶的 Chromium；沒有時退到 ROBOTMAN_CHROMIUM 或 /opt/pw-browsers/chromium。
    兩者都沒有 → 失敗（不是 skip）。"""
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import sync_playwright
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    launch_args = ["--use-gl=swiftshader", "--enable-unsafe-swiftshader"]
    with sync_playwright() as p:
        browser = None
        errors = []
        try:
            browser = p.chromium.launch(headless=True, args=launch_args)
        except PlaywrightError as exc:
            errors.append(f"bundled: {str(exc).splitlines()[0]}")
            for candidate in CHROMIUM_CANDIDATES:
                if candidate and Path(candidate).exists():
                    browser = p.chromium.launch(headless=True, executable_path=candidate, args=launch_args)
                    break
        if browser is None:
            raise RuntimeError("找不到可用的 Chromium：" + "; ".join(errors) +
                               "；請 `playwright install chromium` 或設 ROBOTMAN_CHROMIUM")
        yield browser
        browser.close()


class PageLog:
    """收集 console error 與 page error；每個測試結束時斷言為零。"""

    def __init__(self, page):
        self.page = page
        self.console_errors: list[str] = []
        self.page_errors: list[str] = []
        page.on("console", lambda msg: self.console_errors.append(msg.text) if msg.type == "error" else None)
        page.on("pageerror", lambda err: self.page_errors.append(str(err)))

    def assert_clean(self) -> None:
        assert not self.page_errors, f"page errors: {self.page_errors}"
        assert not self.console_errors, f"console errors: {self.console_errors}"

    def screenshot(self, name: str) -> Path:
        """用 CDP 直接取當前幀；three.js 持續重繪，Playwright 的 screenshot() 會等穩定而逾時。"""
        cdp = self.page.context.new_cdp_session(self.page)
        data = cdp.send("Page.captureScreenshot", {"format": "png"})["data"]
        import base64
        out = ARTIFACTS / f"{name}.png"
        out.write_bytes(base64.b64decode(data))
        return out


@pytest.fixture()
def page(browser, server: str):
    context = browser.new_context(viewport=VIEWPORT, device_scale_factor=1)
    pg = context.new_page()
    log = PageLog(pg)
    pg.goto(server + "/", wait_until="networkidle")
    yield pg, log
    context.close()


def png_distinct_colors(path: Path, sample_every: int = 7) -> int:
    """不靠 PIL：用 Playwright 的瀏覽器算太繞，改讀 PNG 需要解碼——這裡用 zlib+struct 手解 8-bit RGBA。"""
    import struct
    import zlib
    raw = path.read_bytes()
    assert raw[:8] == b"\x89PNG\r\n\x1a\n"
    pos = 8
    width = height = 0
    idat = b""
    color_type = bit_depth = None
    while pos < len(raw):
        length, ctype = struct.unpack(">I4s", raw[pos:pos + 8])
        data = raw[pos + 8:pos + 8 + length]
        pos += 12 + length
        if ctype == b"IHDR":
            width, height, bit_depth, color_type = struct.unpack(">IIBB", data[:10])
        elif ctype == b"IDAT":
            idat += data
        elif ctype == b"IEND":
            break
    assert bit_depth == 8 and color_type in (2, 6), f"unexpected PNG format {bit_depth}/{color_type}"
    bpp = 4 if color_type == 6 else 3
    stride = width * bpp
    decompressed = zlib.decompress(idat)
    prev = bytearray(stride)
    colors: set[bytes] = set()
    off = 0
    for y in range(height):
        filt = decompressed[off]
        line = bytearray(decompressed[off + 1:off + 1 + stride])
        off += 1 + stride
        for x in range(stride):
            a = line[x - bpp] if x >= bpp else 0
            b = prev[x]
            c = prev[x - bpp] if x >= bpp else 0
            if filt == 1:
                line[x] = (line[x] + a) & 255
            elif filt == 2:
                line[x] = (line[x] + b) & 255
            elif filt == 3:
                line[x] = (line[x] + ((a + b) >> 1)) & 255
            elif filt == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                pred = a if pa <= pb and pa <= pc else (b if pb <= pc else c)
                line[x] = (line[x] + pred) & 255
        if y % sample_every == 0:
            for x in range(0, stride, bpp * sample_every):
                colors.add(bytes(line[x:x + 3]))
        prev = line
    return len(colors)
