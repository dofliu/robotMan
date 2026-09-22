"""Capture-point 對照組控制器：只換兩個法則、其餘逐字沿用 Raibert；harness 專用註冊。"""

import numpy as np
import pytest

import controller_cp
import run_motion_task
from config_schema import GaitParams, default_robot
from controller_cp import GAINS, CapturePointController
from controller_raibert import RaibertController
from live_sim import LiveSession

G = 9.81


def _bare(cls, **attrs):
    """不建 MuJoCo model 的裸控制器；只放法則用到的屬性。"""
    controller = object.__new__(cls)
    controller.T_step = 0.5
    controller.hw = 0.09
    controller.ankle_h = 0.05
    controller.kR = 0.30
    controller.stance_ankle = np.zeros(3)
    controller._cp_dbg = (np.zeros(2), 0.0, 0.0)
    controller.t = 0.0
    controller._decide_last = {}
    controller.decisions = []
    for key, value in attrs.items():
        setattr(controller, key, value)
    return controller


# ---------------------------------------------------------------- 單因子：只覆寫兩個法則


def test_cp_overrides_only_the_placement_rule_the_ankle_rule_and_the_mode_message():
    overridden = {name for name in vars(CapturePointController) if not name.startswith("__")}
    assert overridden == {
        "set_mode", "_dcm_offsets", "_foot_placement", "_placement_note", "_ankle_strategy",
    }
    assert CapturePointController.compute is RaibertController.compute
    assert CapturePointController.update_gait is RaibertController.update_gait


def test_gains_are_the_pre_registered_values():
    assert GAINS == {"k_ankle_nm_per_m": 120.0, "ankle_clip_nm": 35.0, "lateral_spacing_m": None}


# ---------------------------------------------------------------- DCM 偏移解析式


def test_dcm_offsets_follow_the_lipm_closed_form():
    cp = _bare(CapturePointController)
    omega0 = np.sqrt(G / 0.85)
    b_x, b_y = cp._dcm_offsets(0.7, omega0)
    e = np.exp(omega0 * cp.T_step)
    assert b_x == pytest.approx(0.7 * cp.T_step / (e - 1.0))
    assert b_y == pytest.approx(2.0 * cp.hw / (e + 1.0))
    assert cp._dcm_offsets(0.0, omega0)[0] == 0.0        # 零速：前後偏移為零
    assert 0.0 < b_y < cp.hw                              # 側向偏移小於半髖寬


def test_foot_lands_behind_the_capture_point_by_the_forward_offset():
    cp = _bare(CapturePointController)
    omega0 = np.sqrt(G / 0.85)
    pelvis = np.array([1.0, 0.02, 0.85])
    v = np.array([0.6, -0.05, 0.0])
    p = cp._foot_placement(
        pelvis=pelvis, v=v, v_des=0.7, omega0=omega0,
        swing="l", sign_sw=+1.0, hip_sw_y=pelvis[1] + cp.hw, neutral_x=pelvis[0] + v[0] * cp.T_step * 0.5,
    )
    xi = pelvis[:2] + v[:2] / omega0
    b_x, b_y = cp._dcm_offsets(0.7, omega0)
    assert p[0] == pytest.approx(xi[0] - b_x)
    assert p[1] == pytest.approx(xi[1] + b_y)
    assert p[2] == cp.ankle_h


# ---------------------------------------------------------------- 踝策略：CP 誤差而非速度誤差


def test_ankle_torque_is_zero_at_lipm_steady_state_and_opposes_a_leading_capture_point():
    cp = _bare(CapturePointController)
    omega0 = np.sqrt(G / 0.85)
    v_des = 0.7
    cp.stance_ankle = np.array([2.0, 0.0, 0.05])
    # 等速 LIPM：ξ_x − p_stance = v_des/ω0 → 零扭矩
    pelvis = np.array([2.0, 0.0, 0.85])
    v = np.array([v_des, 0.0, 0.0])
    assert cp._ankle_strategy(pelvis=pelvis, v=v, v_des=v_des, omega0=omega0) == pytest.approx(0.0)
    # CP 超前 5 cm → 負扭矩，大小 = k·e，未達飽和
    pelvis_ahead = pelvis + np.array([0.05, 0.0, 0.0])
    tau = cp._ankle_strategy(pelvis=pelvis_ahead, v=v, v_des=v_des, omega0=omega0)
    assert tau == pytest.approx(-GAINS["k_ankle_nm_per_m"] * 0.05)
    # 遠超前 → 飽和在 ±35 N·m
    far = pelvis + np.array([1.0, 0.0, 0.0])
    assert cp._ankle_strategy(pelvis=far, v=v, v_des=v_des, omega0=omega0) == -GAINS["ankle_clip_nm"]


