# runpod-mineru

<!-- badges: ci, license, python, runpod -->
[![CI](https://github.com/OWNER/runpod-mineru/actions/workflows/ci.yml/badge.svg)](https://github.com/OWNER/runpod-mineru/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12-blue.svg)](pyproject.toml)
[![MinerU](https://img.shields.io/badge/MinerU-2.5-purple)](https://github.com/opendatalab/MinerU)
[![Deploy on RunPod](https://img.shields.io/badge/Deploy-RunPod-7c3aed?logo=runpod&logoColor=white)](https://www.runpod.io/console/hub?ref=YOUR_RUNPOD_REFERRAL_CODE)
[![Conventional Commits](https://img.shields.io/badge/Conventional%20Commits-1.0.0-fa6673.svg)](https://www.conventionalcommits.org/)

> Replace `OWNER` and `YOUR_RUNPOD_REFERRAL_CODE` with real values before publishing.

Generic, reusable [MinerU 2.5](https://github.com/opendatalab/MinerU) PDF-parsing service running on [RunPod Serverless](https://www.runpod.io/serverless?ref=YOUR_RUNPOD_REFERRAL_CODE). **Scales to zero**, idles in seconds, **costs cents per document**.

This repo intentionally knows nothing about any specific project. Callers (a research-paper indexer, a documents pipeline, anything that needs PDF → structured Markdown/JSON) just `pip install` the client package and submit jobs.

## 30-second taste

```python
from mineru_client import MineruClient

client = MineruClient(endpoint_id="<your-endpoint-id>")
result = client.parse_pdf(pdf_url="https://arxiv.org/pdf/2401.00000.pdf", end_page=4)
client.save_tarball(result, "./out/paper")
# → markdown + content_list + middle.json + images
```

## Why this exists

- **MinerU 2.5** is SOTA for PDF → structured Markdown/JSON (charts, tables, math, multi-language). Apache 2.0 licensed.
- **RunPod Serverless** bills per-second and **scales to zero**. With `idle_timeout=10` and FlashBoot, a 100-page paper costs roughly **$0.01** instead of paying for an always-on GPU.
- **You don't have to wire any of that together yourself.** Push this repo to GitHub → RunPod auto-builds → endpoint id in your `.env` → done.

## Use cases this is built for

| Use case | Why MinerU + serverless fits |
|---|---|
| **Scientific paper indexing** (RAG, search, citations) | Spiky ingest, pay only during bursts; preserves equations + tables |
| **Document RAG pipelines** | Section-aware chunks with page provenance out of the box |
| **Contract / spec / standards parsing** | Handles long attribute tables and cross-page constructs |
| **Invoice / receipt extraction** | Table fidelity + image extraction in one pass |
| **Multi-language documents** | MinerU 2.5 supports 40+ languages, including handwriting |

## Architecture

```
caller ──▶ MineruClient.parse_pdf(pdf_url=...) ──▶ RunPod endpoint ──▶ worker container
                                                                            │
                                                          ┌─────────────────┴─────────────────┐
                                                          ▼                                   ▼
                                                  handler.py                          MinerU 2.5 VLM
                                                  (RunPod SDK)                        (vllm-backend, GPU)
                                                          │                                   │
                                                          └────── tarball / inline ◀──────────┘
caller ◀── result dict (md + JSON + images) ◀──────────────────┘
```

- **`handler.py`** is the serverless worker. Accepts PDF via URL, base64, or mounted-volume path; calls MinerU's async parse; returns markdown + content_list + middle.json + images.
- **`mineru_client/`** is the Python package consumers import. One class, two methods. Imports nothing GPU- or MinerU-related.
- **`deploy.py`** / **`destroy.py`** stand up / tear down the RunPod endpoint.

## Service API contract

Submit jobs with exactly one of `pdf_url`, `pdf_b64`, `volume_path`:

```json
{
  "input": {
    "pdf_url":       "https://...",
    "start_page":    0,
    "end_page":      99,
    "lang":          "en",
    "backend":       "vlm-vllm-async-engine",
    "formula_enable": true,
    "table_enable":   true,
    "return":         "tarball_b64",
    "basename":       "my-doc"
  }
}
```

Response on success:

```json
{
  "ok": true,
  "elapsed_seconds": 18.4,
  "pages_processed": 100,
  "mineru_version": "2.5.x",
  "source": "url:https://...",
  "tarball_b64": "..."
}
```

Full contract lives in [handler.py](handler.py) — keep that file as the source of truth.

## Deploy

### Option A — RunPod GitHub auto-build (recommended for long-term use)

1. Push this repo to a GitHub repository (public or private).
2. In the RunPod dashboard: **Serverless → Templates → New → Import Git Repository**, pick this repo and `Dockerfile` as the path.
3. RunPod builds the image (~5–10 min, watchable in the dashboard) and gives you a `template_id`.
4. Create the endpoint. Pick one:
   - **(A1) Dashboard, no local Python needed**: **Serverless → Endpoints → New** → select the template, set `idle_timeout=10`, `workers_min=0`, `workers_max=3`, FlashBoot on, GPU pool `AMPERE_24`. Save → grab the endpoint id.
   - **(A2) As code, reproducible across deployments**:
     ```powershell
     cp .env.example .env       # fill RUNPOD_API_KEY and MINERU_TEMPLATE_ID
     pip install -e .[deploy]
     python deploy.py --template-id $env:MINERU_TEMPLATE_ID
     ```
     Every knob in `deploy.py --help` matches a setting in the dashboard.

Subsequent pushes to `main` rebuild the image automatically; the endpoint picks up the new image on next cold start (or you can force a redeploy from the dashboard).

### Option B — bring your own image

Build and push to Docker Hub / GHCR yourself, then:

```powershell
python deploy.py --image yourhandle/runpod-mineru:0.1
```

### Endpoint defaults

| Setting | Value | Why |
|---|---|---|
| `gpu_ids` | `AMPERE_24` | 24 GB A5000 / 3090 class — fits MinerU 2.5 1.2B VLM comfortably with KV cache |
| `idle_timeout` | `10 s` | Scale workers to zero after 10 s of inactivity |
| `workers_min` | `0` | Pay only when processing |
| `workers_max` | `3` | Concurrency cap; bump for production |
| `execution_timeout` | `900 s` | Per-job cap; covers a several-hundred-page parse |
| `flashboot` | `true` | RunPod's fast cold-start tech |

Override any of these via flags to `deploy.py` (e.g. `--gpu-ids ADA_24 --workers-max 5`).

## Use from another project

### Install the client

Pick the flavour that matches your project's tooling:

```powershell
# pip (single project)
pip install -e C:\Projects\runpod-mineru

# uv (workspaces, recommended for monorepos)
uv add "mineru-client @ file:///C:/Projects/runpod-mineru"

# Once you've pushed this repo to GitHub:
uv add "mineru-client @ git+https://github.com/<owner>/runpod-mineru@v0.1.0"
pip install "mineru-client @ git+https://github.com/<owner>/runpod-mineru@v0.1.0"

# Or, if/when published to PyPI:
pip install mineru-client
uv add mineru-client
```

Pin to a tag (`@v0.1.0`) rather than `main` once you depend on it in production — semantic-release publishes one tag per release, so version drift is explicit.

### Direct use

```python
from mineru_client import MineruClient

client = MineruClient(
    endpoint_id="<endpoint-id>",
    api_key=os.environ["RUNPOD_API_KEY"],
)

# Parse pages 0-99 of an externally hosted PDF, get a tarball back
result = client.parse_pdf(
    pdf_url="https://example.com/paper.pdf",
    start_page=0,
    end_page=99,
)
client.save_tarball(result, dest_dir="./out/paper")

# Or parse a small local file inline
result = MineruClient.parse_pdf_from_file(
    client,
    "small_paper.pdf",
    return_format="inline",
)
client.save_inline(result, "./out/small_paper", basename="small_paper")
```

### Wrapping in a domain-specific adapter

For systems that need their own typed domain model (sections, chunks, provenance) — e.g. a scientific-paper indexer — see [`examples/parser_adapter_example.py`](examples/parser_adapter_example.py). It shows the pattern: a `ParserAdapter` ABC, a `MineruParserAdapter` implementation that wraps `MineruClient`, and a `_to_parsed_document` step that converts MinerU's `content_list` into Pydantic-typed sections + chunks with page provenance preserved. Copy and specialize.

`examples/` also has runnable smoke tests for URL and base64 flows.

## Cost & throughput rules of thumb

- Cold start (worker boot + model load): **~30–60 s** first time, **~10–20 s** with FlashBoot warm
- Per-page on `AMPERE_24`: **~0.2 s** (≈ 5 pages/s)
- ~$0.0001 per page on AMPERE_24 at $0.44/h. A 5,000-page doc ≈ **$0.10–0.25**.

## Local development

Worker container is GPU-only; you can't fully test the handler on a CPU box. For client-side iteration:

```powershell
pip install -e .[deploy]
python examples/parse_url_example.py https://arxiv.org/pdf/2401.00000.pdf
```

The MinerU container itself rebuilds with `docker build -t runpod-mineru:dev .` if you have a CUDA box handy for smoke tests.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Commits must follow [Conventional Commits](https://www.conventionalcommits.org/) — commitlint enforces this in CI and `CHANGELOG.md` is generated automatically by semantic-release on push to `main`.

## License

[MIT](LICENSE). The underlying [MinerU 2.5](https://github.com/opendatalab/MinerU) is Apache-2.0; the [RunPod SDK](https://github.com/runpod/runpod-python) is MIT.
