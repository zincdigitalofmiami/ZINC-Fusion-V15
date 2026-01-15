-- Event Category to Cuisine Affinity Scores
-- This drives the smart matching between event types and restaurant cuisines
-- Scores are 0-100 representing likelihood that this cuisine type benefits from this event type

-- Drop and recreate for clean state (this is a lookup table, not user data)
DROP TABLE IF EXISTS ops.vegas_cuisine_affinity;

CREATE TABLE ops.vegas_cuisine_affinity (
  id SERIAL PRIMARY KEY,
  event_category VARCHAR(50) NOT NULL,  -- concerts, conferences, expos, festivals, performing-arts, sports
  cuisine_type VARCHAR(50) NOT NULL,     -- steakhouse, burger, asian, mexican, italian, seafood, pub, buffet, cafe, chicken, pizza, bbq, american, service, general
  affinity_score INTEGER NOT NULL CHECK (affinity_score >= 0 AND affinity_score <= 100),
  reasoning TEXT,  -- Brief explanation for Kevin's intel sheets
  created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(event_category, cuisine_type)
);

-- Insert affinity scores based on crowd demographics and dining patterns
-- These are the 6 main event categories × cuisine types

-- EXPOS (trade shows, conventions) - Business travelers, expense accounts, networking
INSERT INTO ops.vegas_cuisine_affinity (event_category, cuisine_type, affinity_score, reasoning) VALUES
  ('expos', 'steakhouse', 95, 'Business dinners, expense accounts, client entertainment'),
  ('expos', 'buffet', 85, 'Large groups, time-efficient, variety for diverse tastes'),
  ('expos', 'italian', 80, 'Classic business dining, group-friendly'),
  ('expos', 'american', 75, 'Safe choice for diverse corporate groups'),
  ('expos', 'asian', 70, 'Upscale options for business dinners'),
  ('expos', 'seafood', 70, 'Premium dining for client entertainment'),
  ('expos', 'pub', 60, 'After-hours networking, casual meetings'),
  ('expos', 'cafe', 55, 'Quick breakfast, coffee meetings'),
  ('expos', 'burger', 50, 'Quick lunch between sessions'),
  ('expos', 'mexican', 45, 'Group-friendly casual option'),
  ('expos', 'bbq', 45, 'Casual group dining'),
  ('expos', 'chicken', 35, 'Quick service option'),
  ('expos', 'pizza', 30, 'Late night, casual groups'),
  ('expos', 'service', 90, 'Banquets and catering surge');

-- CONFERENCES (smaller, focused professional gatherings)
INSERT INTO ops.vegas_cuisine_affinity (event_category, cuisine_type, affinity_score, reasoning) VALUES
  ('conferences', 'steakhouse', 90, 'Professional dinners, networking'),
  ('conferences', 'italian', 85, 'Elegant group dining'),
  ('conferences', 'american', 80, 'Reliable for mixed groups'),
  ('conferences', 'seafood', 75, 'Upscale dining option'),
  ('conferences', 'asian', 70, 'Sophisticated choice'),
  ('conferences', 'buffet', 65, 'Efficient for tight schedules'),
  ('conferences', 'pub', 55, 'Casual networking'),
  ('conferences', 'cafe', 60, 'Working breakfasts'),
  ('conferences', 'burger', 45, 'Quick casual option'),
  ('conferences', 'mexican', 40, 'Group casual'),
  ('conferences', 'bbq', 40, 'Casual group option'),
  ('conferences', 'chicken', 30, 'Quick service'),
  ('conferences', 'pizza', 25, 'Late sessions'),
  ('conferences', 'service', 85, 'Catering and banquet services');

-- CONCERTS (entertainment seekers, varied demographics by genre)
INSERT INTO ops.vegas_cuisine_affinity (event_category, cuisine_type, affinity_score, reasoning) VALUES
  ('concerts', 'pub', 90, 'Pre/post show drinks and food'),
  ('concerts', 'burger', 85, 'Quick casual before show'),
  ('concerts', 'american', 80, 'Mainstream appeal'),
  ('concerts', 'mexican', 75, 'Fun, shareable, group-friendly'),
  ('concerts', 'chicken', 70, 'Quick finger food'),
  ('concerts', 'pizza', 70, 'Late night post-show'),
  ('concerts', 'bbq', 65, 'Casual group dining'),
  ('concerts', 'italian', 55, 'Pre-show sit-down'),
  ('concerts', 'asian', 50, 'Quick noodles/bites'),
  ('concerts', 'steakhouse', 45, 'Special occasion pre-show'),
  ('concerts', 'cafe', 40, 'Quick coffee/snacks'),
  ('concerts', 'buffet', 35, 'Less time for leisurely dining'),
  ('concerts', 'seafood', 35, 'Niche audience'),
  ('concerts', 'service', 80, 'Arena concessions surge');

