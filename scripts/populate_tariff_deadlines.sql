-- Populate alt.tariff_deadlines with comprehensive trade policy deadlines
-- Sources: USTR, White House, USDA, EPA policy calendars

-- Clear existing (we'll repopulate with comprehensive list)
DELETE FROM alt.tariff_deadlines;

-- Insert comprehensive tariff/trade policy deadlines
INSERT INTO alt.tariff_deadlines 
  (deadline_name, deadline_date, days_to_expiry, renewal_probability, policy_type, description, is_active)
VALUES
  -- Section 301 China Tariffs
  ('Section 301 China Tariffs - Quarterly Review', '2026-03-31', 
   (DATE '2026-03-31' - CURRENT_DATE)::integer, 0.7, 'TRADE',
   'USTR quarterly review of Section 301 tariffs on $370B of Chinese goods. Potential modifications to List 1-4A tariffs.',
   (DATE '2026-03-31' >= CURRENT_DATE)),
  
  ('Section 301 China Tariffs - Annual Review', '2026-06-15',
   (DATE '2026-06-15' - CURRENT_DATE)::integer, 0.5, 'TRADE',
   'Annual USTR review of Section 301 China tariffs. May result in exclusions, rate adjustments, or renewals.',
   (DATE '2026-06-15' >= CURRENT_DATE)),
  
  -- EU/Canada/Mexico Trade
  ('USMCA Sunset Review', '2026-07-01',
   (DATE '2026-07-01' - CURRENT_DATE)::integer, 0.9, 'TRADE',
   'USMCA (US-Mexico-Canada Agreement) 6-year review. Determines if agreement continues or requires renegotiation.',
   (DATE '2026-07-01' >= CURRENT_DATE)),
  
  ('EU Steel/Aluminum Tariff Suspension', '2026-12-31',
   (DATE '2026-12-31' - CURRENT_DATE)::integer, 0.6, 'TRADE',
   'Suspension of Section 232 steel/aluminum tariffs on EU. May affect soybean/ag trade negotiations.',
   (DATE '2026-12-31' >= CURRENT_DATE)),
  
  -- Biofuel Policy (Critical for Biofuel Specialist)
  ('RFS 2026 RVO Final Rule', '2026-06-14',
   (DATE '2026-06-14' - CURRENT_DATE)::integer, 0.95, 'BIOFUEL',
   'EPA must finalize 2026 Renewable Volume Obligations (RVO) for biodiesel, advanced biofuel, cellulosic. Affects RIN prices and soybean oil demand.',
   (DATE '2026-06-14' >= CURRENT_DATE)),
  
  ('RFS 2027 RVO Proposed Rule', '2026-09-30',
   (DATE '2026-09-30' - CURRENT_DATE)::integer, 0.9, 'BIOFUEL',
   'EPA must propose 2027 RVO. Market watches for biodiesel mandate changes.',
   (DATE '2026-09-30' >= CURRENT_DATE)),
  
  ('Small Refinery Exemption Review', '2026-04-30',
   (DATE '2026-04-30' - CURRENT_DATE)::integer, 0.5, 'BIOFUEL',
   'EPA review of pending small refinery exemption (SRE) petitions. Could reduce effective biodiesel mandate.',
   (DATE '2026-04-30' >= CURRENT_DATE)),
  
  ('California LCFS Credit Market Review', '2026-03-31',
   (DATE '2026-03-31' - CURRENT_DATE)::integer, 0.8, 'BIOFUEL',
   'California quarterly LCFS (Low Carbon Fuel Standard) review. Affects renewable diesel and biodiesel margins.',
   (DATE '2026-03-31' >= CURRENT_DATE)),
  
  -- Brazil/Argentina (Crush Specialist)
  ('Argentina Soy Export Tax Review', '2026-12-10',
   (DATE '2026-12-10' - CURRENT_DATE)::integer, 0.6, 'AGRICULTURE',
   'Argentina reviews export tax rates on soybeans, soybean meal, and soybean oil. Affects global crush economics.',
   (DATE '2026-12-10' >= CURRENT_DATE)),
  
  -- USDA/Farm Bill
  ('Farm Bill Reauthorization Deadline', '2026-09-30',
   (DATE '2026-09-30' - CURRENT_DATE)::integer, 0.4, 'AGRICULTURE',
   '2024 Farm Bill expires. Renewal affects CCC, marketing loans, and ag trade programs.',
   (DATE '2026-09-30' >= CURRENT_DATE)),
  
  -- Tax Policy (Trump Effect)
  ('2017 Tax Cuts Expiration (TCJA)', '2026-12-31',
   (DATE '2026-12-31' - CURRENT_DATE)::integer, 0.5, 'TAX',
   'Tax Cuts and Jobs Act provisions expire. Affects corporate tax rates, depreciation (Section 179), and pass-through deductions.',
   (DATE '2026-12-31' >= CURRENT_DATE)),
  
  ('45Z Clean Fuel Production Credit Review', '2026-06-30',
   (DATE '2026-06-30' - CURRENT_DATE)::integer, 0.8, 'TAX',
   'IRS/Treasury review of 45Z tax credit guidance for clean transportation fuels (biodiesel, SAF, renewable diesel).',
   (DATE '2026-06-30' >= CURRENT_DATE)),
  
  -- China Agricultural Trade
  ('China Phase One Ag Purchase Commitment Review', '2026-02-15',
   (DATE '2026-02-15' - CURRENT_DATE)::integer, 0.3, 'AGRICULTURE',
   'Informal review of China Phase One ag purchase targets. May affect soybean export expectations.',
   (DATE '2026-02-15' >= CURRENT_DATE)),
  
  -- Sanctions/Export Controls (Trump Effect)
  ('Russia Sanctions Review (EU Coordination)', '2026-07-31',
   (DATE '2026-07-31' - CURRENT_DATE)::integer, 0.7, 'SANCTIONS',
   'US-EU coordination on Russia sanctions. May affect energy markets and ag trade flows.',
   (DATE '2026-07-31' >= CURRENT_DATE)),
  
  ('Iran Oil Sanctions Waiver Renewal', '2026-05-01',
   (DATE '2026-05-01' - CURRENT_DATE)::integer, 0.4, 'ENERGY',
   'US waivers for Iranian oil imports (China, India). Affects crude oil supply and energy complex.',
   (DATE '2026-05-01' >= CURRENT_DATE));

-- Update days_to_expiry calculation (ensure it's current)
UPDATE alt.tariff_deadlines
SET days_to_expiry = (deadline_date - CURRENT_DATE)::integer;

-- Summary
SELECT 
  policy_type,
  COUNT(*) as count
FROM alt.tariff_deadlines
WHERE is_active = true
GROUP BY policy_type
ORDER BY count DESC;
