"use client";

import React, { useEffect, useRef, useState, useMemo } from "react";
import * as d3 from "d3-force";
import { motion, AnimatePresence } from "framer-motion";
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

/* Fallback topics when no data is available — keeps the viz alive */
const FALLBACK_TOPICS: TopicNode[] = [
  { id: "fb-1", topic: "Tariffs", volume: 88, sentiment: -0.75, mentions: 34 },
  { id: "fb-2", topic: "RVO Rule", volume: 95, sentiment: 0.85, mentions: 41 },
  { id: "fb-3", topic: "China Demand", volume: 72, sentiment: 0.4, mentions: 28 },
  { id: "fb-4", topic: "Drought", volume: 58, sentiment: -0.6, mentions: 19 },
  { id: "fb-5", topic: "Biofuel", volume: 65, sentiment: 0.7, mentions: 22 },
  { id: "fb-6", topic: "Export Sales", volume: 50, sentiment: 0.5, mentions: 16 },
  { id: "fb-7", topic: "Crush Margins", volume: 78, sentiment: 0.3, mentions: 25 },
  { id: "fb-8", topic: "Palm Oil", volume: 45, sentiment: -0.35, mentions: 12 },
  { id: "fb-9", topic: "Fed Policy", volume: 55, sentiment: -0.2, mentions: 18 },
  { id: "fb-10", topic: "USDA WASDE", volume: 68, sentiment: 0.15, mentions: 21 },
  { id: "fb-11", topic: "Inflation", volume: 38, sentiment: -0.45, mentions: 11 },
];

/* ─── Sentiment → color helpers ─── */

function getSentimentColor(sentiment: number): { bg: string; text: string; border: string; glow: string } {
  const abs = Math.abs(sentiment);
  const intensity = Math.min(1, abs * 1.3); // amplify slightly

  if (abs < 0.12) {
    return {
      bg: `rgba(100, 116, 139, ${0.12 + intensity * 0.08})`,
      text: "rgb(203, 213, 225)",
      border: `rgba(100, 116, 139, ${0.25 + intensity * 0.1})`,
      glow: "rgba(100, 116, 139, 0.15)",
    };
  }
  if (sentiment > 0) {
    return {
      bg: `rgba(16, 185, 129, ${0.1 + intensity * 0.15})`,
      text: `rgba(52, 211, 153, ${0.7 + intensity * 0.3})`,
      border: `rgba(16, 185, 129, ${0.2 + intensity * 0.2})`,
      glow: `rgba(16, 185, 129, ${0.08 + intensity * 0.12})`,
    };
  }
  return {
    bg: `rgba(244, 63, 94, ${0.1 + intensity * 0.15})`,
    text: `rgba(251, 113, 133, ${0.7 + intensity * 0.3})`,
    border: `rgba(244, 63, 94, ${0.2 + intensity * 0.2})`,
    glow: `rgba(244, 63, 94, ${0.08 + intensity * 0.12})`,
  };
}

