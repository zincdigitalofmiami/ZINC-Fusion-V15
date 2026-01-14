'use client';

import React, { useEffect, useRef, useState } from 'react';
import * as d3 from 'd3-force';
import { motion, AnimatePresence } from 'framer-motion';
import { cn } from '@/lib/utils';
import { Network, Zap, TrendingUp, AlertTriangle, Shield, Droplet, Globe, DollarSign, Activity, Wheat } from 'lucide-react';

interface Node extends d3.SimulationNodeDatum {
  id: string;
  group: string;
  val: number; // Size/Importance
  label: string;
  icon: any;
  status: 'calm' | 'active' | 'critical';
}

interface Link extends d3.SimulationLinkDatum<Node> {
  source: string | Node;
  target: string | Node;
  value: number; // Correlation strength 0-1
}

const SPECIALISTS: any[] = [];
const INITIAL_NODES: Node[] = [];
const INITIAL_LINKS: Link[] = [];

export function FusionBrain() {
  const containerRef = useRef<HTMLDivElement>(null);
  const [nodes, setNodes] = useState<Node[]>(INITIAL_NODES);
  const [links, setLinks] = useState<Link[]>(INITIAL_LINKS);
  const [dimensions, setDimensions] = useState({ width: 800, height: 600 });
  const [hoveredNode, setHoveredNode] = useState<string | null>(null);

  useEffect(() => {
    if (!containerRef.current || nodes.length === 0) return;

    const { clientWidth, clientHeight } = containerRef.current;
    
    // Initial center position
    nodes.forEach(node => {
        node.x = clientWidth / 2 + (Math.random() - 0.5) * 50;
        node.y = clientHeight / 2 + (Math.random() - 0.5) * 50;
    });

    setDimensions({ width: clientWidth, height: clientHeight });

    const simulation = d3.forceSimulation(nodes)
      .force('link', d3.forceLink(links).id((d: any) => d.id).distance((d: any) => 200 * (1 - d.value)))
      .force('charge', d3.forceManyBody().strength(-400))
      .force('center', d3.forceCenter(clientWidth / 2, clientHeight / 2))
      .force('collide', d3.forceCollide().radius((d: any) => d.val + 20).strength(0.7));

    simulation.on('tick', () => {
      setNodes([...simulation.nodes()]);
    }); // Links use references so we don't need to spread them constantly if simulation mutates them in place (which it does)

    return () => {
      simulation.stop();
    };
  }, []); 

  // Helper to get coords safe
  const getCoords = (link: Link) => {
    const source: any = link.source;
    const target: any = link.target;
    return { 
      x1: source.x || 0, y1: source.y || 0,
      x2: target.x || 0, y2: target.y || 0 
    };
  };

  return (
    <div ref={containerRef} className="relative w-full h-[600px] overflow-hidden bg-[#0a0a0a] rounded-xl border border-white/5 shadow-2xl">
      {nodes.length === 0 && (
        <div className="absolute inset-0 z-10 flex items-center justify-center">
          <div className="text-sm text-slate-400">No causal network data available.</div>
        </div>
      )}
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,_var(--tw-gradient-stops))] from-[#1e293b]/20 via-[#0a0a0a] to-[#0a0a0a]" />
      
      <svg className="absolute inset-0 w-full h-full pointer-events-none">
        <defs>
          <filter id="glow">
            <feGaussianBlur stdDeviation="2.5" result="coloredBlur" />
            <feMerge>
              <feMergeNode in="coloredBlur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
          <linearGradient id="synapse-gradient" gradientUnits="userSpaceOnUse">
            <stop offset="0%" stopColor="#3b82f6" stopOpacity="0" />
            <stop offset="50%" stopColor="#3b82f6" stopOpacity="1" />
            <stop offset="100%" stopColor="#3b82f6" stopOpacity="0" />
          </linearGradient>
        </defs>
        <AnimatePresence>
          {links.map((link, i) => {
            const { x1, y1, x2, y2 } = getCoords(link);
            const isStrong = link.value > 0.8;
            return (
              <g key={`link-${i}`}>
                {/* Base Line */}
                <line
                  x1={x1} y1={y1} x2={x2} y2={y2}
                  stroke={isStrong ? "#3b82f6" : "#334155"}
                  strokeWidth={isStrong ? 2 : 1}
                  strokeOpacity={0.2}
                />
                {/* Active Pulse (Only for strong correlations) */}
                {isStrong && (
                  <motion.circle
                    r={3}
                    fill="#3b82f6"
                    filter="url(#glow)"
                  >
                    <animateMotion
                      dur={`${3 / link.value}s`}
                      repeatCount="indefinite"
                      path={`M${x1},${y1} L${x2},${y2}`}
                    />
                  </motion.circle>
                )}
              </g>
            );
          })}
        </AnimatePresence>
      </svg>

      {nodes.map((node) => (
        <motion.div
          key={node.id}
          className={cn(
            "absolute flex flex-col items-center justify-center cursor-pointer will-change-transform z-10",
            hoveredNode && hoveredNode !== node.id && "opacity-30 blur-[1px]"
          )}
          style={{
            x: node.x, 
            y: node.y,
            width: node.val * 3, // slightly larger visual target
            height: node.val * 3,
            left: -(node.val * 1.5), // Center offset
            top: -(node.val * 1.5)
          }}
          onHoverStart={() => setHoveredNode(node.id)}
          onHoverEnd={() => setHoveredNode(null)}
          animate={{
            scale: node.status === 'critical' ? [1, 1.1, 1] : 1,
          }}
          transition={{
            scale: { duration: 2, repeat: Infinity, ease: "easeInOut" }
          }}
        >
          {/* Node Visual */}
          <div className={cn(
            "relative w-full h-full rounded-full border-2 flex items-center justify-center backdrop-blur-md transition-all duration-500",
            node.status === 'critical' 
              ? "bg-red-500/10 border-red-500 text-red-400 shadow-[0_0_30px_rgba(239,68,68,0.3)]" 
              : node.status === 'active'
                ? "bg-blue-500/10 border-blue-500 text-blue-400 shadow-[0_0_20px_rgba(59,130,246,0.2)]"
                : "bg-slate-800/40 border-slate-700 text-slate-500 hover:border-slate-500"
          )}>
            <node.icon size={24} strokeWidth={1.5} />
            
            {/* Orbiting Particles for Active Nodes */}
            {node.status === 'active' && (
              <div className="absolute inset-0 animate-spin-slow pointer-events-none">
                <div className="absolute top-0 left-1/2 w-1.5 h-1.5 bg-blue-400 rounded-full shadow-[0_0_10px_blue]" />
              </div>
            )}
          </div>

          {/* Label */}
          <motion.div 
            className={cn(
                "absolute top-full mt-2 text-xs font-mono font-medium tracking-wider pointer-events-none whitespace-nowrap px-2 py-1 rounded bg-black/50 backdrop-blur-sm border border-white/10",
                node.status === 'critical' ? 'text-red-400 border-red-900/50' : 
                node.status === 'active' ? 'text-blue-400 border-blue-900/50' : 'text-slate-500'
            )}
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
          >
            {node.label}
          </motion.div>
        </motion.div>
      ))}
    </div>
  );
}
