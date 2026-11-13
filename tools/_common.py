"""Shared helpers for the newsletter tools: paths, .env loading, slugs."""
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
TEMPLATES = TOOLS / "templates"
TMP = ROOT / ".tmp"

load_dotenv(ROOT / ".env")


def slugify(text: str, max_len: int = 60) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:max_len].rstrip("-") or "untitled"


def launch_browser(playwright):
    """Start a headless browser: an installed Google Chrome if there is one,
    otherwise Playwright's own Chromium (`python -m playwright install chromium`)."""
    try:
        return playwright.chromium.launch(channel="chrome")
    except Exception:
        pass
    try:
        return playwright.chromium.launch()
    except Exception:
        fail("No browser available to render images. Run: python -m playwright install chromium")


def fail(message: str, code: int = 1) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    sys.exit(code)
