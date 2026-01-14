/**
 * TechnicalGauge - TradingView-style Semicircle Meter
 * 
 * Shows buy/sell signal strength with gradient arc
 * Strong Sell ← Sell ← Neutral → Buy → Strong Buy
 */
'use client';

import React, { useMemo } from 'react';
import TV from '@/lib/colors';

type Signal = 'strong_sell' | 'sell' | 'neutral' | 'buy' | 'strong_buy';

interface TechnicalGaugeProps {
  value: number;           // 0-100 where 50 is neutral
  signal: Signal;
  title?: string;
  sellCount?: number;
  neutralCount?: number;
  buyCount?: number;
  size?: 'sm' | 'md' | 'lg';
}

const signalLabels: Record<Signal, string> = {
  strong_sell: 'Strong sell',
  sell: 'Sell',
  neutral: 'Neutral',
  buy: 'Buy',
  strong_buy: 'Strong buy',
};

const signalColors: Record<Signal, string> = {
  strong_sell: '#f23645',
  sell: '#ff5252',
  neutral: '#787b86',
  buy: '#26a69a',
  strong_buy: '#22ab94',
};

export function TechnicalGauge({
  value,
  signal,
  title = 'Summary',
  sellCount,
  neutralCount,
  buyCount,
  size = 'md',
}: TechnicalGaugeProps) {
  
  const dimensions = useMemo(() => {
    switch (size) {
      case 'sm': return { width: 160, height: 100, strokeWidth: 8, fontSize: 12 };
      case 'lg': return { width: 280, height: 160, strokeWidth: 14, fontSize: 18 };
      default: return { width: 220, height: 130, strokeWidth: 12, fontSize: 14 };
    }
  }, [size]);

  // Calculate needle angle (0 = left, 180 = right)
  // value 0 = strong sell (left), 100 = strong buy (right)
  const needleAngle = (value / 100) * 180;
  
  // Arc calculations
  const cx = dimensions.width / 2;
  const cy = dimensions.height - 10;
  const radius = Math.min(cx, cy) - dimensions.strokeWidth;
  
  // Needle endpoint
  const needleLength = radius - 15;
  const needleRadians = (needleAngle - 180) * (Math.PI / 180);
  const needleX = cx + needleLength * Math.cos(needleRadians);
  const needleY = cy + needleLength * Math.sin(needleRadians);

  return (
    <div className="flex flex-col items-center">
      {/* Title */}
      {title && (
        <div className="text-sm font-medium text-[#d1d4dc] mb-2">{title}</div>
      )}

      <svg width={dimensions.width} height={dimensions.height} viewBox={`0 0 ${dimensions.width} ${dimensions.height}`}>
        <defs>
          {/* Gradient for the arc - Strong Sell (red) to Strong Buy (teal) */}
          <linearGradient id="gaugeGradient" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="#f23645" />
            <stop offset="25%" stopColor="#ff5252" />
            <stop offset="50%" stopColor="#787b86" />
            <stop offset="75%" stopColor="#26a69a" />
            <stop offset="100%" stopColor="#22ab94" />
          </linearGradient>
          
          {/* Drop shadow for needle */}
          <filter id="needleShadow" x="-50%" y="-50%" width="200%" height="200%">
            <feDropShadow dx="0" dy="1" stdDeviation="2" floodColor="#000" floodOpacity="0.5" />
          </filter>
        </defs>

        {/* Background arc (dark) */}
        <path
          d={describeArc(cx, cy, radius, 0, 180)}
          fill="none"
          stroke="#2a2e39"
          strokeWidth={dimensions.strokeWidth}
          strokeLinecap="round"
        />

        {/* Colored gradient arc */}
        <path
          d={describeArc(cx, cy, radius, 0, 180)}
          fill="none"
          stroke="url(#gaugeGradient)"
          strokeWidth={dimensions.strokeWidth}
          strokeLinecap="round"
        />

        {/* Tick marks */}
        {[0, 45, 90, 135, 180].map((angle) => {
          const tickRadius = radius + dimensions.strokeWidth / 2 + 2;
          const tickRadians = (angle - 180) * (Math.PI / 180);
          const x1 = cx + tickRadius * Math.cos(tickRadians);
          const y1 = cy + tickRadius * Math.sin(tickRadians);
          const x2 = cx + (tickRadius + 5) * Math.cos(tickRadians);
          const y2 = cy + (tickRadius + 5) * Math.sin(tickRadians);
          return (
            <line
              key={angle}
              x1={x1}
              y1={y1}
              x2={x2}
              y2={y2}
              stroke="#434651"
              strokeWidth={1}
            />
          );
        })}

        {/* Needle */}
        <line
          x1={cx}
          y1={cy}
          x2={needleX}
          y2={needleY}
          stroke="#d1d4dc"
          strokeWidth={2}
          strokeLinecap="round"
          filter="url(#needleShadow)"
        />
        
        {/* Needle center dot */}
        <circle cx={cx} cy={cy} r={6} fill="#d1d4dc" />
        <circle cx={cx} cy={cy} r={3} fill="#131722" />

        {/* Labels around the arc */}
        <text x={15} y={cy - 5} fill="#787b86" fontSize={10} textAnchor="start">
          Strong sell
        </text>
        <text x={dimensions.width / 4} y={30} fill="#787b86" fontSize={10} textAnchor="middle">
          Sell
        </text>
        <text x={dimensions.width / 2} y={15} fill="#787b86" fontSize={10} textAnchor="middle">
          Neutral
        </text>
        <text x={(dimensions.width * 3) / 4} y={30} fill="#787b86" fontSize={10} textAnchor="middle">
          Buy
        </text>
        <text x={dimensions.width - 15} y={cy - 5} fill={signalColors.strong_buy} fontSize={10} textAnchor="end">
          Strong buy
        </text>
      </svg>

      {/* Signal label */}
      <div 
        className="text-lg font-bold mt-1"
        style={{ color: signalColors[signal] }}
      >
        {signalLabels[signal]}
      </div>

      {/* Counts row */}
      {(sellCount !== undefined || neutralCount !== undefined || buyCount !== undefined) && (
        <div className="flex items-center gap-6 mt-3 text-sm">
          <div className="text-center">
            <div className="text-[#787b86]">Sell</div>
            <div className="font-bold text-[#d1d4dc]">{sellCount ?? '-'}</div>
          </div>
          <div className="text-center">
            <div className="text-[#787b86]">Neutral</div>
            <div className="font-bold text-[#d1d4dc]">{neutralCount ?? '-'}</div>
          </div>
          <div className="text-center">
            <div className="text-[#787b86]">Buy</div>
            <div className="font-bold text-[#d1d4dc]">{buyCount ?? '-'}</div>
          </div>
        </div>
      )}
    </div>
  );
}

