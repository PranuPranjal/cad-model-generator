import { useEffect, useRef, useState } from 'react';
import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls';

interface STLViewerProps {
  stlUrl: string;
  width?: number;
  height?: number;
}

const STLViewer: React.FC<STLViewerProps> = ({ stlUrl, width = 400, height = 300 }) => {
  const mountRef = useRef<HTMLDivElement>(null);
  const rendererRef = useRef<THREE.WebGLRenderer | null>(null);
  const frameRef = useRef<number | null>(null);
  const meshRef = useRef<THREE.Mesh | null>(null);
  const controlsRef = useRef<OrbitControls | null>(null);

  const [autoRotate, setAutoRotate] = useState(true);

  useEffect(() => {
    if (!mountRef.current) return;

    // Scene
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0xf0f0f0);

    // Camera
    const camera = new THREE.PerspectiveCamera(75, width / height, 0.1, 5000);
    camera.position.set(100, 100, 100);

    // Renderer
    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setSize(width, height);
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    rendererRef.current = renderer;
    mountRef.current.appendChild(renderer.domElement);

    // Controls
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.05;
    controls.enablePan = true;
    controls.enableZoom = true;
    controls.rotateSpeed = 0.8;
    controls.zoomSpeed = 1.0;
    controls.panSpeed = 0.8;
    controlsRef.current = controls;

    // Lights
    scene.add(new THREE.AmbientLight(0x404040, 0.8));

    const directionalLight = new THREE.DirectionalLight(0xffffff, 0.9);
    directionalLight.position.set(100, 100, 100);
    directionalLight.castShadow = true;
    scene.add(directionalLight);

    // Load STL
    const loadSTL = async () => {
      try {
        const response = await fetch(stlUrl);
        const arrayBuffer = await response.arrayBuffer();
        const geometry = parseSTL(arrayBuffer);

        // Center geometry
        geometry.computeBoundingBox();
        const center = new THREE.Vector3();
        geometry.boundingBox!.getCenter(center);
        geometry.translate(-center.x, -center.y, -center.z);

        const material = new THREE.MeshLambertMaterial({
          color: 0x00a0ff,
          side: THREE.DoubleSide,
        });

        const mesh = new THREE.Mesh(geometry, material);
        mesh.castShadow = true;
        mesh.receiveShadow = true;
        scene.add(mesh);
        meshRef.current = mesh;

        // Fit camera
        const box = new THREE.Box3().setFromObject(mesh);
        const size = box.getSize(new THREE.Vector3());
        const maxDim = Math.max(size.x, size.y, size.z);

        camera.position.set(maxDim * 2, maxDim * 2, maxDim * 2);
        camera.lookAt(0, 0, 0);
        controls.target.set(0, 0, 0);
        controls.update();
      } catch (error) {
        console.error('Error loading STL:', error);
      }
    };

    loadSTL();

    // Animate
    const animate = () => {
      frameRef.current = requestAnimationFrame(animate);

      if (autoRotate && meshRef.current) {
        meshRef.current.rotation.y += 0.01;
      }

      controls.update();
      renderer.render(scene, camera);
    };
    animate();

    // Cleanup
    return () => {
      if (frameRef.current) cancelAnimationFrame(frameRef.current);

      if (mountRef.current && renderer.domElement) {
        mountRef.current.removeChild(renderer.domElement);
      }

      renderer.dispose();
      scene.traverse((object) => {
        if (object instanceof THREE.Mesh) {
          object.geometry.dispose();
          if (Array.isArray(object.material)) {
            object.material.forEach((m) => m.dispose());
          } else {
            object.material.dispose();
          }
        }
      });
    };
  }, [stlUrl, width, height, autoRotate]);

  return (
    <div className="flex flex-col items-center space-y-2">
      <div
        ref={mountRef}
        className="border rounded-lg overflow-hidden shadow-md bg-gray-100"
        style={{ width, height }}
      />
      <button
        onClick={() => setAutoRotate(!autoRotate)}
        className="px-3 py-1 rounded-xl bg-blue-500 text-white shadow hover:bg-blue-600 transition"
      >
        {autoRotate ? 'Stop Auto-Rotate' : 'Start Auto-Rotate'}
      </button>
    </div>
  );
};

// STL parser
function parseSTL(data: ArrayBuffer): THREE.BufferGeometry {
  if (isASCII(data)) {
    return parseASCIISTL(data);
  }
  return parseBinarySTL(new DataView(data));
}

function isASCII(data: ArrayBuffer): boolean {
  const text = new TextDecoder().decode(data.slice(0, 256));
  return text.includes('facet normal') && text.includes('vertex');
}

function parseASCIISTL(data: ArrayBuffer): THREE.BufferGeometry {
  const text = new TextDecoder().decode(data);
  const geometry = new THREE.BufferGeometry();
  const vertices: number[] = [];
  const normals: number[] = [];

  const lines = text.split('\n');
  let currentNormal: number[] = [];

  for (const line of lines) {
    const trimmed = line.trim();

    if (trimmed.startsWith('facet normal')) {
      const parts = trimmed.split(/\s+/);
      currentNormal = [parseFloat(parts[2]), parseFloat(parts[3]), parseFloat(parts[4])];
    } else if (trimmed.startsWith('vertex')) {
      const parts = trimmed.split(/\s+/);
      vertices.push(parseFloat(parts[1]), parseFloat(parts[2]), parseFloat(parts[3]));
      normals.push(...currentNormal);
    }
  }

  geometry.setAttribute('position', new THREE.Float32BufferAttribute(vertices, 3));
  geometry.setAttribute('normal', new THREE.Float32BufferAttribute(normals, 3));

  return geometry;
}

function parseBinarySTL(view: DataView): THREE.BufferGeometry {
  const triangles = view.getUint32(80, true);
  const geometry = new THREE.BufferGeometry();

  const vertices: number[] = [];
  const normals: number[] = [];

  let offset = 84;

  for (let i = 0; i < triangles; i++) {
    const nx = view.getFloat32(offset, true);
    const ny = view.getFloat32(offset + 4, true);
    const nz = view.getFloat32(offset + 8, true);
    offset += 12;

    for (let j = 0; j < 3; j++) {
      const x = view.getFloat32(offset, true);
      const y = view.getFloat32(offset + 4, true);
      const z = view.getFloat32(offset + 8, true);

      vertices.push(x, y, z);
      normals.push(nx, ny, nz);

      offset += 12;
    }
    offset += 2; // Skip attribute byte count
  }

  geometry.setAttribute('position', new THREE.Float32BufferAttribute(vertices, 3));
  geometry.setAttribute('normal', new THREE.Float32BufferAttribute(normals, 3));

  return geometry;
}

export default STLViewer;
