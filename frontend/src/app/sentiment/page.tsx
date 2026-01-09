'use client';

import React from 'react';
import { OrganicTopicCloud } from '@/components/viz/OrganicTopicCloud';
import { MessageSquare, Twitter, TrendingUp, AlertOctagon, Scale } from 'lucide-react';

export default function SentimentPage() {
  return (
    <div className="min-h-screen bg-[#0a0a0a] text-slate-200 p-6 pb-20 animate-in fade-in duration-700">
      
        {/* Header */}
        <div className="flex items-center justify-between mb-8 pb-4 border-b border-white/5">
            <div>
                <h1 className="text-3xl font-bold text-white tracking-tight">MARKET PSYCHOLOGY</h1>
                <p className="text-slate-400 text-sm font-mono mt-1">NARRATIVE CLUSTERING // UNSTRUCTURED DATA FUSION</p>
            </div>
            <div className="flex items-center gap-6">
                <div className="text-right">
                    <div className="text-2xl font-bold text-emerald-400">+0.72σ</div>
                    <div className="text-[10px] text-slate-500 uppercase tracking-widest">Bullish Bias</div>
                </div>
            </div>
        </div>

        {/* Narrative Cloud - The Living Component */}
        <div className="mb-8">
            <h3 className="text-lg font-bold text-white mb-4 flex items-center gap-2">
                <MessageSquare size={18} className="text-blue-400" />
                Active Narrative Clusters
            </h3>
            <div className="w-full bg-[#0a0a0a] border border-white/5 rounded-2xl p-1 overflow-hidden shadow-2xl relative">
                 <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_right,rgba(59,130,246,0.05),transparent_60%)] pointer-events-none" />
                 <OrganicTopicCloud />

                 {/* Legend */}
                 <div className="absolute bottom-6 left-6 p-4 bg-black/40 backdrop-blur border border-white/10 rounded-xl max-w-xs pointer-events-none">
                     <h4 className="text-xs font-bold text-white mb-2 uppercase">Size = Impact</h4>
                     <p className="text-[10px] text-slate-400">
                         Bubble dynamics driven by mention volume and sentiment intensity.
                         <br/>
                         Physics simulation enabled.
                     </p>
                 </div>
            </div>
        </div>

        {/* Lower Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
            
            {/* News Feed - Updated UI */}
            <div>
                <h3 className="text-lg font-bold text-white mb-4 flex items-center gap-2">
                    <TrendingUp size={18} className="text-slate-400" />
                    High Impact Headlines
                </h3>
                <div className="space-y-4">
                    <HeadlineCard 
                        sentiment="bullish" 
                        source="EPA.gov" 
                        time="2h ago"
                        title="EPA signals strong biodiesel mandate for 2025"
                        summary="Sources indicate final RVO rule will exceed industry expectations, supporting soybean oil demand profile."
                        tags={['BIOFUEL', 'REGULATION']}
                    />
                    <HeadlineCard 
                        sentiment="bearish" 
                        source="Truth Social" 
                        time="5h ago"
                        title="Trump threatens 25% China tariffs on Day 1"
                        summary="Direct executive action threat increases probability of retaliatory trade barriers on US exports."
                        tags={['TRUMP', 'TRADE WAR']}
                    />
                    <HeadlineCard 
                        sentiment="bullish" 
                        source="USDA" 
                        time="12h ago"
                        title="USDA export sales beat expectations"
                        summary="Weekly soybean export sales up 23% vs 4-week average. Unexpected China buying volume."
                        tags={['CHINA', 'EXPORTS']}
                    />
                </div>
            </div>

            {/* COT & Metrics */}
            <div className="space-y-8">
                
                {/* COT */}
                <div className="bg-[#0a0a0a] border border-white/5 rounded-xl p-6">
                     <div className="flex items-center justify-between mb-6">
                        <h3 className="text-lg font-bold text-white flex items-center gap-2">
                            <Scale size={18} className="text-slate-400" />
                            Smart Money (COT)
                        </h3>
                        <span className="text-xs font-mono text-emerald-400">NET LONG +42k</span>
                     </div>
                     
                     <div className="space-y-6">
                        <CotBar label="Managed Money" value={65} color="bg-emerald-500" valueText="+42,150" type="bullish" />
                        <CotBar label="Producers / Commercials" value={40} color="bg-red-500" valueText="-38,200" type="bearish" />
                        <CotBar label="Swap Dealers" value={48} color="bg-slate-500" valueText="-2,450" type="neutral" />
                     </div>
                </div>

                {/* Social Meters */}
                <div className="grid grid-cols-2 gap-4">
                    <div className="bg-[#0a0a0a] border border-white/5 rounded-xl p-6 text-center shadow-lg shadow-black/50">
                        <Twitter className="w-6 h-6 text-blue-400 mx-auto mb-2" />
                        <div className="text-2xl font-bold text-white">1.2k</div>
                        <div className="text-xs text-slate-500 uppercase">Mentions (24h)</div>
                    </div>
                    <div className="bg-[#0a0a0a] border border-white/5 rounded-xl p-6 text-center shadow-lg shadow-black/50">
                        <AlertOctagon className="w-6 h-6 text-amber-400 mx-auto mb-2" />
                        <div className="text-2xl font-bold text-amber-400">Elevated</div>
                        <div className="text-xs text-slate-500 uppercase">Fear Index</div>
                    </div>
                </div>

            </div>
        </div>

    </div>
  );
}

function HeadlineCard({ sentiment, source, time, title, summary, tags }: any) {
    const borderColor = sentiment === 'bullish' ? 'border-l-emerald-500' : sentiment === 'bearish' ? 'border-l-red-500' : 'border-l-slate-500';
    const textColor = sentiment === 'bullish' ? 'text-emerald-400' : sentiment === 'bearish' ? 'text-red-400' : 'text-slate-400';
    
    return (
        <div className={`bg-[#0a0a0a] border border-white/5 border-l-4 ${borderColor} rounded-r-xl p-4 hover:bg-white/[0.02] transition-colors`}>
            <div className="flex justify-between items-start mb-2">
                <div className="flex items-center gap-2">
                    <span className={`text-xs font-bold uppercase ${textColor}`}>{sentiment}</span>
                    <span className="text-xs text-slate-600">•</span>
                    <span className="text-xs text-slate-500">{source}</span>
                </div>
                <span className="text-xs text-slate-600 font-mono">{time}</span>
            </div>
            <h4 className="text-sm font-bold text-white mb-2 leading-tight">{title}</h4>
            <p className="text-xs text-slate-400 mb-3 leading-relaxed">{summary}</p>
            <div className="flex gap-2">
                {tags.map((t: string) => (
                    <span key={t} className="px-1.5 py-0.5 rounded bg-white/5 text-[10px] text-slate-400 font-mono border border-white/5">
                        {t}
                    </span>
                ))}
            </div>
        </div>
    );
}

function CotBar({ label, value, color, valueText, type }: any) {
    return (
        <div>
            <div className="flex justify-between text-xs mb-2">
                <span className="text-slate-400">{label}</span>
                <span className={type === 'bullish' ? 'text-emerald-400' : type === 'bearish' ? 'text-red-400' : 'text-slate-500'}>
                    {valueText}
                </span>
            </div>
            <div className="h-2 bg-slate-800 rounded-full overflow-hidden">
                <div className={`h-full ${color}`} style={{ width: `${value}%` }} />
            </div>
        </div>
    );
}
