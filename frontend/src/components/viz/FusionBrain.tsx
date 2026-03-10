'use client';

import React, { useEffect, useRef, useState, useMemo } from 'react';
import * as d3 from 'd3-force';
import { motion, AnimatePresence } from 'framer-motion';
import { cn } from '@/lib/utils';
import { Zap, TrendingUp, AlertTriangle, Shield, Globe, DollarSign, Activity, Wheat, Landmark, Flame } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

interface Node extends d3.SimulationNodeDatum {
  id: string;
  group: string;
  val: number;
  label: string;
  icon: LucideIcon;
  status: 'calm' | 'active' | 'critical';
  // Hover card data
  hoverTitle?: string;
  hoverScore?: number | null;
  hoverStatus?: string;
  hoverDetail?: string;
  hoverCorrelation?: number | null;
  hoverDirection?: string;
}

interface Link extends d3.SimulationLinkDatum<Node> {
  source: string | Node;
  target: string | Node;
  value: number;
}

interface DriverInput {
  name: string;
  score: number;
  status: string;
  impact: string;
  source: 'live' | 'stale' | 'unavailable';
  rawValue?: number | null;
  unit?: string;
}

interface CorrelationInput {
  asset: string;
  correlation: number | null;
  direction: string;
  implication?: string;
  source: 'calculated' | 'unavailable';
}

interface FusionBrainProps {
  drivers?: DriverInput[];
  correlations?: CorrelationInput[];
}

const DRIVER_ICONS: Record<string, LucideIcon> = {
  Markets: Activity,
  Crush: Zap,
  China: Globe,
  Tariffs: Shield,
  'Trump Effect': Landmark,
  Energy: Flame,
};

const DRIVER_VISUAL_MULTIPLIER: Record<string, number> = {
  Markets: 1.45, // VIX anchor
  Energy: 1.35,  // Crude oil anchor
  Crush: 1.0,
  China: 1.0,
  Tariffs: 1.0,
  'Trump Effect': 1.0,
};

const CORR_ICONS: Record<string, LucideIcon> = {
  'Soybean Meal (ZM)': TrendingUp,
  'Soybeans (ZS)': TrendingUp,
  'Crude Oil (CL)': DollarSign,
  'VIX (Fear Index)': AlertTriangle,
  'Corn (ZC)': TrendingUp,
  'Palm Oil (CPO)': TrendingUp,
};

const CORR_LABELS: Record<string, string> = {
  'Soybean Meal (ZM)': 'Soybean Meal',
  'Soybeans (ZS)': 'Soybeans',
  'Crude Oil (CL)': 'Crude Oil',
  'VIX (Fear Index)': 'VIX',
  'Corn (ZC)': 'Corn',
  'Palm Oil (CPO)': 'Palm Oil',
};

const CORR_HOVER_TITLES: Record<string, string> = {
  'Soybean Meal (ZM)': 'Crush Economics',
  'Soybeans (ZS)': 'Bean Complex',
  'Crude Oil (CL)': 'Energy / Biofuel Link',
  'VIX (Fear Index)': 'Risk Transmission',
  'Corn (ZC)': 'Ag Complex',
  'Palm Oil (CPO)': 'Palm Oil Substitution',
};

function driverStatus(score: number, source: string): 'calm' | 'active' | 'critical' {
  if (source === 'unavailable') return 'calm';
  if (score >= 65) return 'critical';
  return 'active';
}

