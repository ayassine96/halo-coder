// Approval queue (FF-R4)
async function addApprovalCard(data) {
  const queue = document.getElementById('approval-queue');
  if (!queue) return;
  const card = document.createElement('div');
  card.className = 'approval-card';
  card.innerHTML = `
    <h3>${data.spec_id || 'Unknown'}</h3>
    <p>${data.data || 'Approval needed'}</p>
    <button class="approve-btn">Approve</button>
    <button class="reject-btn">Reject</button>
  `;
  card.querySelector('.approve-btn').addEventListener('click', () => approveSpec(data.spec_id));
  card.querySelector('.reject-btn').addEventListener('click', () => rejectSpec(data.spec_id));
  queue.appendChild(card);
}

async function approveSpec(specId) {
  const { fetchCsrf, API_BASE } = window.haloApp;
  if (!window.csrfToken) await fetchCsrf();
  await fetch(`${API_BASE}/api/approve`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ spec_id: specId, csrf_token: window.csrfToken })
  });
}

async function rejectSpec(specId) {
  const { fetchCsrf, API_BASE } = window.haloApp;
  if (!window.csrfToken) await fetchCsrf();
  const reason = prompt('Rejection reason:');
  if (reason) {
    await fetch(`${API_BASE}/api/reject`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ spec_id: specId, reason, csrf_token: window.csrfToken })
    });
  }
}

export { addApprovalCard, approveSpec, rejectSpec };