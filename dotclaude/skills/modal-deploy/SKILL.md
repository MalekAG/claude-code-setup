---
name: modal-deploy
description: Deploy execution scripts to Modal cloud. Use when user asks to deploy to Modal, push code to cloud, update Modal functions, or build new API endpoints for n8n workflows.
allowed-tools: Bash, Read, Write, Edit, Glob, Grep
---

# Modal Cloud Deployment

## Goal
Deploy Python-powered API endpoints to Modal for serverless cloud execution. When the user describes a workflow:

1. **Build** — Write a Modal Python function
2. **Test** — Test locally with `modal run`
3. **Deploy** — Deploy with `modal deploy`
4. **Return** — Give the user their endpoint URL + ready-to-use cURL

**All endpoints must implement Bearer token authentication.**

## Setup & Authentication

Already configured in `~/.modal.toml`. If reconfiguration needed:

1. Go to https://modal.com/settings → API Tokens
2. Create new token
3. Run: `modal token set --token-id <ID> --token-secret <SECRET>`

### Modal Secrets (use with `modal.Secret.from_name()`)

- `anthropic-api-key` → `ANTHROPIC_API_KEY`
- `api-auth-token` → `API_AUTH_TOKEN` (Bearer token for endpoint auth)

```bash
# Create new secrets
modal secret create my-secret-name API_KEY=xxx ANOTHER_KEY=yyy

# Generate a secure Bearer token
openssl rand -hex 32
modal secret create api-auth-token API_AUTH_TOKEN=<generated-token>
```

## Deploy Commands

```bash
# Deploy orchestrator webhooks
modal deploy execution/modal_webhook.py

# Deploy standalone app
modal deploy modal_app.py

# Test locally without deploying
modal run modal_app.py::func_name --data '{"key": "value"}'
```

## Key Orchestrator Endpoints

| Endpoint | Purpose |
|----------|---------|
| `directive` | Execute a directive by slug |
| `list_webhooks` | List available webhooks |
| `general_agent` | Run general agent tasks |
| `scrape_leads` | Lead scraping endpoint |
| `generate_proposal` | Proposal generation |
| `youtube_outliers` | YouTube outlier scraping |

## Adding New Functions

1. Add function to `execution/modal_webhook.py` (orchestrator) or a new `modal_app.py` (standalone)
2. Decorate with `@app.function()` or `@app.function(schedule=modal.Cron(...))`
3. Deploy with `modal deploy <file>`

## Templates

### Basic HTTP Endpoint with Auth

```python
import modal
from fastapi import Header, HTTPException

app = modal.App("my-app-name")
image = modal.Image.debian_slim().pip_install("anthropic", "fastapi", "httpx")

@app.function(
    image=image,
    secrets=[
        modal.Secret.from_name("anthropic-api-key"),
        modal.Secret.from_name("api-auth-token"),
    ],
    timeout=120,
)
@modal.fastapi_endpoint(method="POST")
def my_endpoint(data: dict, authorization: str = Header(None)) -> dict:
    import os

    # Bearer token authentication
    expected_token = os.environ.get("API_AUTH_TOKEN")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")
    token = authorization.replace("Bearer ", "")
    if token != expected_token:
        raise HTTPException(status_code=403, detail="Invalid authentication token")

    # Your logic here
    return {"result": "ok"}
```

### AI/LLM Endpoint (Claude)

```python
@app.function(
    image=modal.Image.debian_slim().pip_install("anthropic", "fastapi"),
    secrets=[
        modal.Secret.from_name("anthropic-api-key"),
        modal.Secret.from_name("api-auth-token"),
    ],
    timeout=120,
)
@modal.fastapi_endpoint(method="POST")
def process(data: dict, authorization: str = Header(None)) -> dict:
    import anthropic, os

    # Auth check (same pattern as above)
    # ...

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    message = client.messages.create(
        model="claude-sonnet-4-5-20250929",
        max_tokens=1024,
        messages=[{"role": "user", "content": data.get("prompt", "")}],
        system="Your system prompt here",
    )
    return {"response": message.content[0].text}
```

### Cron Job

```python
@app.function(schedule=modal.Cron("0 * * * *"))  # Every hour
def my_scheduled_function():
    pass
```

## After Deployment — Return to User

1. **Endpoint URL**: `https://<profile>--<app-name>-<function-name>.modal.run`
2. **Bearer Token**: from Modal secret `api-auth-token`
3. **cURL command**:
```bash
curl -X POST "https://<profile>--<app>-<func>.modal.run" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN_HERE" \
  -d '{"your": "payload"}'
```
4. **n8n HTTP Request node config**:
   - Method: POST
   - URL: the endpoint
   - Authentication: Header Auth → Name: `Authorization`, Value: `Bearer YOUR_TOKEN_HERE`
   - Body: JSON

## Quick Reference

| Command | Purpose |
|---------|---------|
| `modal deploy <file>` | Deploy to Modal |
| `modal run <file>::<func>` | Test locally |
| `modal secret create name KEY=value` | Create secret |
| `modal secret list` | List secrets |
| `modal app list` | List deployed apps |
| `modal app stop app-name` | Stop an app |
