"""硬體規格資料庫：馬達與減速機預設型錄。

注意：以下皆為「代表性示意規格」，用於設計階段的相對比較，
非任何原廠 datasheet 數值。實際選型時請以原廠規格替換（前端可自訂覆寫）。
"""

# 馬達型錄
# rated_torque / peak_torque: Nm（馬達軸端）
# rated_speed_rpm: 額定轉速
# mass: kg（含外殼）
# rotor_inertia: kg·m²（轉子慣量，經減速比平方反映到關節端 → MJCF armature）
# efficiency: 電機效率（電→機械）
MOTORS = [
    {
        "id": "bldc_s",
        "name": "小型 BLDC (示意)",
        "rated_torque": 0.45,
        "peak_torque": 1.4,
        "rated_speed_rpm": 3200,
        "mass": 0.28,
        "rotor_inertia": 2.0e-5,
        "efficiency": 0.85,
    },
    {
        "id": "bldc_m",
        "name": "中型 BLDC (示意)",
        "rated_torque": 1.2,
        "peak_torque": 3.6,
        "rated_speed_rpm": 3000,
        "mass": 0.52,
        "rotor_inertia": 6.5e-5,
        "efficiency": 0.87,
    },
    {
        "id": "bldc_l",
        "name": "大型 BLDC (示意)",
        "rated_torque": 2.6,
        "peak_torque": 7.5,
        "rated_speed_rpm": 2600,
        "mass": 0.95,
        "rotor_inertia": 1.8e-4,
        "efficiency": 0.88,
    },
    {
        "id": "outrunner_hp",
        "name": "高扭矩外轉子 (示意)",
        "rated_torque": 4.5,
        "peak_torque": 12.0,
        "rated_speed_rpm": 1900,
        "mass": 1.45,
        "rotor_inertia": 4.2e-4,
        "efficiency": 0.86,
    },
    {
        "id": "qdd_m",
        "name": "準直驅模組 QDD-M (示意)",
        "rated_torque": 7.0,
        "peak_torque": 20.0,
        "rated_speed_rpm": 1800,
        "mass": 1.15,
        "rotor_inertia": 4.5e-4,
        "efficiency": 0.88,
    },
    {
        "id": "qdd_l",
        "name": "準直驅模組 QDD-L (示意)",
        "rated_torque": 14.0,
        "peak_torque": 40.0,
        "rated_speed_rpm": 1600,
        "mass": 2.0,
        "rotor_inertia": 1.1e-3,
        "efficiency": 0.88,
    },
]

# 減速機型錄
# ratio: 減速比（關節扭矩 = 馬達扭矩 × ratio × efficiency）
# efficiency: 傳動效率
# rated_torque_out: 輸出端額定扭矩 Nm（超過視為減速機超載）
GEARBOXES = [
    {
        "id": "direct",
        "name": "直驅 (無減速)",
        "type": "direct",
        "ratio": 1.0,
        "efficiency": 1.0,
        "mass": 0.0,
        "rated_torque_out": 999.0,
    },
    {
        "id": "planet_6",
        "name": "行星 6:1 (示意)",
        "type": "planetary",
        "ratio": 6.0,
        "efficiency": 0.95,
        "mass": 0.25,
        "rated_torque_out": 60.0,
    },
    {
        "id": "planet_9",
        "name": "行星 9:1 (示意)",
        "type": "planetary",
        "ratio": 9.0,
        "efficiency": 0.94,
        "mass": 0.32,
        "rated_torque_out": 90.0,
    },
    {
        "id": "cyclo_15",
        "name": "擺線 15:1 (示意)",
        "type": "cycloidal",
        "ratio": 15.0,
        "efficiency": 0.90,
        "mass": 0.55,
        "rated_torque_out": 380.0,
    },
    {
        "id": "harmonic_50",
        "name": "諧波 50:1 (示意)",
        "type": "harmonic",
        "ratio": 50.0,
        "efficiency": 0.75,
        "mass": 0.48,
        "rated_torque_out": 180.0,
    },
    {
        "id": "harmonic_100",
        "name": "諧波 100:1 (示意)",
        "type": "harmonic",
        "ratio": 100.0,
        "efficiency": 0.70,
        "mass": 0.62,
        "rated_torque_out": 280.0,
    },
]


def motor_by_id(mid: str) -> dict:
    for m in MOTORS:
        if m["id"] == mid:
            return m
    raise KeyError(f"unknown motor id: {mid}")


def gearbox_by_id(gid: str) -> dict:
    for g in GEARBOXES:
        if g["id"] == gid:
            return g
    raise KeyError(f"unknown gearbox id: {gid}")
