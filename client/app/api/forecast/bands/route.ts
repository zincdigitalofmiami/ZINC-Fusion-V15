import { NextRequest } from "next/server";

import { proxyToFusionApi } from "../../_utils";

export async function GET(request: NextRequest) {
  return proxyToFusionApi(request, "/api/forecast/bands");
}

