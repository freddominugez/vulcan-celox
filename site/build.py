#!/usr/bin/env python3
"""Build three complete static pages, with no runtime framework or external asset."""
import html
import json
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "dist"
SETTINGS = json.loads((ROOT / "settings.json").read_text())
ORIGIN = SETTINGS["origin"].rstrip("/")
REPO = "https://github.com/freddominugez/vulcan-celox"
LANGUAGES = [("pt-br", "pt-BR", "PT", "/"), ("en-us", "en-US", "EN", "/en-us/"), ("es-es", "es-ES", "ES", "/es-es/")]
PATHS = {slug: path for slug, _, _, path in LANGUAGES}
ALTERNATES = {lang: ORIGIN + path for _, lang, _, path in LANGUAGES}
ALTERNATES["x-default"] = ORIGIN + "/"


def esc(text):
    return html.escape(str(text), quote=True)


def icon(name):
    return f'<img class="icon" src="/assets/icons/{name}.svg" alt="" width="24" height="24" aria-hidden="true">'


def button(label, href, primary=True):
    return f'<a class="button {"primary" if primary else "secondary"}" href="{esc(href)}">{esc(label)}</a>'


def structured_data(c, url, image_url):
    website_id = ORIGIN + "/#website"
    software_id = ORIGIN + "/#software"
    return {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "WebSite",
                "@id": website_id,
                "url": ORIGIN + "/",
                "name": "Vulcan Celox",
                "inLanguage": [lang for _, lang, _, _ in LANGUAGES],
            },
            {
                "@type": "WebPage",
                "@id": url + "#page",
                "url": url,
                "name": c["title"],
                "description": c["description"],
                "inLanguage": c["lang"],
                "isPartOf": {"@id": website_id},
                "mainEntity": {"@id": software_id},
            },
            {
                "@type": "SoftwareApplication",
                "@id": software_id,
                "name": "Vulcan Celox",
                "url": ORIGIN + "/",
                "description": c["description"],
                "applicationCategory": "DeveloperApplication",
                "operatingSystem": "macOS 13+",
                "softwareVersion": SETTINGS["version"],
                "softwareRequirements": "Python 3.9+",
                "inLanguage": [lang for _, lang, _, _ in LANGUAGES],
                "offers": {"@type": "Offer", "price": 0},
                "license": REPO + "/blob/main/LICENSE",
                "sameAs": REPO,
                "downloadUrl": SETTINGS["downloadUrl"],
                "screenshot": image_url,
                "featureList": c["terminalItems"],
            },
        ],
    }


