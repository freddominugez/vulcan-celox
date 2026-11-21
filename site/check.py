#!/usr/bin/env python3
"""Check static output and content; no server or browser is started."""
import argparse
import json
import re
import struct
import xml.etree.ElementTree as ET
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

from biblioteca.conteudo import ARTICLES, HUB, PAGES as LIBRARY_PAGES, PROMPTS

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"
PAGES = [DIST / "index.html"] + [DIST / slug / "index.html" for slug in ("pt-br", "en-us", "es-es")]
LIBRARY_PATHS = {DIST / route.strip("/") / "index.html": route for route in LIBRARY_PAGES}
SETTINGS = json.loads((ROOT / "settings.json").read_text())
ORIGIN = SETTINGS["origin"].rstrip("/")
CANONICALS = {"pt-BR": ORIGIN + "/", "en-US": ORIGIN + "/en-us/", "es-ES": ORIGIN + "/es-es/"}
ALTERNATES = CANONICALS | {"x-default": CANONICALS["pt-BR"]}
SITEMAP_NS = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9", "x": "http://www.w3.org/1999/xhtml"}


class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids, self.refs, self.images, self.inline = [], [], [], []
        self.canonicals, self.alternates, self.metadata = [], [], {}
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
        if tag == "link":
            if attributes.get("rel") == "canonical":
                self.canonicals.append(attributes.get("href"))
            if attributes.get("rel") == "alternate" and "hreflang" in attributes:
                self.alternates.append((attributes["hreflang"], attributes.get("href")))
        if tag == "meta" and "content" in attributes:
            self.metadata.setdefault(attributes.get("property") or attributes.get("name"), []).append(attributes["content"])
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


def check_page_metadata(page, language):
    errors = []
    canonical = CANONICALS[language]
    if page.canonicals != [canonical]:
        errors.append("canonical URL")
    if Counter(page.alternates) != Counter(ALTERNATES.items()):
        errors.append("hreflang URLs")
    if page.metadata.get("robots") != ["index, follow, max-image-preview:large"]:
        errors.append("robots meta")
    locale = language.replace("-", "_")
    if page.metadata.get("og:locale") != [locale]:
        errors.append("Open Graph locale")
    other_locales = sorted(lang.replace("-", "_") for lang in CANONICALS if lang != language)
    if sorted(page.metadata.get("og:locale:alternate", [])) != other_locales:
        errors.append("Open Graph alternate locales")
    if page.metadata.get("og:url") != [canonical]:
        errors.append("Open Graph URL")
    image = ORIGIN + f"/assets/screens/overview-{language.split('-')[0]}.png"
    png = DIST / urlsplit(image).path.lstrip("/")
    dimensions = ()
    if png.is_file():
        with png.open("rb") as source:
            dimensions = struct.unpack(">II", source.read(24)[16:24])
    og_dimensions = page.metadata.get("og:image:width", []) + page.metadata.get("og:image:height", [])
    if (page.metadata.get("og:image") != [image] or page.metadata.get("twitter:image") != [image]
            or not dimensions or og_dimensions != [str(size) for size in dimensions]):
        errors.append("social image URL or dimensions")
    graph = next((item["@graph"] for item in page.inline if "@graph" in item), [])
    entities = {entity["@type"]: entity for entity in graph}
    website, webpage, app = (entities.get(key, {}) for key in ("WebSite", "WebPage", "SoftwareApplication"))
    if (website.get("url") != ORIGIN + "/" or webpage.get("url") != canonical
            or webpage.get("inLanguage") != language or app.get("url") != ORIGIN + "/"
            or app.get("downloadUrl") != SETTINGS["downloadUrl"] or app.get("screenshot") != image
            or app.get("softwareVersion") != SETTINGS["version"] or app.get("offers", {}).get("price") != 0):
        errors.append("structured data")
    return errors


