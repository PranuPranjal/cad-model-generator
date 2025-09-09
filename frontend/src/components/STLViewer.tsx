import { Suspense } from "react";
import { Canvas } from "@react-three/fiber";
import { OrbitControls, Stage } from "@react-three/drei";
import { STLLoader } from "three/examples/jsm/loaders/STLLoader.js";
import { useLoader } from "@react-three/fiber";

function Model({ url }: { url: string }) {
  const geometry = useLoader(STLLoader, url);
  return (
    <mesh geometry={geometry}>
      <meshStandardMaterial color="orange" />
    </mesh>
  );
}

export default function STLViewer({ url }: { url: string }) {
  return (
    <Canvas 
    style={{ width: '800px', height: '600px', backgroundColor: '#43a9e8', borderRadius: '10px' }}
    camera={{ position: [0, 0, 100], fov: 50 }}>
      <ambientLight />
      <Suspense fallback={null}>
        <Stage>
          <Model url={url} />
        </Stage>
      </Suspense>
      <OrbitControls />
    </Canvas>
  );
}
