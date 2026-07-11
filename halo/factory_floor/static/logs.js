// Live log stream (FF-R3)
function appendLog(data) {
  const stream = document.getElementById('log-stream');
  if (!stream) return;
  const line = document.createElement('div');
  line.textContent = `[${data.timestamp || ''}] ${data.message || ''}`;
  stream.appendChild(line);
  while (stream.children.length > 500) {
    stream.removeChild(stream.firstChild);
  }
  stream.scrollTop = stream.scrollHeight;
}

export { appendLog };