def check_library_metadata(page, route):
    errors = []
    canonical = ORIGIN + route
    if page.canonicals != [canonical] or page.metadata.get("og:url") != [canonical]:
        errors.append("library canonical/social URL")
    if page.alternates:
        errors.append("library pages in this edition have no translated equivalents")
    if page.metadata.get("description") != [LIBRARY_PAGES[route][1]]:
        errors.append("library description")
    if page.metadata.get("robots") != ["index, follow, max-image-preview:large"]:
        errors.append("library robots meta")
    image = page.metadata.get("og:image", [])
    if (len(image) != 1 or not image[0].startswith(ORIGIN + "/assets/screens/")
            or not (DIST / urlsplit(image[0]).path.lstrip("/")).is_file()
            or page.metadata.get("twitter:image") != image):
        errors.append("library social image")
    graph = next((item["@graph"] for item in page.inline if "@graph" in item), [])
    entities = {entity["@type"]: entity for entity in graph}
    expected_crumbs = [ORIGIN + "/"] + ([ORIGIN + HUB] if route != HUB else []) + [canonical]
    crumbs = entities.get("BreadcrumbList", {}).get("itemListElement", [])
    if [crumb.get("item") for crumb in crumbs] != expected_crumbs:
        errors.append("library breadcrumb data")
    if route in ARTICLES and entities.get("Article", {}).get("mainEntityOfPage") != canonical:
        errors.append("library Article data")
    return errors


def check_crawl_files():
    errors = []
    sitemap = ET.parse(DIST / "sitemap.xml")
    entries = sitemap.findall("s:url", SITEMAP_NS)
    locations = [entry.findtext("s:loc", namespaces=SITEMAP_NS) for entry in entries]
    expected_locations = [*CANONICALS.values(), *(ORIGIN + route for route in LIBRARY_PAGES)]
    if Counter(locations) != Counter(expected_locations):
        errors.append("Sitemap locations differ from canonical URLs")
    for entry, location in zip(entries, locations):
        alternates = [
            (link.get("hreflang"), link.get("href"))
            for link in entry.findall("x:link", SITEMAP_NS)
            if link.get("rel") == "alternate"
        ]
        expected = ALTERNATES.items() if location in CANONICALS.values() else []
        if Counter(alternates) != Counter(expected):
            errors.append(f"Sitemap hreflang mismatch at {location}")
    robots = (DIST / "robots.txt").read_text().splitlines()
    if robots != ["User-agent: *", "Allow: /", f"Sitemap: {ORIGIN}/sitemap.xml"]:
        errors.append("Robots file crawl directives or sitemap")
    return errors


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--allow-pending-download", action="store_true")
    args = parser.parse_args()
    errors, checked, pending = [], [], []
    all_pages = {}
    for path in [*PAGES, *LIBRARY_PATHS]:
        parsed = Page()
        source = path.read_text()
        parsed.feed(source)
        all_pages[path] = parsed
    for path, parsed in all_pages.items():
        expected_lang = {"pt-br": "pt-BR", "en-us": "en-US", "es-es": "es-ES"}.get(path.parent.name, "pt-BR")
        if parsed.lang != expected_lang:
            errors.append(f"{path}: wrong language")
        if parsed.h1 != 1:
            errors.append(f"{path}: expected one h1")
        if path in LIBRARY_PATHS:
            issues = check_library_metadata(parsed, LIBRARY_PATHS[path])
        else:
            issues = check_page_metadata(parsed, expected_lang)
            if HUB not in parsed.refs:
                issues.append("missing library navigation")
        errors.extend(f"{path}: invalid {error}" for error in issues)
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
            if url.fragment and destination in all_pages and url.fragment not in all_pages[destination].ids:
                errors.append(f"{path}: missing anchor {ref}")
        source = path.read_text()
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
    for slug, _, _, _, _, body in PROMPTS:
        download = DIST / "prompts" / "arquivos" / f"{slug}.md"
        if not download.is_file() or not download.read_text().endswith(f"---\n{body}\n"):
            errors.append(f"Missing or stale prompt download: {slug}")
    errors.extend(check_crawl_files())
    print(json.dumps({"pages": checked, "locale_shapes_equal": not any(shape(c) != shape(catalogs[0]) for c in catalogs), "pending_downloads": sorted(set(pending)), "errors": errors}, ensure_ascii=False, indent=2))
    raise SystemExit(bool(errors))
