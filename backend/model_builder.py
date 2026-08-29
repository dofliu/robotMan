"""由 RobotConfig 生成 MuJoCo MJCF 模型。

設計要點：
- 分析模式（dynamic=False）：所有 geom 關閉碰撞，採「運動學步態 +
  解析地面反力 + 逆動力學」流程，結果可重現且不會跌倒。
- 互動模式（dynamic=True）：開啟機器人與環境的 MuJoCo simulated contact
  （機器人自身不互碰），每個關節配 torque 致動器；forcerange 使用目前
  representative parameter 算出的 constant torque cap，僅供 SIM-only screening。
- 致動器（馬達+減速機）重量以點質量 geom 放在關節位置，使模型質量
  分布與反射慣量隨設定改變；尚未以 CAD 或 bench data 校準。
- 轉子慣量經減速比平方反映為 joint armature（反射慣量）。
- geom group：機器人=1、地面與障礙物=2，供 raycast 感測器過濾。
"""

import numpy as np
import mujoco
from config_schema import RobotConfig, Obstacle

# 關節順序（qpos 中 freejoint 之後的排列，全系統共用此順序）
JOINT_ORDER = [
    "hip_roll_l", "hip_pitch_l", "knee_l", "ankle_l",
    "hip_roll_r", "hip_pitch_r", "knee_r", "ankle_r",
    "shoulder_l", "elbow_l", "shoulder_r", "elbow_r",
]

# 關節名稱 → 致動器群組（左右共用同一組硬體配置）
JOINT_GROUP = {
    "hip_roll_l": "hip_roll", "hip_roll_r": "hip_roll",
    "hip_pitch_l": "hip_pitch", "hip_pitch_r": "hip_pitch",
    "knee_l": "knee", "knee_r": "knee",
    "ankle_l": "ankle", "ankle_r": "ankle",
    "shoulder_l": "shoulder", "shoulder_r": "shoulder",
    "elbow_l": "elbow", "elbow_r": "elbow",
}


def pelvis_height(cfg: RobotConfig, crouch: float) -> float:
    """站立時骨盆（髖關節）離地高度。"""
    d = cfg.dims
    return d.thigh_len + d.shin_len + d.foot_height - crouch


def joint_peak_torque(cfg: RobotConfig, joint_name: str) -> float:
    """關節端峰值扭矩（馬達峰值 × 減速比 × 傳動效率）。"""
    a = cfg.actuators[JOINT_GROUP[joint_name]]
    return a.motor.peak_torque * a.gear.ratio * a.gear.efficiency


