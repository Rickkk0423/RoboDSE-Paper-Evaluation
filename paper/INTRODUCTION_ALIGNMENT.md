# Suggested claim replacements

Replace the final contribution's area-budget and matched-success area placeholders:

> We use RoboDSE to jointly explore hardware configurations and execution
> organizations, characterizing latency--refresh tradeoffs and hardware-resource
> Pareto frontiers. Across 22 timing-constraint boxes, task-aware selection yields
> five strictly improved and three extended core-count/bandwidth frontiers. We
> further examine their task implications through coverage-restricted projection
> onto an empirical success-rate grid, and report area and bandwidth uncertainty
> as secondary sensitivity analyses.

Do not claim same-budget SR gains from the current optimizer comparison: the
minimum-latency serial baselines lack grid coverage. The controlled k=1/k=2
interpolation difference is a separate execution-ablation diagnostic.

In Introduction paragraph 4, replace the categorical lower-area/power conclusion
with a motivation: jointly evaluating L and S can expose hardware-resource
tradeoffs overlooked by latency-only selection; whether these improve task
success and physical cost must be established with matching task and cost data.

Section 4's last sentence should describe direct closed-loop validation as the
required final validation stage, not as an already executed result of this DSE.
