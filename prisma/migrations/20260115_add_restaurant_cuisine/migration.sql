-- Add cuisine_type column to vegas_restaurants for event-cuisine matching
-- This is a computed/inferred field based on restaurant name keywords

ALTER TABLE ops.vegas_restaurants ADD COLUMN IF NOT EXISTS cuisine_type VARCHAR(50);

-- Cuisine type classification based on restaurant name keywords
-- Categories: steakhouse, burger, asian, mexican, italian, seafood, pub, buffet, cafe, chicken, american, service
-- 'service' = back-of-house operations (EDR, banquets, main kitchen, room service)

UPDATE ops.vegas_restaurants SET cuisine_type =
  CASE
    -- Steakhouse (highest priority - specific)
    WHEN LOWER(data->>'MHXYO') LIKE '%steakhouse%' THEN 'steakhouse'
    WHEN LOWER(data->>'MHXYO') LIKE '%prime rib%' THEN 'steakhouse'
    WHEN LOWER(data->>'MHXYO') LIKE '%butcher%' THEN 'steakhouse'
    WHEN LOWER(data->>'MHXYO') LIKE '%gallagher%' THEN 'steakhouse'
    WHEN LOWER(data->>'MHXYO') LIKE '%binion%' THEN 'steakhouse'
    WHEN LOWER(data->>'MHXYO') LIKE '%twin creeks%' THEN 'steakhouse'

    -- Burger
    WHEN LOWER(data->>'MHXYO') LIKE '%burger%' THEN 'burger'
    WHEN LOWER(data->>'MHXYO') LIKE '%burgr%' THEN 'burger'

    -- Asian (noodles, japanese, chinese, korean)
    WHEN LOWER(data->>'MHXYO') LIKE '%noodle%' THEN 'asian'
    WHEN LOWER(data->>'MHXYO') LIKE '%beijing%' THEN 'asian'
    WHEN LOWER(data->>'MHXYO') LIKE '%nobu%' THEN 'asian'
    WHEN LOWER(data->>'MHXYO') LIKE '%wuhu%' THEN 'asian'
    WHEN LOWER(data->>'MHXYO') LIKE '%tomo%' THEN 'asian'
    WHEN LOWER(data->>'MHXYO') LIKE '%ondori%' THEN 'asian'
    WHEN LOWER(data->>'MHXYO') LIKE '%asian%' THEN 'asian'
    WHEN LOWER(data->>'MHXYO') LIKE '%mok bar%' THEN 'asian'

    -- Mexican/Latin
    WHEN LOWER(data->>'MHXYO') LIKE '%burrito%' THEN 'mexican'
    WHEN LOWER(data->>'MHXYO') LIKE '%taco%' THEN 'mexican'
    WHEN LOWER(data->>'MHXYO') LIKE '%tortazo%' THEN 'mexican'
    WHEN LOWER(data->>'MHXYO') LIKE '%gonzalez%' THEN 'mexican'
    WHEN LOWER(data->>'MHXYO') LIKE '%burro%' THEN 'mexican'
    WHEN LOWER(data->>'MHXYO') LIKE '%mi casa%' THEN 'mexican'
    WHEN LOWER(data->>'MHXYO') LIKE '%su casa%' THEN 'mexican'
    WHEN LOWER(data->>'MHXYO') LIKE '%havana%' THEN 'mexican'

    -- Italian
    WHEN LOWER(data->>'MHXYO') LIKE '%amalfi%' THEN 'italian'
    WHEN LOWER(data->>'MHXYO') LIKE '%giada%' THEN 'italian'
    WHEN LOWER(data->>'MHXYO') LIKE '%caramello%' THEN 'italian'

    -- Seafood
    WHEN LOWER(data->>'MHXYO') LIKE '%fish%' THEN 'seafood'
    WHEN LOWER(data->>'MHXYO') LIKE '%seafood%' THEN 'seafood'
    WHEN LOWER(data->>'MHXYO') LIKE '%mar%' AND LOWER(data->>'MHXYO') LIKE '%bazaar%' THEN 'seafood'
    WHEN LOWER(data->>'MHXYO') LIKE '%mermaid%' THEN 'seafood'

    -- Pub/Bar
    WHEN LOWER(data->>'MHXYO') LIKE '%pub%' THEN 'pub'
    WHEN LOWER(data->>'MHXYO') LIKE '%tavern%' THEN 'pub'
    WHEN LOWER(data->>'MHXYO') LIKE '%bar & grill%' THEN 'pub'
    WHEN LOWER(data->>'MHXYO') LIKE '%brew%' THEN 'pub'
    WHEN LOWER(data->>'MHXYO') LIKE '%sports deli%' THEN 'pub'
    WHEN LOWER(data->>'MHXYO') LIKE '%flanker%' THEN 'pub'

    -- Buffet
    WHEN LOWER(data->>'MHXYO') LIKE '%buffet%' THEN 'buffet'
    WHEN LOWER(data->>'MHXYO') LIKE '%bacchanal%' THEN 'buffet'

    -- Cafe/Casual
    WHEN LOWER(data->>'MHXYO') LIKE '%cafe%' THEN 'cafe'
    WHEN LOWER(data->>'MHXYO') LIKE '%bistro%' THEN 'cafe'
    WHEN LOWER(data->>'MHXYO') LIKE '%diner%' THEN 'cafe'
    WHEN LOWER(data->>'MHXYO') LIKE '%du pars%' THEN 'cafe'

    -- Chicken/Wings
    WHEN LOWER(data->>'MHXYO') LIKE '%chicken%' THEN 'chicken'
    WHEN LOWER(data->>'MHXYO') LIKE '%wing%' THEN 'chicken'
    WHEN LOWER(data->>'MHXYO') LIKE '%huey magoo%' THEN 'chicken'

    -- Pizza
    WHEN LOWER(data->>'MHXYO') LIKE '%pizza%' THEN 'pizza'

    -- BBQ/Southern
    WHEN LOWER(data->>'MHXYO') LIKE '%bbq%' THEN 'bbq'
    WHEN LOWER(data->>'MHXYO') LIKE '%smokey%' THEN 'bbq'
    WHEN LOWER(data->>'MHXYO') LIKE '%cajun%' THEN 'bbq'
    WHEN LOWER(data->>'MHXYO') LIKE '%southern%' THEN 'bbq'
    WHEN LOWER(data->>'MHXYO') LIKE '%hash house%' THEN 'bbq'
    WHEN LOWER(data->>'MHXYO') LIKE '%tony roma%' THEN 'bbq'

    -- American/General (celebrity chef spots, generic american)
    WHEN LOWER(data->>'MHXYO') LIKE '%hell''s kitchen%' THEN 'american'
    WHEN LOWER(data->>'MHXYO') LIKE '%guy fieri%' THEN 'american'
    WHEN LOWER(data->>'MHXYO') LIKE '%flavortown%' THEN 'american'
    WHEN LOWER(data->>'MHXYO') LIKE '%americana%' THEN 'american'
    WHEN LOWER(data->>'MHXYO') LIKE '%america%' THEN 'american'
    WHEN LOWER(data->>'MHXYO') LIKE '%jason aldean%' THEN 'american'
    WHEN LOWER(data->>'MHXYO') LIKE '%house of blues%' THEN 'american'
    WHEN LOWER(data->>'MHXYO') LIKE '%stanton social%' THEN 'american'
    WHEN LOWER(data->>'MHXYO') LIKE '%martha stewart%' THEN 'american'
    WHEN LOWER(data->>'MHXYO') LIKE '%vanderpump%' THEN 'american'
    WHEN LOWER(data->>'MHXYO') LIKE '%craft kitchen%' THEN 'american'
    WHEN LOWER(data->>'MHXYO') LIKE '%triple george%' THEN 'american'
    WHEN LOWER(data->>'MHXYO') LIKE '%dominique ansel%' THEN 'american'
    WHEN LOWER(data->>'MHXYO') LIKE '%cheesesteak%' THEN 'american'
    WHEN LOWER(data->>'MHXYO') LIKE '%brasserie%' THEN 'american'

    -- Service/Back-of-house (not customer-facing classification)
    WHEN LOWER(data->>'MHXYO') LIKE '%edr%' THEN 'service'
    WHEN LOWER(data->>'MHXYO') LIKE '%employee dining%' THEN 'service'
    WHEN LOWER(data->>'MHXYO') LIKE '%team dining%' THEN 'service'
    WHEN LOWER(data->>'MHXYO') LIKE '%banquet%' THEN 'service'
    WHEN LOWER(data->>'MHXYO') LIKE '%room service%' THEN 'service'
    WHEN LOWER(data->>'MHXYO') LIKE '%main kitchen%' THEN 'service'
    WHEN LOWER(data->>'MHXYO') LIKE '%production kitchen%' THEN 'service'
    WHEN LOWER(data->>'MHXYO') LIKE '%service kitchen%' THEN 'service'
    WHEN LOWER(data->>'MHXYO') LIKE '%in-room dining%' THEN 'service'
    WHEN LOWER(data->>'MHXYO') LIKE '%pool%' THEN 'service'
    WHEN LOWER(data->>'MHXYO') LIKE '%arena%' THEN 'service'
    WHEN LOWER(data->>'MHXYO') LIKE '%bowling%' THEN 'service'
    WHEN LOWER(data->>'MHXYO') LIKE '%snack bar%' THEN 'service'

    -- Default: general (food hall, unclassified)
    ELSE 'general'
  END
WHERE cuisine_type IS NULL OR cuisine_type = '';

-- Create index for cuisine_type queries
CREATE INDEX IF NOT EXISTS idx_vegas_restaurants_cuisine ON ops.vegas_restaurants(cuisine_type);

-- Verify the tagging results
-- SELECT cuisine_type, COUNT(*) FROM ops.vegas_restaurants GROUP BY cuisine_type ORDER BY COUNT(*) DESC;
