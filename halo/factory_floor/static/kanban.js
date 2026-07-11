// Kanban board (FF-R3)
const STATUSES = ['draft', 'ready', 'in_progress', 'implemented', 'failed', 'merged'];
const COLORS = {
  draft: '#8b949e', ready: '#3fb950', in_progress: '#58a6ff',
  implemented: '#a371f7', failed: '#f85149', merged: '#ffffff'
};

function renderKanban(specs) {
  const board = document.getElementById('kanban');
  board.innerHTML = '';
  for (const status of STATUSES) {
    const col = document.createElement('div');
    col.className = 'kanban-col';
    col.innerHTML = `<h3 style="color:${COLORS[status]}">${status}</h3>`;
    const cards = specs.filter(s => s.status === status);
    for (const spec of cards) {
      const card = document.createElement('div');
      card.className = 'kanban-card';
      card.style.borderColor = COLORS[spec.status];
      card.innerHTML = `<div class="card-id">${spec.id}</div><div class="card-title">${spec.title}</div>`;
      card.addEventListener('click', () => showSpecDetail(spec));
      col.appendChild(card);
    }
    board.appendChild(col);
  }
}

function showSpecDetail(spec) {
  alert(`${spec.id}: ${spec.title}\nStatus: ${spec.status}\n\n${spec.body || ''}`);
}

export { renderKanban };