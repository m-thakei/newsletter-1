"""Render an infographic from a JSON spec into a PNG, using the HTML templates
in tools/templates/infographics/ and free Lucide icons (ISC license).

Usage:
    python tools/render_infographic.py spec.json [--out path.png]

Spec format (one of four templates):
    {
      "template": "key_figures" | "process" | "comparison" | "bar_chart",
      "eyebrow": "Optional small label above the title",
      "title": "Headline of the infographic",
      "subtitle": "Optional one-line explanation",
      "source": "Optional source line",
      "theme": {"navy": "#0B2545", "accent": "#B08D57", "soft": "#F3F5F8"},   # optional

      # key_figures: 2-4 items      {"icon", "value", "label", "note"}
      # process:     3-5 items      {"icon", "label", "title", "text"}
      # bar_chart:   3-7 items      {"label", "value" (number), "display", "highlight"}
      "items": [...],
      # comparison:  exactly 2      {"icon", "heading", "points": [...]}
      "columns": [...]
    }

Icon names are Lucide names, e.g. "trending-up", "shield-check", "users",
"globe", "landmark", "cpu", "clock", "target". Browse them at lucide.dev/icons.
Output defaults to .tmp/infographics/<spec name>.png (1200px wide, retina).
"""
import argparse
import json
import re

from _common import TEMPLATES, TMP, fail, launch_browser

import requests
from jinja2 import Environment, FileSystemLoader, StrictUndefined
from markupsafe import Markup

LUCIDE_VERSION = "0.460.0"
LUCIDE_URL = "https://unpkg.com/lucide-static@{v}/icons/{name}.svg"
ICON_CACHE = TMP / "icons"
DEFAULT_THEME = {"navy": "#0B2545", "accent": "#B08D57", "soft": "#F3F5F8"}
TEMPLATE_NAMES = {"key_figures", "process", "comparison", "bar_chart"}


def load_icon(name):
    if not re.fullmatch(r"[a-z0-9-]+", name):
        fail(f"Invalid icon name: {name!r}")
    ICON_CACHE.mkdir(parents=True, exist_ok=True)
    path = ICON_CACHE / f"{name}.svg"
    if not path.exists():
        resp = requests.get(LUCIDE_URL.format(v=LUCIDE_VERSION, name=name), timeout=30)
        if resp.status_code == 404:
            fail(f"Lucide has no icon named {name!r}. Browse names at https://lucide.dev/icons")
        resp.raise_for_status()
        path.write_text(resp.text)
    svg = path.read_text()
    svg = re.sub(r"<!--.*?-->", "", svg, flags=re.S)
    svg = re.sub(r'\s(width|height)="\d+"', "", svg)
    return Markup(svg.strip())


def collect_icon_names(spec):
    names = set()
    for it in spec.get("items", []) + spec.get("columns", []):
        if it.get("icon"):
            names.add(it["icon"])
    return names


def validate(spec):
    t = spec.get("template")
    if t not in TEMPLATE_NAMES:
        fail(f"'template' must be one of {sorted(TEMPLATE_NAMES)}, got {t!r}")
    if not spec.get("title"):
        fail("Spec needs a 'title'.")
    if t == "comparison":
        if len(spec.get("columns", [])) != 2:
            fail("comparison needs exactly 2 'columns'.")
    else:
        n = len(spec.get("items", []))
        limits = {"key_figures": (2, 4), "process": (3, 5), "bar_chart": (3, 7)}[t]
        if not limits[0] <= n <= limits[1]:
            fail(f"{t} needs {limits[0]}-{limits[1]} 'items', got {n}.")
        if t == "bar_chart" and not all(isinstance(i.get("value"), (int, float)) for i in spec["items"]):
            fail("bar_chart items need a numeric 'value'.")


def render_html(spec):
    env = Environment(loader=FileSystemLoader(str(TEMPLATES / "infographics")),
                      autoescape=True, undefined=StrictUndefined)
    n = len(spec.get("items", []))
    ctx = {
        "eyebrow": spec.get("eyebrow"),
        "title": spec["title"],
        "subtitle": spec.get("subtitle"),
        "source": spec.get("source"),
        "theme": {**DEFAULT_THEME, **spec.get("theme", {})},
        "items": spec.get("items", []),
        "columns": spec.get("columns", []),
        "cols": 2 if n in (2, 4) else max(n, 1),
        "icons": {name: load_icon(name) for name in collect_icon_names(spec)},
    }
    # Optional item fields default to None so StrictUndefined only catches typos in templates.
    for it in ctx["items"] + ctx["columns"]:
        for key in ("icon", "note", "label", "text", "display", "highlight"):
            it.setdefault(key, None)
    return env.get_template(f"{spec['template']}.html").render(**ctx)


def screenshot(html, out_path):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = launch_browser(p)
        page = browser.new_page(viewport={"width": 600, "height": 800}, device_scale_factor=2)
        page.set_content(html, wait_until="networkidle")
        page.evaluate("document.fonts.ready")
        page.locator(".card").screenshot(path=str(out_path))
        browser.close()


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("spec", help="Path to the infographic JSON spec")
    p.add_argument("--out", help="Output PNG path")
    p.add_argument("--html", action="store_true", help="Also save the intermediate HTML next to the PNG")
    args = p.parse_args()

    with open(args.spec) as f:
        spec = json.load(f)
    validate(spec)

    from pathlib import Path
    out = Path(args.out) if args.out else TMP / "infographics" / (Path(args.spec).stem + ".png")
    out.parent.mkdir(parents=True, exist_ok=True)

    html = render_html(spec)
    if args.html:
        out.with_suffix(".html").write_text(html)
    screenshot(html, out)
    print(f"Saved infographic -> {out}")


if __name__ == "__main__":
    main()
