#!/usr/bin/env python3
"""Nanoclaw — lightweight Unix socket concierge (DP-R8, INT-INT-5).

Listens on /tmp/nanoclaw.sock using JSON line protocol.
Maintains memory.jsonl (append-only, rotated at 10MB).
Proxies chat to HALO Kernel gateway (localhost:13305/v1).
"""

import os
import json
import socket
import threading
import urllib.request

from halo.nanoclaw.memory import MemoryFile


SOCKET_PATH = "/tmp/nanoclaw.sock"
KERNEL_URL = "http://localhost:13305/v1/chat/completions"
DEFAULT_MODEL = "halo-reasoning"


class NanoclawServer:
    """Unix socket concierge server (DP-R8)."""

    def __init__(self, sock_path=SOCKET_PATH, kernel_url=KERNEL_URL,
                 memory_path=None, model=DEFAULT_MODEL, log=None):
        self.sock_path = sock_path
        self.kernel_url = kernel_url
        self.model = model
        self.log = log
        self._running = False
        self._memory = MemoryFile(memory_path or os.path.expanduser("~/memory.jsonl"))

    def start(self):
        """Start the Unix socket server."""
        if os.path.exists(self.sock_path):
            os.unlink(self.sock_path)
        self._server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._server.bind(self.sock_path)
        self._server.listen(5)
        self._server.settimeout(1.0)
        self._running = True
        while self._running:
            try:
                conn, _ = self._server.accept()
                threading.Thread(target=self._handle, args=(conn,), daemon=True).start()
            except socket.timeout:
                continue
            except OSError:
                break
        self._server.close()
        if os.path.exists(self.sock_path):
            os.unlink(self.sock_path)

    def stop(self):
        self._running = False

    def _handle(self, conn):
        """Handle a client connection."""
        try:
            data = b""
            while True:
                chunk = conn.recv(4096)
                if not chunk:
                    break
                data += chunk
                while b"\n" in data:
                    line, data = data.split(b"\n", 1)
                    response = self._process(json.loads(line.decode()))
                    conn.sendall((json.dumps(response) + "\n").encode())
        except Exception as e:
            try:
                conn.sendall((json.dumps({"error": str(e)}) + "\n").encode())
            except Exception:
                pass
        finally:
            conn.close()

    def _process(self, request):
        """Process a JSON request."""
        action = request.get("action", "")
        if action == "chat":
            return self._handle_chat(request.get("message", ""))
        elif action == "memory_append":
            self._memory.append(request.get("entry", {}))
            return {"status": "ok"}
        elif action == "memory_read":
            entries = self._memory.read_recent(request.get("count", 10))
            return {"entries": entries}
        elif action == "health":
            return {"status": "ok", "model": self.model}
        return {"error": f"unknown action: {action}"}

    def _handle_chat(self, message):
        """Proxy chat to HALO Kernel and log to memory.jsonl."""
        self._memory.append({"role": "user", "content": message})
        response_text = self._call_kernel(message)
        self._memory.append({"role": "assistant", "content": response_text})
        return {"response": response_text}

    def _call_kernel(self, message):
        """Call HALO Kernel gateway (INT-INT-6)."""
        body = json.dumps({
            "model": self.model,
            "messages": [{"role": "user", "content": message}],
        }).encode("utf-8")
        req = urllib.request.Request(
            self.kernel_url, data=body,
            headers={"Content-Type": "application/json"}, method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode())
                return data.get("choices", [{}])[0].get("message", {}).get("content", "")
        except Exception as e:
            return f"[kernel error: {e}]"


if __name__ == "__main__":
    server = NanoclawServer()
    server.start()