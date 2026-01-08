import { serve } from "inngest/next";
import { inngest } from "@/inngest/client";
// import { zlPrice } from "@/inngest/functions";

// Inngest integration ready but deactivated
// Uncomment zlPrice when ready to enable 15-min price updates
export const { GET, POST, PUT } = serve({
  client: inngest,
  functions: [
    // zlPrice,  // Deactivated - uncomment to enable
  ],
});
