"""人形機器人運動設計模擬器 — API 伺服器。

啟動：python main.py（服務 API 並掛載 frontend/dist 靜態頁面）
"""

import asyncio
import mimetypes
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import ORJSONResponse, JSONResponse
from pydantic import ValidationError

from config_schema import SimRequest, default_robot, GaitParams, LiveInitCommand
from hardware_db import MOTORS, GEARBOXES
from simulator import run_simulation
from live_sim import LiveSession, live_error, validation_error_message
from compare_live import CompareSession
from rl.policy_registry import public_policy_inventory
from run_trace import TRACE_STORE, TraceIntegrityError

try:
    import orjson  # noqa: F401
    ResponseClass = ORJSONResponse
except ImportError:
    ResponseClass = JSONResponse

app = FastAPI(title="Humanoid Motion Design Simulator", default_response_class=ResponseClass)

# 本機開發用，允許 vite dev server 跨源存取
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/defaults")
def get_defaults():
    """預設機器人配置 + 硬體型錄（前端初始化用）。"""
    return {
        "robot": default_robot().model_dump(),
        "gait": GaitParams().model_dump(),
        "motors": MOTORS,
        "gearboxes": GEARBOXES,
    }


@app.post("/api/simulate")
def simulate(req: SimRequest):
    return run_simulation(req)


@app.get("/api/policies")
def policies():
    """回傳 RL artifact inventory；inventory 本身不是 performance evidence。"""
    return public_policy_inventory()


@app.get("/api/traces")
def list_traces(limit: int = Query(default=100, ge=1, le=500)):
    """列出完成的 realized simulation traces；active/tmp artifacts 不可見。"""
    return {
        "schema_version": "DYNAMIC_RUN_TRACE_LIST_V1",
        "evidence_scope": "SOFTWARE_ONLY_MUJOCO_REALIZED_SIMULATION",
        "traces": TRACE_STORE.list_traces(limit=limit),
    }


@app.get("/api/traces/{run_id}")
def get_trace(run_id: str, max_points: int = Query(default=2000, ge=10, le=5000)):
    """驗證 artifact identity 後回傳 bounded decimated analysis series。"""
    try:
        return TRACE_STORE.load_trace(run_id, max_points=max_points)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="trace not found")
    except (TraceIntegrityError, ValueError, KeyError, OSError) as exc:
        raise HTTPException(status_code=409, detail=f"trace integrity failure: {type(exc).__name__}")


@app.websocket("/ws/live")
async def ws_live(ws: WebSocket):
    """即時互動模式：MuJoCo forward contact simulation + 控制器，30fps 串流。

    Client 先送 {"type":"init","robot":RobotConfig,"gait":GaitParams,
    "obstacles":[...]}，之後可隨時送 push/obstacle/mode/speed/pause/step/
    gait/reset 指令（見 live_sim.py）。
    """
    await ws.accept()
    session: LiveSession | None = None
    queue: asyncio.Queue = asyncio.Queue()

    async def reader():
        while True:
            try:
                queue.put_nowait(await ws.receive_json())
            except WebSocketDisconnect:
                queue.put_nowait({"__disconnect__": True})
                return
            except RuntimeError:
                queue.put_nowait({"__disconnect__": True})
                return
            except Exception as exc:
                # JSON decode/type errors are returned to the client; they are not
                # silently swallowed and do not mutate the current session.
                queue.put_nowait({"__invalid_json__": type(exc).__name__})

    task = asyncio.create_task(reader())
    try:
        last = time.perf_counter()
        while True:
            while not queue.empty():
                msg = queue.get_nowait()
                if isinstance(msg, dict) and msg.get("__disconnect__"):
                    raise WebSocketDisconnect()
                if isinstance(msg, dict) and msg.get("__invalid_json__"):
                    await ws.send_json(live_error(
                        "INVALID_COMMAND", f"WebSocket JSON 無法解析：{msg['__invalid_json__']}",
                    ))
                    continue
                if not isinstance(msg, dict):
                    await ws.send_json(live_error("INVALID_COMMAND", "command 必須是 JSON object"))
                    continue
                if msg.get("type") == "init":
                    try:
                        init = LiveInitCommand.model_validate(msg)
                        candidate = await asyncio.to_thread(
                            LiveSession, init.robot, init.gait, init.obstacles,
                        )
                    except ValidationError as exc:
                        await ws.send_json(live_error("INVALID_INIT", validation_error_message(exc)))
                        continue
                    except Exception as exc:
                        await ws.send_json(live_error(
                            "INVALID_INIT", f"session 初始化失敗：{type(exc).__name__}",
                        ))
                        continue
                    # 只有完整建構成功才取代既有 session。
                    session = candidate
                    await ws.send_json(session.scene())
                elif session is None:
                    await ws.send_json(live_error(
                        "INVALID_COMMAND", "尚未完成有效 init，command 未執行",
                    ))
                else:
                    # 模擬計算丟到 thread，避免卡住事件迴圈
                    result = await asyncio.to_thread(session.command, msg)
                    if isinstance(result, dict):
                        await ws.send_json(result)
                    elif result == "scene":
                        await ws.send_json(session.scene())
            now = time.perf_counter()
            wall = now - last
            last = now
            if session is not None:
                await asyncio.to_thread(session.advance, min(wall, 0.1))
                await ws.send_json(session.frame())
            await asyncio.sleep(0.033)
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        task.cancel()


