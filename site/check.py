#!/usr/bin/env python3
"""Check static output and content; no server or browser is started."""
import argparse
import json
import re
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"
PAGES = [DIST / "index.html"] + [DIST / slug / "index.html" for slug in ("pt-br", "en-us", "es-es")]


class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids, self.refs, self.images, self.inline = [], [], [], []
        self.lang = None
        self.h1 = 0
        self.script = None

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "html":
            self.lang = attributes.get("lang")
        if "id" in attributes:
            self.ids.append(attributes["id"])
        if tag == "h1":
            self.h1 += 1
        for key in ("href", "src"):
            if key in attributes:
                self.refs.append(attributes[key])
        if tag == "img":
            self.images.append(attributes)
        if tag == "script" and attributes.get("type") in ("application/json", "application/ld+json"):
            self.script = ""

    def handle_data(self, data):
        if self.script is not None:
            self.script += data

    def handle_endtag(self, tag):
        if tag == "script" and self.script is not None:
            self.inline.append(json.loads(self.script))
            self.script = None


def shape(value):
    if isinstance(value, dict):
        return {key: shape(item) for key, item in value.items()}
    if isinstance(value, list):
        return [shape(item) for item in value]
    return type(value).__name__


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--allow-pending-download", action="store_true")
    args = parser.parse_args()
    errors, checked, pending = [], [], []
    for path in PAGES:
        parsed = Page()
        source = path.read_text()
        parsed.feed(source)
        expected_lang = {"pt-br": "pt-BR", "en-us": "en-US", "es-es": "es-ES"}.get(path.parent.name, "pt-BR")
        if parsed.lang != expected_lang:
            errors.append(f"{path}: wrong language")
        if parsed.h1 != 1:
            errors.append(f"{path}: expected one h1")
        duplicates = [name for name, count in Counter(parsed.ids).items() if count > 1]
        if duplicates:
            errors.append(f"{path}: duplicate ids {duplicates}")
        for image in parsed.images:
            if "alt" not in image:
                errors.append(f"{path}: image without alt")
        for ref in parsed.refs:
            url = urlsplit(ref)
            if url.scheme or url.netloc:
                continue
            destination = (DIST / unquote(url.path).lstrip("/")) if url.path.startswith("/") else (path.parent / unquote(url.path))
            if not url.path:
                if url.fragment and url.fragment not in parsed.ids:
                    errors.append(f"{path}: missing anchor {ref}")
                continue
            if destination.is_dir():
                destination = destination / "index.html"
            if not destination.exists():
                if args.allow_pending_download and url.path.startswith("/downloads/"):
                    pending.append(ref)
                else:
                    errors.append(f"{path}: missing {ref}")
        if "—" in source or "TODO" in source:
            errors.append(f"{path}: prohibited marker")
        checked.append({"page": str(path.relative_to(DIST)), "lang": parsed.lang, "images": len(parsed.images), "h1": parsed.h1, "inline_json": len(parsed.inline)})
    catalogs = [json.loads((ROOT / "content" / (slug + ".json")).read_text()) for slug in ("pt-br", "en-us", "es-es")]
    if any(shape(catalog) != shape(catalogs[0]) for catalog in catalogs[1:]):
        errors.append("Locale content structures differ")
    css = (DIST / "assets/site.css").read_text()
    if "prefers-reduced-motion" not in css:
        errors.append("Reduced motion missing")
    for url in re.findall(r"url\(['\"]?([^)'\"]+)", css):
        if not (DIST / url.lstrip("/")).exists():
            errors.append(f"Missing CSS asset: {url}")
    if (DIST / "assets/fonts/InterVariable.woff2").read_bytes()[:4] != b"wOF2":
        errors.append("Font is not WOFF2")
    print(json.dumps({"pages": checked, "locale_shapes_equal": not any(shape(c) != shape(catalogs[0]) for c in catalogs), "pending_downloads": sorted(set(pending)), "errors": errors}, ensure_ascii=False, indent=2))
    raise SystemExit(bool(errors))