-- SPORTS (game day crowds, tribal, celebratory)
INSERT INTO ops.vegas_cuisine_affinity (event_category, cuisine_type, affinity_score, reasoning) VALUES
  ('sports', 'pub', 95, 'Sports bar culture, beer and wings'),
  ('sports', 'burger', 90, 'Classic game day food'),
  ('sports', 'chicken', 85, 'Wings are essential game food'),
  ('sports', 'american', 80, 'Mainstream sports food'),
  ('sports', 'bbq', 75, 'Hearty game day food'),
  ('sports', 'pizza', 70, 'Group sharing, game watching'),
  ('sports', 'mexican', 65, 'Nachos, shareable plates'),
  ('sports', 'steakhouse', 50, 'Pre-game splurge'),
  ('sports', 'buffet', 45, 'All-you-can-eat before game'),
  ('sports', 'asian', 35, 'Less typical for sports crowd'),
  ('sports', 'italian', 35, 'Less game-day focused'),
  ('sports', 'seafood', 30, 'Niche'),
  ('sports', 'cafe', 25, 'Not game day food'),
  ('sports', 'service', 85, 'Arena concessions, suite catering');

-- FESTIVALS (outdoor events, younger crowds, experiential)
INSERT INTO ops.vegas_cuisine_affinity (event_category, cuisine_type, affinity_score, reasoning) VALUES
  ('festivals', 'mexican', 90, 'Portable, shareable, fun'),
  ('festivals', 'burger', 85, 'Quick, portable'),
  ('festivals', 'chicken', 80, 'Finger food friendly'),
  ('festivals', 'pizza', 80, 'Shareable, late night'),
  ('festivals', 'bbq', 75, 'Festival food staple'),
  ('festivals', 'pub', 70, 'Drinks and apps'),
  ('festivals', 'american', 65, 'Broad appeal'),
  ('festivals', 'asian', 50, 'Quick noodles/bao'),
  ('festivals', 'cafe', 40, 'Morning after coffee'),
  ('festivals', 'italian', 35, 'Sit-down less practical'),
  ('festivals', 'buffet', 30, 'Time constraints'),
  ('festivals', 'steakhouse', 25, 'Not festival crowd'),
  ('festivals', 'seafood', 25, 'Not typical festival fare'),
  ('festivals', 'service', 70, 'Event catering');

-- PERFORMING-ARTS (theater, shows, upscale entertainment seekers)
INSERT INTO ops.vegas_cuisine_affinity (event_category, cuisine_type, affinity_score, reasoning) VALUES
  ('performing-arts', 'steakhouse', 85, 'Pre-theater dinner tradition'),
  ('performing-arts', 'italian', 90, 'Classic theater dining'),
  ('performing-arts', 'american', 75, 'Upscale casual pre-show'),
  ('performing-arts', 'seafood', 75, 'Elegant pre-show option'),
  ('performing-arts', 'asian', 65, 'Upscale sushi pre-show'),
  ('performing-arts', 'cafe', 60, 'Light pre-show bite'),
  ('performing-arts', 'pub', 55, 'Casual pre/post show'),
  ('performing-arts', 'buffet', 50, 'Time-efficient option'),
  ('performing-arts', 'burger', 45, 'Casual option'),
  ('performing-arts', 'mexican', 40, 'Less typical for theater crowd'),
  ('performing-arts', 'bbq', 35, 'Less elegant'),
  ('performing-arts', 'chicken', 30, 'Quick casual'),
  ('performing-arts', 'pizza', 25, 'Post-show late night'),
  ('performing-arts', 'service', 75, 'VIP dining, intermission service');

-- Create index for lookups
CREATE INDEX idx_vegas_cuisine_affinity_category ON ops.vegas_cuisine_affinity(event_category);
CREATE INDEX idx_vegas_cuisine_affinity_cuisine ON ops.vegas_cuisine_affinity(cuisine_type);
