What “forward fills” are (a precise definition)

Forward fill (a.k.a. “carry-forward,” “last observation carried forward,” LOCF) is a time-series imputation rule:

If a value is missing at time t, replace it with the most recent observed value from some earlier time t′ < t.

Formally, for a series x_t with missing entries,
\tilde{x}_t =
\begin{cases}
 x_t & \text{if } x_t \text{ observed}\\
 \tilde{x}_{t-1} & \text{if } x_t \text{ missing}
\end{cases}
(optionally bounded by a max “age” / TTL, e.g., only carry forward up to 30 days).

Typical examples:
	•	Monthly CPI “filled” across all business days until the next CPI print.
	•	Fundamentals reported quarterly carried forward daily.
	•	A sensor that drops out for 3 hours.

⸻

How forward fills help modeling

1) Makes mixed-frequency data usable

Most ML pipelines want a rectangular daily matrix. Macro/fundamental series are often weekly/monthly/quarterly. Forward fill lets you join them to daily targets without losing most rows.

Benefit: you keep sample size and can incorporate slow-moving drivers.

2) Reduces spurious missingness from data plumbing

Missingness is often a pipeline artifact (API gaps, late ingestion, holiday/weekend alignment). Forward fill can prevent the model from learning “missingness = something” when it’s just ETL noise.

3) Works well for state variables

If the variable is plausibly “sticky” (policy rate target between meetings, regulatory regime, contract specs), carry-forward is a reasonable approximation of the latent state.

4) Stabilizes downstream transforms

Many features (ratios, z-scores, rolling windows) break or become noisy with gaps. Forward fill can keep computations well-defined and reduce variance from sparse updates.

⸻

How forward fills hurt modeling (the failure modes that actually matter)

1) Creates fake high-frequency signal

Forward filling a monthly series to daily creates step functions: constant for ~20 trading days, then a jump. That can:
	•	Artificially inflate correlation with daily targets (especially if target also has autocorrelation).
	•	Produce misleading “momentum” or “volatility” features that collapse to zero within the month.

Classic pathology:
Monthly value forward-filled daily → daily returns of that series are 0 for 19 days, then one big move → rolling vol / momentum becomes a calendar artifact, not economics.

2) Information leakage if you fill from revised/late data

If you forward fill the latest revised value backward across days where it wasn’t known yet, you leak future information.

This happens when:
	•	You use a series without as-of timestamps / vintage control.
	•	You “align by date” but ignore the actual release time and later revisions.

Leakage is one of the fastest ways to get a model that backtests great and fails live.

3) Masks staleness (models silently run on old info)

Forward fill makes the matrix look “complete,” but the feature may be 45 days old. That produces two problems:
	•	The model treats stale values as current.
	•	Validation gates that check “non-null coverage” are fooled.

This is why “≥95% non-null” can be meaningless: forward fill can turn a dead series into a perfectly filled one.

4) Induces regime-dependent bias

When volatility changes, stale carried values become actively misleading. Example: a risk index updated weekly carried through a crisis week—your “risk” feature does not move while the market does.

5) Interacts badly with regularization / tree splits
	•	Linear models: repeated constants can make coefficients appear stable/strong when they’re just picking up mean shifts at release dates.
	•	Trees/GBMs: can learn splits that effectively detect “pre/post release window” rather than the underlying economic effect.

⸻

The right mental model: forward fill is a piecewise-constant latent state assumption

Forward fill says: “Between prints, the true state stays constant.”
Sometimes that’s acceptable (policy target), often it’s wrong (prices, fast-moving latent demand).

So the question is not “Is forward fill good?” It’s:
	•	Is the variable conceptually a state that persists?
	•	Do you control “as-of” and staleness?
	•	Are you extracting features that are invariant to the step-function artifact?

⸻

Practical guardrails (what to do if you must forward fill)

A) Put a TTL on fills (max age)

Only carry forward up to a maximum horizon tied to the variable’s cadence.
	•	Daily series: TTL maybe 3–5 days (ETL tolerance)
	•	Weekly: TTL maybe 10–14 days
	•	Monthly: TTL maybe 45–60 days
	•	Quarterly: TTL maybe 120–150 days

After TTL, set missing again (or abstain), don’t pretend it’s current.

B) Add “age since last observation” as a feature (or gate)

Create:
	•	age_days = t - last_observed_date
	•	is_stale = age_days > threshold

Then either:
	•	Gate it (abstain / drop row / drop feature contribution), or
	•	Let the model learn that stale values are less informative.

C) Use event encoding for truly low-frequency fundamentals

Instead of forward-filling the level daily, encode release events:
	•	release_today (0/1)
	•	surprise = actual - expected
	•	delta = actual - prior
	•	days_since_release
	•	direction / bucketed surprise

This avoids fake daily dynamics while still injecting information when it arrives.

D) Enforce “as-of” correctness

If you don’t have vintage/as-of timestamps, forward fill is dangerous. The correct approach is:
	•	Join by knowledge time (what was known when), not by event date.
	•	If you can’t, treat the feature as suspect and cap its influence.

⸻

When forward fill is usually OK vs usually wrong

Usually OK
	•	Policy targets between meetings
	•	Contract specs, static metadata
	•	Slowly changing fundamentals if you model them as states and track staleness

Usually wrong
	•	Anything that should move daily (prices, spreads, vol)
	•	Macro series used to compute daily “momentum/volatility”
	•	Any series with revisions, if you lack as-of/vintage control

⸻

Rule you can operationalize

If a feature is forward-filled, one of these must be true, or you’re building a trap:
	1.	TTL + staleness gate exists, AND
	2.	You don’t compute high-frequency transforms that assume real daily movement, AND/OR
	3.	You use event encoding rather than level-as-daily truth, AND
	4.	You prevent leakage with as-of alignment.

If you tell me the kinds of series you’re forward-filling (macro prints, fundamentals, news sentiment, etc.) and the target cadence (1d/1h), I’ll classify which ones should be event-encoded vs TTL-forward-filled and what the gating thresholds should be.
