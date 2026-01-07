<template>
    <div class="page-legislation">
        <div style="padding: 40px; max-width: 1400px; margin: 128px auto 0;">
            <!-- Page Header -->
            <div style="margin-bottom: 40px;">
                <h1 style="font-size: 32px; font-weight: 700; margin-bottom: 8px;">Legislation &amp; Policy</h1>
                <p style="font-size: 16px; opacity: 0.6;">Regulatory calendar, active bills, executive orders, and policy impact analysis</p>
            </div>

            <!-- Alert Banner -->
            <div style="background: rgba(239, 83, 80, 0.1); border: 1px solid rgba(239, 83, 80, 0.3); border-radius: 8px; padding: 16px 20px; margin-bottom: 32px; display: flex; align-items: center; gap: 12px;">
                <svg style="width: 20px; height: 20px; color: #ef5350; flex-shrink: 0;" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
                </svg>
                <div>
                    <span style="font-weight: 600; color: #ef5350;">HIGH ALERT:</span>
                    <span style="opacity: 0.9;"> Section 301 tariff review deadline in 12 days — potential 25% duty on Chinese vegetable oil imports</span>
                </div>
                <div style="margin-left: auto; display: flex; gap: 8px;">
                    <span style="background: rgba(239, 83, 80, 0.2); padding: 4px 10px; border-radius: 4px; font-size: 11px; font-weight: 600; color: #ef5350;">TARIFF</span>
                    <span style="background: rgba(239, 83, 80, 0.2); padding: 4px 10px; border-radius: 4px; font-size: 11px; font-weight: 600; color: #ef5350;">CHINA</span>
                </div>
            </div>

            <!-- Main Grid -->
            <div style="display: grid; grid-template-columns: 1fr 360px; gap: 24px;">
                
                <!-- Left Column -->
                <div style="display: flex; flex-direction: column; gap: 24px;">
                    
                    <!-- Regulatory Calendar -->
                    <div style="background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.1); border-radius: 12px; padding: 24px;">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
                            <h2 style="font-size: 18px; font-weight: 600;">Regulatory Calendar</h2>
                            <div style="display: flex; gap: 8px;">
                                <button style="background: rgba(255,255,255,0.1); border: 1px solid rgba(255,255,255,0.2); color: #fff; padding: 6px 12px; border-radius: 6px; font-size: 12px; cursor: pointer;">This Week</button>
                                <button style="background: transparent; border: 1px solid rgba(255,255,255,0.1); color: #fff; padding: 6px 12px; border-radius: 6px; font-size: 12px; cursor: pointer; opacity: 0.7;">This Month</button>
                            </div>
                        </div>
                        
                        <!-- Calendar Events -->
                        <div style="display: flex; flex-direction: column; gap: 12px;">
                            <!-- Event 1 -->
                            <div style="display: flex; gap: 16px; padding: 16px; background: rgba(255,255,255,0.03); border-radius: 8px; border-left: 3px solid #ef5350;">
                                <div style="text-align: center; min-width: 48px;">
                                    <div style="font-size: 24px; font-weight: 700;">15</div>
                                    <div style="font-size: 11px; opacity: 0.6; text-transform: uppercase;">Jan</div>
                                </div>
                                <div style="flex: 1;">
                                    <div style="font-weight: 600; margin-bottom: 4px;">Section 301 Tariff Review Deadline</div>
                                    <div style="font-size: 13px; opacity: 0.7; margin-bottom: 8px;">USTR decision on Chinese vegetable oil duties. 25% tariff possible.</div>
                                    <div style="display: flex; gap: 6px;">
                                        <span style="background: rgba(239, 83, 80, 0.2); padding: 2px 8px; border-radius: 4px; font-size: 10px; font-weight: 600; color: #ef5350;">HIGH IMPACT</span>
                                        <span style="background: rgba(255,255,255,0.1); padding: 2px 8px; border-radius: 4px; font-size: 10px; opacity: 0.8;">Tariff</span>
                                        <span style="background: rgba(255,255,255,0.1); padding: 2px 8px; border-radius: 4px; font-size: 10px; opacity: 0.8;">China</span>
                                    </div>
                                </div>
                                <div style="text-align: right; min-width: 80px;">
                                    <div style="font-size: 11px; opacity: 0.5;">Model Impact</div>
                                    <div style="font-size: 18px; font-weight: 700; color: #ef5350;">+4.2%</div>
                                </div>
                            </div>

                            <!-- Event 2 -->
                            <div style="display: flex; gap: 16px; padding: 16px; background: rgba(255,255,255,0.03); border-radius: 8px; border-left: 3px solid #ffb464;">
                                <div style="text-align: center; min-width: 48px;">
                                    <div style="font-size: 24px; font-weight: 700;">10</div>
                                    <div style="font-size: 11px; opacity: 0.6; text-transform: uppercase;">Jan</div>
                                </div>
                                <div style="flex: 1;">
                                    <div style="font-weight: 600; margin-bottom: 4px;">WASDE Report Release</div>
                                    <div style="font-size: 13px; opacity: 0.7; margin-bottom: 8px;">USDA World Agricultural Supply and Demand Estimates. Key soybean data.</div>
                                    <div style="display: flex; gap: 6px;">
                                        <span style="background: rgba(255, 180, 100, 0.2); padding: 2px 8px; border-radius: 4px; font-size: 10px; font-weight: 600; color: #ffb464;">MEDIUM IMPACT</span>
                                        <span style="background: rgba(255,255,255,0.1); padding: 2px 8px; border-radius: 4px; font-size: 10px; opacity: 0.8;">USDA</span>
                                        <span style="background: rgba(255,255,255,0.1); padding: 2px 8px; border-radius: 4px; font-size: 10px; opacity: 0.8;">Supply</span>
                                    </div>
                                </div>
                                <div style="text-align: right; min-width: 80px;">
                                    <div style="font-size: 11px; opacity: 0.5;">Model Impact</div>
                                    <div style="font-size: 18px; font-weight: 700; color: #ffb464;">±1.8%</div>
                                </div>
                            </div>

                            <!-- Event 3 -->
                            <div style="display: flex; gap: 16px; padding: 16px; background: rgba(255,255,255,0.03); border-radius: 8px; border-left: 3px solid #2962FF;">
                                <div style="text-align: center; min-width: 48px;">
                                    <div style="font-size: 24px; font-weight: 700;">29</div>
                                    <div style="font-size: 11px; opacity: 0.6; text-transform: uppercase;">Jan</div>
                                </div>
                                <div style="flex: 1;">
                                    <div style="font-weight: 600; margin-bottom: 4px;">FOMC Interest Rate Decision</div>
                                    <div style="font-size: 13px; opacity: 0.7; margin-bottom: 8px;">Federal Reserve policy announcement. Expected hold at current rates.</div>
                                    <div style="display: flex; gap: 6px;">
                                        <span style="background: rgba(41, 98, 255, 0.2); padding: 2px 8px; border-radius: 4px; font-size: 10px; font-weight: 600; color: #2962FF;">LOW IMPACT</span>
                                        <span style="background: rgba(255,255,255,0.1); padding: 2px 8px; border-radius: 4px; font-size: 10px; opacity: 0.8;">Fed</span>
                                        <span style="background: rgba(255,255,255,0.1); padding: 2px 8px; border-radius: 4px; font-size: 10px; opacity: 0.8;">Rates</span>
                                    </div>
                                </div>
                                <div style="text-align: right; min-width: 80px;">
                                    <div style="font-size: 11px; opacity: 0.5;">Model Impact</div>
                                    <div style="font-size: 18px; font-weight: 700; color: #2962FF;">±0.5%</div>
                                </div>
                            </div>

                            <!-- Event 4 -->
                            <div style="display: flex; gap: 16px; padding: 16px; background: rgba(255,255,255,0.03); border-radius: 8px; border-left: 3px solid #ffb464;">
                                <div style="text-align: center; min-width: 48px;">
                                    <div style="font-size: 24px; font-weight: 700;">01</div>
                                    <div style="font-size: 11px; opacity: 0.6; text-transform: uppercase;">Feb</div>
                                </div>
                                <div style="flex: 1;">
                                    <div style="font-weight: 600; margin-bottom: 4px;">EPA RFS Volume Obligation Deadline</div>
                                    <div style="font-size: 13px; opacity: 0.7; margin-bottom: 8px;">2026 Renewable Fuel Standard compliance volumes finalized.</div>
                                    <div style="display: flex; gap: 6px;">
                                        <span style="background: rgba(255, 180, 100, 0.2); padding: 2px 8px; border-radius: 4px; font-size: 10px; font-weight: 600; color: #ffb464;">MEDIUM IMPACT</span>
                                        <span style="background: rgba(255,255,255,0.1); padding: 2px 8px; border-radius: 4px; font-size: 10px; opacity: 0.8;">Biofuel</span>
                                        <span style="background: rgba(255,255,255,0.1); padding: 2px 8px; border-radius: 4px; font-size: 10px; opacity: 0.8;">EPA</span>
                                    </div>
                                </div>
                                <div style="text-align: right; min-width: 80px;">
                                    <div style="font-size: 11px; opacity: 0.5;">Model Impact</div>
                                    <div style="font-size: 18px; font-weight: 700; color: #ffb464;">+2.1%</div>
                                </div>
                            </div>
                        </div>
                    </div>

                    <!-- Active Legislation -->
                    <div style="background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.1); border-radius: 12px; padding: 24px;">
                        <h2 style="font-size: 18px; font-weight: 600; margin-bottom: 20px;">Active Legislation</h2>
                        
                        <div style="display: flex; flex-direction: column; gap: 16px;">
                            <!-- Bill 1 -->
                            <div style="padding: 16px; background: rgba(255,255,255,0.03); border-radius: 8px;">
                                <div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 12px;">
                                    <div>
                                        <div style="font-weight: 600; margin-bottom: 4px;">H.R. 4521 — Biofuel Infrastructure Investment Act</div>
                                        <div style="font-size: 13px; opacity: 0.6;">Sponsor: Rep. Johnson (R-SD) • Introduced: Nov 15, 2025</div>
                                    </div>
                                    <div style="background: rgba(41, 98, 255, 0.2); padding: 4px 10px; border-radius: 4px; font-size: 11px; font-weight: 600; color: #2962FF;">IN COMMITTEE</div>
                                </div>
                                <div style="font-size: 13px; opacity: 0.8; margin-bottom: 12px;">$2.4B authorization for renewable diesel infrastructure. Expands blender tax credits through 2030.</div>
                                <div style="display: flex; justify-content: space-between; align-items: center;">
                                    <div style="display: flex; gap: 6px;">
                                        <span style="background: rgba(255,255,255,0.1); padding: 2px 8px; border-radius: 4px; font-size: 10px;">Biofuel</span>
                                        <span style="background: rgba(255,255,255,0.1); padding: 2px 8px; border-radius: 4px; font-size: 10px;">Energy</span>
                                    </div>
                                    <div style="font-size: 12px;">
                                        <span style="opacity: 0.5;">Passage Odds:</span>
                                        <span style="font-weight: 600; color: #2962FF;"> 68%</span>
                                    </div>
                                </div>
                                <!-- Progress Bar -->
                                <div style="margin-top: 12px;">
                                    <div style="display: flex; justify-content: space-between; font-size: 10px; opacity: 0.5; margin-bottom: 4px;">
                                        <span>Introduced</span>
                                        <span>Committee</span>
                                        <span>Floor Vote</span>
                                        <span>Signed</span>
                                    </div>
                                    <div style="height: 4px; background: rgba(255,255,255,0.1); border-radius: 2px; overflow: hidden;">
                                        <div style="width: 35%; height: 100%; background: #2962FF; border-radius: 2px;"></div>
                                    </div>
                                </div>
                            </div>

                            <!-- Bill 2 -->
                            <div style="padding: 16px; background: rgba(255,255,255,0.03); border-radius: 8px;">
                                <div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 12px;">
                                    <div>
                                        <div style="font-weight: 600; margin-bottom: 4px;">S. 892 — Fair Agricultural Trade Act</div>
                                        <div style="font-size: 13px; opacity: 0.6;">Sponsor: Sen. Grassley (R-IA) • Introduced: Dec 3, 2025</div>
                                    </div>
                                    <div style="background: rgba(255, 180, 100, 0.2); padding: 4px 10px; border-radius: 4px; font-size: 11px; font-weight: 600; color: #ffb464;">MARKUP</div>
                                </div>
                                <div style="font-size: 13px; opacity: 0.8; margin-bottom: 12px;">Retaliatory tariff authority for agricultural exports. Targets Chinese non-tariff barriers.</div>
                                <div style="display: flex; justify-content: space-between; align-items: center;">
                                    <div style="display: flex; gap: 6px;">
                                        <span style="background: rgba(255,255,255,0.1); padding: 2px 8px; border-radius: 4px; font-size: 10px;">Tariff</span>
                                        <span style="background: rgba(255,255,255,0.1); padding: 2px 8px; border-radius: 4px; font-size: 10px;">China</span>
                                    </div>
                                    <div style="font-size: 12px;">
                                        <span style="opacity: 0.5;">Passage Odds:</span>
                                        <span style="font-weight: 600; color: #ffb464;"> 45%</span>
                                    </div>
                                </div>
                                <div style="margin-top: 12px;">
                                    <div style="display: flex; justify-content: space-between; font-size: 10px; opacity: 0.5; margin-bottom: 4px;">
                                        <span>Introduced</span>
                                        <span>Committee</span>
                                        <span>Floor Vote</span>
                                        <span>Signed</span>
                                    </div>
                                    <div style="height: 4px; background: rgba(255,255,255,0.1); border-radius: 2px; overflow: hidden;">
                                        <div style="width: 25%; height: 100%; background: #ffb464; border-radius: 2px;"></div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- Right Sidebar -->
                <div style="display: flex; flex-direction: column; gap: 24px;">
                    
                    <!-- Executive Orders -->
                    <div style="background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.1); border-radius: 12px; padding: 24px;">
                        <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 20px;">
                            <svg style="width: 20px; height: 20px; opacity: 0.8;" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                                <path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/>
                            </svg>
                            <h2 style="font-size: 18px; font-weight: 600;">Executive Orders</h2>
                        </div>
                        
                        <div style="display: flex; flex-direction: column; gap: 12px;">
                            <!-- EO 1 -->
                            <div style="padding: 12px; background: rgba(255,255,255,0.03); border-radius: 8px; border-left: 3px solid #ef5350;">
                                <div style="font-size: 11px; opacity: 0.5; margin-bottom: 4px;">EO 14178 • Dec 20, 2025</div>
                                <div style="font-weight: 600; font-size: 14px; margin-bottom: 6px;">Energy Independence Acceleration</div>
                                <div style="font-size: 12px; opacity: 0.7; margin-bottom: 8px;">Fast-track permitting for domestic biofuel refineries. 90-day review mandate.</div>
                                <div style="display: flex; gap: 4px;">
                                    <span style="background: rgba(41, 98, 255, 0.2); padding: 2px 6px; border-radius: 3px; font-size: 9px; color: #2962FF;">Biofuel ↑</span>
                                    <span style="background: rgba(41, 98, 255, 0.2); padding: 2px 6px; border-radius: 3px; font-size: 9px; color: #2962FF;">Energy ↑</span>
                                </div>
                            </div>

                            <!-- EO 2 -->
                            <div style="padding: 12px; background: rgba(255,255,255,0.03); border-radius: 8px; border-left: 3px solid #ffb464;">
                                <div style="font-size: 11px; opacity: 0.5; margin-bottom: 4px;">EO 14175 • Dec 12, 2025</div>
                                <div style="font-weight: 600; font-size: 14px; margin-bottom: 6px;">Trade Enforcement Modernization</div>
                                <div style="font-size: 12px; opacity: 0.7; margin-bottom: 8px;">Expanded USTR authority for agricultural tariff negotiations.</div>
                                <div style="display: flex; gap: 4px;">
                                    <span style="background: rgba(255, 180, 100, 0.2); padding: 2px 6px; border-radius: 3px; font-size: 9px; color: #ffb464;">Tariff ↔</span>
                                    <span style="background: rgba(239, 83, 80, 0.2); padding: 2px 6px; border-radius: 3px; font-size: 9px; color: #ef5350;">China ↓</span>
                                </div>
                            </div>

                            <!-- EO 3 -->
                            <div style="padding: 12px; background: rgba(255,255,255,0.03); border-radius: 8px; border-left: 3px solid #2962FF;">
                                <div style="font-size: 11px; opacity: 0.5; margin-bottom: 4px;">EO 14172 • Nov 28, 2025</div>
                                <div style="font-weight: 600; font-size: 14px; margin-bottom: 6px;">SAF Production Tax Credit Extension</div>
                                <div style="font-size: 12px; opacity: 0.7; margin-bottom: 8px;">Sustainable Aviation Fuel credits extended to 2032. $1.75/gal incentive.</div>
                                <div style="display: flex; gap: 4px;">
                                    <span style="background: rgba(41, 98, 255, 0.2); padding: 2px 6px; border-radius: 3px; font-size: 9px; color: #2962FF;">Biofuel ↑</span>
                                </div>
                            </div>
                        </div>
                    </div>

                    <!-- Policy Impact Matrix -->
                    <div style="background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.1); border-radius: 12px; padding: 24px;">
                        <h2 style="font-size: 18px; font-weight: 600; margin-bottom: 20px;">Specialist Impact</h2>
                        
                        <div style="display: flex; flex-direction: column; gap: 10px;">
                            <div style="display: flex; justify-content: space-between; align-items: center; padding: 8px 0; border-bottom: 1px solid rgba(255,255,255,0.05);">
                                <span style="font-size: 13px;">Tariff Regime</span>
                                <div style="display: flex; align-items: center; gap: 8px;">
                                    <div style="width: 80px; height: 6px; background: rgba(255,255,255,0.1); border-radius: 3px; overflow: hidden;">
                                        <div style="width: 85%; height: 100%; background: #ef5350;"></div>
                                    </div>
                                    <span style="font-size: 12px; font-weight: 600; color: #ef5350; min-width: 32px;">HIGH</span>
                                </div>
                            </div>
                            <div style="display: flex; justify-content: space-between; align-items: center; padding: 8px 0; border-bottom: 1px solid rgba(255,255,255,0.05);">
                                <span style="font-size: 13px;">Biofuel Mandate</span>
                                <div style="display: flex; align-items: center; gap: 8px;">
                                    <div style="width: 80px; height: 6px; background: rgba(255,255,255,0.1); border-radius: 3px; overflow: hidden;">
                                        <div style="width: 78%; height: 100%; background: #ef5350;"></div>
                                    </div>
                                    <span style="font-size: 12px; font-weight: 600; color: #ef5350; min-width: 32px;">HIGH</span>
                                </div>
                            </div>
                            <div style="display: flex; justify-content: space-between; align-items: center; padding: 8px 0; border-bottom: 1px solid rgba(255,255,255,0.05);">
                                <span style="font-size: 13px;">China Demand</span>
                                <div style="display: flex; align-items: center; gap: 8px;">
                                    <div style="width: 80px; height: 6px; background: rgba(255,255,255,0.1); border-radius: 3px; overflow: hidden;">
                                        <div style="width: 72%; height: 100%; background: #ffb464;"></div>
                                    </div>
                                    <span style="font-size: 12px; font-weight: 600; color: #ffb464; min-width: 32px;">MED</span>
                                </div>
                            </div>
                            <div style="display: flex; justify-content: space-between; align-items: center; padding: 8px 0; border-bottom: 1px solid rgba(255,255,255,0.05);">
                                <span style="font-size: 13px;">Trump Effect</span>
                                <div style="display: flex; align-items: center; gap: 8px;">
                                    <div style="width: 80px; height: 6px; background: rgba(255,255,255,0.1); border-radius: 3px; overflow: hidden;">
                                        <div style="width: 68%; height: 100%; background: #ffb464;"></div>
                                    </div>
                                    <span style="font-size: 12px; font-weight: 600; color: #ffb464; min-width: 32px;">MED</span>
                                </div>
                            </div>
                            <div style="display: flex; justify-content: space-between; align-items: center; padding: 8px 0; border-bottom: 1px solid rgba(255,255,255,0.05);">
                                <span style="font-size: 13px;">Energy Complex</span>
                                <div style="display: flex; align-items: center; gap: 8px;">
                                    <div style="width: 80px; height: 6px; background: rgba(255,255,255,0.1); border-radius: 3px; overflow: hidden;">
                                        <div style="width: 45%; height: 100%; background: #2962FF;"></div>
                                    </div>
                                    <span style="font-size: 12px; font-weight: 600; color: #2962FF; min-width: 32px;">LOW</span>
                                </div>
                            </div>
                            <div style="display: flex; justify-content: space-between; align-items: center; padding: 8px 0;">
                                <span style="font-size: 13px;">Fed Policy</span>
                                <div style="display: flex; align-items: center; gap: 8px;">
                                    <div style="width: 80px; height: 6px; background: rgba(255,255,255,0.1); border-radius: 3px; overflow: hidden;">
                                        <div style="width: 25%; height: 100%; background: #2962FF;"></div>
                                    </div>
                                    <span style="font-size: 12px; font-weight: 600; color: #2962FF; min-width: 32px;">LOW</span>
                                </div>
                            </div>
                        </div>
                    </div>

                    <!-- Policy Volatility Index -->
                    <div style="background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.1); border-radius: 12px; padding: 24px; text-align: center;">
                        <div style="font-size: 12px; opacity: 0.6; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 12px;">Policy Volatility Index</div>
                        <div style="font-size: 48px; font-weight: 700; color: #ef5350; margin-bottom: 8px;">0.74</div>
                        <div style="font-size: 13px; opacity: 0.7;">ELEVATED</div>
                        <div style="font-size: 11px; opacity: 0.5; margin-top: 8px;">↑ 0.12 from last week</div>
                    </div>
                </div>
            </div>
        </div>
    </div>
</template>

<script setup>
</script>

<style scoped>
</style>
