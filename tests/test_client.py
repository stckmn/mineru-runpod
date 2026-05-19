"""Client-side unit tests. No GPU, no MinerU, no network."""

from __future__ import annotations

import base64
import io
import json
import os
import tarfile
from pathlib import Path

import pytest

from mineru_client import MineruClient, MineruClientError


@pytest.fixture
def fake_endpoint(monkeypatch):
    """Patch runpod.Endpoint so MineruClient never reaches the network."""
    import runpod

    class _FakeEndpoint:
        def __init__(self, endpoint_id):
            self.endpoint_id = endpoint_id
            self.last_payload = None
            # next_result is mutated by tests before calling parse_pdf().
            self.next_result = {"ok": True, "elapsed_seconds": 0.1, "pages_processed": 0,
                                "mineru_version": "fake", "tarball_b64": ""}

        def run_sync(self, payload, timeout):  # noqa: ARG002
            self.last_payload = payload
            return self.next_result

    monkeypatch.setattr(runpod, "Endpoint", _FakeEndpoint)
    return _FakeEndpoint


def test_requires_endpoint_id():
    with pytest.raises(ValueError, match="endpoint_id is required"):
        MineruClient(endpoint_id="")


def test_requires_api_key():
    os.environ.pop("RUNPOD_API_KEY", None)
    with pytest.raises(ValueError, match="api_key not provided"):
        MineruClient(endpoint_id="ep-1")


def test_constructs_with_explicit_api_key(fake_endpoint):
    client = MineruClient(endpoint_id="ep-1", api_key="secret")
    assert client.endpoint_id == "ep-1"


def test_constructs_with_env_api_key(monkeypatch, fake_endpoint):
    monkeypatch.setenv("RUNPOD_API_KEY", "secret-env")
    client = MineruClient(endpoint_id="ep-1")
    assert client.endpoint_id == "ep-1"


def test_parse_pdf_rejects_no_source(fake_endpoint):
    client = MineruClient(endpoint_id="ep-1", api_key="x")
    with pytest.raises(ValueError, match="exactly one"):
        client.parse_pdf()


def test_parse_pdf_rejects_multiple_sources(fake_endpoint):
    client = MineruClient(endpoint_id="ep-1", api_key="x")
    with pytest.raises(ValueError, match="exactly one"):
        client.parse_pdf(pdf_url="https://x", pdf_b64="abc")


def test_parse_pdf_forwards_options(fake_endpoint):
    client = MineruClient(endpoint_id="ep-1", api_key="x")
    client.parse_pdf(
        pdf_url="https://example.com/p.pdf",
        start_page=10,
        end_page=20,
        lang="ja",
        backend="vlm-auto-engine",
        formula_enable=False,
        table_enable=False,
        return_format="inline",
        basename="custom",
    )
    payload = client._endpoint.last_payload
    assert payload["pdf_url"] == "https://example.com/p.pdf"
    assert payload["start_page"] == 10
    assert payload["end_page"] == 20
    assert payload["lang"] == "ja"
    assert payload["backend"] == "vlm-auto-engine"
    assert payload["formula_enable"] is False
    assert payload["table_enable"] is False
    assert payload["return"] == "inline"
    assert payload["basename"] == "custom"


def test_parse_pdf_raises_on_handler_error(fake_endpoint):
    client = MineruClient(endpoint_id="ep-1", api_key="x")
    client._endpoint.next_result = {"ok": False, "error": "boom"}
    with pytest.raises(MineruClientError, match="boom"):
        client.parse_pdf(pdf_url="https://x")


def test_parse_pdf_from_file_inlines_bytes(fake_endpoint, tmp_path):
    pdf = tmp_path / "tiny.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%%EOF")
    client = MineruClient(endpoint_id="ep-1", api_key="x")
    MineruClient.parse_pdf_from_file(client, pdf)
    payload = client._endpoint.last_payload
    assert "pdf_b64" in payload
    assert base64.b64decode(payload["pdf_b64"]) == b"%PDF-1.4\n%%EOF"


def test_save_tarball_requires_tarball_field(tmp_path):
    with pytest.raises(MineruClientError, match="no tarball_b64"):
        MineruClient.save_tarball({"ok": True}, tmp_path)


def test_save_tarball_roundtrip(tmp_path):
    # Build a fake tarball that mirrors what the handler emits.
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        md_data = b"# hello\n"
        info = tarfile.TarInfo("doc.md")
        info.size = len(md_data)
        tar.addfile(info, io.BytesIO(md_data))
    encoded = base64.b64encode(buf.getvalue()).decode("ascii")
    dest = MineruClient.save_tarball({"tarball_b64": encoded}, tmp_path / "out")
    assert (Path(dest) / "doc.md").read_bytes() == b"# hello\n"


def test_save_inline_writes_files(tmp_path):
    result = {
        "markdown": "# md\n",
        "content_list": [{"type": "text", "text": "hi"}],
        "middle": {"k": 1},
        "images": {"a.png": base64.b64encode(b"\x89PNG").decode("ascii")},
    }
    dest = MineruClient.save_inline(result, tmp_path / "out", basename="x")
    assert (dest / "x.md").read_text() == "# md\n"
    assert json.loads((dest / "x_content_list.json").read_text())[0]["text"] == "hi"
    assert json.loads((dest / "x_middle.json").read_text())["k"] == 1
    assert (dest / "images" / "a.png").read_bytes() == b"\x89PNG"


def test_save_inline_requires_markdown_field(tmp_path):
    with pytest.raises(MineruClientError, match="no markdown"):
        MineruClient.save_inline({"ok": True}, tmp_path)
