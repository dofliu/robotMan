// 與後端 config_schema.py / simulator.py 對應的型別定義

export interface MotorSpec {
  id: string;
  name: string;
  rated_torque: number;
  peak_torque: number;
  rated_speed_rpm: number;
  mass: number;
  rotor_inertia: number;
  efficiency: number;
}

export interface GearSpec {
  id: string;
  name: string;
  type: string;
  ratio: number;
  efficiency: number;
  mass: number;
  rated_torque_out: number;
}

export interface JointActuator {
  motor: MotorSpec;
  gear: GearSpec;
}

export interface RobotDims {
  torso_len: number;
  torso_width: number;
  head_radius: number;
  hip_width: number;
  thigh_len: number;
  shin_len: number;
  foot_len: number;
  foot_height: number;
  upper_arm_len: number;
  forearm_len: number;
}

export interface SegmentMasses {
  trunk: number;
  head: number;
  thigh: number;
  shin: number;
  foot: number;
  upper_arm: number;
  forearm: number;
  payload: number;
}

export interface RobotConfig {
  dims: RobotDims;
  masses: SegmentMasses;
  actuators: Record<string, JointActuator>;
}

export interface GaitParams {
  mode: "walk" | "run";
  speed: number;
  step_length: number;
  duty: number;
  clearance: number;
  arm_swing_deg: number;
  torso_lean_deg: number;
  pelvis_sway: number;
  pelvis_bounce: number;
  crouch: number;
  duration: number;
}

export interface Obstacle {
  x: number;
  depth: number;
  height: number;
  width: number;
}

export interface GeomDef {
  name: string;
  body: number;
  type: "plane" | "sphere" | "capsule" | "box";
  size: number[];
  pos: number[];
  quat: number[];
  rgba: number[];
}

export interface GroupStats {
  peak_tau_joint: number;
  peak_tau_motor: number;
  rms_tau_motor: number;
  p99_5_tau_joint?: number;
  p99_5_tau_motor?: number;
  p99_5_util_pct?: number;
  p99_5_vs_peak_pct?: number;
  p99_5_speed_rpm?: number;
  p99_5_speed_util_pct?: number;
  p99_5_gearbox_util_pct?: number;
  peak_util_pct: number;
  rms_util_pct: number;
  peak_vs_peak_pct: number;
  peak_speed_rpm: number;
  speed_util_pct: number;
  gearbox_util_pct: number;
}

export interface SimSummary {
  total_mass: number;
  actuator_mass: number;
  cycle_time: number;
  cadence_spm: number;
  elapsed_time_s: number;
  distance: number;
  net_displacement: number;
  avg_speed: number;
  energy_J: number;
  avg_power_W: number;
  cot: number | null;
  actuator_stats_window: {
    mode: "steady_window" | "full_window_fallback";
    start_s: number;
    end_s: number;
    n_samples: number;
  };
  zmp_stable_pct: number | null;
  zmp_valid_sample_count?: number;
  zmp_candidate_sample_count?: number;
  zmp_valid_coverage_pct?: number | null;
  min_zmp_margin_cm: number | null;
  p01_zmp_margin_cm?: number | null;
  min_com_margin_cm: number | null;
  stopped_by_obstacle: boolean;
  groups: Record<string, GroupStats>;
}

// 新版後端可逐步補齊這些欄位；全部 optional 以相容既有 response。
export interface SimulationProvenance {
  schema_version?: string;
  run_id?: string;
  scenario_id?: string;
  config_hash?: string;
  result_hash?: string;
  model_hash?: string;
  code_hash?: string | null;
  random_seed?: number | null;
  engine?: string;
  engine_version?: string | null;
  model_version?: string;
  controller?: string;
  controller_version?: string | null;
  policy_version?: string | null;
  metric_set_version?: string;
  code_version?: string | null;
  git_sha?: string | null;
  integrator?: string;
  integrator_applicable?: boolean;
  solver?: string;
  solver_applicable?: boolean;
  configured_model_timestep_s?: number;
  simulation_class?: string;
  assist_enabled?: boolean;
  internal_dt_s?: number;
  output_dt_s?: number;
  analysis_rate_hz?: number;
  output_rate_hz?: number;
  controller_rate_hz?: number | null;
  controller_rate_applicable?: boolean;
  deterministic?: boolean;
  deterministic_content_hash?: string;
  content_hash_algorithm?: string;
  content_hash_scope?: string;
  content_hash_canonicalization?: string;
  content_hash_excluded_fields?: string[];
  evidence_scope?: string;
  calibration_status?: string;
  created_at?: string;
}

