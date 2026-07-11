// Model utilization panel (FF-R3, HK-R5)
function renderModels(metrics) {
  const container = document.getElementById('model-util');
  if (!container) return;
  container.innerHTML = `
    <div class="metric-card">
      <div class="metric-label">Queue Depth</div>
      <div class="metric-value">${metrics.queue_depth || 0}</div>
    </div>
    <div class="metric-card">
      <div class="metric-label">Tokens/sec</div>
      <div class="metric-value">${metrics.tokens_per_sec || 0}</div>
    </div>
    <div class="metric-card">
      <div class="metric-label">Active Sequences</div>
      <div class="metric-value">${metrics.active_seqs || 0}</div>
    </div>
  `;
}

export { renderModels };