// Helper function to describe an arc path
function describeArc(cx: number, cy: number, radius: number, startAngle: number, endAngle: number): string {
  const start = polarToCartesian(cx, cy, radius, endAngle - 180);
  const end = polarToCartesian(cx, cy, radius, startAngle - 180);
  const largeArcFlag = endAngle - startAngle <= 180 ? '0' : '1';
  return `M ${start.x} ${start.y} A ${radius} ${radius} 0 ${largeArcFlag} 0 ${end.x} ${end.y}`;
}

function polarToCartesian(cx: number, cy: number, radius: number, angleInDegrees: number) {
  const angleInRadians = (angleInDegrees * Math.PI) / 180.0;
  return {
    x: cx + radius * Math.cos(angleInRadians),
    y: cy + radius * Math.sin(angleInRadians),
  };
}

// =============================================================================
// Mini gauge for sidebar / compact views
// =============================================================================

interface MiniGaugeProps {
  value: number;
  signal: Signal;
  label?: string;
}

export function MiniTechnicalGauge({ value, signal, label }: MiniGaugeProps) {
  const needleAngle = (value / 100) * 180;
  
  return (
    <div className="flex items-center gap-3">
      <svg width={60} height={35} viewBox="0 0 60 35">
        <defs>
          <linearGradient id="miniGaugeGrad" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="#f23645" />
            <stop offset="50%" stopColor="#787b86" />
            <stop offset="100%" stopColor="#22ab94" />
          </linearGradient>
        </defs>
        
        {/* Arc */}
        <path
          d="M 5 30 A 25 25 0 0 1 55 30"
          fill="none"
          stroke="url(#miniGaugeGrad)"
          strokeWidth={4}
          strokeLinecap="round"
        />
        
        {/* Needle */}
        {(() => {
          const cx = 30;
          const cy = 30;
          const needleLength = 18;
          const needleRadians = (needleAngle - 180) * (Math.PI / 180);
          const needleX = cx + needleLength * Math.cos(needleRadians);
          const needleY = cy + needleLength * Math.sin(needleRadians);
          return (
            <>
              <line x1={cx} y1={cy} x2={needleX} y2={needleY} stroke="#d1d4dc" strokeWidth={1.5} />
              <circle cx={cx} cy={cy} r={2} fill="#d1d4dc" />
            </>
          );
        })()}
      </svg>
      
      <div>
        <div 
          className="text-sm font-bold"
          style={{ color: signalColors[signal] }}
        >
          {signalLabels[signal]}
        </div>
        {label && <div className="text-[10px] text-[#787b86]">{label}</div>}
      </div>
    </div>
  );
}

export default TechnicalGauge;
