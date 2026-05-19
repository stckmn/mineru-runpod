"""mineru_client — thin Python wrapper around a deployed runpod-mineru endpoint.

Usage:

    from mineru_client import MineruClient

    client = MineruClient(endpoint_id="...", api_key="...")
    result = client.parse_pdf(pdf_url="https://...", start_page=0, end_page=99)
    client.save_tarball(result, dest_dir="./out")
"""

from .client import MineruClient, MineruClientError

__all__ = ["MineruClient", "MineruClientError"]
