import { serve } from "inngest/next";
import { inngest } from "@/inngest/client";
import { zlPrice, yahooEod, fredDaily, cftcWeekly } from "@/inngest/functions";

export const { GET, POST, PUT } = serve({
  client: inngest,
  functions: [zlPrice, yahooEod, fredDaily, cftcWeekly],
});
