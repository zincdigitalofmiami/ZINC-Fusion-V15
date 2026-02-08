"use client";

import React, { useEffect, useRef, useState } from "react";
import * as d3 from "d3-force";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";

export interface TopicNode extends d3.SimulationNodeDatum {
  id: string;
  topic: string;
  volume: number;
  sentiment: number; // -1 to 1
  mentions?: number;
}

interface OrganicTopicCloudProps {
  topics?: TopicNode[];
  loading?: boolean;
}

export function OrganicTopicCloud({
  topics = [],
  loading = false,
}: OrganicTopicCloudProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [nodes, setNodes] = useState<TopicNode[]>([]);
  const simulationRef = useRef<d3.Simulation<TopicNode, undefined> | null>(
    null,
  );

  useEffect(() => {
    if (!containerRef.current || topics.length === 0) {
      setNodes([]);
      return;
    }
    const { clientWidth, clientHeight } = containerRef.current;

    // Deep-clone topics so d3 can mutate x/y
    const simNodes: TopicNode[] = topics.map((t) => ({
      ...t,
      x: clientWidth / 2 + (Math.random() - 0.5) * 100,
      y: clientHeight / 2 + (Math.random() - 0.5) * 100,
    }));

    // Stop any existing simulation
    simulationRef.current?.stop();

    const simulation = d3
      .forceSimulation(simNodes)
      .force("charge", d3.forceManyBody().strength(8))
      .force("center", d3.forceCenter(clientWidth / 2, clientHeight / 2))
      .force(
        "collide",
        d3
          .forceCollide<TopicNode>()
          .radius((d) => d.volume * 0.65 + 8)
          .strength(0.9),
      )
      .force("y", d3.forceY(clientHeight / 2).strength(0.04))
      .force("x", d3.forceX(clientWidth / 2).strength(0.04))
      .alphaDecay(0.02);

    simulation.on("tick", () => {
      setNodes([...simulation.nodes()]);
    });

    simulationRef.current = simulation;

    return () => {
      simulation.stop();
    };
  }, [topics]);

  return (
    <div
      ref={containerRef}
      className="relative w-full h-[420px] overflow-hidden bg-[#0a0a0a] rounded-xl border border-white/5"
    >
      {/* Loading state */}
      {loading && (
        <div className="absolute inset-0 z-10 flex items-center justify-center">
          <div className="text-sm text-slate-500 animate-pulse">
            Loading topic clusters…
          </div>
        </div>
      )}

      {/* Empty state */}
      {!loading && topics.length === 0 && (
        <div className="absolute inset-0 z-10 flex items-center justify-center">
          <div className="text-sm text-slate-500">
            No topic data available yet.
          </div>
        </div>
      )}

      {/* Ambient gradient */}
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,_var(--tw-gradient-stops))] from-[#1e293b]/10 via-[#0a0a0a] to-[#0a0a0a]" />

      {nodes.map((node) => {
        const isPositive = node.sentiment > 0;
        const isNeutral = Math.abs(node.sentiment) < 0.15;
        const colorClass = isNeutral
          ? "bg-slate-500/15 text-slate-300 border-slate-500/25"
          : isPositive
            ? "bg-emerald-500/15 text-emerald-300 border-emerald-500/25"
            : "bg-rose-500/15 text-rose-300 border-rose-500/25";

        const size = node.volume * 1.1;
        const fontSize = Math.max(9, Math.min(16, node.volume * 0.14));

        return (
          <motion.div
            key={node.id}
            className={cn(
              "absolute flex flex-col items-center justify-center rounded-full border backdrop-blur-sm shadow-xl cursor-pointer transition-colors duration-300 select-none",
              colorClass,
            )}
            style={{
              x: node.x,
              y: node.y,
              width: size,
              height: size,
              left: -size / 2,
              top: -size / 2,
            }}
            whileHover={{ scale: 1.12, zIndex: 10 }}
            initial={{ scale: 0, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            transition={{
              type: "spring",
              damping: 15,
              delay: Math.random() * 0.3,
            }}
            title={`${node.topic}: ${node.mentions ?? 0} mentions`}
          >
            <span
              className="font-semibold leading-tight text-center px-1"
              style={{ fontSize }}
            >
              {node.topic}
            </span>
            {node.mentions !== undefined && node.volume > 45 && (
              <span className="text-[9px] opacity-60 mt-0.5">
                {node.mentions}
              </span>
            )}
          </motion.div>
        );
      })}
    </div>
  );
}
