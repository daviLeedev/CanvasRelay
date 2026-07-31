"use client";

import { Grid } from "@react-three/drei";
import { Canvas, useFrame } from "@react-three/fiber";
import { useEffect, useMemo, useRef } from "react";
import * as THREE from "three";

import type { DemoJob, JobStatus } from "./types";
import styles from "./studio.module.css";

const statusColors: Record<JobStatus, string> = {
  queued: "#efb74e",
  running: "#6f9cff",
  completed: "#48c992",
};

function JobPlate({ job, y, selected, animated, onSelect }: Readonly<{
  job: DemoJob;
  y: number;
  selected: boolean;
  animated: boolean;
  onSelect: () => void;
}>) {
  const marker = useRef<THREE.Mesh>(null);
  const geometry = useMemo(() => new THREE.BoxGeometry(1.8, 0.72, 0.16), []);
  const material = useMemo(
    () =>
      new THREE.MeshStandardMaterial({
        color: selected ? "#27364a" : "#1d2530",
        emissive: selected ? "#142648" : "#000000",
        emissiveIntensity: selected ? 0.7 : 0,
        roughness: 0.7,
      }),
    [selected],
  );
  const markerMaterial = useMemo(
    () => new THREE.MeshBasicMaterial({ color: statusColors[job.status] }),
    [job.status],
  );

  useEffect(() => {
    return () => {
      geometry.dispose();
      material.dispose();
      markerMaterial.dispose();
    };
  }, [geometry, markerMaterial, material]);

  useFrame(({ clock }) => {
    if (!marker.current || !animated || job.status !== "running") return;
    marker.current.position.x = -1.96 + ((clock.elapsedTime * 0.58) % 1) * 2.65;
  });

  return (
    <group position={[-3.15, y, 0]}>
      <mesh
        geometry={geometry}
        material={material}
        onClick={(event) => {
          event.stopPropagation();
          onSelect();
        }}
        scale={selected ? [1.04, 1.04, 1.04] : 1}
      />
      <mesh position={[-0.78, 0, 0.11]}>
        <boxGeometry args={[0.06, 0.48, 0.05]} />
        <meshBasicMaterial color={statusColors[job.status]} />
      </mesh>
      <mesh ref={marker} position={[-1.96, 0, 0]} material={markerMaterial}>
        <boxGeometry args={[0.18, 0.12, 0.12]} />
      </mesh>
    </group>
  );
}

function RelayScene({ jobs, selectedId, animated, onSelect }: Readonly<{
  jobs: DemoJob[];
  selectedId: string;
  animated: boolean;
  onSelect: (id: string) => void;
}>) {
  const planeGeometry = useMemo(() => new THREE.BoxGeometry(4.2, 3.25, 0.18), []);
  const planeMaterial = useMemo(
    () => new THREE.MeshStandardMaterial({ color: "#18212b", roughness: 0.66, metalness: 0.2 }),
    [],
  );

  useEffect(() => {
    return () => {
      planeGeometry.dispose();
      planeMaterial.dispose();
    };
  }, [planeGeometry, planeMaterial]);

  return (
    <>
      <color attach="background" args={["#090c10"]} />
      <ambientLight intensity={0.75} />
      <directionalLight position={[3, 4, 6]} intensity={2.3} color="#dbe7ff" />
      <directionalLight position={[-5, -2, 3]} intensity={1.1} color="#77d7b0" />

      <Grid
        position={[0, -2.3, -0.7]}
        args={[16, 10]}
        cellSize={0.55}
        cellThickness={0.5}
        cellColor="#25303b"
        sectionSize={2.2}
        sectionThickness={0.7}
        sectionColor="#354251"
        fadeDistance={13}
        fadeStrength={1.4}
        infiniteGrid={false}
      />

      {jobs.map((job, index) => (
        <JobPlate
          key={job.id}
          job={job}
          y={1.35 - index * 1.35}
          selected={selectedId === job.id}
          animated={animated}
          onSelect={() => onSelect(job.id)}
        />
      ))}

      {jobs.map((job, index) => (
        <mesh key={`${job.id}-rail`} position={[-1.15, 1.35 - index * 1.35, -0.08]}>
          <boxGeometry args={[2.15, 0.035, 0.035]} />
          <meshBasicMaterial color={statusColors[job.status]} transparent opacity={0.72} />
        </mesh>
      ))}

      <mesh geometry={planeGeometry} material={planeMaterial} position={[1.25, 0, 0]} />
      <mesh position={[1.25, 0, 0.13]}>
        <planeGeometry args={[3.6, 2.7]} />
        <meshBasicMaterial color="#11171e" />
      </mesh>
      <mesh position={[1.25, -1.15, 0.18]}>
        <boxGeometry args={[3.25, 0.08, 0.04]} />
        <meshBasicMaterial color="#344355" />
      </mesh>
      <mesh position={[-0.37 + 1.625 * (jobs.find((job) => job.id === selectedId)?.progress ?? 0) / 100, -1.15, 0.21]}>
        <boxGeometry args={[
          Math.max(0.08, 3.25 * (jobs.find((job) => job.id === selectedId)?.progress ?? 0) / 100),
          0.09,
          0.05,
        ]} />
        <meshBasicMaterial color="#6f9cff" />
      </mesh>

      <mesh position={[4.05, 0, 0]}>
        <boxGeometry args={[0.65, 1.75, 0.18]} />
        <meshStandardMaterial color="#26313a" roughness={0.6} />
      </mesh>
      <mesh position={[3.03, 0, -0.08]}>
        <boxGeometry args={[1.45, 0.04, 0.04]} />
        <meshBasicMaterial color="#48c992" />
      </mesh>
    </>
  );
}

export function StudioStage3D({
  jobs,
  selectedId,
  onSelect,
  reducedMotion,
  pageVisible,
}: Readonly<{
  jobs: DemoJob[];
  selectedId: string;
  onSelect: (id: string) => void;
  reducedMotion: boolean;
  pageVisible: boolean;
}>) {
  const animated = pageVisible && !reducedMotion;

  return (
    <div className={styles.stage3d} data-testid="stage-3d" data-motion={animated ? "active" : "paused"}>
      <Canvas
        camera={{ position: [0, 0.25, 9.4], fov: 45, near: 0.1, far: 40 }}
        dpr={[1, 1.5]}
        frameloop={animated ? "always" : "demand"}
        gl={{ antialias: true, alpha: false, powerPreference: "high-performance" }}
      >
        <RelayScene jobs={jobs} selectedId={selectedId} animated={animated} onSelect={onSelect} />
      </Canvas>

      <div className={styles.sceneLabels} aria-hidden="true">
        <span>QUEUE</span>
        <span>MEDIA PROCESSING PLANE</span>
        <span>OUTPUT</span>
      </div>
      <div className={styles.sceneJobLabels}>
        {jobs.map((job) => (
          <button
            key={job.id}
            type="button"
            data-active={selectedId === job.id}
            onClick={() => onSelect(job.id)}
          >
            <span>{job.name}</span>
            <strong>{job.progress}%</strong>
          </button>
        ))}
      </div>
    </div>
  );
}