export function FusionBrain({ drivers = [], correlations = [] }: FusionBrainProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [nodes, setNodes] = useState<Node[]>([]);
  const [links, setLinks] = useState<Link[]>([]);
  const [, setDimensions] = useState({ width: 800, height: 600 });
  const [hoveredNode, setHoveredNode] = useState<string | null>(null);

  // Build graph data from props
  const graphData = useMemo(() => {
    if (drivers.length === 0) return { nodes: [] as Node[], links: [] as Link[] };

    // Only average drivers with real data (exclude NO DATA / unavailable / score 0 with no rawValue)
    const liveDrivers = drivers.filter(d => d.source !== 'unavailable' && d.score > 0);
    const avgScore = liveDrivers.length > 0
      ? liveDrivers.reduce((s, d) => s + d.score, 0) / liveDrivers.length
      : 0;
    const zlStatus: 'calm' | 'active' | 'critical' = avgScore >= 60 ? 'critical' : avgScore >= 40 ? 'active' : 'calm';

    const builtNodes: Node[] = [
      {
        id: 'ZL', group: 'center', val: 40, label: 'ZL Soybean Oil', icon: Wheat, status: zlStatus,
        hoverTitle: 'ZL Soybean Oil', hoverScore: Math.round(avgScore), hoverStatus: zlStatus === 'critical' ? 'ELEVATED' : zlStatus === 'active' ? 'ACTIVE' : 'CALM',
        hoverDetail: `Avg driver score: ${Math.round(avgScore)}/100`,
      },
    ];

    const builtLinks: Link[] = [];

    // Driver nodes
    for (const d of drivers) {
      const icon = DRIVER_ICONS[d.name] ?? Activity;
      const baseVal = 20 + (d.score / 100) * 15;
      const visualBoost = DRIVER_VISUAL_MULTIPLIER[d.name] ?? 1.0;
      const val = baseVal * visualBoost;
      const linkValue = Math.min(1, Math.max(0.2, (d.score / 100) * visualBoost));
      builtNodes.push({
        id: `driver-${d.name}`,
        group: 'driver',
        val,
        label: d.name,
        icon,
        status: driverStatus(d.score, d.source),
        hoverTitle: d.name,
        hoverScore: d.score,
        hoverStatus: d.status,
        hoverDetail: d.impact,
      });
      builtLinks.push({
        source: 'ZL',
        target: `driver-${d.name}`,
        value: linkValue,
      });
    }

    // Correlation nodes
    for (const c of correlations) {
      if (c.source === 'unavailable' || c.correlation === null) continue;
      const label = CORR_LABELS[c.asset] ?? c.asset;
      const icon = CORR_ICONS[c.asset] ?? TrendingUp;
      const absCorr = Math.abs(c.correlation);
      builtNodes.push({
        id: `corr-${label}`,
        group: 'correlation',
        val: 15 + absCorr * 10,
        label,
        icon,
        status: absCorr > 0.6 ? 'active' : 'calm',
        hoverTitle: CORR_HOVER_TITLES[c.asset] ?? label,
        hoverCorrelation: c.correlation,
        hoverDirection: c.direction,
        hoverDetail: c.implication ?? '',
      });
      builtLinks.push({
        source: 'ZL',
        target: `corr-${label}`,
        value: Math.max(0.1, absCorr),
      });
    }

    return { nodes: builtNodes, links: builtLinks };
  }, [drivers, correlations]);

  useEffect(() => {
    if (!containerRef.current || graphData.nodes.length === 0) return;

    const { clientWidth, clientHeight } = containerRef.current;
    setDimensions({ width: clientWidth, height: clientHeight });

    // Clone nodes/links so D3 can mutate them
    const simNodes = graphData.nodes.map(n => ({ ...n }));
    const simLinks = graphData.links.map(l => ({ ...l }));

    // Initial positions
    simNodes.forEach(node => {
      node.x = clientWidth / 2 + (Math.random() - 0.5) * 100;
      node.y = clientHeight / 2 + (Math.random() - 0.5) * 100;
    });

    const simulation = d3.forceSimulation(simNodes)
      .force('link', d3.forceLink(simLinks).id((d: unknown) => (d as Node).id).distance((d: unknown) => 160 * (1 - (d as Link).value * 0.4)))
      .force('charge', d3.forceManyBody().strength(-300))
      .force('center', d3.forceCenter(clientWidth / 2, clientHeight / 2))
      .force('collide', d3.forceCollide().radius((d: unknown) => (d as Node).val + 12).strength(0.7));

    simulation.on('tick', () => {
      setNodes([...simulation.nodes()]);
      setLinks([...simLinks]);
    });

    return () => {
      simulation.stop();
    };
  }, [graphData]);

  const getCoords = (link: Link) => {
    const source = link.source as Node;
    const target = link.target as Node;
    return {
      x1: source.x || 0, y1: source.y || 0,
      x2: target.x || 0, y2: target.y || 0,
    };
  };

  const hoveredNodeData = nodes.find(n => n.id === hoveredNode);

  return (
    <div ref={containerRef} className="relative w-full h-[500px] overflow-hidden bg-[#0a0a0a] rounded-xl border border-white/5 shadow-2xl">
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
        </defs>
        <AnimatePresence>
          {links.map((link, i) => {
            const { x1, y1, x2, y2 } = getCoords(link);
            const isStrong = link.value > 0.6;
            return (
              <g key={`link-${i}`}>
                <line
                  x1={x1} y1={y1} x2={x2} y2={y2}
                  stroke={isStrong ? "#3b82f6" : "#334155"}
                  strokeWidth={isStrong ? 2 : 1}
                  strokeOpacity={isStrong ? 0.4 : 0.15}
                />
                {isStrong && (
                  <motion.circle
                    r={2.5}
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
            width: node.val * 2.5,
            height: node.val * 2.5,
            left: -(node.val * 1.25),
            top: -(node.val * 1.25),
          }}
          onHoverStart={() => setHoveredNode(node.id)}
          onHoverEnd={() => setHoveredNode(null)}
          animate={{
            scale: node.status === 'critical' ? [1, 1.1, 1] : 1,
          }}
          transition={{
            scale: { duration: 2, repeat: Infinity, ease: "easeInOut" },
          }}
        >
          <div className={cn(
            "relative w-full h-full rounded-full border-2 flex items-center justify-center backdrop-blur-md transition-all duration-500",
            node.status === 'critical'
              ? "bg-red-500/10 border-red-500 text-red-400 shadow-[0_0_30px_rgba(239,68,68,0.3)]"
              : node.status === 'active'
                ? "bg-blue-500/10 border-blue-500 text-blue-400 shadow-[0_0_20px_rgba(59,130,246,0.2)]"
                : "bg-slate-800/40 border-slate-700 text-slate-500 hover:border-slate-500"
          )}>
            <node.icon size={node.id === 'ZL' ? 28 : 18} strokeWidth={1.5} />

            {node.status === 'active' && (
              <div className="absolute inset-0 animate-spin-slow pointer-events-none">
                <div className="absolute top-0 left-1/2 w-1.5 h-1.5 bg-blue-400 rounded-full shadow-[0_0_10px_blue]" />
              </div>
            )}
          </div>

          <motion.div
            className={cn(
              "absolute top-full mt-2 text-[10px] font-mono font-medium tracking-wider pointer-events-none whitespace-nowrap px-2 py-1 rounded bg-black/50 backdrop-blur-sm border border-white/10",
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

      {/* Hover Data Card */}
      <AnimatePresence>
        {hoveredNodeData && hoveredNode && (
          <motion.div
            key={`card-${hoveredNode}`}
            className="absolute z-50 pointer-events-none"
            style={{
              left: Math.min(
                Math.max(16, (hoveredNodeData.x ?? 0) + hoveredNodeData.val * 1.5),
                (containerRef.current?.clientWidth ?? 800) - 220
              ),
              top: Math.max(16, (hoveredNodeData.y ?? 0) - 60),
            }}
            initial={{ opacity: 0, scale: 0.9, x: -8 }}
            animate={{ opacity: 1, scale: 1, x: 0 }}
            exit={{ opacity: 0, scale: 0.9, x: -8 }}
            transition={{ duration: 0.15 }}
          >
            <div className="w-[200px] bg-[#111]/95 backdrop-blur-md border border-white/10 rounded-lg p-3 shadow-2xl">
              <div className={cn(
                "text-[11px] font-bold uppercase tracking-wider mb-1.5",
                hoveredNodeData.status === 'critical' ? 'text-red-400' :
                hoveredNodeData.status === 'active' ? 'text-blue-400' : 'text-slate-400'
              )}>
                {hoveredNodeData.hoverTitle}
              </div>
              <div className="h-px bg-white/10 mb-2" />

              {/* Driver card */}
              {hoveredNodeData.group === 'driver' && hoveredNodeData.hoverScore !== undefined && (
                <>
                  <div className="flex items-center justify-between mb-1.5">
                    <span className="text-[10px] text-slate-500">Score</span>
                    <span className={cn(
                      "text-sm font-mono font-bold",
                      (hoveredNodeData.hoverScore ?? 0) >= 65 ? 'text-red-400' :
                      (hoveredNodeData.hoverScore ?? 0) >= 40 ? 'text-amber-400' : 'text-emerald-400'
                    )}>
                      {hoveredNodeData.hoverScore}/100
                    </span>
                  </div>
                  <div className="h-1 bg-slate-800 rounded-full overflow-hidden mb-2">
                    <div
                      className={cn(
                        "h-full rounded-full",
                        (hoveredNodeData.hoverScore ?? 0) >= 65 ? 'bg-red-500' :
                        (hoveredNodeData.hoverScore ?? 0) >= 40 ? 'bg-amber-500' : 'bg-emerald-500'
                      )}
                      style={{ width: `${hoveredNodeData.hoverScore ?? 0}%` }}
                    />
                  </div>
                  {hoveredNodeData.hoverStatus && (
                    <div className="text-[9px] font-mono text-slate-400 uppercase tracking-widest mb-1">
                      {hoveredNodeData.hoverStatus}
                    </div>
                  )}
                </>
              )}

              {/* Center node (ZL) card */}
              {hoveredNodeData.group === 'center' && hoveredNodeData.hoverScore !== undefined && (
                <>
                  <div className="flex items-center justify-between mb-1.5">
                    <span className="text-[10px] text-slate-500">Avg Score</span>
                    <span className={cn(
                      "text-sm font-mono font-bold",
                      (hoveredNodeData.hoverScore ?? 0) >= 60 ? 'text-red-400' :
                      (hoveredNodeData.hoverScore ?? 0) >= 40 ? 'text-amber-400' : 'text-emerald-400'
                    )}>
                      {hoveredNodeData.hoverScore}/100
                    </span>
                  </div>
                </>
              )}

              {/* Correlation card */}
              {hoveredNodeData.group === 'correlation' && hoveredNodeData.hoverCorrelation !== undefined && (
                <>
                  <div className="flex items-center justify-between mb-1.5">
                    <span className="text-[10px] text-slate-500">Correlation</span>
                    <span className={cn(
                      "text-sm font-mono font-bold",
                      Math.abs(hoveredNodeData.hoverCorrelation ?? 0) >= 0.6 ? 'text-blue-400' :
                      Math.abs(hoveredNodeData.hoverCorrelation ?? 0) >= 0.3 ? 'text-slate-300' : 'text-slate-500'
                    )}>
                      {((hoveredNodeData.hoverCorrelation ?? 0) * 100).toFixed(0)}%
                    </span>
                  </div>
                  {hoveredNodeData.hoverDirection && (
                    <div className="text-[9px] font-mono text-slate-400 uppercase tracking-widest mb-1">
                      {hoveredNodeData.hoverDirection}
                    </div>
                  )}
                </>
              )}

              {/* Detail text */}
              {hoveredNodeData.hoverDetail && (
                <div className="text-[10px] text-slate-500 leading-tight mt-1 line-clamp-2">
                  {hoveredNodeData.hoverDetail.split('.')[0]}
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
