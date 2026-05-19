# MinerU 2.5 on RunPod Serverless — generic PDF parsing worker.
#
# Base image: vllm/vllm-openai (recommended by MinerU upstream — bundles CUDA
# + a working vLLM that the VLM backend depends on).
#
# At runtime: handler.py listens for RunPod jobs, downloads/decodes the input
# PDF, calls MinerU's async parse, and returns the result as a base64 tarball.
#
# The MinerU 2.5 VLM model (~2.5 GB) is downloaded on first worker boot and
# cached. With RunPod FlashBoot + idle_timeout = 10 s the model stays in GPU
# memory across requests within the same warm container.

ARG VLLM_VERSION=v0.6.6
FROM vllm/vllm-openai:${VLLM_VERSION}

# Keep Python noise down, write cache to a single root.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HOME=/root/.cache/huggingface \
    TRANSFORMERS_OFFLINE=0

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

# Install MinerU + RunPod worker SDK. mineru[core,vllm] pulls the VLM-engine
# dependencies that match the vllm version in the base image.
COPY requirements.txt /worker/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the worker code last so iterating on it doesn't bust the pip cache.
COPY handler.py /worker/handler.py

# Tiny fixture PDF used by the RunPod Hub validation tests (.runpod/tests.json
# references /worker/test-fixture.pdf). Tiny (<1 KB) so it adds nothing to the
# image and gives Hub a real document to round-trip on submission.
COPY .runpod/test-fixture.pdf /worker/test-fixture.pdf

# RunPod's serverless runtime invokes Python directly.
CMD ["python", "-u", "handler.py"]
