/**
 * Inngest Batching Helper
 * 
 * Solves the counter tracking issue when using step.run() in loops.
 * 
 * PROBLEM: When incrementing counters inside step.run(), values don't 
 * propagate back to parent scope correctly in Inngest.
 * 
 * SOLUTION: Batch items and return counts from each step, then aggregate.
 */

export interface BatchResult {
  attempted: number;
  inserted: number;
  skipped: number;
  quarantined: number;
}

/**
 * Process items in batches with proper counter tracking
 * 
 * @param items - Array of items to process
 * @param batchSize - Number of items per batch (default: 20)
 * @param processFn - Async function to process each item, returns BatchResult for that item
 * @param stepRunner - The step.run function from Inngest
 * @param stepPrefix - Prefix for step names
 * @returns Aggregated batch results
 */
export async function processBatched<T>(
  items: T[],
  batchSize: number,
  processFn: (item: T) => Promise<BatchResult>,
  stepRunner: (name: string, fn: () => Promise<any>) => Promise<any>,
  stepPrefix: string = "batch"
): Promise<BatchResult> {
  const totalBatches = Math.ceil(items.length / batchSize);
  const aggregated: BatchResult = {
    attempted: 0,
    inserted: 0,
    skipped: 0,
    quarantined: 0,
  };

  for (let batchIdx = 0; batchIdx < totalBatches; batchIdx++) {
    const batchResult = await stepRunner(`${stepPrefix}-${batchIdx + 1}`, async () => {
      const start = batchIdx * batchSize;
      const end = Math.min(start + batchSize, items.length);
      const batch = items.slice(start, end);

      const batchCounts: BatchResult = {
        attempted: 0,
        inserted: 0,
        skipped: 0,
        quarantined: 0,
      };

      for (const item of batch) {
        const itemResult = await processFn(item);
        batchCounts.attempted += itemResult.attempted;
        batchCounts.inserted += itemResult.inserted;
        batchCounts.skipped += itemResult.skipped;
        batchCounts.quarantined += itemResult.quarantined;
      }

      return batchCounts;
    });

    // Aggregate results from this batch
    aggregated.attempted += batchResult.attempted;
    aggregated.inserted += batchResult.inserted;
    aggregated.skipped += batchResult.skipped;
    aggregated.quarantined += batchResult.quarantined;
  }

  return aggregated;
}
