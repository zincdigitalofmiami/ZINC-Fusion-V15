'use client';

import { useEffect, useRef } from 'react';
import * as THREE from 'three';

interface NeuralSphereProps {
  size?: number;
  color?: string;
  particleColor?: string;
  wireframeOpacity?: number;
  particleCount?: number;
  rotationSpeed?: number;
}

/**
 * NeuralSphere - A rotating neural network sphere visualization
 * Based on AlgoSensei template design
 */
export function NeuralSphere({ 
  size = 400,
  color = '#2962ff',
  particleColor = '#00d4ff',
  wireframeOpacity = 0.3,
  particleCount = 200,
  rotationSpeed = 0.002,
}: NeuralSphereProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const rendererRef = useRef<THREE.WebGLRenderer | null>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    // Scene setup
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(75, 1, 0.1, 1000);
    camera.position.z = 2.5;

    // Renderer
    const renderer = new THREE.WebGLRenderer({
      antialias: true,
      alpha: true
    });
    renderer.setSize(size, size);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    container.appendChild(renderer.domElement);
    rendererRef.current = renderer;

    // Convert hex to THREE color
    const mainColor = new THREE.Color(color);
    const pColor = new THREE.Color(particleColor);

    // Wireframe sphere
    const sphereGeometry = new THREE.IcosahedronGeometry(1, 2);
    const wireframeMaterial = new THREE.MeshBasicMaterial({
      color: mainColor,
      wireframe: true,
      transparent: true,
      opacity: wireframeOpacity,
    });
    const sphere = new THREE.Mesh(sphereGeometry, wireframeMaterial);
    scene.add(sphere);

    // Inner glow sphere
    const innerGeometry = new THREE.IcosahedronGeometry(0.95, 2);
    const innerMaterial = new THREE.MeshBasicMaterial({
      color: pColor,
      wireframe: true,
      transparent: true,
      opacity: wireframeOpacity * 0.5,
    });
    const innerSphere = new THREE.Mesh(innerGeometry, innerMaterial);
    scene.add(innerSphere);

    // Floating particles
    const particlesGeometry = new THREE.BufferGeometry();
    const positions = new Float32Array(particleCount * 3);
    
    for (let i = 0; i < particleCount; i++) {
      const theta = Math.random() * Math.PI * 2;
      const phi = Math.acos(2 * Math.random() - 1);
      const r = 1.2 + Math.random() * 0.5;
      
      positions[i * 3] = r * Math.sin(phi) * Math.cos(theta);
      positions[i * 3 + 1] = r * Math.sin(phi) * Math.sin(theta);
      positions[i * 3 + 2] = r * Math.cos(phi);
    }
    
    particlesGeometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    
    const particlesMaterial = new THREE.PointsMaterial({
      color: pColor,
      size: 0.02,
      transparent: true,
      opacity: 0.6,
    });
    
    const particles = new THREE.Points(particlesGeometry, particlesMaterial);
    scene.add(particles);

    // Animation
    let animationId: number;
    const animate = () => {
      animationId = requestAnimationFrame(animate);
      
      sphere.rotation.x += rotationSpeed;
      sphere.rotation.y += rotationSpeed * 1.5;
      
      innerSphere.rotation.x -= rotationSpeed * 0.5;
      innerSphere.rotation.y -= rotationSpeed;
      
      particles.rotation.y += rotationSpeed * 0.5;
      
      renderer.render(scene, camera);
    };
    animate();

    // Cleanup
    return () => {
      cancelAnimationFrame(animationId);
      renderer.dispose();
      sphereGeometry.dispose();
      wireframeMaterial.dispose();
      innerGeometry.dispose();
      innerMaterial.dispose();
      particlesGeometry.dispose();
      particlesMaterial.dispose();
      if (container && renderer.domElement) {
        container.removeChild(renderer.domElement);
      }
    };
  }, [size, color, particleColor, wireframeOpacity, particleCount, rotationSpeed]);

  return (
    <div 
      ref={containerRef} 
      style={{ 
        width: size, 
        height: size,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
      }} 
    />
  );
}
