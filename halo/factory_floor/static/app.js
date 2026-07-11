// HALO Factory Floor — main app controller
import { renderKanban } from './kanban.js';
import { renderDevPods } from './devpods.js';
import { renderModels } from './models.js';
import { renderGraph } from './graph.js';
import { appendLog } from './logs.js';
import { addApprovalCard } from './approvals.js';

const API_BASE = '';
let csrfToken = '';
let paused = false;

async function fetchCsrf() {
  const resp = await fetch(`${API_BASE}/api/csrf-token`);
  const data = await resp.json();
  csrfToken = data.csrf_token;
}

async function fetchState() {
  const resp = await fetch(`${API_BASE}/api/state`);
  return resp.json();
}

function switchView(view) {
  document.querySelectorAll('.view').forEach(v => v.classList.add('hidden'));
  document.getElementById(`view-${view}`).classList.remove('hidden');
  document.querySelectorAll('#topbar nav button').forEach(b => b.classList.remove('active'));
  document.querySelector(`[data-view="${view}"]`).classList.add('active');
}

document.querySelectorAll('#topbar nav button').forEach(btn => {
  btn.addEventListener('click', () => switchView(btn.dataset.view));
});

document.getElementById('pause-btn').addEventListener('click', async () => {
  if (!csrfToken) await fetchCsrf();
  const resp = await fetch(`${API_BASE}/api/pause`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ csrf_token: csrfToken })
  });
  const data = await resp.json();
  paused = data.status === 'paused';
  document.getElementById('pause-btn').textContent = paused ? 'Resume' : 'Pause';
});

function renderAll(state) {
  paused = state.paused || false;
  document.getElementById('pause-btn').textContent = paused ? 'Resume' : 'Pause';
  if (state.specs) renderKanban(state.specs);
  if (state.specs) renderGraph(state.specs);
  if (state.devpods) renderDevPods(state.devpods);
  if (state.model_metrics) renderModels(state.model_metrics);
}

// SSE connection with auto-reconnect (FF-NF1)
function connectSSE() {
  const es = new EventSource(`${API_BASE}/api/sse`);
  es.onmessage = (event) => {
    const data = JSON.parse(event.data);
    if (data.type === 'connected') return;
    if (data.type === 'log' || data.channel === 'halo:factory:logs') {
      appendLog({type: 'log', message: data.data || data.message || '', spec_id: data.spec_id || ''});
    }
    if (data.type === 'approval_request' || data.channel === 'halo:factory:approvals') {
      addApprovalCard({spec_id: data.spec_id, data: data.data || ''});
    }
    if (data.type === 'alert' || data.channel === 'halo:factory:alerts') {
      console.warn('ALERT:', data);
    }
    if (data.type === 'metric' || data.channel === 'halo:factory:metrics') {
      fetchState().then(renderAll);
    }
  };
  es.onerror = () => {
    es.close();
    setTimeout(connectSSE, Math.min(30000, 1000 * Math.random() * 10));
  };
}

connectSSE();
fetchState().then(renderAll);

setInterval(() => { fetchState().then(renderAll); }, 5000);

window.haloApp = { fetchCsrf, fetchState, switchView, renderAll, API_BASE };
export { fetchCsrf, fetchState, switchView, renderAll };