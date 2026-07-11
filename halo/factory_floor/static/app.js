// HALO Factory Floor — main app controller
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

// SSE connection with auto-reconnect (FF-NF1)
function connectSSE() {
  const es = new EventSource(`${API_BASE}/api/sse`);
  es.onmessage = (event) => {
    const data = JSON.parse(event.data);
    if (data.type === 'log') appendLog(data);
    if (data.type === 'approval_request') addApprovalCard(data);
    if (data.type === 'alert') console.warn('ALERT:', data);
  };
  es.onerror = () => {
    es.close();
    setTimeout(connectSSE, Math.min(30000, 1000 * Math.random() * 10));
  };
}

connectSSE();
fetchState().then(state => {
  paused = state.paused || false;
  renderKanban(state.specs || []);
});

window.haloApp = { fetchCsrf, fetchState, switchView, API_BASE };
export { fetchCsrf, fetchState, switchView };