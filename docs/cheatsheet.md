# Enthernet Prep AI: Ops Cheatsheet

Live deployment lives on `root@89.47.249.196` at `/opt/eprep`. Reached from the
world at **https://eprep.enthernetservice.com**. Isolated from the other four
sites on the VPS via docker compose project name `eprep` and localhost-only
ports `8100 / 3100 / 9100 / 9101`.

---

## URLs

| Purpose | URL |
|---|---|
| App / dashboard | https://eprep.enthernetservice.com/ |
| Demo shortcut (dev-only) | `POST /api/v1/demo/seed` |
| REST API base | https://eprep.enthernetservice.com/api/v1 |
| **MCP endpoint (Alexa+ submission)** | https://eprep.enthernetservice.com/api/v1/mcp/ |
| Health | https://eprep.enthernetservice.com/api/v1/health/ |

Auth: `Authorization: Bearer <jwt>` on every protected route.
Get a JWT with `POST /api/v1/auth/login` or the demo seed endpoint.

---

## SSH + everyday container ops

```bash
ssh root@89.47.249.196
cd /opt/eprep

# state
docker compose -p eprep ps
docker compose -p eprep logs -f backend
docker compose -p eprep logs -f frontend

# restart just one service
docker compose -p eprep --env-file .env restart backend

# bring everything down / up
docker compose -p eprep --env-file .env down
docker compose -p eprep --env-file .env up -d
```

---

## Deploying code changes

Run from your local machine (WSL box, wherever the source lives):

```bash
rsync -az --delete-after \
  --exclude 'node_modules' --exclude '__pycache__' --exclude '.pytest_cache' \
  --exclude '.next' --exclude '*.pyc' --exclude 'tsconfig.tsbuildinfo' \
  --exclude '.env' --exclude 'postgres_data' --exclude 'minio_data' \
  /home/glitch/Eprep/ root@89.47.249.196:/opt/eprep/

ssh root@89.47.249.196 "cd /opt/eprep && \
  docker compose -p eprep --env-file .env up -d --build && \
  docker compose -p eprep --env-file .env exec -T backend alembic upgrade head"
```

**Warning:** the `--exclude '.env'` matters. `.env` on the VPS holds rotated
production secrets; don't overwrite it with your local dev copy.

**Also important:** the prod compose override drops the source-code bind mount
on both `backend` and `frontend`, so **backend/frontend code changes need
`--build`, not just `restart`.** The above rsync-then-`up -d --build` sequence
handles that. If you only run `restart`, the container keeps serving the old
baked image and your changes look like they were ignored.

---

## Provider swap (Mock → OpenAI / Bedrock)

Edit `/opt/eprep/.env` on the VPS:

```
LLM_PROVIDER=openai            # or 'bedrock' or 'mock'
LLM_MODEL=gpt-4o-mini          # or e.g. us.anthropic.claude-3-5-sonnet-20241022-v2:0
OPENAI_API_KEY=sk-...
# For Bedrock:
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_BEDROCK_REGION=us-east-1
```

Then just `docker compose -p eprep --env-file .env up -d backend`.

Test after:
```bash
curl -sS https://eprep.enthernetservice.com/api/v1/health/
```

---

## Alexa signature verification

Off by default so the demo path (Bearer JWT) still works. Turn on for cert:

```
ALEXA_VERIFY_SIGNATURE=true
```

then `docker compose -p eprep --env-file .env up -d backend`.

---

## Nginx

Site config lives at:
```
/etc/nginx/sites-available/eprep.enthernetservice.com.conf
```
Managed by certbot for TLS. To edit:
```bash
sudo nano /etc/nginx/sites-available/eprep.enthernetservice.com.conf
sudo nginx -t
sudo systemctl reload nginx
```

TLS auto-renews via the certbot systemd timer:
```bash
systemctl list-timers | grep certbot
certbot renew --dry-run     # test
```

---

## Fast health / smoke checks

```bash
# Everything from your laptop:
curl -sS https://eprep.enthernetservice.com/ | head -c 200
curl -sS https://eprep.enthernetservice.com/api/v1/health/
curl -sS -X POST https://eprep.enthernetservice.com/api/v1/demo/seed \
     -H 'Content-Type: application/json' -d '{}'
curl -sS -X POST https://eprep.enthernetservice.com/api/v1/mcp/ \
     -H 'Content-Type: application/json' \
     -H 'Accept: application/json, text/event-stream' \
     -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{
           "protocolVersion":"2025-11-25","capabilities":{},
           "clientInfo":{"name":"probe","version":"1"}}}'
```

---

## Emergency: stop the eprep stack without touching other sites

```bash
docker compose -p eprep --env-file .env down
```

Other sites (`enthernetservice.com`, `admin.enthernetservice.com`,
`api.sereneparagon.com`, `profile.enthernet.com`) are on separate compose
projects and unaffected.

---

## What NOT to touch

- `enthernet-services-web-1` (port 8000). powers `enthernetservice.com`.
- `enthernet-admin-*` (port 5000). powers `admin.enthernetservice.com`.
- `serene-*`: powers `api.sereneparagon.com`.
- `profile-enthernet` (port 8003). powers `profile.enthernet.com`.
- Nginx conf files for those hostnames.

Everything else in `/opt/eprep/` is fair game.
