<template>
    <div class="page-strategy">
        <div style="padding: 40px; max-width: 1400px; margin: 128px auto 0;">
            <!-- Page Header -->
            <div style="margin-bottom: 40px;">
                <h1 style="font-size: 32px; font-weight: 700; margin-bottom: 8px;">Procurement Strategy</h1>
                <p style="font-size: 16px; opacity: 0.6;">Model-driven posture recommendations, scenario analysis, and entry point guidance</p>
            </div>

            <!-- Main Posture Card -->
            <div style="background: linear-gradient(135deg, rgba(255,255,255,0.04) 0%, rgba(255,255,255,0.01) 100%); border: 1px solid rgba(255,255,255,0.15); border-radius: 16px; padding: 40px; margin-bottom: 32px; position: relative; overflow: hidden;">
                <div style="position: absolute; top: 0; right: 0; width: 300px; height: 300px; background: radial-gradient(circle, rgba(120,123,134,0.1) 0%, transparent 70%); pointer-events: none;"></div>
                
                <div style="display: grid; grid-template-columns: 200px 1fr auto; gap: 40px; align-items: center;">
                    <!-- Posture Badge -->
                    <div style="text-align: center;">
                        <div style="font-size: 11px; opacity: 0.5; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 12px;">Current Posture</div>
                        <div style="font-size: 64px; font-weight: 700; color: #787B86; letter-spacing: 2px; line-height: 1;">WAIT</div>
                        <div style="font-size: 13px; opacity: 0.6; margin-top: 8px;">Since Jan 2, 2026</div>
                    </div>
                    
                    <!-- Reasoning -->
                    <div style="border-left: 1px solid rgba(255,255,255,0.1); padding-left: 40px;">
                        <div style="font-size: 14px; font-weight: 600; margin-bottom: 12px; opacity: 0.8;">MODEL REASONING</div>
                        <div style="font-size: 15px; line-height: 1.7; opacity: 0.9;">
                            The ensemble projects <span style="color: #2962FF; font-weight: 600;">+3.4% upside</span> at the 1-month horizon with 62% bullish probability. However, the <span style="color: #ef5350; font-weight: 600;">Section 301 tariff decision</span> on Jan 15 introduces binary event risk. Current P10 floor at $46.80 suggests waiting for a pullback to the <span style="font-weight: 600;">$47.20–$47.80</span> range before initiating positions.
                        </div>
                        <div style="display: flex; gap: 16px; margin-top: 16px;">
                            <div style="display: flex; align-items: center; gap: 6px; font-size: 12px; opacity: 0.7;">
                                <span style="width: 8px; height: 8px; background: #2962FF; border-radius: 50%;"></span>
                                Crush +0.65
                            </div>
                            <div style="display: flex; align-items: center; gap: 6px; font-size: 12px; opacity: 0.7;">
                                <span style="width: 8px; height: 8px; background: #2962FF; border-radius: 50%;"></span>
                                Biofuel +0.54
                            </div>
                            <div style="display: flex; align-items: center; gap: 6px; font-size: 12px; opacity: 0.7;">
                                <span style="width: 8px; height: 8px; background: #ef5350; border-radius: 50%;"></span>
                                Tariff +0.71
                            </div>
                            <div style="display: flex; align-items: center; gap: 6px; font-size: 12px; opacity: 0.7;">
                                <span style="width: 8px; height: 8px; background: #ef5350; border-radius: 50%;"></span>
                                China -0.32
                            </div>
                        </div>
                    </div>
                    
                    <!-- Confidence Dial -->
                    <div style="text-align: center; min-width: 120px;">
                        <div style="font-size: 11px; opacity: 0.5; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 8px;">Confidence</div>
                        <div style="width: 100px; height: 100px; margin: 0 auto; position: relative;">
                            <svg viewBox="0 0 100 100" style="transform: rotate(-90deg);">
                                <circle cx="50" cy="50" r="40" fill="none" stroke="rgba(255,255,255,0.1)" stroke-width="8"/>
                                <circle cx="50" cy="50" r="40" fill="none" stroke="#787B86" stroke-width="8" stroke-dasharray="181" stroke-dashoffset="50" stroke-linecap="round"/>
                            </svg>
                            <div style="position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; font-size: 24px; font-weight: 700;">72%</div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Main Grid -->
            <div style="display: grid; grid-template-columns: 1fr 360px; gap: 24px;">
                
                <!-- Left Column -->
                <div style="display: flex; flex-direction: column; gap: 24px;">
                    
                    <!-- Horizon Recommendations -->
                    <div style="background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.1); border-radius: 12px; padding: 24px;">
                        <h2 style="font-size: 18px; font-weight: 600; margin-bottom: 20px;">Horizon Analysis</h2>
                        
                        <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px;">
                            <!-- 1 Week -->
                            <div style="background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.08); border-radius: 10px; padding: 20px;">
                                <div style="font-size: 12px; opacity: 0.5; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 12px;">1 Week</div>
                                <div style="font-size: 28px; font-weight: 700; margin-bottom: 4px;">$49.12</div>
                                <div style="font-size: 14px; color: #2962FF; margin-bottom: 12px;">+0.7%</div>
                                <div style="font-size: 11px; opacity: 0.6; margin-bottom: 8px;">P10: $47.90 • P90: $50.35</div>
                                <div style="display: flex; justify-content: space-between; align-items: center; padding-top: 12px; border-top: 1px solid rgba(255,255,255,0.08);">
                                    <span style="font-size: 11px; opacity: 0.6;">Posture</span>
                                    <span style="font-size: 12px; font-weight: 600; color: #787B86;">WAIT</span>
                                </div>
                            </div>
                            
                            <!-- 1 Month -->
                            <div style="background: rgba(41, 98, 255, 0.08); border: 1px solid rgba(41, 98, 255, 0.25); border-radius: 10px; padding: 20px;">
                                <div style="font-size: 12px; opacity: 0.5; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 12px;">1 Month</div>
                                <div style="font-size: 28px; font-weight: 700; margin-bottom: 4px;">$50.45</div>
                                <div style="font-size: 14px; color: #2962FF; margin-bottom: 12px;">+3.4%</div>
                                <div style="font-size: 11px; opacity: 0.6; margin-bottom: 8px;">P10: $46.80 • P90: $54.10</div>
                                <div style="display: flex; justify-content: space-between; align-items: center; padding-top: 12px; border-top: 1px solid rgba(255,255,255,0.08);">
                                    <span style="font-size: 11px; opacity: 0.6;">Posture</span>
                                    <span style="font-size: 12px; font-weight: 600; color: #2962FF;">BUY ZONE</span>
                                </div>
                            </div>
                            
                            <!-- 3 Months -->
                            <div style="background: rgba(41, 98, 255, 0.08); border: 1px solid rgba(41, 98, 255, 0.25); border-radius: 10px; padding: 20px;">
                                <div style="font-size: 12px; opacity: 0.5; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 12px;">3 Months</div>
                                <div style="font-size: 28px; font-weight: 700; margin-bottom: 4px;">$52.18</div>
                                <div style="font-size: 14px; color: #2962FF; margin-bottom: 12px;">+7.0%</div>
                                <div style="font-size: 11px; opacity: 0.6; margin-bottom: 8px;">P10: $45.20 • P90: $58.90</div>
                                <div style="display: flex; justify-content: space-between; align-items: center; padding-top: 12px; border-top: 1px solid rgba(255,255,255,0.08);">
                                    <span style="font-size: 11px; opacity: 0.6;">Posture</span>
                                    <span style="font-size: 12px; font-weight: 600; color: #2962FF;">BUY ZONE</span>
                                </div>
                            </div>
                            
                            <!-- 6 Months -->
                            <div style="background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.08); border-radius: 10px; padding: 20px;">
                                <div style="font-size: 12px; opacity: 0.5; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 12px;">6 Months</div>
                                <div style="font-size: 28px; font-weight: 700; margin-bottom: 4px;">$54.92</div>
                                <div style="font-size: 14px; color: #2962FF; margin-bottom: 12px;">+12.6%</div>
                                <div style="font-size: 11px; opacity: 0.6; margin-bottom: 8px;">P10: $44.10 • P90: $65.80</div>
                                <div style="display: flex; justify-content: space-between; align-items: center; padding-top: 12px; border-top: 1px solid rgba(255,255,255,0.08);">
                                    <span style="font-size: 11px; opacity: 0.6;">Posture</span>
                                    <span style="font-size: 12px; font-weight: 600; color: #ffb464;">HOLD</span>
                                </div>
                            </div>
                        </div>
                    </div>

                    <!-- Scenario Analysis -->
                    <div style="background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.1); border-radius: 12px; padding: 24px;">
                        <h2 style="font-size: 18px; font-weight: 600; margin-bottom: 20px;">Scenario Analysis</h2>
                        
                        <div style="display: flex; flex-direction: column; gap: 12px;">
                            <!-- Scenario 1: Tariff Imposed -->
                            <div style="padding: 16px; background: rgba(239, 83, 80, 0.08); border: 1px solid rgba(239, 83, 80, 0.2); border-radius: 8px;">
                                <div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 10px;">
                                    <div>
                                        <div style="font-weight: 600; margin-bottom: 4px;">Section 301 Tariff Imposed (25%)</div>
                                        <div style="font-size: 12px; opacity: 0.6;">Chinese vegetable oil imports face new duties</div>
                                    </div>
                                    <div style="text-align: right;">
                                        <div style="font-size: 11px; opacity: 0.5;">Probability</div>
                                        <div style="font-size: 16px; font-weight: 600;">35%</div>
                                    </div>
                                </div>
                                <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-top: 12px;">
                                    <div style="text-align: center;">
                                        <div style="font-size: 10px; opacity: 0.5;">1w Impact</div>
                                        <div style="font-size: 14px; font-weight: 600; color: #2962FF;">+$2.40</div>
                                    </div>
                                    <div style="text-align: center;">
                                        <div style="font-size: 10px; opacity: 0.5;">1m Impact</div>
                                        <div style="font-size: 14px; font-weight: 600; color: #2962FF;">+$4.80</div>
                                    </div>
                                    <div style="text-align: center;">
                                        <div style="font-size: 10px; opacity: 0.5;">3m Impact</div>
                                        <div style="font-size: 14px; font-weight: 600; color: #2962FF;">+$3.20</div>
                                    </div>
                                    <div style="text-align: center;">
                                        <div style="font-size: 10px; opacity: 0.5;">Specialists</div>
                                        <div style="font-size: 11px; opacity: 0.8;">Tariff, China</div>
                                    </div>
                                </div>
                            </div>

                            <!-- Scenario 2: Tariff Delayed -->
                            <div style="padding: 16px; background: rgba(41, 98, 255, 0.08); border: 1px solid rgba(41, 98, 255, 0.2); border-radius: 8px;">
                                <div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 10px;">
                                    <div>
                                        <div style="font-weight: 600; margin-bottom: 4px;">Section 301 Tariff Delayed / Reduced</div>
                                        <div style="font-size: 12px; opacity: 0.6;">Negotiated settlement or phase-in period</div>
                                    </div>
                                    <div style="text-align: right;">
                                        <div style="font-size: 11px; opacity: 0.5;">Probability</div>
                                        <div style="font-size: 16px; font-weight: 600;">45%</div>
                                    </div>
                                </div>
                                <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-top: 12px;">
                                    <div style="text-align: center;">
                                        <div style="font-size: 10px; opacity: 0.5;">1w Impact</div>
                                        <div style="font-size: 14px; font-weight: 600; color: #ef5350;">-$0.80</div>
                                    </div>
                                    <div style="text-align: center;">
                                        <div style="font-size: 10px; opacity: 0.5;">1m Impact</div>
                                        <div style="font-size: 14px; font-weight: 600; color: #787B86;">+$0.40</div>
                                    </div>
                                    <div style="text-align: center;">
                                        <div style="font-size: 10px; opacity: 0.5;">3m Impact</div>
                                        <div style="font-size: 14px; font-weight: 600; color: #2962FF;">+$1.80</div>
                                    </div>
                                    <div style="text-align: center;">
                                        <div style="font-size: 10px; opacity: 0.5;">Specialists</div>
                                        <div style="font-size: 11px; opacity: 0.8;">Tariff, China, Trump</div>
                                    </div>
                                </div>
                            </div>

                            <!-- Scenario 3: Brazil Harvest Delay -->
                            <div style="padding: 16px; background: rgba(41, 98, 255, 0.08); border: 1px solid rgba(41, 98, 255, 0.2); border-radius: 8px;">
                                <div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 10px;">
                                    <div>
                                        <div style="font-weight: 600; margin-bottom: 4px;">Brazil Harvest Delay Extends (&gt;2 weeks)</div>
                                        <div style="font-size: 12px; opacity: 0.6;">Weather disruptions continue through January</div>
                                    </div>
                                    <div style="text-align: right;">
                                        <div style="font-size: 11px; opacity: 0.5;">Probability</div>
                                        <div style="font-size: 16px; font-weight: 600;">25%</div>
                                    </div>
                                </div>
                                <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-top: 12px;">
                                    <div style="text-align: center;">
                                        <div style="font-size: 10px; opacity: 0.5;">1w Impact</div>
                                        <div style="font-size: 14px; font-weight: 600; color: #2962FF;">+$1.20</div>
                                    </div>
                                    <div style="text-align: center;">
                                        <div style="font-size: 10px; opacity: 0.5;">1m Impact</div>
                                        <div style="font-size: 14px; font-weight: 600; color: #2962FF;">+$3.60</div>
                                    </div>
                                    <div style="text-align: center;">
                                        <div style="font-size: 10px; opacity: 0.5;">3m Impact</div>
                                        <div style="font-size: 14px; font-weight: 600; color: #2962FF;">+$2.40</div>
                                    </div>
                                    <div style="text-align: center;">
                                        <div style="font-size: 10px; opacity: 0.5;">Specialists</div>
                                        <div style="font-size: 11px; opacity: 0.8;">Crush, Volatility</div>
                                    </div>
                                </div>
                            </div>

                            <!-- Scenario 4: Palm Glut -->
                            <div style="padding: 16px; background: rgba(239, 83, 80, 0.08); border: 1px solid rgba(239, 83, 80, 0.2); border-radius: 8px;">
                                <div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 10px;">
                                    <div>
                                        <div style="font-weight: 600; margin-bottom: 4px;">Palm Oil Inventory Surge Accelerates</div>
                                        <div style="font-size: 12px; opacity: 0.6;">MPOB stocks exceed 2.5M tonnes</div>
                                    </div>
                                    <div style="text-align: right;">
                                        <div style="font-size: 11px; opacity: 0.5;">Probability</div>
                                        <div style="font-size: 16px; font-weight: 600;">20%</div>
                                    </div>
                                </div>
                                <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-top: 12px;">
                                    <div style="text-align: center;">
                                        <div style="font-size: 10px; opacity: 0.5;">1w Impact</div>
                                        <div style="font-size: 14px; font-weight: 600; color: #ef5350;">-$1.60</div>
                                    </div>
                                    <div style="text-align: center;">
                                        <div style="font-size: 10px; opacity: 0.5;">1m Impact</div>
                                        <div style="font-size: 14px; font-weight: 600; color: #ef5350;">-$2.80</div>
                                    </div>
                                    <div style="text-align: center;">
                                        <div style="font-size: 10px; opacity: 0.5;">3m Impact</div>
                                        <div style="font-size: 14px; font-weight: 600; color: #ef5350;">-$1.40</div>
                                    </div>
                                    <div style="text-align: center;">
                                        <div style="font-size: 10px; opacity: 0.5;">Specialists</div>
                                        <div style="font-size: 11px; opacity: 0.8;">Palm, Substitutes</div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- Right Sidebar -->
                <div style="display: flex; flex-direction: column; gap: 24px;">
                    
                    <!-- Entry Points -->
                    <div style="background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.1); border-radius: 12px; padding: 24px;">
                        <h2 style="font-size: 18px; font-weight: 600; margin-bottom: 20px;">Entry Points</h2>
                        
                        <div style="display: flex; flex-direction: column; gap: 16px;">
                            <!-- Current Price -->
                            <div style="text-align: center; padding: 16px; background: rgba(255,255,255,0.05); border-radius: 8px;">
                                <div style="font-size: 11px; opacity: 0.5; margin-bottom: 4px;">CURRENT PRICE</div>
                                <div style="font-size: 32px; font-weight: 700;">$48.78</div>
                            </div>
                            
                            <!-- Buy Zones -->
                            <div style="padding: 12px; border-left: 3px solid #2962FF; background: rgba(41, 98, 255, 0.08); border-radius: 0 8px 8px 0;">
                                <div style="display: flex; justify-content: space-between; align-items: center;">
                                    <div>
                                        <div style="font-size: 12px; color: #2962FF; font-weight: 600;">AGGRESSIVE BUY</div>
                                        <div style="font-size: 11px; opacity: 0.6;">High conviction entry</div>
                                    </div>
                                    <div style="font-size: 18px; font-weight: 700;">$47.80</div>
                                </div>
                            </div>
                            
                            <div style="padding: 12px; border-left: 3px solid #2962FF; background: rgba(41, 98, 255, 0.05); border-radius: 0 8px 8px 0;">
                                <div style="display: flex; justify-content: space-between; align-items: center;">
                                    <div>
                                        <div style="font-size: 12px; color: #2962FF; font-weight: 600;">TARGET BUY</div>
                                        <div style="font-size: 11px; opacity: 0.6;">Optimal risk/reward</div>
                                    </div>
                                    <div style="font-size: 18px; font-weight: 700;">$47.20</div>
                                </div>
                            </div>
                            
                            <div style="padding: 12px; border-left: 3px solid #787B86; background: rgba(255,255,255,0.03); border-radius: 0 8px 8px 0;">
                                <div style="display: flex; justify-content: space-between; align-items: center;">
                                    <div>
                                        <div style="font-size: 12px; opacity: 0.8; font-weight: 600;">FLOOR (P10)</div>
                                        <div style="font-size: 11px; opacity: 0.6;">1-month downside</div>
                                    </div>
                                    <div style="font-size: 18px; font-weight: 700;">$46.80</div>
                                </div>
                            </div>
                            
                            <!-- Upside Targets -->
                            <div style="margin-top: 8px; padding-top: 16px; border-top: 1px solid rgba(255,255,255,0.1);">
                                <div style="font-size: 12px; opacity: 0.6; margin-bottom: 12px;">UPSIDE TARGETS</div>
                                
                                <div style="padding: 8px 12px; border-left: 3px solid #ffb464; background: rgba(255, 180, 100, 0.08); border-radius: 0 8px 8px 0; margin-bottom: 8px;">
                                    <div style="display: flex; justify-content: space-between; align-items: center;">
                                        <span style="font-size: 12px; opacity: 0.8;">Target 1 (1m)</span>
                                        <span style="font-size: 16px; font-weight: 600;">$50.45</span>
                                    </div>
                                </div>
                                
                                <div style="padding: 8px 12px; border-left: 3px solid #ffb464; background: rgba(255, 180, 100, 0.05); border-radius: 0 8px 8px 0;">
                                    <div style="display: flex; justify-content: space-between; align-items: center;">
                                        <span style="font-size: 12px; opacity: 0.8;">Target 2 (3m)</span>
                                        <span style="font-size: 16px; font-weight: 600;">$52.18</span>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>

                    <!-- Monte Carlo Summary -->
                    <div style="background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.1); border-radius: 12px; padding: 24px;">
                        <h2 style="font-size: 18px; font-weight: 600; margin-bottom: 20px;">Monte Carlo (10K runs)</h2>
                        
                        <div style="display: flex; flex-direction: column; gap: 12px;">
                            <div style="display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid rgba(255,255,255,0.05);">
                                <span style="font-size: 13px; opacity: 0.7;">P90 (Ceiling)</span>
                                <span style="font-size: 13px; font-weight: 600; color: #2962FF;">$54.10</span>
                            </div>
                            <div style="display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid rgba(255,255,255,0.05);">
                                <span style="font-size: 13px; opacity: 0.7;">P75</span>
                                <span style="font-size: 13px; font-weight: 600;">$51.80</span>
                            </div>
                            <div style="display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid rgba(255,255,255,0.05);">
                                <span style="font-size: 13px; opacity: 0.7;">P50 (Median)</span>
                                <span style="font-size: 13px; font-weight: 600;">$50.45</span>
                            </div>
                            <div style="display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid rgba(255,255,255,0.05);">
                                <span style="font-size: 13px; opacity: 0.7;">P25</span>
                                <span style="font-size: 13px; font-weight: 600;">$48.20</span>
                            </div>
                            <div style="display: flex; justify-content: space-between; padding: 8px 0;">
                                <span style="font-size: 13px; opacity: 0.7;">P10 (Floor)</span>
                                <span style="font-size: 13px; font-weight: 600; color: #ef5350;">$46.80</span>
                            </div>
                        </div>
                        
                        <div style="margin-top: 16px; padding-top: 16px; border-top: 1px solid rgba(255,255,255,0.1);">
                            <div style="display: flex; justify-content: space-between; margin-bottom: 8px;">
                                <span style="font-size: 12px; opacity: 0.6;">Bullish Probability</span>
                                <span style="font-size: 12px; font-weight: 600; color: #2962FF;">62%</span>
                            </div>
                            <div style="height: 8px; background: rgba(255,255,255,0.1); border-radius: 4px; overflow: hidden;">
                                <div style="width: 62%; height: 100%; background: linear-gradient(90deg, #2962FF, #2962FF); border-radius: 4px;"></div>
                            </div>
                        </div>
                    </div>

                    <!-- Risk Metrics -->
                    <div style="background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.1); border-radius: 12px; padding: 24px;">
                        <h2 style="font-size: 18px; font-weight: 600; margin-bottom: 20px;">Risk Metrics</h2>
                        
                        <div style="display: flex; flex-direction: column; gap: 10px;">
                            <div style="display: flex; justify-content: space-between;">
                                <span style="font-size: 12px; opacity: 0.6;">VaR (95%, 1m)</span>
                                <span style="font-size: 12px; font-weight: 600;">-$2.84</span>
                            </div>
                            <div style="display: flex; justify-content: space-between;">
                                <span style="font-size: 12px; opacity: 0.6;">Expected Shortfall</span>
                                <span style="font-size: 12px; font-weight: 600;">-$3.62</span>
                            </div>
                            <div style="display: flex; justify-content: space-between;">
                                <span style="font-size: 12px; opacity: 0.6;">Sharpe (annualized)</span>
                                <span style="font-size: 12px; font-weight: 600;">1.24</span>
                            </div>
                            <div style="display: flex; justify-content: space-between;">
                                <span style="font-size: 12px; opacity: 0.6;">Max Drawdown (sim)</span>
                                <span style="font-size: 12px; font-weight: 600;">-8.2%</span>
                            </div>
                        </div>
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