def build_mjcf(cfg: RobotConfig, obstacles: list[Obstacle], dynamic: bool = False) -> str:
    d = cfg.dims
    m = cfg.masses
    act = cfg.actuators

    # 碰撞遮罩：機器人 contype=1/conaffinity=2、環境 contype=2/conaffinity=1
    # → 機器人與環境互碰，但機器人自身不互碰（避免步態中腿部誤觸發散）
    rc = 'contype="1" conaffinity="2"' if dynamic else 'contype="0" conaffinity="0"'
    ec = 'contype="2" conaffinity="1"' if dynamic else 'contype="0" conaffinity="0"'
    # 互動模式用較小的積分步長與較穩定的積分器
    option = ('<option gravity="0 0 -9.81" timestep="0.002" integrator="implicitfast"/>'
              if dynamic else '<option gravity="0 0 -9.81" timestep="0.005"/>')
    leg_dmp = 'damping="1.0"' if dynamic else ''
    arm_dmp = 'damping="0.3"' if dynamic else ''

    def armature(group: str) -> float:
        a = act[group]
        return a.motor.rotor_inertia * a.gear.ratio ** 2

    def act_mass(group: str) -> float:
        a = act[group]
        return a.motor.mass + a.gear.mass

    # 髖部致動器（roll+pitch 兩顆）重量集中在髖關節點
    hip_act = act_mass("hip_roll") + act_mass("hip_pitch")

    sh_y = d.torso_width / 2 + 0.05          # 肩關節側向位置
    sh_z = d.torso_len - 0.03                # 肩關節高度（相對骨盆）
    head_z = d.torso_len + d.head_radius + 0.06
    foot_cx = d.foot_len / 2 - 0.06          # 腳板中心相對踝關節的前移量

    obs_xml = ""
    for i, ob in enumerate(obstacles):
        obs_xml += (
            f'<geom name="obstacle_{i}" type="box" group="2" {ec} '
            f'size="{ob.depth/2} {ob.width/2} {ob.height/2}" '
            f'pos="{ob.x} 0 {ob.height/2}" rgba="0.85 0.45 0.2 1"/>\n'
        )

    def leg(side: str, sign: int) -> str:
        s = side  # "l" / "r"
        return f"""
      <body name="thigh_{s}" pos="0 {sign * d.hip_width / 2} 0">
        <joint name="hip_roll_{s}" axis="1 0 0" armature="{armature('hip_roll')}" {leg_dmp}/>
        <joint name="hip_pitch_{s}" axis="0 -1 0" armature="{armature('hip_pitch')}" {leg_dmp}/>
        <geom name="thigh_{s}" type="capsule" group="1" {rc}
              fromto="0 0 0 0 0 {-d.thigh_len}" size="0.055" mass="{m.thigh}" rgba="0.45 0.52 0.60 1"/>
        <geom name="knee_act_{s}" type="sphere" group="1" {rc}
              size="0.034" pos="0 0 {-d.thigh_len}" mass="{act_mass('knee')}" rgba="0.95 0.55 0.15 1"/>
        <body name="shin_{s}" pos="0 0 {-d.thigh_len}">
          <joint name="knee_{s}" axis="0 1 0" armature="{armature('knee')}" {leg_dmp}/>
          <geom name="shin_{s}" type="capsule" group="1" {rc}
                fromto="0 0 0 0 0 {-d.shin_len}" size="0.042" mass="{m.shin}" rgba="0.55 0.62 0.70 1"/>
          <geom name="ankle_act_{s}" type="sphere" group="1" {rc}
                size="0.030" pos="0 0 {-d.shin_len}" mass="{act_mass('ankle')}" rgba="0.95 0.55 0.15 1"/>
          <body name="foot_{s}" pos="0 0 {-d.shin_len}">
            <joint name="ankle_{s}" axis="0 -1 0" armature="{armature('ankle')}" {leg_dmp}/>
            <geom name="foot_{s}" type="box" group="1" {rc} friction="1.0 0.005 0.0001"
                  size="{d.foot_len/2} 0.045 {d.foot_height/2}"
                  pos="{foot_cx} 0 {-d.foot_height/2}" mass="{m.foot}" rgba="0.25 0.28 0.33 1"/>
            <site name="sole_{s}" pos="{foot_cx} 0 {-d.foot_height}" size="0.01"/>
          </body>
        </body>
      </body>"""

    def arm(side: str, sign: int) -> str:
        s = side
        return f"""
      <body name="uarm_{s}" pos="0 {sign * sh_y} {sh_z}">
        <joint name="shoulder_{s}" axis="0 -1 0" armature="{armature('shoulder')}" {arm_dmp}/>
        <geom name="uarm_{s}" type="capsule" group="1" {rc}
              fromto="0 0 0 0 0 {-d.upper_arm_len}" size="0.038" mass="{m.upper_arm}" rgba="0.45 0.52 0.60 1"/>
        <geom name="elbow_act_{s}" type="sphere" group="1" {rc}
              size="0.026" pos="0 0 {-d.upper_arm_len}" mass="{act_mass('elbow')}" rgba="0.95 0.55 0.15 1"/>
        <body name="farm_{s}" pos="0 0 {-d.upper_arm_len}">
          <joint name="elbow_{s}" axis="0 -1 0" armature="{armature('elbow')}" {arm_dmp}/>
          <geom name="farm_{s}" type="capsule" group="1" {rc}
                fromto="0 0 0 0 0 {-d.forearm_len}" size="0.032" mass="{m.forearm}" rgba="0.55 0.62 0.70 1"/>
        </body>
      </body>"""

    # 互動模式：torque 致動器；出力上限採 D0 representative parameter
    # torque cap，尚未以實體 actuator curve 校準。
    act_xml = ""
    if dynamic:
        lines = []
        for jn in JOINT_ORDER:
            pk = joint_peak_torque(cfg, jn)
            # 不可先 round 到 2 位：低但合法的 representative cap 會變成 0。
            lo, hi = f"{-pk:.12g}", f"{pk:.12g}"
            lines.append(
                f'<motor name="act_{jn}" joint="{jn}" '
                f'ctrlrange="{lo} {hi}" forcerange="{lo} {hi}"/>'
            )
        act_xml = "<actuator>\n" + "\n".join(lines) + "\n</actuator>"

    trunk_extra = m.payload  # 額外負載直接加在軀幹

    xml = f"""
<mujoco model="humanoid_design">
  <compiler angle="radian" autolimits="true"/>
  {option}
  <worldbody>
    <geom name="floor" type="plane" group="2" {ec} friction="1.0 0.005 0.0001"
          size="60 8 0.1" rgba="0.35 0.38 0.42 1"/>
    {obs_xml}
    <body name="trunk" pos="0 0 {pelvis_height(cfg, 0.0)}">
      <freejoint name="root"/>
      <geom name="pelvis" type="box" group="1" {rc}
            size="0.09 {d.hip_width/2 + 0.04} 0.055" pos="0 0 0.01"
            mass="{m.trunk * 0.35}" rgba="0.30 0.34 0.40 1"/>
      <geom name="torso" type="box" group="1" {rc}
            size="0.10 {d.torso_width/2} {d.torso_len/2 - 0.05}" pos="0 0 {d.torso_len/2 + 0.05}"
            mass="{m.trunk * 0.65 + trunk_extra}" rgba="0.62 0.68 0.75 1"/>
      <geom name="head" type="sphere" group="1" {rc}
            size="{d.head_radius}" pos="0.01 0 {head_z}" mass="{m.head}" rgba="0.62 0.68 0.75 1"/>
      <geom name="hip_act_l" type="sphere" group="1" {rc}
            size="0.04" pos="0 {d.hip_width/2} 0" mass="{hip_act}" rgba="0.95 0.55 0.15 1"/>
      <geom name="hip_act_r" type="sphere" group="1" {rc}
            size="0.04" pos="0 {-d.hip_width/2} 0" mass="{hip_act}" rgba="0.95 0.55 0.15 1"/>
      <geom name="sh_act_l" type="sphere" group="1" {rc}
            size="0.03" pos="0 {sh_y} {sh_z}" mass="{act_mass('shoulder')}" rgba="0.95 0.55 0.15 1"/>
      <geom name="sh_act_r" type="sphere" group="1" {rc}
            size="0.03" pos="0 {-sh_y} {sh_z}" mass="{act_mass('shoulder')}" rgba="0.95 0.55 0.15 1"/>
      <site name="lidar" pos="0.10 0 {head_z}" size="0.012"/>
      {leg('l', +1)}
      {leg('r', -1)}
      {arm('l', +1)}
      {arm('r', -1)}
    </body>
  </worldbody>
  {act_xml}
</mujoco>
"""
    return xml


