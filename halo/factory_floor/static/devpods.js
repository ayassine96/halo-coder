// DevPod status panel (FF-R3)
function renderDevPods(devpods) {
  const container = document.getElementById('devpod-status');
  if (!container) return;
  container.innerHTML = '';
  for (const pod of devpods) {
    const div = document.createElement('div');
    div.className = 'devpod-card';
    div.innerHTML = `
      <div class="pod-name">${pod.name || pod.spec_id}</div>
      <div class="pod-status ${pod.status}">${pod.status}</div>
      <div class="pod-details">Started: ${pod.started_at || 'N/A'}</div>
    `;
    container.appendChild(div);
  }
}

export { renderDevPods };