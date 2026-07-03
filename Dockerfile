# MinerU on RunPod Serverless — generic PDF parsing worker.
# MinerU 3.4.2 runtime, MinerU2.5-Pro-2605-1.2B VLM as the default model.
#
# Base image: vllm/vllm-openai (recommended by MinerU upstream — bundles CUDA
# + a working vLLM that the VLM backend depends on).
#
# At runtime: handler.py listens for RunPod jobs, downloads/decodes the input
# PDF, calls MinerU's async parse, and returns the result as a base64 tarball.
#
# Model weights are NOT baked into this image. They are downloaded on the
# first parse request to HF's default cache at /root/.cache/huggingface.
# This keeps the image small enough to pass RunPod Hub's build/test window
# (under 30 min build / 160 min total). Trade-off: the first request on a
# cold worker is slow while ~4 GB of weights download. Set the execution
# timeout high (>= 600 s) and idle timeout long enough to keep workers warm.

ARG VLLM_VERSION=v0.21.0
FROM vllm/vllm-openai:${VLLM_VERSION}

# Allow HuggingFace libs to download model weights at runtime. Models are
# cached under /root/.cache/huggingface inside the worker; on a warm worker
# they are reused across requests. On a cold start the first parse triggers
# the download, so keep the execution timeout generous.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HUB_OFFLINE=0 \
    TRANSFORMERS_OFFLINE=0 \
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

# NOTE: Model weights are intentionally downloaded at runtime, not baked
# into the image. See the comment at the top of this file for the rationale.

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