def page(slug, c):
    path = PATHS[slug]
    url = ORIGIN + path
    nav_ids = ["product", "inside", "workflow", "faq"]
    docs_lang = "pt-BR" if slug == "pt-br" else "en"
    docs = REPO + "/blob/main/docs/" + docs_lang
    nav = "".join(f'<a href="#{section}">{esc(label)}</a>' for label, section in zip(c["nav"], nav_ids))
    languages = "".join(f'<a href="{target}" lang="{lang}" hreflang="{lang}" data-language="{code}" {"aria-current=page" if code == slug else ""}>{label}</a>' for code, lang, label, target in LANGUAGES)
    alternates = "\n".join(f'<link rel="alternate" hreflang="{lang}" href="{href}">' for lang, href in ALTERNATES.items())
    og_alternates = "\n".join(f'<meta property="og:locale:alternate" content="{lang.replace("-", "_")}">' for _, lang, _, _ in LANGUAGES if lang != c["lang"])
    image_path = f'/assets/screens/overview-{c["screenLang"]}.png'
    image_url = ORIGIN + image_path
    image_alt = c["screens"][0]["alt"]
    with (OUT / image_path.lstrip("/")).open("rb") as image:
        image_width, image_height = struct.unpack(">II", image.read(24)[16:24])
    terminal_screen = next(screen for screen in c["screens"] if screen["id"] == "terminals")
    terminal_path = f'/assets/screens/terminals-{c["screenLang"]}.png'
    tabs = "".join(f'<button type="button" role="tab" id="tab-{s["id"]}" aria-controls="showcase-panel" aria-selected="{str(i == 0).lower()}" tabindex="{0 if i == 0 else -1}" data-screen="{s["id"]}">{esc(s["title"])}</button>' for i, s in enumerate(c["screens"]))
    workflow = "".join(f'<article class="workflow-item"><span class="workflow-icon">{icon(name)}</span><div><h3>{esc(item["title"])}</h3><p>{esc(item["text"])}</p></div></article>' for item, name in zip(c["workflow"], ("folder", "sparkle", "git-branch")))
    privacy = "".join(f'<article class="privacy-item">{icon(name)}<h3>{esc(item["title"])}</h3><p>{esc(item["text"])}</p></article>' for item, name in zip(c["privacy"], ("database", "lock", "code")))
    install = "".join(f'<li><h3>{esc(item["title"])}</h3><p>{esc(item["text"])}</p></li>' for item in c["installSteps"])
    faq = "".join(f'<details><summary>{esc(item["q"])}</summary><p>{esc(item["a"])}</p></details>' for item in c["faq"])
    stack = "".join(f'<span>{esc(item)}</span>' for item in c["stack"])
    terminal_items = "".join(f'<li>{icon("check")}<span>{esc(item)}</span></li>' for item in c["terminalItems"])
    env_items = "".join(f'<li>{icon("check")}<span>{esc(item)}</span></li>' for item in c["environmentItems"])
    language_items = "".join(f'<a class="language-card" href="{target}" lang="{language}" hreflang="{language}" data-language="{code}" {"aria-current=page" if code == slug else ""}><span>{label}</span><b>{esc(name)}</b></a>' for (code, language, label, target), name in zip(LANGUAGES, c["languageNames"]))
    footer_urls = [docs + "/README.md", docs + "/installation.md", docs + "/security.md", REPO, REPO + "/blob/main/LICENSE"]
    footer_links = "".join(f'<a href="{url}" target="_blank" rel="noopener noreferrer">{esc(label)}</a>' for label, url in zip(c["footerLinks"], footer_urls))
    downloads = SETTINGS["downloadUrl"]
    download_note = c["downloadNote"]
    if SETTINGS.get("downloadKind") == "direct":
        download_note = {
            "pt-br": f'Versão {SETTINGS["version"]} universal, para Apple Silicon e Intel, com os três idiomas. Aplicativo sem notarização Apple.',
            "en-us": f'Version {SETTINGS["version"]}, universal for Apple Silicon and Intel, with all three languages. The app is not notarized by Apple.',
            "es-es": f'Versión {SETTINGS["version"]} universal para Apple Silicon e Intel, con los tres idiomas. La aplicación no está notarizada por Apple.'
        }[slug]
    gallery_data = json.dumps({"screens": c["screens"], "screenLang": c["screenLang"], "menu": c["menu"], "closeMenu": c["closeMenu"]}, ensure_ascii=False).replace("</", "<\/")
    schema = json.dumps(structured_data(c, url, image_url), ensure_ascii=False).replace("<", "\\u003c")
    return f'''<!doctype html>
<html lang="{c['lang']}">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(c['title'])}</title><meta name="description" content="{esc(c['description'])}"><meta name="theme-color" content="#FAF6EE" media="(prefers-color-scheme: light)"><meta name="theme-color" content="#070D18" media="(prefers-color-scheme: dark)">
<link rel="canonical" href="{url}">
{alternates}
<meta name="robots" content="index, follow, max-image-preview:large">
<meta property="og:type" content="website"><meta property="og:site_name" content="Vulcan Celox"><meta property="og:locale" content="{c['locale']}">
{og_alternates}
<meta property="og:title" content="{esc(c['title'])}"><meta property="og:description" content="{esc(c['description'])}"><meta property="og:url" content="{url}">
<meta property="og:image" content="{image_url}"><meta property="og:image:type" content="image/png"><meta property="og:image:width" content="{image_width}"><meta property="og:image:height" content="{image_height}"><meta property="og:image:alt" content="{esc(image_alt)}">
<meta name="twitter:card" content="summary_large_image"><meta name="twitter:title" content="{esc(c['title'])}"><meta name="twitter:description" content="{esc(c['description'])}"><meta name="twitter:image" content="{image_url}"><meta name="twitter:image:alt" content="{esc(image_alt)}">
<link rel="icon" type="image/png" href="/assets/brand/favicon.png"><link rel="apple-touch-icon" href="/assets/brand/app-icon.png"><link rel="preload" as="font" href="/assets/fonts/InterVariable.woff2" type="font/woff2" crossorigin><link rel="stylesheet" href="/assets/site.css">
<script type="application/ld+json">{schema}</script><script type="application/json" id="page-data">{gallery_data}</script><script src="/assets/site.js" defer></script>
</head>
<body>
<a class="skip-link" href="#main">{esc(c['skip'])}</a>
<header class="site-header">
  <div class="nav-shell container">
    <a class="brand" href="{path}"><picture>
      <source media="(prefers-color-scheme: dark)" srcset="/assets/brand/logo-reverse.svg">
      <img src="/assets/brand/logo-primary.svg" alt="Vulcan Celox" width="280" height="64">
    </picture></a>
    <nav class="desktop-nav" aria-label="{esc(c['footerProduct'])}">{nav}</nav>
    <div class="nav-actions">
      <nav class="language-nav" aria-label="{esc(c['languageLabel'])}">{languages}</nav>
      <a href="#download" class="nav-download">{esc(c['downloadShort'])}</a>
      <button class="menu-toggle" type="button" aria-expanded="false" aria-controls="mobile-menu" aria-label="{esc(c['menu'])}">{icon('list')}</button>
    </div>
  </div>
  <nav id="mobile-menu" class="mobile-menu container" aria-label="{esc(c['menu'])}" hidden>{nav}<a href="#download">{esc(c['download'])}</a></nav>
</header>
<main id="main">
  <section class="hero container" aria-labelledby="hero-title">
    <div class="hero-grid">
      <div class="hero-copy">
        <h1 id="hero-title">{c['headline']}</h1>
        <p class="hero-intro">{esc(c['intro'])}</p>
        <div class="hero-actions">
          {button(c['download'], downloads)}
          {button(c['github'], REPO, False)}
        </div>
      </div>
      <figure class="hero-screenshot">
        <a class="screenshot-button shot" href="{image_path}" data-zoom aria-label="{esc(c['zoom'])}">
          <img src="{image_path}" alt="{esc(image_alt)}" width="{image_width}" height="{image_height}" fetchpriority="high" decoding="async">
        </a>
        <figcaption>{esc(c['imageNote'])}</figcaption>
      </figure>
    </div>
    <dl class="spec-strip">
      <div><dt>{esc(c['versionLabel'])}</dt><dd>{esc(SETTINGS['version'])}</dd></div>
      <div><dt>{esc(c['systemLabel'])}</dt><dd>macOS 13+</dd></div>
      <div><dt>{esc(c['architectureLabel'])}</dt><dd>Apple Silicon · Intel</dd></div>
      <div><dt>{esc(c['licenseLabel'])}</dt><dd><a href="{REPO}/blob/main/LICENSE">MIT</a></dd></div>
    </dl>
  </section>

  <section class="session-band section" id="product" aria-labelledby="product-title">
    <div class="container session-layout">
      <div>
        <h2 id="product-title">{esc(c['exampleTitle'])}</h2>
        <p>{esc(c['exampleBody'])}</p>
      </div>
      <figure class="session-example">
        <div class="session-top"><code>feat/checkout-pix</code><span class="session-status">{esc(c['exampleStatus'])}</span></div>
        <p class="session-ask">{esc(c['exampleAsk'])}</p>
        <ol class="session-trail">
          <li class="is-complete">{esc(c['exampleEdit'])}</li><li class="is-complete">Commit</li><li>Push</li><li>PR</li>
        </ol>
        <p class="session-meta">Claude Code <span>{esc(c['exampleMeta'])}</span></p>
        <figcaption>{esc(c['exampleNote'])}</figcaption>
      </figure>
    </div>
  </section>

  <section class="showcase section" id="inside" aria-labelledby="inside-title">
    <div class="container">
      <div class="section-heading">
        <h2 id="inside-title">{c['showcaseTitle']}</h2>
        <p>{esc(c['showcaseBody'])}</p>
      </div>
      <div class="showcase-grid">
        <div class="showcase-sidebar">
          <div class="screen-tabs" role="tablist" aria-label="{esc(c['galleryLabel'])}">{tabs}</div>
          <p class="image-note">{esc(c['imageNote'])}</p>
        </div>
        <div class="gallery">
          <div class="app-frame shot" id="showcase-panel" role="tabpanel" aria-labelledby="tab-overview" tabindex="0">
            <div class="window-bar"><span>Vulcan Celox</span><span id="gallery-window-label">{esc(c['screens'][0]['title'])}</span></div>
            <a class="screenshot-button" href="{image_path}" data-zoom aria-label="{esc(c['zoom'])}">
              <img id="gallery-image" src="{image_path}" alt="{esc(c['screens'][0]['alt'])}" width="1600" height="1000" loading="lazy" decoding="async">
            </a>
          </div>
          <div class="gallery-caption">
            <p id="gallery-caption" aria-live="polite">{esc(c['screens'][0]['caption'])}</p>
            <button type="button" class="text-button" data-gallery-zoom>{esc(c['zoom'])}</button>
          </div>
        </div>
      </div>
    </div>
  </section>

  <section class="section container split workflow-section" id="workflow" aria-labelledby="workflow-title">
    <div>
      <h2 id="workflow-title">{c['productTitle']}</h2>
      <p>{esc(c['productBody'])}</p>
    </div>
    <div class="workflow-list">{workflow}</div>
  </section>

  <section class="section panel-band">
    <div class="container split terminal-feature">
      <div>
        <h2>{c['terminalTitle']}</h2>
        <p>{esc(c['terminalBody'])}</p>
        <ul class="check-list">{terminal_items}</ul>
      </div>
      <figure>
        <a class="screenshot-button shot" href="{terminal_path}" data-zoom aria-label="{esc(c['zoom'])}">
          <img src="{terminal_path}" alt="{esc(terminal_screen['alt'])}" width="1600" height="1000" loading="lazy" decoding="async">
        </a>
      </figure>
    </div>
  </section>

  <section class="section container split">
    <div>
      <h2>{c['environmentTitle']}</h2>
      <p>{esc(c['environmentBody'])}</p>
      <div class="tool-strip" aria-label="{esc(c['stackLabel'])}">{stack}</div>
    </div>
    <ul class="check-list environment-list">{env_items}</ul>
  </section>

  <section class="section panel-band">
    <div class="container">
      <div class="section-heading">
        <h2>{c['localTitle']}</h2>
        <p>{esc(c['localBody'])}</p>
      </div>
      <div class="privacy-grid">{privacy}</div>
    </div>
  </section>

  <section class="section container split">
    <div>
      <h2>{c['languagesTitle']}</h2>
      <p>{esc(c['languagesBody'])}</p>
    </div>
    <nav class="language-cards" aria-label="{esc(c['languageLabel'])}">{language_items}</nav>
  </section>

  <section class="section container split faq-section" id="faq">
    <h2>{esc(c['faqTitle'])}</h2>
    <div class="faq-list">{faq}</div>
  </section>

  <section class="section download-section" id="download">
    <div class="container split">
      <div>
        <img class="app-icon" src="/assets/brand/app-icon.png" alt="" width="96" height="96" loading="lazy">
        <h2>{c['installTitle']}</h2>
        <p>{esc(c['installBody'])}</p>
        <div class="download-actions">
          {button(c['download'], downloads)}
          <a class="download-guide" href="{docs}/installation.md" target="_blank" rel="noopener noreferrer">{esc(c['guide'])}</a>
        </div>
        <p class="requirements">{esc(c['requirements'])}</p>
        <p class="download-note">{esc(download_note)}</p>
      </div>
      <ol class="install-steps">{install}</ol>
    </div>
  </section>
</main>

<footer class="site-footer">
  <div class="container">
    <div class="footer-top">
      <div>
        <a class="footer-brand" href="{path}"><picture>
          <source media="(prefers-color-scheme: dark)" srcset="/assets/brand/logo-reverse.svg">
          <img src="/assets/brand/logo-primary.svg" alt="Vulcan Celox" width="280" height="64">
        </picture></a>
        <p>{esc(c['footerLine'])}</p>
      </div>
      <nav class="footer-nav" aria-label="{esc(c['footerProduct'])}"><b>{esc(c['footerProduct'])}</b>{nav}</nav>
      <nav class="footer-nav" aria-label="{esc(c['footerResources'])}"><b>{esc(c['footerResources'])}</b>{footer_links}</nav>
    </div>
    <div class="footer-bottom"><p>{esc(c['footerLegal'])}</p></div>
  </div>
</footer>
<dialog id="screenshot-dialog" aria-label="{esc(c['zoom'])}">
  <div class="dialog-bar"><span>Vulcan Celox</span><button type="button" data-close-dialog aria-label="{esc(c['closeZoom'])}">{icon('x')}</button></div>
  <img id="dialog-image" src="{image_path}" alt="{esc(c['screens'][0]['alt'])}" width="1600" height="1000" loading="lazy">
  <p id="dialog-caption">{esc(c['imageNote'])}</p>
</dialog>
</body></html>'''


if __name__ == "__main__":
    for slug, _, _, path in LANGUAGES:
        content = json.loads((ROOT / "content" / (slug + ".json")).read_text())
        destination = OUT / slug
        destination.mkdir(parents=True, exist_ok=True)
        rendered = page(slug, content)
        (destination / "index.html").write_text(rendered)
        if path == "/":
            (OUT / "index.html").write_text(rendered)
    (OUT / "robots.txt").write_text("User-agent: *\nAllow: /\nSitemap: " + ORIGIN + "/sitemap.xml\n")
    alternates = '\n'.join(f'    <xhtml:link rel="alternate" hreflang="{lang}" href="{url}" />' for lang, url in ALTERNATES.items())
    entries = '\n'.join(f'  <url>\n    <loc>{ORIGIN + path}</loc>\n{alternates}\n  </url>' for _, _, _, path in LANGUAGES)
    sitemap = f'''<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:xhtml="http://www.w3.org/1999/xhtml">
{entries}
</urlset>
'''
    (OUT / "sitemap.xml").write_text(sitemap)
    print("Built /, /pt-br/, /en-us/, /es-es/")
