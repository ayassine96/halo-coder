// Command palette (Ctrl+K) (FF-R5)
document.addEventListener('keydown', (e) => {
  if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
    e.preventDefault();
    const palette = document.getElementById('command-palette');
    palette.classList.toggle('hidden');
    if (!palette.classList.contains('hidden')) {
      document.getElementById('cmd-input').focus();
    }
  }
  if (e.key === 'Escape') {
    document.getElementById('command-palette').classList.add('hidden');
  }
});

document.getElementById('cmd-input').addEventListener('keydown', (e) => {
  if (e.key === 'Enter') {
    const input = e.target.value.trim();
    handleCommand(input);
    e.target.value = '';
    document.getElementById('command-palette').classList.add('hidden');
  }
});

function handleCommand(input) {
  if (input.startsWith('> spec ')) {
    const specId = input.replace('> spec ', '').trim();
    console.log('Jump to spec:', specId);
  } else if (input.startsWith('> project ')) {
    const project = input.replace('> project ', '').trim();
    console.log('Filter to project:', project);
  } else if (input === '> logs') {
    window.haloApp.switchView('logs');
  } else if (input === '> pause') {
    document.getElementById('pause-btn').click();
  }
}

export { handleCommand };