export interface SimResult {
  meta: {
    dt: number;
    n_frames: number;
    cycle_time: number;
    joint_names: string[];
    body_names: string[];
    warnings: string[];
    summary: SimSummary;
    provenance?: SimulationProvenance;
  };
  geoms: GeomDef[];
  frames: { time: number[]; xpos: number[][][]; xquat: number[][][] };
  telemetry: {
    q: number[][];
    qd: number[][];
    tau: number[][];
    tau_motor: number[][];
    util: number[][];
    speed_rpm: number[][];
    power: number[][];
  };
  gait: {
    contact_l: number[];
    contact_r: number[];
    grf_l: number[][];
    grf_r: number[][];
    com: number[][];
    zmp: (number[] | null[])[];
  };
  sensor: {
    origin: number[][];
    hits: number[][][];
    dists: number[][];
    detected: number[][];
  };
  stability: {
    zmp_margin: (number | null)[];
    com_margin: (number | null)[];
    polygons: number[][][];
  };
}

export interface Defaults {
  robot: RobotConfig;
  gait: GaitParams;
  motors: MotorSpec[];
  gearboxes: GearSpec[];
}

export interface DynamicTraceSummary {
  duration_s: number;
  distance_m: number;
  average_forward_speed_mps: number;
  final_state: string;
  fell: boolean;
  first_fall_time_s: number | null;
  max_abs_pitch_deg: number;
  max_abs_roll_deg: number;
  positive_mechanical_work_j: number;
  absolute_mechanical_work_j: number;
  tracking_rmse_rad: number[];
  max_saturation_pct: Record<string, number>;
  max_grf_n: { left: number; right: number };
  cop_coverage_pct: number;
  max_contact_count: number;
}

export interface MotionTaskCriterion {
  id: string;
  passed: boolean;
  value: string | number | boolean | number[];
  operator: string;
  limit: string | number | boolean | number[];
  unit: string;
}

export interface MotionTaskEvaluation {
  status: "PASS" | "FAIL" | "CANCELLED";
  criteria: MotionTaskCriterion[];
  evaluated_samples: number;
}

export interface MotionTaskResult {
  task_id: string;
  contract: {
    schema_version: string;
    task_id: string;
    name: string;
    duration_s: number;
    gait: { mode: string; speed: number; step_length: number; duty: number; clearance: number };
    phases: { id: string; start_s: number; end_s: number; mode: string }[];
  };
  phase_events: { phase: string; scheduled_s: number; actual_s: number; mode: string }[];
  evaluation: MotionTaskEvaluation;
}

export interface DynamicTraceListItem {
  run_id: string;
  group_id: string | null;
  controller: string;
  policy_id: string | null;
  sample_count: number;
  summary: DynamicTraceSummary;
  artifact_sha256: string;
  evidence_scope: string;
  label: string;
  completed_at: string;
  source_mode: "live" | "compare";
  task?: MotionTaskResult | null;
}

export interface DynamicTraceManifest {
  schema_version: "DYNAMIC_RUN_TRACE_V1";
  run_id: string;
  group_id: string | null;
  label: string;
  source_mode: "live" | "compare";
  evidence_scope: string;
  controller: string;
  policy_id: string | null;
  sample_count: number;
  summary: DynamicTraceSummary;
  physics_dt_s: number;
  sample_rate_hz: number;
  max_duration_s: number;
  stop_reason: string;
  joint_names: string[];
  group_names: string[];
  gait: GaitParams;
  assist_enabled_at_start: boolean;
  policy_evidence_status: string | null;
  task: MotionTaskResult | null;
}

export interface DynamicTraceDetail {
  manifest: DynamicTraceManifest;
  returned_points: number;
  series: {
    time: number[];
    base_x: number[];
    com: number[][];
    com_vel: number[][];
    pitch_deg: number[];
    roll_deg: number[];
    grf_lr: number[][];
    cop_xy: (number | null)[][];
    positive_power_w: number[];
    absolute_power_w: number[];
    tracking_rmse_rad: number[];
    max_saturation_pct: number[];
    state_code: number[];
    joint_q: number[][];
    joint_q_ref: number[][];
    joint_tau: number[][];
  };
}

// 關節群組中文名稱
export const GROUP_LABELS: Record<string, string> = {
  hip_roll: "髖外展 (roll)",
  hip_pitch: "髖屈伸 (pitch)",
  knee: "膝關節",
  ankle: "踝關節",
  shoulder: "肩關節",
  elbow: "肘關節",
};

export const JOINT_LABELS: Record<string, string> = {
  hip_roll_l: "左髖 roll",
  hip_pitch_l: "左髖 pitch",
  knee_l: "左膝",
  ankle_l: "左踝",
  hip_roll_r: "右髖 roll",
  hip_pitch_r: "右髖 pitch",
  knee_r: "右膝",
  ankle_r: "右踝",
  shoulder_l: "左肩",
  elbow_l: "左肘",
  shoulder_r: "右肩",
  elbow_r: "右肘",
};
