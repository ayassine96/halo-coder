#!/bin/bash
set -e
# HALO-CODER Docker entrypoint — full workspace with nginx reverse proxy

log() { echo "[halo-coder] $*" >&2; }

log "setting up directories"
cd /tmp/browser

# Create nginx config
log "writing nginx config"
cat > /tmp/nginx.conf <<'CFG'
daemon off;
pid /tmp/nginx.pid;
error_log /dev/stderr info;
events { worker_connections 1024; }
http {
  client_body_temp_path /tmp/nginx_body;
  proxy_temp_path /tmp/nginx_proxy;
  access_log /dev/stdout;
  server {
    listen 80 default_server;
    client_max_body_size 100m;
    location /vscode {
      rewrite ^/vscode/?(.*) /$1 break;
      proxy_pass http://127.0.0.1:8080;
      proxy_http_version 1.1;
      proxy_set_header Upgrade $http_upgrade;
      proxy_set_header Connection "upgrade";
      proxy_set_header Host 127.0.0.1:8080;
      proxy_set_header Origin http://127.0.0.1:8080;
      proxy_set_header X-Real-IP $remote_addr;
      proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
      proxy_set_header X-Forwarded-Proto $scheme;
      proxy_read_timeout 86400s;
      proxy_send_timeout 86400s;
    }
    location /terminal/ {
      proxy_pass http://127.0.0.1:7681/;
      proxy_http_version 1.1;
      proxy_set_header Upgrade $http_upgrade;
      proxy_set_header Connection "upgrade";
      proxy_set_header Host $host;
    }
    location / {
      proxy_pass http://127.0.0.1:6080;
      proxy_http_version 1.1;
      proxy_set_header Upgrade $http_upgrade;
      proxy_set_header Connection "upgrade";
      proxy_set_header Host $host;
      proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
  }
}
CFG

log "starting code-server on :8080"
code-server --bind-addr 127.0.0.1:8080 --auth none /home/dev &

log "starting ttyd on :7681"
ttyd --writable -p 7681 --interface 127.0.0.1 bash &

log "starting halo-coder API on :6080"
python3 server.py &

log "starting nginx reverse proxy on :80"
nginx -c /tmp/nginx.conf &

wait -n
