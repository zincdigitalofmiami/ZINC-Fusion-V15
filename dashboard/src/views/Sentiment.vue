<template>
    <div class="page-sentiment">
        <div style="padding: 40px; max-width: 1400px; margin: 128px auto 0;">
            <!-- Page Header -->
            <div style="margin-bottom: 40px;">
                <h1 style="font-size: 32px; font-weight: 700; margin-bottom: 8px;">Sentiment Analysis</h1>
                <p style="font-size: 16px; opacity: 0.6;">FinBERT-powered news scoring with specialist routing and keyword extraction</p>
            </div>

            <!-- Top Stats Row -->
            <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 32px;">
                <!-- Aggregate Sentiment -->
                <div style="background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.1); border-radius: 12px; padding: 20px; text-align: center;">
                    <div style="font-size: 11px; opacity: 0.5; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 8px;">Aggregate Sentiment</div>
                    <div style="font-size: 36px; font-weight: 700; color: #2962FF; margin-bottom: 4px;">+0.34</div>
                    <div style="font-size: 12px; color: #2962FF;">BULLISH</div>
                </div>
                <!-- Articles Today -->
                <div style="background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.1); border-radius: 12px; padding: 20px; text-align: center;">
                    <div style="font-size: 11px; opacity: 0.5; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 8px;">Articles (24h)</div>
                    <div style="font-size: 36px; font-weight: 700; margin-bottom: 4px;">147</div>
                    <div style="font-size: 12px; opacity: 0.6;">↑ 23 from yesterday</div>
                </div>
                <!-- Avg Confidence -->
                <div style="background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.1); border-radius: 12px; padding: 20px; text-align: center;">
                    <div style="font-size: 11px; opacity: 0.5; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 8px;">Avg Confidence</div>
                    <div style="font-size: 36px; font-weight: 700; margin-bottom: 4px;">0.72</div>
                    <div style="font-size: 12px; opacity: 0.6;">Above τ=0.55 threshold</div>
                </div>
                <!-- Routed Articles -->
                <div style="background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.1); border-radius: 12px; padding: 20px; text-align: center;">
                    <div style="font-size: 11px; opacity: 0.5; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 8px;">Multi-Routed</div>
                    <div style="font-size: 36px; font-weight: 700; margin-bottom: 4px;">38%</div>
                    <div style="font-size: 12px; opacity: 0.6;">2+ specialists</div>
                </div>
            </div>

            <!-- Main Grid -->
            <div style="display: grid; grid-template-columns: 1fr 360px; gap: 24px;">
                
                <!-- Left Column: News Feed -->
                <div style="display: flex; flex-direction: column; gap: 24px;">
                    
                    <!-- Sentiment Trend -->
                    <div style="background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.1); border-radius: 12px; padding: 24px;">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
                            <h2 style="font-size: 18px; font-weight: 600;">7-Day Sentiment Trend</h2>
                            <div style="display: flex; gap: 16px; font-size: 12px;">
                                <span style="display: flex; align-items: center; gap: 4px;"><span style="width: 12px; height: 3px; background: #2962FF; border-radius: 2px;"></span> Positive</span>
                                <span style="display: flex; align-items: center; gap: 4px;"><span style="width: 12px; height: 3px; background: #ef5350; border-radius: 2px;"></span> Negative</span>
                                <span style="display: flex; align-items: center; gap: 4px;"><span style="width: 12px; height: 3px; background: #787B86; border-radius: 2px;"></span> Neutral</span>
                            </div>
                        </div>
                        <!-- Mini Chart -->
                        <div style="height: 120px; background: #131722; border-radius: 8px; position: relative; overflow: hidden; padding: 16px;">
                            <!-- Y-axis labels -->
                            <div style="position: absolute; left: 8px; top: 16px; font-size: 10px; opacity: 0.5;">+1.0</div>
                            <div style="position: absolute; left: 8px; top: 50%; transform: translateY(-50%); font-size: 10px; opacity: 0.5;">0.0</div>
                            <div style="position: absolute; left: 8px; bottom: 16px; font-size: 10px; opacity: 0.5;">-1.0</div>
                            <!-- Zero line -->
                            <div style="position: absolute; left: 40px; right: 16px; top: 50%; height: 1px; background: rgba(255,255,255,0.1);"></div>
                            <!-- Trend line (mock SVG) -->
                            <svg style="position: absolute; left: 40px; top: 16px; right: 16px; bottom: 16px; width: calc(100% - 56px); height: calc(100% - 32px);" viewBox="0 0 200 80" preserveAspectRatio="none">
                                <path d="M0,50 L30,45 L60,55 L90,40 L120,35 L150,30 L180,25 L200,28" fill="none" stroke="#2962FF" stroke-width="2"/>
                                <path d="M0,50 L30,52 L60,48 L90,55 L120,58 L150,52 L180,55 L200,50" fill="none" stroke="#ef5350" stroke-width="2" opacity="0.7"/>
                            </svg>
                            <!-- X-axis labels -->
                            <div style="position: absolute; bottom: 4px; left: 40px; right: 16px; display: flex; justify-content: space-between; font-size: 9px; opacity: 0.4;">
                                <span>Dec 28</span>
                                <span>Dec 30</span>
                                <span>Jan 1</span>
                                <span>Jan 3</span>
                            </div>
                        </div>
                    </div>

                    <!-- News Feed -->
                    <div style="background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.1); border-radius: 12px; padding: 24px;">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
                            <h2 style="font-size: 18px; font-weight: 600;">Live News Feed</h2>
                            <div style="display: flex; gap: 8px;">
                                <select style="background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1); color: #fff; padding: 6px 12px; border-radius: 6px; font-size: 12px;">
                                    <option>All Specialists</option>
                                    <option>Crush</option>
                                    <option>China</option>
                                    <option>Tariff</option>
                                    <option>Biofuel</option>
                                </select>
                                <select style="background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1); color: #fff; padding: 6px 12px; border-radius: 6px; font-size: 12px;">
                                    <option>All Sentiment</option>
                                    <option>Positive</option>
                                    <option>Negative</option>
                                    <option>Neutral</option>
                                </select>
                            </div>
                        </div>

                        <!-- Article List -->
                        <div style="display: flex; flex-direction: column; gap: 12px;">
                            
                            <!-- Article 1 - Positive -->
                            <div style="padding: 16px; background: rgba(255,255,255,0.03); border-radius: 8px; border-left: 3px solid #2962FF;">
                                <div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 10px;">
                                    <div style="flex: 1;">
                                        <div style="font-weight: 600; font-size: 14px; margin-bottom: 6px; line-height: 1.4;">Brazil soybean harvest delays boost U.S. export outlook as Chinese buyers return</div>
                                        <div style="font-size: 12px; opacity: 0.5;">Reuters • 14 mins ago</div>
                                    </div>
                                    <div style="text-align: right; min-width: 100px;">
                                        <div style="font-size: 20px; font-weight: 700; color: #2962FF;">+0.78</div>
                                        <div style="font-size: 10px; opacity: 0.5;">conf: 0.89</div>
                                    </div>
                                </div>
                                <!-- Sentiment Bar -->
                                <div style="margin-bottom: 12px;">
                                    <div style="height: 6px; background: rgba(255,255,255,0.1); border-radius: 3px; overflow: hidden; position: relative;">
                                        <div style="position: absolute; left: 50%; width: 39%; height: 100%; background: #2962FF; border-radius: 0 3px 3px 0;"></div>
                                    </div>
                                    <div style="display: flex; justify-content: space-between; font-size: 9px; opacity: 0.4; margin-top: 2px;">
                                        <span>-1.0</span><span>0</span><span>+1.0</span>
                                    </div>
                                </div>
                                <!-- Routing & Keywords -->
                                <div style="display: flex; justify-content: space-between; align-items: center;">
                                    <div style="display: flex; gap: 4px; flex-wrap: wrap;">
                                        <span style="background: rgba(41, 98, 255, 0.2); padding: 3px 8px; border-radius: 4px; font-size: 10px; color: #2962FF; font-weight: 600;">Crush</span>
                                        <span style="background: rgba(41, 98, 255, 0.2); padding: 3px 8px; border-radius: 4px; font-size: 10px; color: #2962FF; font-weight: 600;">China</span>
                                    </div>
                                    <div style="font-size: 10px; opacity: 0.6;">
                                        <span style="background: rgba(255,255,255,0.1); padding: 2px 6px; border-radius: 3px; margin-left: 4px;">harvest</span>
                                        <span style="background: rgba(255,255,255,0.1); padding: 2px 6px; border-radius: 3px; margin-left: 4px;">exports</span>
                                        <span style="background: rgba(255,255,255,0.1); padding: 2px 6px; border-radius: 3px; margin-left: 4px;">China</span>
                                    </div>
                                </div>
                            </div>

                            <!-- Article 2 - Negative -->
                            <div style="padding: 16px; background: rgba(255,255,255,0.03); border-radius: 8px; border-left: 3px solid #ef5350;">
                                <div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 10px;">
                                    <div style="flex: 1;">
                                        <div style="font-weight: 600; font-size: 14px; margin-bottom: 6px; line-height: 1.4;">USTR signals expanded Section 301 tariffs on Chinese agricultural imports</div>
                                        <div style="font-size: 12px; opacity: 0.5;">Bloomberg • 42 mins ago</div>
                                    </div>
                                    <div style="text-align: right; min-width: 100px;">
                                        <div style="font-size: 20px; font-weight: 700; color: #ef5350;">-0.62</div>
                                        <div style="font-size: 10px; opacity: 0.5;">conf: 0.84</div>
                                    </div>
                                </div>
                                <div style="margin-bottom: 12px;">
                                    <div style="height: 6px; background: rgba(255,255,255,0.1); border-radius: 3px; overflow: hidden; position: relative;">
                                        <div style="position: absolute; right: 50%; width: 31%; height: 100%; background: #ef5350; border-radius: 3px 0 0 3px;"></div>
                                    </div>
                                    <div style="display: flex; justify-content: space-between; font-size: 9px; opacity: 0.4; margin-top: 2px;">
                                        <span>-1.0</span><span>0</span><span>+1.0</span>
                                    </div>
                                </div>
                                <div style="display: flex; justify-content: space-between; align-items: center;">
                                    <div style="display: flex; gap: 4px; flex-wrap: wrap;">
                                        <span style="background: rgba(239, 83, 80, 0.2); padding: 3px 8px; border-radius: 4px; font-size: 10px; color: #ef5350; font-weight: 600;">Tariff</span>
                                        <span style="background: rgba(239, 83, 80, 0.2); padding: 3px 8px; border-radius: 4px; font-size: 10px; color: #ef5350; font-weight: 600;">China</span>
                                        <span style="background: rgba(239, 83, 80, 0.2); padding: 3px 8px; border-radius: 4px; font-size: 10px; color: #ef5350; font-weight: 600;">Trump</span>
                                    </div>
                                    <div style="font-size: 10px; opacity: 0.6;">
                                        <span style="background: rgba(255,255,255,0.1); padding: 2px 6px; border-radius: 3px; margin-left: 4px;">Section 301</span>
                                        <span style="background: rgba(255,255,255,0.1); padding: 2px 6px; border-radius: 3px; margin-left: 4px;">tariff</span>
                                    </div>
                                </div>
                            </div>

                            <!-- Article 3 - Neutral -->
                            <div style="padding: 16px; background: rgba(255,255,255,0.03); border-radius: 8px; border-left: 3px solid #787B86;">
                                <div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 10px;">
                                    <div style="flex: 1;">
                                        <div style="font-weight: 600; font-size: 14px; margin-bottom: 6px; line-height: 1.4;">CBOT soybean oil futures settle mixed ahead of WASDE report</div>
                                        <div style="font-size: 12px; opacity: 0.5;">Dow Jones • 1 hour ago</div>
                                    </div>
                                    <div style="text-align: right; min-width: 100px;">
                                        <div style="font-size: 20px; font-weight: 700; color: #787B86;">+0.08</div>
                                        <div style="font-size: 10px; opacity: 0.5;">conf: 0.52</div>
                                    </div>
                                </div>
                                <div style="margin-bottom: 12px;">
                                    <div style="height: 6px; background: rgba(255,255,255,0.1); border-radius: 3px; overflow: hidden; position: relative;">
                                        <div style="position: absolute; left: 50%; width: 4%; height: 100%; background: #787B86;"></div>
                                    </div>
                                    <div style="display: flex; justify-content: space-between; font-size: 9px; opacity: 0.4; margin-top: 2px;">
                                        <span>-1.0</span><span>0</span><span>+1.0</span>
                                    </div>
                                </div>
                                <div style="display: flex; justify-content: space-between; align-items: center;">
                                    <div style="display: flex; gap: 4px; flex-wrap: wrap;">
                                        <span style="background: rgba(120, 123, 134, 0.2); padding: 3px 8px; border-radius: 4px; font-size: 10px; color: #787B86; font-weight: 600;">Volatility</span>
                                    </div>
                                    <div style="font-size: 10px; opacity: 0.6;">
                                        <span style="background: rgba(255,255,255,0.1); padding: 2px 6px; border-radius: 3px; margin-left: 4px;">CBOT</span>
                                        <span style="background: rgba(255,255,255,0.1); padding: 2px 6px; border-radius: 3px; margin-left: 4px;">WASDE</span>
                                    </div>
                                </div>
                            </div>

                            <!-- Article 4 - Positive -->
                            <div style="padding: 16px; background: rgba(255,255,255,0.03); border-radius: 8px; border-left: 3px solid #2962FF;">
                                <div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 10px;">
                                    <div style="flex: 1;">
                                        <div style="font-weight: 600; font-size: 14px; margin-bottom: 6px; line-height: 1.4;">EPA finalizes higher RFS volumes for 2026, renewable diesel demand to surge</div>
                                        <div style="font-size: 12px; opacity: 0.5;">S&amp;P Global • 2 hours ago</div>
                                    </div>
                                    <div style="text-align: right; min-width: 100px;">
                                        <div style="font-size: 20px; font-weight: 700; color: #2962FF;">+0.85</div>
                                        <div style="font-size: 10px; opacity: 0.5;">conf: 0.91</div>
                                    </div>
                                </div>
                                <div style="margin-bottom: 12px;">
                                    <div style="height: 6px; background: rgba(255,255,255,0.1); border-radius: 3px; overflow: hidden; position: relative;">
                                        <div style="position: absolute; left: 50%; width: 42%; height: 100%; background: #2962FF; border-radius: 0 3px 3px 0;"></div>
                                    </div>
                                    <div style="display: flex; justify-content: space-between; font-size: 9px; opacity: 0.4; margin-top: 2px;">
                                        <span>-1.0</span><span>0</span><span>+1.0</span>
                                    </div>
                                </div>
                                <div style="display: flex; justify-content: space-between; align-items: center;">
                                    <div style="display: flex; gap: 4px; flex-wrap: wrap;">
                                        <span style="background: rgba(41, 98, 255, 0.2); padding: 3px 8px; border-radius: 4px; font-size: 10px; color: #2962FF; font-weight: 600;">Biofuel</span>
                                        <span style="background: rgba(41, 98, 255, 0.2); padding: 3px 8px; border-radius: 4px; font-size: 10px; color: #2962FF; font-weight: 600;">Energy</span>
                                    </div>
                                    <div style="font-size: 10px; opacity: 0.6;">
                                        <span style="background: rgba(255,255,255,0.1); padding: 2px 6px; border-radius: 3px; margin-left: 4px;">RFS</span>
                                        <span style="background: rgba(255,255,255,0.1); padding: 2px 6px; border-radius: 3px; margin-left: 4px;">EPA</span>
                                        <span style="background: rgba(255,255,255,0.1); padding: 2px 6px; border-radius: 3px; margin-left: 4px;">renewable diesel</span>
                                    </div>
                                </div>
                            </div>

                            <!-- Article 5 - Negative -->
                            <div style="padding: 16px; background: rgba(255,255,255,0.03); border-radius: 8px; border-left: 3px solid #ef5350;">
                                <div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 10px;">
                                    <div style="flex: 1;">
                                        <div style="font-weight: 600; font-size: 14px; margin-bottom: 6px; line-height: 1.4;">Palm oil inventories surge to 18-month high, Malaysia export duty reduced</div>
                                        <div style="font-size: 12px; opacity: 0.5;">AgriCensus • 3 hours ago</div>
                                    </div>
                                    <div style="text-align: right; min-width: 100px;">
                                        <div style="font-size: 20px; font-weight: 700; color: #ef5350;">-0.54</div>
                                        <div style="font-size: 10px; opacity: 0.5;">conf: 0.77</div>
                                    </div>
                                </div>
                                <div style="margin-bottom: 12px;">
                                    <div style="height: 6px; background: rgba(255,255,255,0.1); border-radius: 3px; overflow: hidden; position: relative;">
                                        <div style="position: absolute; right: 50%; width: 27%; height: 100%; background: #ef5350; border-radius: 3px 0 0 3px;"></div>
                                    </div>
                                    <div style="display: flex; justify-content: space-between; font-size: 9px; opacity: 0.4; margin-top: 2px;">
                                        <span>-1.0</span><span>0</span><span>+1.0</span>
                                    </div>
                                </div>
                                <div style="display: flex; justify-content: space-between; align-items: center;">
                                    <div style="display: flex; gap: 4px; flex-wrap: wrap;">
                                        <span style="background: rgba(239, 83, 80, 0.2); padding: 3px 8px; border-radius: 4px; font-size: 10px; color: #ef5350; font-weight: 600;">Palm</span>
                                        <span style="background: rgba(239, 83, 80, 0.2); padding: 3px 8px; border-radius: 4px; font-size: 10px; color: #ef5350; font-weight: 600;">Substitutes</span>
                                    </div>
                                    <div style="font-size: 10px; opacity: 0.6;">
                                        <span style="background: rgba(255,255,255,0.1); padding: 2px 6px; border-radius: 3px; margin-left: 4px;">MPOB</span>
                                        <span style="background: rgba(255,255,255,0.1); padding: 2px 6px; border-radius: 3px; margin-left: 4px;">inventory</span>
                                    </div>
                                </div>
                            </div>
                        </div>

                        <!-- Load More -->
                        <div style="text-align: center; margin-top: 20px;">
                            <button style="background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1); color: #fff; padding: 10px 24px; border-radius: 6px; font-size: 13px; cursor: pointer;">Load More Articles</button>
                        </div>
                    </div>
                </div>

                <!-- Right Sidebar -->
                <div style="display: flex; flex-direction: column; gap: 24px;">
                    
                    <!-- Specialist Sentiment Breakdown -->
                    <div style="background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.1); border-radius: 12px; padding: 24px;">
                        <h2 style="font-size: 18px; font-weight: 600; margin-bottom: 20px;">By Specialist</h2>
                        
                        <div style="display: flex; flex-direction: column; gap: 12px;">
                            <div style="display: flex; justify-content: space-between; align-items: center;">
                                <span style="font-size: 13px;">Biofuel Mandate</span>
                                <div style="display: flex; align-items: center; gap: 8px;">
                                    <span style="font-size: 14px; font-weight: 600; color: #2962FF;">+0.72</span>
                                    <span style="font-size: 10px; opacity: 0.5;">18 articles</span>
                                </div>
                            </div>
                            <div style="display: flex; justify-content: space-between; align-items: center;">
                                <span style="font-size: 13px;">Crush Economics</span>
                                <div style="display: flex; align-items: center; gap: 8px;">
                                    <span style="font-size: 14px; font-weight: 600; color: #2962FF;">+0.58</span>
                                    <span style="font-size: 10px; opacity: 0.5;">24 articles</span>
                                </div>
                            </div>
                            <div style="display: flex; justify-content: space-between; align-items: center;">
                                <span style="font-size: 13px;">Energy Complex</span>
                                <div style="display: flex; align-items: center; gap: 8px;">
                                    <span style="font-size: 14px; font-weight: 600; color: #2962FF;">+0.31</span>
                                    <span style="font-size: 10px; opacity: 0.5;">31 articles</span>
                                </div>
                            </div>
                            <div style="display: flex; justify-content: space-between; align-items: center;">
                                <span style="font-size: 13px;">Trump Effect</span>
                                <div style="display: flex; align-items: center; gap: 8px;">
                                    <span style="font-size: 14px; font-weight: 600; color: #787B86;">+0.05</span>
                                    <span style="font-size: 10px; opacity: 0.5;">12 articles</span>
                                </div>
                            </div>
                            <div style="display: flex; justify-content: space-between; align-items: center;">
                                <span style="font-size: 13px;">China Demand</span>
                                <div style="display: flex; align-items: center; gap: 8px;">
                                    <span style="font-size: 14px; font-weight: 600; color: #ef5350;">-0.24</span>
                                    <span style="font-size: 10px; opacity: 0.5;">28 articles</span>
                                </div>
                            </div>
                            <div style="display: flex; justify-content: space-between; align-items: center;">
                                <span style="font-size: 13px;">Tariff Regime</span>
                                <div style="display: flex; align-items: center; gap: 8px;">
                                    <span style="font-size: 14px; font-weight: 600; color: #ef5350;">-0.41</span>
                                    <span style="font-size: 10px; opacity: 0.5;">15 articles</span>
                                </div>
                            </div>
                            <div style="display: flex; justify-content: space-between; align-items: center;">
                                <span style="font-size: 13px;">Palm Substitution</span>
                                <div style="display: flex; align-items: center; gap: 8px;">
                                    <span style="font-size: 14px; font-weight: 600; color: #ef5350;">-0.38</span>
                                    <span style="font-size: 10px; opacity: 0.5;">19 articles</span>
                                </div>
                            </div>
                        </div>
                    </div>

                    <!-- Source Breakdown -->
                    <div style="background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.1); border-radius: 12px; padding: 24px;">
                        <h2 style="font-size: 18px; font-weight: 600; margin-bottom: 20px;">By Source</h2>
                        
                        <div style="display: flex; flex-direction: column; gap: 10px;">
                            <div style="display: flex; justify-content: space-between; align-items: center; padding: 8px 0; border-bottom: 1px solid rgba(255,255,255,0.05);">
                                <div>
                                    <div style="font-size: 13px; font-weight: 500;">Reuters</div>
                                    <div style="font-size: 10px; opacity: 0.5;">Tier 1 • Financial</div>
                                </div>
                                <div style="text-align: right;">
                                    <div style="font-size: 13px; font-weight: 600;">32</div>
                                    <div style="font-size: 10px; opacity: 0.5;">articles</div>
                                </div>
                            </div>
                            <div style="display: flex; justify-content: space-between; align-items: center; padding: 8px 0; border-bottom: 1px solid rgba(255,255,255,0.05);">
                                <div>
                                    <div style="font-size: 13px; font-weight: 500;">Bloomberg</div>
                                    <div style="font-size: 10px; opacity: 0.5;">Tier 1 • Financial</div>
                                </div>
                                <div style="text-align: right;">
                                    <div style="font-size: 13px; font-weight: 600;">28</div>
                                    <div style="font-size: 10px; opacity: 0.5;">articles</div>
                                </div>
                            </div>
                            <div style="display: flex; justify-content: space-between; align-items: center; padding: 8px 0; border-bottom: 1px solid rgba(255,255,255,0.05);">
                                <div>
                                    <div style="font-size: 13px; font-weight: 500;">S&amp;P Global</div>
                                    <div style="font-size: 10px; opacity: 0.5;">Tier 1 • Commodity</div>
                                </div>
                                <div style="text-align: right;">
                                    <div style="font-size: 13px; font-weight: 600;">24</div>
                                    <div style="font-size: 10px; opacity: 0.5;">articles</div>
                                </div>
                            </div>
                            <div style="display: flex; justify-content: space-between; align-items: center; padding: 8px 0; border-bottom: 1px solid rgba(255,255,255,0.05);">
                                <div>
                                    <div style="font-size: 13px; font-weight: 500;">AgriCensus</div>
                                    <div style="font-size: 10px; opacity: 0.5;">Tier 2 • Agriculture</div>
                                </div>
                                <div style="text-align: right;">
                                    <div style="font-size: 13px; font-weight: 600;">21</div>
                                    <div style="font-size: 10px; opacity: 0.5;">articles</div>
                                </div>
                            </div>
                            <div style="display: flex; justify-content: space-between; align-items: center; padding: 8px 0;">
                                <div>
                                    <div style="font-size: 13px; font-weight: 500;">Dow Jones</div>
                                    <div style="font-size: 10px; opacity: 0.5;">Tier 1 • Financial</div>
                                </div>
                                <div style="text-align: right;">
                                    <div style="font-size: 13px; font-weight: 600;">18</div>
                                    <div style="font-size: 10px; opacity: 0.5;">articles</div>
                                </div>
                            </div>
                        </div>
                    </div>

                    <!-- FinBERT Model Info -->
                    <div style="background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.1); border-radius: 12px; padding: 24px;">
                        <h2 style="font-size: 18px; font-weight: 600; margin-bottom: 16px;">Model Info</h2>
                        <div style="display: flex; flex-direction: column; gap: 8px; font-size: 12px;">
                            <div style="display: flex; justify-content: space-between;">
                                <span style="opacity: 0.6;">Model</span>
                                <span style="font-family: monospace;">ProsusAI/finbert</span>
                            </div>
                            <div style="display: flex; justify-content: space-between;">
                                <span style="opacity: 0.6;">Polarity</span>
                                <span>3-way (pos/neg/neu)</span>
                            </div>
                            <div style="display: flex; justify-content: space-between;">
                                <span style="opacity: 0.6;">Score Formula</span>
                                <span style="font-family: monospace;">p_pos - p_neg</span>
                            </div>
                            <div style="display: flex; justify-content: space-between;">
                                <span style="opacity: 0.6;">Confidence τ</span>
                                <span>0.55</span>
                            </div>
                            <div style="display: flex; justify-content: space-between;">
                                <span style="opacity: 0.6;">Last Batch</span>
                                <span>2 mins ago</span>
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
