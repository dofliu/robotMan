"""API 資料結構定義（pydantic）與預設機器人配置。

所有外部輸入採 fail-closed：拒絕未知欄位、NaN/Inf、非物理負值與超出
目前模型有效範圍的參數，避免讓無效設定一路進入 MJCF 或數值管線。
"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, TypeAdapter, model_validator
from hardware_db import motor_by_id, gearbox_by_id

MAX_OBSTACLES = 100
MIN_PELVIS_CLEARANCE_ABOVE_FOOT_M = 0.02
PushDirectionComponent = Annotated[float, Field(ge=-1.0, le=1.0)]


class ContractModel(BaseModel):
    """P0 輸入契約：未知欄位與非有限浮點數一律拒絕。"""

    # strict=True 防止 bool／numeric string 被靜默轉為物理參數。
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, strict=True)


class MotorSpec(ContractModel):
    id: str = "custom"
    name: str = "自訂馬達"
    rated_torque: float = Field(default=1.2, ge=0.001, le=10_000.0)     # Nm
    peak_torque: float = Field(default=3.6, ge=0.001, le=20_000.0)      # Nm
    rated_speed_rpm: float = Field(default=3000.0, ge=1.0, le=200_000.0)
    mass: float = Field(default=0.5, ge=0.001, le=500.0)                # kg
    rotor_inertia: float = Field(default=6.5e-5, ge=1e-9, le=100.0)    # kg·m²
    efficiency: float = Field(default=0.87, ge=0.01, le=1.0)

    @model_validator(mode="after")
    def peak_must_cover_rated(self):
        if self.peak_torque < self.rated_torque:
            raise ValueError("peak_torque 必須大於或等於 rated_torque")
        return self


class GearSpec(ContractModel):
    id: str = "custom"
    name: str = "自訂減速機"
    type: Literal["direct", "planetary", "cycloidal", "harmonic", "custom"] = "planetary"
    ratio: float = Field(default=9.0, ge=0.1, le=500.0)
    efficiency: float = Field(default=0.94, ge=0.01, le=1.0)
    mass: float = Field(default=0.3, ge=0.0, le=500.0)                  # kg
    rated_torque_out: float = Field(default=45.0, ge=0.001, le=100_000.0)  # Nm


class JointActuator(ContractModel):
    """一個關節群組（左右對稱共用）的致動器配置。"""
    motor: MotorSpec
    gear: GearSpec


class RobotDims(ContractModel):
    """連桿幾何尺寸（m）。"""
    # model_builder 使用 torso_len/2 - 0.05 作 box half-size；0.11 m 是
    # current model 的明確可表示下界，避免零或近零 geom。
    torso_len: float = Field(default=0.42, ge=0.11, le=1.50)
    torso_width: float = Field(default=0.26, ge=0.05, le=1.00)
    head_radius: float = Field(default=0.09, ge=0.03, le=0.30)
    hip_width: float = Field(default=0.20, ge=0.05, le=0.80)           # 兩髖關節間距
    thigh_len: float = Field(default=0.38, ge=0.10, le=1.20)
    shin_len: float = Field(default=0.38, ge=0.10, le=1.20)
    foot_len: float = Field(default=0.22, ge=0.05, le=0.60)
    foot_height: float = Field(default=0.05, ge=0.01, le=0.25)
    upper_arm_len: float = Field(default=0.26, ge=0.05, le=1.00)
    forearm_len: float = Field(default=0.24, ge=0.05, le=1.00)


class SegmentMasses(ContractModel):
    """各結構件重量（kg，不含致動器 — 致動器重量由硬體配置自動加總）。"""
    trunk: float = Field(default=14.0, ge=0.001, le=500.0)
    head: float = Field(default=2.5, ge=0.001, le=100.0)
    thigh: float = Field(default=3.2, ge=0.001, le=200.0)              # 單側
    shin: float = Field(default=2.0, ge=0.001, le=200.0)
    foot: float = Field(default=0.8, ge=0.001, le=100.0)
    upper_arm: float = Field(default=1.2, ge=0.001, le=100.0)
    forearm: float = Field(default=0.9, ge=0.001, le=100.0)
    payload: float = Field(default=0.0, ge=0.0, le=500.0)             # 背負/手持額外負載（加在軀幹）


# 關節群組（左右對稱）：每組指定馬達+減速機
ACTUATOR_GROUPS = ["hip_roll", "hip_pitch", "knee", "ankle", "shoulder", "elbow"]


class RobotConfig(ContractModel):
    dims: RobotDims = Field(default_factory=RobotDims)
    masses: SegmentMasses = Field(default_factory=SegmentMasses)
    actuators: dict[str, JointActuator]

    @model_validator(mode="after")
    def require_exact_actuator_groups(self):
        expected = set(ACTUATOR_GROUPS)
        actual = set(self.actuators)
        if actual != expected:
            missing = sorted(expected - actual)
            extra = sorted(actual - expected)
            raise ValueError(f"actuators 關節群組不完整：missing={missing}, extra={extra}")
        return self


class GaitParams(ContractModel):
    mode: Literal["walk", "run"] = "walk"
    speed: float = Field(default=1.2, ge=0.05, le=10.0)               # m/s（目標前進速度）
    step_length: float = Field(default=0.50, ge=0.02, le=3.0)         # m（單步）
    duty: float = Field(default=0.60, ge=0.25, le=0.85)              # 支撐期占比
    clearance: float = Field(default=0.07, ge=0.0, le=1.0)           # 擺動腳離地高度 m
    arm_swing_deg: float = Field(default=20.0, ge=0.0, le=180.0)
    torso_lean_deg: float = Field(default=3.0, ge=-60.0, le=60.0)
    pelvis_sway: float = Field(default=0.018, ge=0.0, le=0.50)
    pelvis_bounce: float = Field(default=0.012, ge=0.0, le=0.50)
    crouch: float = Field(default=0.10, ge=0.0, le=0.60)
    # API 會保留完整 120 Hz 軌跡與多組遙測；60 s 是 P0 的明確資源上限。
    duration: float = Field(default=8.0, ge=0.25, le=60.0)           # 模擬時長 s

    @model_validator(mode="after")
    def require_numerical_phase_resolution(self):
        """拒絕 planner/120 Hz analysis 無法解析的步態週期。"""
        analysis_dt = 1.0 / 120.0
        planner_grid_dt = 0.020
        step_time = self.step_length / self.speed
        cycle_time = 2.0 * step_time
        stance_samples = self.duty * cycle_time / analysis_dt
        swing_samples = (1.0 - self.duty) * cycle_time / analysis_dt
        if step_time < 5.0 * planner_grid_dt:
            raise ValueError(
                "step_length/speed 造成單步時間低於 0.10 s，20 ms planner grid 無法解析"
            )
        if min(stance_samples, swing_samples) < 4.0:
            raise ValueError(
                "支撐期或擺動期低於 4 個 120 Hz samples，inverse-dynamics analysis 不可解析"
            )
        return self


def validate_robot_gait_compatibility(robot: RobotConfig, gait: GaitParams) -> None:
    """拒絕 nominal pelvis 進入腳掌／地面區域的 Robot×Gait 組合。"""
    d = robot.dims
    lowest_pelvis = (
        d.thigh_len + d.shin_len + d.foot_height - gait.crouch - gait.pelvis_bounce
    )
    required = d.foot_height + MIN_PELVIS_CLEARANCE_ABOVE_FOOT_M
    if lowest_pelvis < required:
        clearance = lowest_pelvis - d.foot_height
        raise ValueError(
            "Robot×Gait 不相容：nominal lowest pelvis 僅高於 foot top "
            f"{clearance:.4g} m；current model 至少需要 "
            f"{MIN_PELVIS_CLEARANCE_ABOVE_FOOT_M:.3g} m"
        )


class Obstacle(ContractModel):
    # x 可為負值，因 live mode 重新錨定後，已通過的障礙物會位於機器人後方。
    x: float = Field(default=3.0, ge=-1000.0, le=1000.0)
    depth: float = Field(default=0.3, ge=0.001, le=20.0)
    # MJCF box half-size=height/2；1 mm 是 current model 可表示下界。
    height: float = Field(default=0.15, ge=0.001, le=10.0)
    width: float = Field(default=1.2, ge=0.001, le=20.0)


class SimRequest(ContractModel):
    robot: RobotConfig
    gait: GaitParams = Field(default_factory=GaitParams)
    obstacles: list[Obstacle] = Field(default_factory=list, max_length=MAX_OBSTACLES)

    @model_validator(mode="after")
    def require_robot_gait_compatibility(self):
        validate_robot_gait_compatibility(self.robot, self.gait)
        return self


# ---------------- WebSocket typed command contracts ----------------

class LiveInitCommand(ContractModel):
    type: Literal["init"]
    robot: RobotConfig
    gait: GaitParams = Field(default_factory=GaitParams)
    obstacles: list[Obstacle] = Field(default_factory=list, max_length=MAX_OBSTACLES)

    @model_validator(mode="after")
    def require_robot_gait_compatibility(self):
        validate_robot_gait_compatibility(self.robot, self.gait)
        return self


class LivePushCommand(ContractModel):
    type: Literal["push"]
    # WebSocket JSON array 解析後是 Python list；明列 list 並鎖定長度，
    # 同時由 ContractModel strict numeric 驗證每個元素。
    dir: list[PushDirectionComponent] = Field(
        default_factory=lambda: [1.0, 0.0, 0.0], min_length=3, max_length=3,
    )
    force: float = Field(default=100.0, ge=0.0, le=1500.0)
    duration: float = Field(default=0.2, ge=0.05, le=1.0)

    @model_validator(mode="after")
    def direction_must_be_nonzero(self):
        if sum(v * v for v in self.dir) <= 1e-12:
            raise ValueError("push dir 不可為零向量")
        return self


class LiveObstacleCommand(ContractModel):
    type: Literal["obstacle"]
    dist: float = Field(default=1.5, ge=0.10, le=20.0)
    height: float = Field(default=0.15, ge=0.05, le=0.50)
    depth: float = Field(default=0.30, ge=0.10, le=1.0)


class LiveModeCommand(ContractModel):
    type: Literal["mode"]
    mode: Literal["stand", "walk"] = "stand"
    controller: Literal["track", "raibert", "rl", "rl_task_v2", "rl_task_v5"] | None = None


class LiveSpeedCommand(ContractModel):
    type: Literal["speed"]
    value: float = Field(default=0.25, ge=0.02, le=1.5)


class LivePauseCommand(ContractModel):
    type: Literal["pause"]
    on: StrictBool = True


class LiveStepCommand(ContractModel):
    type: Literal["step"]
    dt: float = Field(default=0.05, ge=0.002, le=0.5)


class LiveGaitCommand(ContractModel):
    type: Literal["gait"]
    mode: Literal["walk", "run"] | None = None
    speed: float | None = Field(default=None, ge=0.05, le=10.0)
    step_length: float | None = Field(default=None, ge=0.02, le=3.0)
    duty: float | None = Field(default=None, ge=0.25, le=0.85)
    clearance: float | None = Field(default=None, ge=0.0, le=1.0)
    arm_swing_deg: float | None = Field(default=None, ge=0.0, le=180.0)
    torso_lean_deg: float | None = Field(default=None, ge=-60.0, le=60.0)
    pelvis_sway: float | None = Field(default=None, ge=0.0, le=0.50)
    pelvis_bounce: float | None = Field(default=None, ge=0.0, le=0.50)
    crouch: float | None = Field(default=None, ge=0.0, le=0.60)
    duration: float | None = Field(default=None, ge=0.25, le=60.0)


class LiveAssistCommand(ContractModel):
    type: Literal["assist"]
    on: StrictBool = True


class LiveResetCommand(ContractModel):
    type: Literal["reset"]


class LiveRecordStartCommand(ContractModel):
    type: Literal["record_start"]
    label: str = Field(default="", max_length=120)
    max_duration_s: float = Field(default=30.0, ge=1.0, le=60.0)


class LiveRecordStopCommand(ContractModel):
    type: Literal["record_stop"]


class LiveTaskStartCommand(ContractModel):
    type: Literal["task_start"]
    task_id: Literal["stand_start_walk_stop_v1"] = "stand_start_walk_stop_v1"


class LiveTaskCancelCommand(ContractModel):
    type: Literal["task_cancel"]


LiveCommand = Annotated[
    LivePushCommand | LiveObstacleCommand | LiveModeCommand | LiveSpeedCommand
    | LivePauseCommand | LiveStepCommand | LiveGaitCommand | LiveAssistCommand
    | LiveResetCommand | LiveRecordStartCommand | LiveRecordStopCommand
    | LiveTaskStartCommand | LiveTaskCancelCommand,
    Field(discriminator="type"),
]
LIVE_COMMAND_ADAPTER = TypeAdapter(LiveCommand)


def validate_live_command(value) -> LiveCommand:
    """解析並驗證非 init 的 WebSocket 指令。"""
    return LIVE_COMMAND_ADAPTER.validate_python(value)


def _preset(motor_id: str, gear_id: str) -> JointActuator:
    return JointActuator(
        motor=MotorSpec(**motor_by_id(motor_id)),
        gear=GearSpec(**gearbox_by_id(gear_id)),
    )


def default_robot() -> RobotConfig:
    """預設配置：下肢用大馬達+較大減速比，手臂用小馬達。"""
    return RobotConfig(
        actuators={
            "hip_roll": _preset("qdd_m", "cyclo_15"),
            "hip_pitch": _preset("qdd_l", "cyclo_15"),
            "knee": _preset("qdd_m", "cyclo_15"),
            "ankle": _preset("qdd_m", "cyclo_15"),
            "shoulder": _preset("bldc_m", "planet_9"),
            "elbow": _preset("bldc_s", "planet_9"),
        }
    )
