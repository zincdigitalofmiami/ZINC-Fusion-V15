'use client';

import React, { useEffect, useRef, useState } from 'react';
import * as d3 from 'd3-force';
import { motion } from 'framer-motion';
import { cn } from '@/lib/utils';

interface TopicNode extends d3.SimulationNodeDatum {
  id: string;
  topic: string;
  volume: number; // Size
  sentiment: number; // -1 to 1
}

const INITIAL_NODES: TopicNode[] = [];

export function OrganicTopicCloud() {
  const containerRef = useRef<HTMLDivElement>(null);
  const [nodes, setNodes] = useState<TopicNode[]>(INITIAL_NODES);

  useEffect(() => {
    if (!containerRef.current || nodes.length === 0) return;
    const { clientWidth, clientHeight } = containerRef.current;

    // Center init
    nodes.forEach(n => {
        n.x = clientWidth / 2 + (Math.random() - 0.5) * 10;
        n.y = clientHeight / 2 + (Math.random() - 0.5) * 10;
    });

    const simulation = d3.forceSimulation(nodes)
      .force('charge', d3.forceManyBody().strength(5))
      .force('center', d3.forceCenter(clientWidth / 2, clientHeight / 2))
      .force('collide', d3.forceCollide().radius((d: unknown) => (d as TopicNode).volume * 0.6 + 5).strength(0.9))
      .force('y', d3.forceY(clientHeight / 2).strength(0.05))
      .force('x', d3.forceX(clientWidth / 2).strength(0.05));

    simulation.on('tick', () => {
      setNodes([...simulation.nodes()]);
    });

    return () => {
      simulation.stop();
    };
  }, []);

  return (
    <div ref={containerRef} className="relative w-full h-[400px] overflow-hidden bg-[#0a0a0a] rounded-xl border border-white/5">
       {nodes.length === 0 && (
         <div className="absolute inset-0 z-10 flex items-center justify-center">
           <div className="text-sm text-slate-400">No sentiment/topic data available.</div>
         </div>
       )}
       <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,_var(--tw-gradient-stops))] from-[#1e293b]/10 via-[#0a0a0a] to-[#0a0a0a]" />
      
      {nodes.map((node) => {
        // Color interpolation based on sentiment
        const isPositive = node.sentiment > 0;
        const colorClass = isPositive ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/30' : 'bg-rose-500/20 text-rose-300 border-rose-500/30';
        
        return (
          <motion.div
            key={node.id}
            className={cn(
              "absolute flex items-center justify-center rounded-full border backdrop-blur-sm shadow-xl font-medium cursor-pointer transition-colors duration-300",
              colorClass
            )}
            style={{
              x: node.x,
              y: node.y,
              width: node.volume * 1.2,
              height: node.volume * 1.2,
              left: -node.volume * 0.6,
              top: -node.volume * 0.6,
              fontSize: Math.max(10, node.volume * 0.15)
            }}
            whileHover={{ scale: 1.1, zIndex: 10 }}
            initial={{ scale: 0 }}
            animate={{ scale: 1 }}
            transition={{ type: "spring", damping: 12 }}
          >
            {node.topic}
          </motion.div>
        );
      })}
    </div>
  );
}
