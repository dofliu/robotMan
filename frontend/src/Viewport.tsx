import { useEffect, useRef } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import type { SimResult } from "./types";
import type { Playback } from "./playback";

// MuJoCo 為 z-up 座標系，直接把 three 的相機 up 設為 z 軸，
// 資料不需轉換
export default function Viewport({
  result,
  playback,
}: {
  result: SimResult | null;
  playback: Playback;
}) {
  const mountRef = useRef<HTMLDivElement>(null);
  const sceneRef = useRef<{
    renderer: THREE.WebGLRenderer;
    scene: THREE.Scene;
    camera: THREE.PerspectiveCamera;
    controls: OrbitControls;
    robotGroups: THREE.Group[];
    obstacleMeshes: THREE.Mesh[];
    comMarker: THREE.Mesh;
    zmpMarker: THREE.Mesh;
    comTrail: THREE.Line;
    zmpTrail: THREE.Line;
    grfArrows: { l: THREE.ArrowHelper; r: THREE.ArrowHelper };
    rayLines: THREE.LineSegments;
    dynamicRoot: THREE.Group;
    supportLine: THREE.Line;
    comProjLine: THREE.Line;
    comProjDot: THREE.Mesh;
  } | null>(null);
  const resultRef = useRef<SimResult | null>(null);
  resultRef.current = result;

  // ---------- 初始化場景（一次） ----------
  useEffect(() => {
    const mount = mountRef.current!;
    // preserveDrawingBuffer：允許使用者直接截圖 canvas 留存模擬畫面
    const renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
    renderer.setPixelRatio(window.devicePixelRatio);
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    mount.appendChild(renderer.domElement);

    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x14181f);
    scene.fog = new THREE.Fog(0x14181f, 12, 40);

    const camera = new THREE.PerspectiveCamera(45, 1, 0.05, 200);
    camera.up.set(0, 0, 1);
    camera.position.set(-2.2, -2.8, 1.6);

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.target.set(0, 0, 0.8);
    controls.enableDamping = true;

    // 光源
    scene.add(new THREE.HemisphereLight(0xbfd4e6, 0x33404d, 0.9));
    const sun = new THREE.DirectionalLight(0xffffff, 1.6);
    sun.position.set(3, -4, 8);
    sun.castShadow = true;
    sun.shadow.mapSize.set(2048, 2048);
    sun.shadow.camera.left = -6;
    sun.shadow.camera.right = 6;
    sun.shadow.camera.top = 6;
    sun.shadow.camera.bottom = -6;
    scene.add(sun);

    // 地面 + 格線
    const ground = new THREE.Mesh(
      new THREE.PlaneGeometry(200, 30),
      new THREE.MeshStandardMaterial({ color: 0x232a33, roughness: 0.95 })
    );
    ground.receiveShadow = true;
    scene.add(ground);
    const grid = new THREE.GridHelper(200, 200, 0x3a4654, 0x2b333e);
    grid.rotation.x = Math.PI / 2; // GridHelper 預設在 xz 平面（y-up），轉到 xy 平面
    grid.position.z = 0.002;
    scene.add(grid);

    // 動態內容容器（換模型時整批清除）
    const dynamicRoot = new THREE.Group();
    scene.add(dynamicRoot);

    // 標記與軌跡
    const comMarker = new THREE.Mesh(
      new THREE.SphereGeometry(0.03),
      new THREE.MeshBasicMaterial({ color: 0xffd54a })
    );
    const zmpMarker = new THREE.Mesh(
      new THREE.CylinderGeometry(0.035, 0.035, 0.004),
      new THREE.MeshBasicMaterial({ color: 0x4ade80 })
    );
    zmpMarker.rotation.x = Math.PI / 2;
    const comTrail = new THREE.Line(
      new THREE.BufferGeometry(),
      new THREE.LineBasicMaterial({ color: 0xffd54a, transparent: true, opacity: 0.35 })
    );
    const zmpTrail = new THREE.Line(
      new THREE.BufferGeometry(),
      new THREE.LineBasicMaterial({ color: 0x4ade80, transparent: true, opacity: 0.3 })
    );
    scene.add(comMarker, zmpMarker, comTrail, zmpTrail);

    // 地面反力箭頭
    const mkArrow = (color: number) => {
      const a = new THREE.ArrowHelper(
        new THREE.Vector3(0, 0, 1),
        new THREE.Vector3(),
        0.5,
        color,
        0.06,
        0.04
      );
      a.visible = false;
      scene.add(a);
      return a;
    };
    const grfArrows = { l: mkArrow(0xf87171), r: mkArrow(0x60a5fa) };

    // 支撐多邊形（腳掌接觸面凸包）：綠=ZMP 在內、紅=在外
    const polyGeom = new THREE.BufferGeometry();
    polyGeom.setAttribute("position", new THREE.BufferAttribute(new Float32Array(20 * 3), 3));
    const supportLine = new THREE.Line(
      polyGeom,
      new THREE.LineBasicMaterial({ color: 0x4ade80 })
    );
    supportLine.frustumCulled = false;
    scene.add(supportLine);

    // 質心鉛直投影線（黃色虛線感：用細線）
    const comProjGeom = new THREE.BufferGeometry();
    comProjGeom.setAttribute("position", new THREE.BufferAttribute(new Float32Array(2 * 3), 3));
    const comProjLine = new THREE.Line(
      comProjGeom,
      new THREE.LineBasicMaterial({ color: 0xffd54a, transparent: true, opacity: 0.5 })
    );
    comProjLine.frustumCulled = false;
    scene.add(comProjLine);
    const comProjDot = new THREE.Mesh(
      new THREE.RingGeometry(0.02, 0.032, 24),
      new THREE.MeshBasicMaterial({ color: 0xffd54a, side: THREE.DoubleSide })
    );
    comProjDot.position.z = 0.004;
    scene.add(comProjDot);

    // 感測射線
    const rayGeom = new THREE.BufferGeometry();
    rayGeom.setAttribute("position", new THREE.BufferAttribute(new Float32Array(7 * 2 * 3), 3));
    const rayLines = new THREE.LineSegments(
      rayGeom,
      new THREE.LineBasicMaterial({ color: 0x22d3ee, transparent: true, opacity: 0.45 })
    );
    rayLines.frustumCulled = false;
    scene.add(rayLines);

    sceneRef.current = {
      renderer, scene, camera, controls,
      robotGroups: [], obstacleMeshes: [],
      comMarker, zmpMarker, comTrail, zmpTrail, grfArrows, rayLines, dynamicRoot,
      supportLine, comProjLine, comProjDot,
    } as any;

    const resize = () => {
      const w = mount.clientWidth, h = mount.clientHeight;
      renderer.setSize(w, h);
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
    };
    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(mount);

    return () => {
      ro.disconnect();
      renderer.dispose();
      mount.removeChild(renderer.domElement);
      sceneRef.current = null;
    };
  }, []);

  // ---------- 依模擬結果重建機器人與障礙物 ----------
  useEffect(() => {
    const s = sceneRef.current;
    if (!s || !result) return;
    // 清空舊模型
    s.dynamicRoot.clear();
    s.robotGroups = [];
    s.obstacleMeshes = [];

    const nBodies = result.meta.body_names.length;
    for (let b = 0; b < nBodies; b++) {
      const g = new THREE.Group();
      s.dynamicRoot.add(g);
      s.robotGroups.push(g);
    }

    for (const geom of result.geoms) {
      if (geom.type === "plane") continue; // 地面已自建
      let mesh: THREE.Mesh;
      const mat = new THREE.MeshStandardMaterial({
        color: new THREE.Color(geom.rgba[0], geom.rgba[1], geom.rgba[2]),
        roughness: 0.6,
        metalness: 0.25,
      });
      if (geom.type === "box") {
        mesh = new THREE.Mesh(
          new THREE.BoxGeometry(geom.size[0] * 2, geom.size[1] * 2, geom.size[2] * 2),
          mat
        );
      } else if (geom.type === "sphere") {
        mesh = new THREE.Mesh(new THREE.SphereGeometry(geom.size[0], 24, 16), mat);
      } else {
        // capsule：three 沿 y 軸，MuJoCo 沿 z 軸 → 幾何體先轉 90°
        const cap = new THREE.CapsuleGeometry(geom.size[0], geom.size[1] * 2, 6, 16);
        cap.rotateX(Math.PI / 2);
        mesh = new THREE.Mesh(cap, mat);
      }
      mesh.castShadow = true;
      mesh.position.set(geom.pos[0], geom.pos[1], geom.pos[2]);
      mesh.quaternion.set(geom.quat[1], geom.quat[2], geom.quat[3], geom.quat[0]);

      if (geom.body === 0) {
        s.dynamicRoot.add(mesh); // 世界靜態物（障礙物）
        if (geom.name.startsWith("obstacle_")) s.obstacleMeshes.push(mesh);
      } else {
        s.robotGroups[geom.body - 1].add(mesh);
      }
    }

    // CoM / ZMP 全程軌跡
    const comPts = result.gait.com.map((p) => new THREE.Vector3(p[0], p[1], p[2]));
    s.comTrail.geometry.dispose();
    s.comTrail.geometry = new THREE.BufferGeometry().setFromPoints(comPts);
    const zmpPts = result.gait.zmp
      .filter((p): p is number[] => p !== null && p[0] !== null)
      .map((p) => new THREE.Vector3(p[0]!, p[1]!, 0.005));
    s.zmpTrail.geometry.dispose();
    s.zmpTrail.geometry = new THREE.BufferGeometry().setFromPoints(zmpPts);
  }, [result]);

  // ---------- 播放更新 ----------
  useEffect(() => {
    const s = sceneRef.current;
    if (!s) return;

    const unsub = playback.subscribe((t) => {
      const res = resultRef.current;
      if (res) {
        const dt = res.meta.dt;
        const f = Math.min(Math.floor(t / dt), res.meta.n_frames - 1);
        const xpos = res.frames.xpos[f];
        const xquat = res.frames.xquat[f];
        for (let b = 0; b < s.robotGroups.length; b++) {
          s.robotGroups[b].position.set(xpos[b][0], xpos[b][1], xpos[b][2]);
          s.robotGroups[b].quaternion.set(xquat[b][1], xquat[b][2], xquat[b][3], xquat[b][0]);
        }

        // CoM / ZMP 標記
        const com = res.gait.com[f];
        s.comMarker.position.set(com[0], com[1], com[2]);
        const zmp = res.gait.zmp[f];
        if (zmp && zmp[0] !== null) {
          s.zmpMarker.visible = true;
          s.zmpMarker.position.set(zmp[0]!, zmp[1]!, 0.006);
        } else {
          s.zmpMarker.visible = false;
        }

        // GRF 箭頭（畫在腳掌 body 位置）
        const footL = res.meta.body_names.indexOf("foot_l");
        const footR = res.meta.body_names.indexOf("foot_r");
        for (const [key, fi] of [["l", footL], ["r", footR]] as const) {
          const F = key === "l" ? res.gait.grf_l[f] : res.gait.grf_r[f];
          const arrow = s.grfArrows[key];
          const mag = Math.hypot(F[0], F[1], F[2]);
          if (mag > 5) {
            arrow.visible = true;
            arrow.position.set(xpos[fi][0], xpos[fi][1], 0.01);
            arrow.setDirection(new THREE.Vector3(F[0] / mag, F[1] / mag, F[2] / mag));
            arrow.setLength(Math.min(mag / 600, 1.2), 0.06, 0.04);
          } else {
            arrow.visible = false;
          }
        }

        // 支撐多邊形 + ZMP 裕度上色
        const poly = res.stability?.polygons?.[f] ?? [];
        const spos = s.supportLine.geometry.getAttribute("position") as THREE.BufferAttribute;
        if (poly.length >= 3) {
          for (let i = 0; i <= poly.length; i++) {
            const p = poly[i % poly.length];
            spos.setXYZ(i, p[0], p[1], 0.004);
          }
          s.supportLine.geometry.setDrawRange(0, poly.length + 1);
          const margin = res.stability.zmp_margin[f];
          (s.supportLine.material as THREE.LineBasicMaterial).color.setHex(
            margin !== null && margin < 0 ? 0xf87171 : 0x4ade80
          );
          s.supportLine.visible = true;
        } else {
          s.supportLine.visible = false;
        }

        // 質心鉛直投影
        const cpos = s.comProjLine.geometry.getAttribute("position") as THREE.BufferAttribute;
        cpos.setXYZ(0, com[0], com[1], com[2]);
        cpos.setXYZ(1, com[0], com[1], 0);
        cpos.needsUpdate = true;
        s.comProjDot.position.set(com[0], com[1], 0.004);
        spos.needsUpdate = true;

        // 感測射線
        const origin = res.sensor.origin[f];
        const hits = res.sensor.hits[f];
        const pos = s.rayLines.geometry.getAttribute("position") as THREE.BufferAttribute;
        for (let ri = 0; ri < hits.length; ri++) {
          pos.setXYZ(ri * 2, origin[0], origin[1], origin[2]);
          pos.setXYZ(ri * 2 + 1, hits[ri][0], hits[ri][1], hits[ri][2]);
        }
        pos.needsUpdate = true;

        // 被偵測到的障礙物變色
        const det = res.sensor.detected[f];
        s.obstacleMeshes.forEach((m, i) => {
          const mat = m.material as THREE.MeshStandardMaterial;
          const on = det && det[i] === 1;
          mat.emissive.setHex(on ? 0xcc3311 : 0x000000);
          mat.emissiveIntensity = on ? 0.7 : 0;
        });

        // 相機跟隨（僅 x 方向平移）；偏差過大（播放循環）時直接貼齊
        const trunkX = xpos[0][0];
        const dx = trunkX - s.controls.target.x;
        const k = Math.abs(dx) > 1.5 ? 1.0 : 0.15;
        s.controls.target.x += dx * k;
        s.camera.position.x += dx * k;
      }
      s.controls.update();
      s.renderer.render(s.scene, s.camera);
    });
    return unsub;
  }, [playback]);

  return <div ref={mountRef} className="h-full w-full" />;
}
