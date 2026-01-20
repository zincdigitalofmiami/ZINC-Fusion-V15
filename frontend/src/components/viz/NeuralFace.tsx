'use client';

import { useEffect, useRef } from 'react';
import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';

interface NeuralFaceProps {
  size?: number;
  color?: string;
  particleColor?: string;
  wireframeOpacity?: number;
  rotationSpeed?: number;
}

export function NeuralFace({
  size = 400,
  color = '#888888',
  particleColor = '#ffffff',
  wireframeOpacity = 0.5,
  rotationSpeed = 0.0006,
}: NeuralFaceProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(28, 1, 0.1, 1000);
    camera.position.z = 40;
    camera.position.y = 5;

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setSize(size, size);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    container.appendChild(renderer.domElement);

    const mainColor = new THREE.Color(color);
    const headGroup = new THREE.Group();
    scene.add(headGroup);

    const loader = new GLTFLoader();
    loader.load('/head.glb', (gltf) => {
      gltf.scene.traverse((child) => {
        if (child instanceof THREE.Mesh) {
          const edges = new THREE.EdgesGeometry(child.geometry, 15);
          const line = new THREE.LineSegments(
            edges,
            new THREE.LineBasicMaterial({ color: mainColor, transparent: true, opacity: wireframeOpacity })
          );
          headGroup.add(line);
        }
      });

      const box = new THREE.Box3().setFromObject(headGroup);
      const center = box.getCenter(new THREE.Vector3());
      headGroup.position.sub(center);
    });

    // Particles
    const particlesGeometry = new THREE.BufferGeometry();
    const positions = new Float32Array(30 * 3);
    for (let i = 0; i < 30; i++) {
      positions[i * 3] = (Math.random() - 0.5) * 30;
      positions[i * 3 + 1] = (Math.random() - 0.5) * 30;
      positions[i * 3 + 2] = (Math.random() - 0.5) * 30;
    }
    particlesGeometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    const particles = new THREE.Points(
      particlesGeometry,
      new THREE.PointsMaterial({ color: particleColor, size: 0.1, transparent: true, opacity: 0.3 })
    );
    scene.add(particles);

    let animationId: number;
    const animate = () => {
      animationId = requestAnimationFrame(animate);
      headGroup.rotation.y += rotationSpeed;
      particles.rotation.y -= rotationSpeed * 0.1;
      renderer.render(scene, camera);
    };
    animate();

    return () => {
      cancelAnimationFrame(animationId);
      renderer.dispose();
      if (container && renderer.domElement) {
        container.removeChild(renderer.domElement);
      }
    };
  }, [size, color, particleColor, wireframeOpacity, rotationSpeed]);

  return (
    <div
      ref={containerRef}
      style={{ width: size, height: size, display: 'flex', alignItems: 'center', justifyContent: 'center' }}
    />
  );
}