def make_model(cfg: RobotConfig, obstacles: list[Obstacle],
               dynamic: bool = False) -> mujoco.MjModel:
    return mujoco.MjModel.from_xml_string(build_mjcf(cfg, obstacles, dynamic))


def geom_render_list(model: mujoco.MjModel) -> list[dict]:
    """輸出前端渲染所需的 geom 定義（型別/尺寸/相對位姿/顏色/所屬 body）。"""
    type_names = {
        mujoco.mjtGeom.mjGEOM_PLANE: "plane",
        mujoco.mjtGeom.mjGEOM_SPHERE: "sphere",
        mujoco.mjtGeom.mjGEOM_CAPSULE: "capsule",
        mujoco.mjtGeom.mjGEOM_BOX: "box",
    }
    out = []
    for gi in range(model.ngeom):
        gtype = model.geom_type[gi]
        if gtype not in type_names:
            continue
        name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, gi) or f"geom{gi}"
        out.append({
            "name": name,
            "body": int(model.geom_bodyid[gi]),
            "type": type_names[gtype],
            "size": [round(float(s), 4) for s in model.geom_size[gi]],
            "pos": [round(float(p), 4) for p in model.geom_pos[gi]],
            "quat": [round(float(q), 4) for q in model.geom_quat[gi]],
            "rgba": [round(float(c), 3) for c in model.geom_rgba[gi]],
        })
    return out
