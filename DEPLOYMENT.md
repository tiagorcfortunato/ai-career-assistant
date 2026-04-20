# Deployment — CD Pipeline & Operations Runbook

Production deploys run via **GitHub Actions → GHCR → EC2 pull**. No on-box builds.

Prod URL: https://chatbot.tifortunato.com
Host: t3.micro EC2 in eu-central-1, fronted by Nginx + Let's Encrypt.

## Architecture

```
push to main
     ↓
GitHub Actions (ubuntu-latest, 4 GB RAM)
  1. test     → pytest
  2. build    → docker build + push to ghcr.io/<owner>/<repo>:sha-<SHORT>
  3. deploy   → SSH to EC2, docker pull, stop old, run new, wait /health, smoke
     ↓ on failure
  rollback   → re-run previous image
     ↓
EC2 t3.micro
  docker run -v /home/ec2-user/chatbot-data/chroma_db:/app/chroma_db \
             -v /home/ec2-user/chatbot-data/models:/root/.cache/fastembed \
             --memory=800m ghcr.io/…:sha-<SHORT>
     ↓
Container starts in ~5 s because chroma_db + model weights are pre-populated
on the host volume (see Bootstrap below).
     ↓
Nginx (127.0.0.1:8000) → HTTPS → chatbot.tifortunato.com
```

## Required GitHub Secrets

Set these in the repo settings → Secrets and variables → Actions:

| Secret | Value |
|--------|-------|
| `EC2_HOST` | The EC2 public IP or DNS (e.g. `35.157.34.234`) |
| `EC2_USER` | `ec2-user` |
| `EC2_SSH_PRIVATE_KEY` | Full contents of `chatbot-key.pem` including `-----BEGIN/END-----` lines |

`GITHUB_TOKEN` is provided automatically and has `packages: write` for GHCR.

## Required EC2 state (one-time setup)

```bash
# Volume directories (owned by ec2-user)
mkdir -p /home/ec2-user/chatbot-data/{chroma_db,models}
chown -R ec2-user:ec2-user /home/ec2-user/chatbot-data

# Runtime env file (referenced by deploy.yml's --env-file flag)
cat > /home/ec2-user/chatbot.env <<'EOF'
GROQ_API_KEY=<your-real-key>
LLM_MODEL=llama-3.3-70b-versatile
EMBEDDING_MODEL=BAAI/bge-small-en-v1.5
CHROMA_PATH=/app/chroma_db
CHUNK_SIZE=500
CHUNK_OVERLAP=50
RETRIEVAL_K=20
RAG_RERANK_MODEL=jinaai/jina-reranker-v2-base-multilingual
RAG_RERANK_TOP_K=5
RAG_RERANK_MIN_SCORE=0.3
EOF
chmod 600 /home/ec2-user/chatbot.env
```

## Bootstrap (first deploy, or after KB change)

The host volumes start empty. Populate them by running the bootstrap workflow
on a GitHub runner (4 GB RAM — no OOM, unlike t3.micro):

1. GitHub UI → Actions → **Bootstrap ChromaDB + Model Cache** → Run workflow
2. Set `wipe_existing = true` if you want a clean re-ingest
3. Wait ~3-5 min (workflow ingests 4 KBs, pre-warms embedding + reranker model weights, rsyncs both to EC2)

After it completes:
- `/home/ec2-user/chatbot-data/chroma_db/` has the full index
- `/home/ec2-user/chatbot-data/models/` has BAAI-bge-small + Jina reranker weights

Normal `deploy.yml` runs after this will skip ingestion entirely (lifespan sees `_is_already_ingested == True`) and skip model download (fastembed sees cached weights).

## Normal deploy

Push to `main` → deploy.yml triggers automatically. Or manual via UI:

1. Actions → **Deploy** → Run workflow
2. Optionally pass a specific SHA to deploy (default = HEAD of main)

What happens:
- Tests run first (fails → no deploy)
- Docker image built on GitHub runner, pushed to GHCR with tags `sha-<SHORT>` and `latest`
- SSH to EC2 → docker login GHCR → pull new image → stop old container → run new
- Poll `/health` for up to 120 s (returns 503 during startup, 200 when ready)
- Smoke test: `POST /api/query` with a real question → response must be > 50 chars
- On any failure → automatic rollback to previous image ID

## Rollback (manual)

Every past deploy is available in GHCR tagged with its short SHA. To roll back:

```bash
ssh -i chatbot-key.pem ec2-user@<EC2_HOST>
sudo docker login ghcr.io -u <gh-user>   # use a PAT with read:packages
sudo docker pull ghcr.io/<owner>/<repo>:sha-<PREVIOUS_SHA>
sudo docker stop chatbot && sudo docker rm chatbot
sudo docker run -d \
  --name chatbot \
  --restart unless-stopped \
  -p 127.0.0.1:8000:8000 \
  --env-file /home/ec2-user/chatbot.env \
  -v /home/ec2-user/chatbot-data/chroma_db:/app/chroma_db \
  -v /home/ec2-user/chatbot-data/models:/root/.cache/fastembed \
  --memory=800m --memory-swap=1600m \
  ghcr.io/<owner>/<repo>:sha-<PREVIOUS_SHA>
curl -I http://127.0.0.1:8000/health
```

Find previous SHAs at: https://github.com/users/<owner>/packages/container/package/<repo>

## Readiness semantics

- `/health` returns **503 `{"status":"starting"}`** while lifespan is running (ingestion checks, connection warmup)
- `/health` returns **200 `{"status":"ok"}`** once all 4 KBs are verified in ChromaDB
- Deploy workflow polls for 200 before declaring success; Nginx forwards either status through

If you see `/health` stuck on 503 past 30 s post-bootstrap, something is wrong with ingestion — check `docker logs chatbot --tail 100`.

## Resource limits

The container runs with `--memory=800m --memory-swap=1600m` — leaves ~100 MB RAM headroom for Nginx, sshd, and kernel on a 1 GB t3.micro. If we upgrade to t3.small, bump these to `1500m / 3000m`.

## Why this design

1. **Build off-box:** t3.micro can't do `docker build` without OOM. GitHub runner has 4 GB.
2. **Host-volume ChromaDB:** index persists across deploys → no re-ingestion → no 5-15 min startup downtime.
3. **Host-volume fastembed cache:** 300+ MB of model weights persist → no re-download per deploy.
4. **Readiness /health:** automated deploys can wait for actual readiness instead of fixed sleep.
5. **Smoke test in CD:** catches cases where container starts but chat pipeline is broken.
6. **Auto-rollback:** a bad deploy can't leave prod worse than before.
7. **Tag-based rollback:** every past image is reachable by short SHA in GHCR — no magic tooling needed.
