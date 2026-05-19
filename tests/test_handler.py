"""Handler-side unit tests. Exercise the parts that don't need a GPU or MinerU.

The handler module is intentionally written so it imports cleanly even when
the heavy `mineru` dependency is unavailable (it wraps that import in try /
except and falls back to a "mineru is not importable" path). That lets us
test input validation, packaging, and error handling on plain Python CI.
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
import tarfile
from pathlib import Path

import pytest

import handler


# -----------------------------------------------------------------------------
# _resolve_pdf_bytes
# -----------------------------------------------------------------------------

def test_resolve_requires_exactly_one_source():
    with pytest.raises(ValueError, match="exactly one"):
        asyncio.run(handler._resolve_pdf_bytes({}))
    with pytest.raises(ValueError, match="exactly one"):
        asyncio.run(handler._resolve_pdf_bytes({"pdf_url": "x", "pdf_b64": "y"}))


def test_resolve_b64_roundtrip():
    payload = base64.b64encode(b"%PDF-1.4 inline").decode("ascii")
    raw, src = asyncio.run(handler._resolve_pdf_bytes({"pdf_b64": payload}))
    assert raw == b"%PDF-1.4 inline"
    assert src == "b64"


def test_resolve_b64_rejects_oversized_payload():
    too_big = base64.b64encode(b"x" * (handler.MAX_INLINE_PDF_MB * 1024 * 1024 + 1)).decode("ascii")
    with pytest.raises(ValueError, match="inline PDF too large"):
        asyncio.run(handler._resolve_pdf_bytes({"pdf_b64": too_big}))


def test_resolve_volume_path_reads_file(tmp_path):
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.4 volume")
    raw, src = asyncio.run(handler._resolve_pdf_bytes({"volume_path": str(pdf)}))
    assert raw == b"%PDF-1.4 volume"
    assert src.startswith("volume:")


def test_resolve_volume_path_missing_file(tmp_path):
    missing = tmp_path / "nope.pdf"
    with pytest.raises(ValueError, match="volume_path not found"):
        asyncio.run(handler._resolve_pdf_bytes({"volume_path": str(missing)}))


# -----------------------------------------------------------------------------
# _package_tarball / _package_inline
# -----------------------------------------------------------------------------

def _seed_mineru_output(dir_: Path, basename: str) -> None:
    (dir_ / f"{basename}.md").write_text("# heading\n\nbody\n", encoding="utf-8")
    (dir_ / f"{basename}_content_list.json").write_text(
        json.dumps([{"type": "text", "text": "body", "page_idx": 0}]),
        encoding="utf-8",
    )
    (dir_ / f"{basename}_middle.json").write_text(json.dumps({"k": 1}), encoding="utf-8")
    (dir_ / "images").mkdir()
    (dir_ / "images" / "fig1.png").write_bytes(b"\x89PNG fake")


def test_package_tarball_includes_all_artefacts(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    _seed_mineru_output(out, "doc")

    encoded = handler._package_tarball(out)
    raw = base64.b64decode(encoded)
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as tar:
        names = set(tar.getnames())
    assert "doc.md" in names
    assert "doc_content_list.json" in names
    assert "doc_middle.json" in names
    assert "images/fig1.png" in names or "images" in names


def test_package_inline_returns_full_payload(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    _seed_mineru_output(out, "doc")

    pkg = handler._package_inline(out, "doc")
    assert pkg["markdown"].startswith("# heading")
    assert pkg["content_list"][0]["text"] == "body"
    assert pkg["middle"]["k"] == 1
    assert "fig1.png" in pkg["images"]
    assert base64.b64decode(pkg["images"]["fig1.png"]) == b"\x89PNG fake"


# -----------------------------------------------------------------------------
# handler() top-level error paths
# -----------------------------------------------------------------------------

def test_handler_returns_error_on_bad_input():
    result = asyncio.run(handler.handler({"input": {}}))  # no source provided
    # RunPod-convention: top-level `error` key marks the job FAILED.
    assert "error" in result
    assert result["ok"] is False
    assert "exactly one" in result["error"]
    # Even on error, the metadata fields are present.
    assert "mineru_version" in result
    assert "elapsed_seconds" in result


def test_handler_rejects_bad_basename():
    result = asyncio.run(handler.handler({"input": {"pdf_b64": "AA==", "basename": "../bad"}}))
    assert "error" in result
    assert result["ok"] is False
    # rp_validator reports its own message; we just check it's about input.
    assert "input validation" in result["error"].lower() or "basename" in result["error"].lower()


def test_validate_input_rejects_invalid_return_value():
    with pytest.raises(ValueError, match="input validation"):
        handler._validate_input({"pdf_b64": "AA==", "return": "tarball-xml"})


def test_validate_input_defaults_applied():
    cleaned = handler._validate_input({"pdf_b64": "AA=="})
    assert cleaned["start_page"] == 0
    assert cleaned["end_page"] == -1
    assert cleaned["lang"] == "en"
    assert cleaned["backend"] == "vlm-vllm-async-engine"
    assert cleaned["return"] == "tarball_b64"
    assert cleaned["basename"] == "doc"
