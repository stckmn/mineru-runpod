"""RunPod handler stub for GitHub repository indexing.

RunPod's static analyzer requires an unconditional top-level call to
runpod.serverless.start(). This file exists only to satisfy that check.

The actual production entry point is handler.py at the repo root, which is
invoked by the Dockerfile CMD. It uses a custom bootstrap so that eager
warmup and the serve loop share the same asyncio event loop, avoiding vLLM
EngineDeadError.
"""

import runpod

from handler import handler
from handler import _concurrency_modifier

runpod.serverless.start({
    "handler": handler,
    "concurrency_modifier": _concurrency_modifier,
})
