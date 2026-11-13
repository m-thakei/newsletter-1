"""Build the newsletter email from a content JSON file.

Usage:
    .venv/bin/python tools/build_newsletter_html.py content.json

Produces, in .tmp/issues/<slug>/:
    email.html     the email body; images referenced as cid: (inline attachments)
    preview.html   the same layout with local image paths, to open in a browser
    preview.pdf    an A4 print of the preview (for reference or printing)
    manifest.json  subject, preheader and image list, read by send_gmail.py

Content format:
    {
      "name": "Newsletter name",          "tagline": "Optional strapline",
      "issue": "Issue 1",                 "date": "13 November 2026",
      "subject": "Email subject line",    "preheader": "Inbox preview text",
      "title": "Headline of this issue",
      "summary": ["3 short executive-summary points"],
      "sections": [
        {"heading": "...", "paragraphs": ["..."], "bullets": ["..."],
         "infographic": {"path": ".tmp/infographics/x.png", "alt": "Description"}}
      ],
      "closing": "The bottom line, one or two sentences",
      "sources": [{"title": "Publisher - article", "url": "https://..."}],
      "theme": {"navy": "#0B2545", "accent": "#B08D57", "soft": "#F3F5F8"},
      "footer": "Optional footer text"
    }
Text fields may use **bold**. Length rule: the written text is at most one A4
page (MAX_WORDS words). Infographics come on top and are not counted.
"""
import argparse
import json
import re
from pathlib import Path

from _common import ROOT, TEMPLATES, TMP, fail, slugify

from jinja2 import Environment, FileSystemLoader
from markupsafe import Markup, escape

DEFAULT_THEME = {"navy": "#0B2545", "accent": "#B08D57", "soft": "#F3F5F8"}
MAX_WORDS = 550  # about one A4 page of text
MAX_INFOGRAPHICS = 2


def inline(text):
    """Escape text, then turn **bold** into <strong>."""
    safe = str(escape(text))
    return Markup(re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", safe))


def resolve(path):
    p = Path(path)
    return p if p.is_absolute() else (ROOT / p)


def word_count(content):
    parts = [content.get("title", ""), content.get("closing", "")] + content.get("summary", [])
    for sec in content.get("sections", []):
        parts += [sec.get("heading", "")] + sec.get("paragraphs", []) + sec.get("bullets", [])
    return len(re.findall(r"\b[\w'%$.-]+\b", " ".join(parts)))


def render(content, image_src):
    env = Environment(loader=FileSystemLoader(str(TEMPLATES)), autoescape=True)
    env.filters["inline"] = inline
    ctx = {
        "name": content["name"], "tagline": content.get("tagline"),
        "issue": content.get("issue", ""), "date": content.get("date", ""),
        "subject": content["subject"], "preheader": content.get("preheader"),
        "title": content["title"], "summary": content.get("summary", []),
        "sections": content.get("sections", []), "closing": content.get("closing"),
        "sources": content.get("sources", []), "footer": content.get("footer"),
        "theme": {**DEFAULT_THEME, **content.get("theme", {})},
        "image_src": image_src,
    }
    return env.get_template("newsletter_email.html").render(**ctx)


def pdf_pages(html_path, pdf_path):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(channel="chrome")
        except Exception:
            browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(html_path.as_uri(), wait_until="networkidle")
        page.pdf(path=str(pdf_path), format="A4", print_background=True, prefer_css_page_size=True)
        browser.close()
    return len(re.findall(rb"/Type\s*/Page[^s]", pdf_path.read_bytes()))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("content", help="Path to the newsletter content JSON")
    p.add_argument("--out-dir", help="Output folder (default .tmp/issues/<slug>)")
    args = p.parse_args()

    content = json.loads(Path(args.content).read_text())
    for key in ("name", "subject", "title", "sections"):
        if not content.get(key):
            fail(f"Content is missing '{key}'.")

    images = []
    for sec in content["sections"]:
        info = sec.get("infographic")
        if info:
            path = resolve(info["path"])
            if not path.exists():
                fail(f"Infographic not found: {info['path']}")
            images.append({"path": str(path), "cid": f"img{len(images) + 1}", "alt": info.get("alt", "")})
    if len(images) > MAX_INFOGRAPHICS:
        fail(f"{len(images)} infographics; the format allows at most {MAX_INFOGRAPHICS}.")
    cid_for = {img["path"]: img["cid"] for img in images}

    out_dir = Path(args.out_dir) if args.out_dir else TMP / "issues" / slugify(content["title"])
    out_dir.mkdir(parents=True, exist_ok=True)

    email_html = render(content, lambda p: f"cid:{cid_for[str(resolve(p))]}")
    preview_html = render(content, lambda p: resolve(p).as_uri())
    (out_dir / "email.html").write_text(email_html)
    preview_path = out_dir / "preview.html"
    preview_path.write_text(preview_html)

    (out_dir / "manifest.json").write_text(json.dumps({
        "subject": content["subject"],
        "preheader": content.get("preheader", ""),
        "html": str(out_dir / "email.html"),
        "images": images,
    }, indent=2))

    words = word_count(content)
    pages = pdf_pages(preview_path, out_dir / "preview.pdf")
    print(f"Built issue -> {out_dir}")
    print(f"Words: {words} (limit {MAX_WORDS}) | Infographics: {len(images)} | Printed A4 pages incl. images: {pages}")
    if words > MAX_WORDS:
        print(f"WARNING: {words - MAX_WORDS} words over the limit. Tighten the copy before sending.")


if __name__ == "__main__":
    main()
