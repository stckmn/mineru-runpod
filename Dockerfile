# MinerU on RunPod Serverless — generic PDF parsing worker.
# MinerU 3.4.2 runtime, MinerU2.5-Pro-2605-1.2B VLM as the default model.
#
# Base image: vllm/vllm-openai (recommended by MinerU upstream — bundles CUDA
# + a working vLLM that the VLM backend depends on).
#
# At runtime: handler.py listens for RunPod jobs, downloads/decodes the input
# PDF, calls MinerU's async parse, and returns the result as a base64 tarball.
#
# Model weights are BAKED into the image at build time (under HF's default
# cache at /root/.cache/huggingface). This produces a ~22 GB image, so it is
# not suitable for RunPod Hub's GitHub-repo test window. Build this image
# locally (or via GitHub Actions) and deploy from GHCR/Docker Hub instead.
# Trade-off: fast cold starts because no runtime download is needed.

ARG VLLM_VERSION=v0.21.0
FROM vllm/vllm-openai:${VLLM_VERSION}

# HF_HUB_OFFLINE=1 + TRANSFORMERS_OFFLINE=1 force the HuggingFace libs to
# read from cache only. Since model weights are baked into the image, the
# cache is always present. Offline mode prevents accidental downloads if
# anything tries to call out at runtime.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 \
    HF_XET_HIGH_PERFORMANCE=1

# vllm-openai inherits an entrypoint that launches the OpenAI server. Override
# it so our handler can be the process.
ENTRYPOINT []

# System deps. The base image already has CUDA + Python; we only need the
# things mineru/pdf processing want at runtime.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 \
        libglib2.0-0 \
        poppler-utils \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /worker

# Install uv (10x+ faster than pip on resolution-heavy installs like
# mineru[core,vllm], which churns through pydantic / opencv / numpy
# version conflicts with the base image). Negligible image size (~10 MB)
# in exchange for a meaningful build-time win.
# hadolint ignore=DL3013
RUN pip install --no-cache-dir uv

# Install MinerU + RunPod worker SDK. mineru[core,vllm] pulls the VLM-engine
# dependencies that match the vllm version in the base image.
COPY requirements.txt /worker/requirements.txt
RUN uv pip install --system --no-cache -r requirements.txt

# Bake both MinerU model dependencies into the image at /root/.cache/huggingface
# (HF's default cache path). Runs AFTER pip install so huggingface_hub is
# available, and BEFORE the handler.py COPY so iterating on handler code
# doesn't bust these layers.
#
# - MinerU2.5-Pro-2605-1.2B: the VLM backend's model
# - PDF-Extract-Kit-1.0: the pipeline backend's OCR + layout + formula +
#   table models
#
# Split into two RUN layers (one per model) so a partial failure or a
# bump to a single model only re-downloads that model, not both.
#
# HF_HUB_OFFLINE / TRANSFORMERS_OFFLINE are set to "0" inline for these
# RUN steps only — the image-wide ENV directive above keeps them at "1"
# so that runtime stays in offline mode.
# hadolint ignore=DL3059
RUN HF_HUB_OFFLINE=0 TRANSFORMERS_OFFLINE=0 HF_XET_HIGH_PERFORMANCE=1 \
    python3 -c "from huggingface_hub import snapshot_download; \
    snapshot_download(repo_id='opendatalab/MinerU2.5-Pro-2605-1.2B')"
# hadolint ignore=DL3059
RUN HF_HUB_OFFLINE=0 TRANSFORMERS_OFFLINE=0 HF_XET_HIGH_PERFORMANCE=1 \
    python3 -c "from huggingface_hub import snapshot_download; \
    snapshot_download(repo_id='opendatalab/PDF-Extract-Kit-1.0')"

# Copy the worker code last so iterating on it doesn't bust the pip or
# model-cache layers. handler.py is the entry point; the worker/ package
# holds the modules it imports (schema, io, parse, package, debug,
# logging). Both must land at /worker/ so `from worker import ...`
# resolves from the script's directory.
COPY handler.py /worker/handler.py
COPY worker /worker/worker

# Tiny fixture PDF used by local smoke input and optional Hub tests. It is
# copied into /worker/test-fixture.pdf so validations can round-trip a real
# document without adding meaningful image size.
COPY .runpod/test-fixture.pdf /worker/test-fixture.pdf

# RunPod's serverless runtime invokes Python directly. `python3` is what
# vllm/vllm-openai ships on PATH; `python` is not always aliased.
CMD ["python3", "-u", "handler.py"]
