import React, { Suspense, useState } from "react";
import { Canvas, useLoader } from "@react-three/fiber";
import { OrbitControls, Stage, Grid } from "@react-three/drei";
import { Vector3 } from "three";
import { STLLoader } from "three/examples/jsm/loaders/STLLoader.js";
function Model({ url, setDimensions }: { url: string, setDimensions: (dims: {x: number, y: number, z: number}) => void }) {
  const geometry = useLoader(STLLoader, url);
  React.useEffect(() => {
    if (geometry) {
      geometry.computeBoundingBox();
      const box = geometry.boundingBox;
      if (box) {
        const size = new Vector3();
        box.getSize(size);
        setDimensions({ x: size.x, y: size.y, z: size.z });
      }
    }
  }, [geometry, setDimensions]);
  return (
    <mesh geometry={geometry}>
      <meshStandardMaterial color="orange" />
    </mesh>
  );
}

export default function STLViewer({ url }: { url: string }) {
  const [dimensions, setDimensions] = useState<{x: number, y: number, z: number} | null>(null);

  // Gridlines are shown using the Grid component from drei

  return (
    <div style={{ position: 'relative', width: '800px', height: '600px' }}>
      <Canvas 
        style={{ width: '100%', height: '100%', backgroundColor: '#43a9e8', borderRadius: '10px' }}
        camera={{ position: [0, 0, 100], fov: 50 }}>
        <ambientLight />
        <Suspense fallback={null}>
          <Stage>
            <Model url={url} setDimensions={setDimensions} />
          </Stage>
        </Suspense>
        {/* XY Plane */}
        <Grid
          position={[0, 0, 0]}
          args={[100, 100]}
          cellSize={1}
          cellThickness={1}
          sectionSize={10}
          sectionThickness={2}
          sectionColor={'#444'}
          cellColor={'#888'}

        />
        {/* YZ Plane */}
        <Grid
          position={[0, 0, 0]}
          rotation={[0, Math.PI / 2, 0]}
          args={[100, 100]}
          cellSize={1}
          cellThickness={1}
          sectionSize={10}
          sectionThickness={2}
          sectionColor={'#444'}
          cellColor={'#888'}

        />
        {/* XZ Plane */}
        <Grid
          position={[0, 0, 0]}
          rotation={[Math.PI / 2, 0, 0]}
          args={[100, 100]}
          cellSize={1}
          cellThickness={1}
          sectionSize={10}
          sectionThickness={2}
          sectionColor={'#444'}
          cellColor={'#888'}

        />
        <OrbitControls />
      </Canvas>
      {dimensions && (
        <div style={{
          position: 'absolute',
          top: 10,
          right: 20,
          background: 'rgba(255,255,255,0.85)',
          padding: '8px 16px',
          borderRadius: '8px',
          fontSize: '16px',
          color: '#222',
          boxShadow: '0 2px 8px rgba(0,0,0,0.1)'
        }}>
          <div><strong>Dimensions</strong></div>
          <div>X: {dimensions.x.toFixed(2)}</div>
          <div>Y: {dimensions.y.toFixed(2)}</div>
          <div>Z: {dimensions.z.toFixed(2)}</div>
        </div>
      )}
    </div>
  );
}
