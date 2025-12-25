"use client";

import React, { Suspense, useMemo } from "react";
import { Canvas, useLoader } from "@react-three/fiber";
import { OrbitControls } from "@react-three/drei";
import { STLLoader } from "three/examples/jsm/loaders/STLLoader.js";
import * as THREE from "three";

function Model({ url }: { url: string }) {
  const geom = useLoader(STLLoader, url);
  const material = useMemo(() => new THREE.MeshStandardMaterial({ metalness: 0.05, roughness: 0.9 }), []);
  // center geometry
  useMemo(() => {
    geom.computeBoundingBox();
    const bb = geom.boundingBox;
    if (bb) {
      const center = new THREE.Vector3();
      bb.getCenter(center);
      geom.translate(-center.x, -center.y, -center.z);
    }
  }, [geom]);

  return (
    <mesh geometry={geom} material={material} rotation={[-Math.PI / 2, 0, 0]} />
  );
}

export default function STLPreview({ stlUrl }: { stlUrl: string }) {
  if (!stlUrl) {
    return (
      <div style={{ padding: 16 }} className="muted">
        ارفع SVG ثم اضغط “ولّد الختم” عشان تظهر المعاينة.
      </div>
    );
  }

  return (
    <Canvas camera={{ position: [0, 80, 120], fov: 45 }}>
      <ambientLight intensity={0.8} />
      <directionalLight position={[80, 120, 60]} intensity={1.2} />
      <Suspense fallback={null}>
        <Model url={stlUrl} />
      </Suspense>
      <OrbitControls makeDefault />
      <gridHelper args={[200, 20]} />
    </Canvas>
  );
}
