# API

The app layer exposes an OpenAI-compatible surface. Endpoints are documented
here as they land; the live contract is always `/docs` (OpenAPI) on a running
server.

| Endpoint | Status |
|---|---|
| `GET /healthz` | ✅ `{ok, version}` |
| `GET /v1/models` | ✅ lists loaded character packs (OpenAI model-list shape) |
| `POST /v1/chat/completions` | 🚧 honest `model_not_found` until a character pack is loaded |