@app.websocket("/ws/compare")
async def ws_compare(ws: WebSocket):
    """三 controller 同輸入、獨立 plant 的 development comparison。"""
    await ws.accept()
    session: CompareSession | None = None
    queue: asyncio.Queue = asyncio.Queue()

    async def reader():
        while True:
            try:
                queue.put_nowait(await ws.receive_json())
            except WebSocketDisconnect:
                queue.put_nowait({"__disconnect__": True})
                return
            except RuntimeError:
                queue.put_nowait({"__disconnect__": True})
                return
            except Exception as exc:
                queue.put_nowait({"__invalid_json__": type(exc).__name__})

    task = asyncio.create_task(reader())
    try:
        last = time.perf_counter()
        while True:
            while not queue.empty():
                msg = queue.get_nowait()
                if isinstance(msg, dict) and msg.get("__disconnect__"):
                    raise WebSocketDisconnect()
                if isinstance(msg, dict) and msg.get("__invalid_json__"):
                    await ws.send_json(live_error(
                        "INVALID_COMPARE_COMMAND",
                        f"WebSocket JSON 無法解析：{msg['__invalid_json__']}",
                    ))
                    continue
                if not isinstance(msg, dict):
                    await ws.send_json(live_error(
                        "INVALID_COMPARE_COMMAND", "command 必須是 JSON object",
                    ))
                    continue
                if msg.get("type") == "init":
                    try:
                        init = LiveInitCommand.model_validate(msg)
                        candidate = await asyncio.to_thread(
                            CompareSession, init.robot, init.gait, init.obstacles,
                        )
                    except ValidationError as exc:
                        await ws.send_json(live_error("INVALID_COMPARE_INIT", validation_error_message(exc)))
                        continue
                    except Exception as exc:
                        await ws.send_json(live_error(
                            "COMPARE_INIT_FAILED",
                            f"三 controller comparison 初始化失敗：{type(exc).__name__}",
                        ))
                        continue
                    session = candidate
                    await ws.send_json(session.scene())
                elif session is None:
                    await ws.send_json(live_error(
                        "INVALID_COMPARE_COMMAND", "尚未完成有效 init，command 未執行",
                    ))
                else:
                    result = await asyncio.to_thread(session.command, msg)
                    if isinstance(result, dict):
                        await ws.send_json(result)
                    elif result == "scene":
                        await ws.send_json(session.scene())
            now = time.perf_counter()
            wall = now - last
            last = now
            if session is not None:
                await asyncio.to_thread(session.advance, min(wall, 0.1))
                await ws.send_json(session.frame())
            await asyncio.sleep(0.033)
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        task.cancel()


@app.post("/api/debug_shot")
async def debug_shot(request: "Request"):
    """開發用：前端 canvas 截圖存檔，方便無頭環境檢視 3D 畫面。"""
    body = await request.body()
    out = Path(__file__).parent / "debug_shot.jpg"
    out.write_bytes(body)
    return {"saved": str(out), "bytes": len(body)}


# Windows 註冊表常把 .js 誤標為 text/plain，導致瀏覽器拒載 ES module
mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("text/css", ".css")

# 掛載編譯後的前端（若存在）
dist = Path(__file__).parent.parent / "frontend" / "dist"
if dist.exists():
    app.mount("/", StaticFiles(directory=str(dist), html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8710)
