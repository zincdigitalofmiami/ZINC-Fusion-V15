'use client';

import { useEffect, useRef } from 'react';
import * as THREE from 'three';

/**
 * NeuralSphere - A rotating neural network sphere visualization
 * Inspired by AlgoSensei aesthetic - cyan/teal nodes with connecting lines
 * 
 * Features:
 * - Organic node distribution on sphere surface
 * - Dynamic edge connections between nearby nodes
 * - Smooth rotation animation
 * - Glow effect on nodes
 * - Responsive sizing
 */
export function NeuralSphere({ 
  size = 400,
  nodeCount = 120,
  connectionDistance = 0.45,
  rotationSpeed = 0.002,
  primaryColor = '#00d4aa', // Teal/cyan
  secondaryColor = '#0066ff', // Blue accent
  className = ''
}: {
  size?: number;
  nodeCount?: number;
  connectionDistance?: number;
  rotationSpeed?: number;
  primaryColor?: string;
  secondaryColor?: string;
  className?: string;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const rendererRef = useRef<THREE.WebGLRenderer | null>(null);
  const sceneRef = useRef<THREE.Scene | null>(null);
  const cameraRef = useRef<THREE.PerspectiveCamera | null>(null);
  const sphereGroupRef = useRef<THREE.Group | null>(null);
  const frameRef = useRef<number>(0);

  useEffect(() => {
    if (!containerRef.current) return;

    const container = containerRef.current;
    const width = size;
    const height = size;

    // Scene setup
    const scene = new THREE.Scene();
    sceneRef.current = scene;

    // Camera
    const camera = new THREE.PerspectiveCamera(45, width / height, 0.1, 1000);
    camera.position.z = 4;
    cameraRef.current = camera;

    // Renderer
    const renderer = new THREE.WebGLRenderer({ 
      antialias: true, 
      alpha: true,
      powerPreference: 'high-performance'
    });
    renderer.setSize(width, height);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setClearColor(0x000000, 0);
    container.appendChild(renderer.domElement);
    rendererRef.current = renderer;

    // Create sphere group
    const sphereGroup = new THREE.Group();
    sphereGroupRef.current = sphereGroup;
    scene.add(sphereGroup);

    // Generate nodes on sphere surface using fibonacci spiral
    const nodes: THREE.Vector3[] = [];
    const goldenRatio = (1 + Math.sqrt(5)) / 2;
    
    for (let i = 0; i < nodeCount; i++) {
      const theta = 2 * Math.PI * i / goldenRatio;
      const phi = Math.acos(1 - 2 * (i + 0.5) / nodeCount);
      
      const x = Math.cos(theta) * Math.sin(phi);
      const y = Math.sin(theta) * Math.sin(phi);
      const z = Math.cos(phi);
      
      nodes.push(new THREE.Vector3(x, y, z));
    }

    // Create node particles
    const nodeGeometry = new THREE.BufferGeometry();
    const nodePositions = new Float32Array(nodeCount * 3);
    const nodeSizes = new Float32Array(nodeCount);
    
    nodes.forEach((node, i) => {
      nodePositions[i * 3] = node.x;
      nodePositions[i * 3 + 1] = node.y;
      nodePositions[i * 3 + 2] = node.z;
      // Varying sizes for depth effect
      nodeSizes[i] = 0.02 + Math.random() * 0.03;
    });
    
    nodeGeometry.setAttribute('position', new THREE.BufferAttribute(nodePositions, 3));
    nodeGeometry.setAttribute('size', new THREE.BufferAttribute(nodeSizes, 1));

    // Custom shader for glowing nodes
    const nodeMaterial = new THREE.ShaderMaterial({
      uniforms: {
        color: { value: new THREE.Color(primaryColor) },
        glowColor: { value: new THREE.Color(secondaryColor) }
      },
      vertexShader: `
        attribute float size;
        varying float vSize;
        void main() {
          vSize = size;
          vec4 mvPosition = modelViewMatrix * vec4(position, 1.0);
          gl_PointSize = size * (300.0 / -mvPosition.z);
          gl_Position = projectionMatrix * mvPosition;
        }
      `,
      fragmentShader: `
        uniform vec3 color;
        uniform vec3 glowColor;
        varying float vSize;
        void main() {
          float dist = length(gl_PointCoord - vec2(0.5));
          if (dist > 0.5) discard;
          
          float glow = 1.0 - smoothstep(0.0, 0.5, dist);
          vec3 finalColor = mix(glowColor, color, glow);
          float alpha = glow * 0.9;
          
          gl_FragColor = vec4(finalColor, alpha);
        }
      `,
      transparent: true,
      blending: THREE.AdditiveBlending,
      depthWrite: false
    });

    const nodePoints = new THREE.Points(nodeGeometry, nodeMaterial);
    sphereGroup.add(nodePoints);

    // Create connections between nearby nodes
    const edgePositions: number[] = [];
    
    for (let i = 0; i < nodes.length; i++) {
      for (let j = i + 1; j < nodes.length; j++) {
        const dist = nodes[i].distanceTo(nodes[j]);
        if (dist < connectionDistance) {
          edgePositions.push(
            nodes[i].x, nodes[i].y, nodes[i].z,
            nodes[j].x, nodes[j].y, nodes[j].z
          );
        }
      }
    }

    const edgeGeometry = new THREE.BufferGeometry();
    edgeGeometry.setAttribute('position', new THREE.Float32BufferAttribute(edgePositions, 3));

    const edgeMaterial = new THREE.LineBasicMaterial({
      color: new THREE.Color(primaryColor),
      transparent: true,
      opacity: 0.15,
      blending: THREE.AdditiveBlending
    });

    const edges = new THREE.LineSegments(edgeGeometry, edgeMaterial);
    sphereGroup.add(edges);

    // Create outer wireframe sphere
    const wireGeometry = new THREE.IcosahedronGeometry(1.05, 1);
    const wireMaterial = new THREE.MeshBasicMaterial({
      color: new THREE.Color(primaryColor),
      wireframe: true,
      transparent: true,
      opacity: 0.08
    });
    const wireSphere = new THREE.Mesh(wireGeometry, wireMaterial);
    sphereGroup.add(wireSphere);

    // Add some floating particles around the sphere
    const particleCount = 50;
    const particleGeometry = new THREE.BufferGeometry();
    const particlePositions = new Float32Array(particleCount * 3);
    
    for (let i = 0; i < particleCount; i++) {
      const radius = 1.3 + Math.random() * 0.5;
      const theta = Math.random() * Math.PI * 2;
      const phi = Math.random() * Math.PI;
      
      particlePositions[i * 3] = radius * Math.sin(phi) * Math.cos(theta);
      particlePositions[i * 3 + 1] = radius * Math.sin(phi) * Math.sin(theta);
      particlePositions[i * 3 + 2] = radius * Math.cos(phi);
    }
    
    particleGeometry.setAttribute('position', new THREE.BufferAttribute(particlePositions, 3));
    
    const particleMaterial = new THREE.PointsMaterial({
      color: new THREE.Color(primaryColor),
      size: 0.015,
      transparent: true,
      opacity: 0.6,
      blending: THREE.AdditiveBlending
    });
    
    const particles = new THREE.Points(particleGeometry, particleMaterial);
    sphereGroup.add(particles);

    // Animation loop
    const animate = () => {
      frameRef.current = requestAnimationFrame(animate);

      if (sphereGroupRef.current) {
        // Smooth rotation on multiple axes
        sphereGroupRef.current.rotation.y += rotationSpeed;
        sphereGroupRef.current.rotation.x += rotationSpeed * 0.3;
      }

      renderer.render(scene, camera);
    };

    animate();

    // Cleanup
    return () => {
      cancelAnimationFrame(frameRef.current);
      renderer.dispose();
      if (container.contains(renderer.domElement)) {
        container.removeChild(renderer.domElement);
      }
      nodeGeometry.dispose();
      nodeMaterial.dispose();
      edgeGeometry.dispose();
      edgeMaterial.dispose();
      wireGeometry.dispose();
      wireMaterial.dispose();
      particleGeometry.dispose();
      particleMaterial.dispose();
    };
  }, [size, nodeCount, connectionDistance, rotationSpeed, primaryColor, secondaryColor]);

  return (
    <div 
      ref={containerRef} 
      className={className}
      style={{ 
        width: size, 
        height: size,
        position: 'relative'
      }}
    />
  );
}

export default NeuralSphere;
