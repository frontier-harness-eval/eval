// Same website numerator/denominator for every harness. Partial usage stays a lower bound.
export function websiteCost(record, audit = null) {
  if (!audit) return Number.isFinite(record.effective_cost_per_pass) ? record.effective_cost_per_pass : null;
  if (!(record.successful > 0)) return null;
  const observed = new Map((audit.tasks ?? []).map(t => [t.task, t]));
  const costs = (record.task_details ?? []).map(t => {
    if (Number.isFinite(t.cost_first_cold_usd)) return t.cost_first_cold_usd;
    const value = observed.get(t.id)?.observed_cost_usd;
    return Number.isFinite(value) && value >= 0 ? value : null;
  }).filter(Number.isFinite);
  return costs.length ? costs.reduce((sum, value) => sum + value, 0) / record.successful : null;
}