export function OrganicTopicCloud({
  topics = [],
  loading = false,
}: OrganicTopicCloudProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [nodes, setNodes] = useState<TopicNode[]>([]);
  const simulationRef = useRef<d3.Simulation<TopicNode, undefined> | null>(null);
  const isFallback = topics.length === 0 && !loading;

  // Use real data or fallback
  const activeTopics = useMemo(
    () => (topics.length > 0 ? topics : isFallback ? FALLBACK_TOPICS : []),
    [topics, isFallback],
  );

  useEffect(() => {
    if (!containerRef.current || activeTopics.length === 0) {
      setNodes([]);
      return;
    }
    const { clientWidth, clientHeight } = containerRef.current;

    const simNodes: TopicNode[] = activeTopics.map((t) => ({
      ...t,
      x: clientWidth / 2 + (Math.random() - 0.5) * 120,
      y: clientHeight / 2 + (Math.random() - 0.5) * 80,
    }));

    simulationRef.current?.stop();

    const simulation = d3
      .forceSimulation(simNodes)
      .force("charge", d3.forceManyBody().strength(12))
      .force("center", d3.forceCenter(clientWidth / 2, clientHeight / 2))
      .force(
        "collide",
        d3
          .forceCollide<TopicNode>()
          .radius((d) => d.volume * 0.7 + 10)
          .strength(0.95)
          .iterations(3),
      )
      .force("y", d3.forceY(clientHeight / 2).strength(0.06))
      .force("x", d3.forceX(clientWidth / 2).strength(0.06))
      .alphaDecay(0.015)
      .velocityDecay(0.3);

    simulation.on("tick", () => {
      setNodes([...simulation.nodes()]);
    });

    simulationRef.current = simulation;

    return () => {
      simulation.stop();
    };
  }, [activeTopics]);

  return (
    <div
      ref={containerRef}
      className="relative w-full h-[450px] overflow-hidden bg-[#060609] rounded-xl border border-white/[0.06]"
    >
      {/* Loading state */}
      {loading && activeTopics.length === 0 && (
        <div className="absolute inset-0 z-10 flex items-center justify-center">
          <div className="flex items-center gap-3">
            <div className="w-2 h-2 rounded-full bg-blue-500 animate-ping" />
            <div className="text-sm text-slate-500 font-mono tracking-wide">
              Clustering narratives…
            </div>
          </div>
        </div>
      )}

      {/* Ambient background effects */}
      <div className="absolute inset-0 pointer-events-none">
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_30%_40%,rgba(16,185,129,0.04),transparent_55%)]" />
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_70%_60%,rgba(244,63,94,0.03),transparent_55%)]" />
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_50%,rgba(59,130,246,0.02),transparent_60%)]" />
      </div>

      {/* Fallback watermark */}
      {isFallback && (
        <div className="absolute top-3 right-4 z-20">
          <span className="text-[9px] font-mono text-slate-600 bg-slate-900/60 px-2 py-0.5 rounded border border-white/5">
            DEMO · Awaiting live data
          </span>
        </div>
      )}

      {/* Bubbles */}
      <AnimatePresence mode="popLayout">
        {nodes.map((node, i) => {
          const colors = getSentimentColor(node.sentiment);
          const size = node.volume * 1.2;
          const fontSize = Math.max(10, Math.min(18, node.volume * 0.16));
          const mentionSize = Math.max(8, Math.min(11, node.volume * 0.1));

          return (
            <motion.div
              key={node.id}
              className={cn(
                "absolute flex flex-col items-center justify-center rounded-full",
                "backdrop-blur-md cursor-pointer select-none",
                "hover:brightness-125 hover:backdrop-blur-lg",
              )}
              style={{
                x: node.x,
                y: node.y,
                width: size,
                height: size,
                left: -size / 2,
                top: -size / 2,
                background: colors.bg,
                borderWidth: 1,
                borderColor: colors.border,
                boxShadow: `0 0 ${20 + node.volume * 0.3}px ${colors.glow}, inset 0 1px 0 rgba(255,255,255,0.05)`,
                color: colors.text,
              }}
              whileHover={{
                scale: 1.15,
                zIndex: 20,
                boxShadow: `0 0 ${30 + node.volume * 0.5}px ${colors.glow}, 0 0 60px ${colors.glow}, inset 0 1px 0 rgba(255,255,255,0.08)`,
              }}
              initial={{ scale: 0, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0, opacity: 0 }}
              transition={{
                type: "spring",
                damping: 18,
                stiffness: 180,
                delay: i * 0.04,
              }}
              title={`${node.topic}: ${node.mentions ?? 0} mentions`}
            >
              <span
                className="font-bold leading-tight text-center px-2 drop-shadow-sm"
                style={{ fontSize }}
              >
                {node.topic}
              </span>
              {node.mentions !== undefined && size > 55 && (
                <span
                  className="font-mono mt-0.5 opacity-50"
                  style={{ fontSize: mentionSize }}
                >
                  {node.mentions}
                </span>
              )}
            </motion.div>
          );
        })}
      </AnimatePresence>

      {/* Subtle grid lines */}
      <svg className="absolute inset-0 w-full h-full pointer-events-none opacity-[0.03]">
        <defs>
          <pattern id="grid" width="40" height="40" patternUnits="userSpaceOnUse">
            <path d="M 40 0 L 0 0 0 40" fill="none" stroke="white" strokeWidth="0.5" />
          </pattern>
        </defs>
        <rect width="100%" height="100%" fill="url(#grid)" />
      </svg>
    </div>
  );
}