# ---------------------------------------------------------------- Raibert 的 hook 預設值 = 原公式


def test_raibert_hooks_reproduce_the_legacy_formulas():
    rb = _bare(RaibertController)
    omega0 = np.sqrt(G / 0.85)
    pelvis = np.array([1.0, 0.0, 0.85])
    v = np.array([0.5, 0.1, 0.0])
    v_des = 0.7
    hip_sw_y = pelvis[1] + rb.hw
    neutral_x = pelvis[0] + v[0] * rb.T_step * 0.5
    p = rb._foot_placement(
        pelvis=pelvis, v=v, v_des=v_des, omega0=omega0,
        swing="l", sign_sw=+1.0, hip_sw_y=hip_sw_y, neutral_x=neutral_x,
    )
    assert p[0] == pytest.approx(neutral_x + rb.kR * (v[0] - v_des))
    assert p[1] == pytest.approx(hip_sw_y + v[1] * rb.T_step * 0.5 + rb.kR * v[1])
    assert p[2] == rb.ankle_h
    assert rb._ankle_strategy(pelvis=pelvis, v=v, v_des=v_des, omega0=omega0) == pytest.approx(
        float(np.clip(-70.0 * (v[0] - v_des), -35.0, 35.0))
    )
    assert rb._ankle_strategy(pelvis=pelvis, v=np.array([3.0, 0, 0]), v_des=0.0, omega0=omega0) == -35.0


# ---------------------------------------------------------------- 註冊：harness 可用、公開指令拒絕


def test_live_session_switches_to_cp_internally_but_the_public_mode_command_rejects_it():
    session = LiveSession(default_robot(), GaitParams(), [])
    rejected = session.command({"type": "mode", "mode": "stand", "controller": "cp"})
    assert rejected["type"] == "error" and rejected["code"] == "INVALID_COMMAND"
    assert session.walk_controller == "raibert"          # 拒絕時 session 不變

    assert session._switch_controller("cp") is None
    assert session.walk_controller == "cp"
    assert isinstance(session.controller, CapturePointController)
    assert session.controller.decisions[-1]["kind"] == "ctrl_switch"
    assert "Capture-point" in session.controller.decisions[-1]["text"]

    # 內部切換後，不帶 controller 的公開 mode 指令照常可用
    assert session.command({"type": "mode", "mode": "walk"}) is None
    assert session.mode == "walk" and session.controller.state == "WALK"
    assert session.controller.decisions[-1]["kind"] == "mode"
    assert "Capture-point" in session.controller.decisions[-1]["text"]


def test_switch_controller_failure_leaves_the_session_untouched():
    session = LiveSession(default_robot(), GaitParams(), [])
    before = session.controller
    failed = session._switch_controller("no_such_controller")
    assert failed["type"] == "error" and failed["code"] == "CONTROLLER_LOAD_FAILED"
    assert session.controller is before and session.walk_controller == "raibert"


def test_run_motion_task_routes_cp_through_the_internal_switch(monkeypatch):
    calls = []

    class FakeSession:
        walk_controller = "raibert"

        def _switch_controller(self, kind):
            calls.append(("internal", kind))
            return None

        def command(self, msg):
            calls.append(("command", msg["controller"]))
            return None

    fake = FakeSession()
    assert run_motion_task.switch_controller(fake, "cp") is None
    assert run_motion_task.switch_controller(fake, "track") is None
    assert calls == [("internal", "cp"), ("command", "track")]
    assert "cp" in run_motion_task.SINGLE_CONTROLLERS
    assert run_motion_task.HARNESS_ONLY_CONTROLLERS == ("cp",)


def test_cp_is_not_in_compare_live_three_controller_set():
    from compare_live import CONTROLLERS
    assert CONTROLLERS == ("track", "raibert", "rl")
    assert controller_cp.__doc__.startswith("Capture-point")
