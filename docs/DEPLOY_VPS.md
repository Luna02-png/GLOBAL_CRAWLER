# Optional: always-on server (VPS) deployment

A home PC cannot scan at 07:00 while it is off or asleep. For uninterrupted daily runs use a small Linux VPS (1 vCPU / 1 GB RAM is enough).

```bash
sudo apt update && sudo apt install -y python3 python3-venv git
sudo useradd -m gpti && sudo -iu gpti
# copy the gpti folder to /home/gpti/gpti (scp / git)
cd ~/gpti && python3 -m venv .venv && . .venv/bin/activate
pip install -r backend/requirements.txt
cp .env.example .env   # set GPTI_HOST=127.0.0.1 and keep it behind a reverse proxy
cd backend && python -m app.cli init
```

`/etc/systemd/system/gpti.service`:
```ini
[Unit]
Description=GPTI
After=network-online.target
[Service]
User=gpti
WorkingDirectory=/home/gpti/gpti/backend
EnvironmentFile=/home/gpti/gpti/.env
ExecStart=/home/gpti/gpti/.venv/bin/python -m app.cli serve
Restart=always
[Install]
WantedBy=multi-user.target
```
`sudo systemctl enable --now gpti`. The built-in scheduler uses `GPTI_TIMEZONE=Asia/Ho_Chi_Minh` regardless of the server's clock.

Expose the UI only through an authenticated reverse proxy (e.g. Caddy/Nginx with basic auth) or an SSH tunnel
(`ssh -L 8765:127.0.0.1:8765 gpti@server`) — the app itself has no login.

## PostgreSQL
`pip install "psycopg[binary]"`, set `GPTI_DATABASE_URL=postgresql+psycopg://user:pass@host/gpti`, then `python -m app.cli init`
(Alembic creates the schema). To move existing SQLite data, export/import with a tool such as `pgloader`.
