# Vulcan Celox landing page

Static site with complete PT-BR, EN-US and ES-ES pages. No framework, external font or runtime CDN.

## Build and check

```bash
python3 build.py
python3 check.py
node --check dist/assets/site.js
node --check dist/assets/editorial.js
```

`content/` owns the three versions of the copy. `build.py` renders real HTML with locale-specific title, description, Open Graph, hreflang and structured data. The Vercel project uses `site/` as its root and serves the checked-in `dist/`.

## Indexing

The origin in `settings.json` is `https://celox.byvulcan.com`. Brazilian Portuguese uses `/` and is the default language. American English and Spanish use `/en-us/` and `/es-es/`. The former `/pt-br/` route and the `vulcan-celox.vercel.app` hostname redirect permanently. The sitemap lists the three canonical landing URLs with matching language alternates and the eight Portuguese library URLs. The robots file points to `https://celox.byvulcan.com/sitemap.xml`.

## Content library

The landing pages link to `/recursos/`. The guides, articles, prompts, GitHub directory and Harpya radar are maintained in `biblioteca/`. All pages are built as static HTML. Prompt downloads are served as Markdown under `/prompts/arquivos/`; the sitemap lists the library pages.

The documented Harpya references come from a checked-in copy of its public RSS. The normal build works offline. To refresh the selected references, run `python3 build.py --atualizar-harpya`, review changes to `biblioteca/harpya-rss.json` and the generated pages, then commit both. Adding a new reference requires reviewing the original and adding its URL and practical context to `FEED_TOPICS`.

## Assets and screenshots

The brand assets and locally served Inter font come from the product. The layout follows the original Vercel landing, with a real screenshot in the hero, a navy session trail, and support for the system light and dark appearance. Inter's OFL and the Phosphor MIT notice ship with the assets.

The capture helper generates actual product screenshots with isolated demonstration data at:

```text
dist/assets/screens/{overview,code,agents,prompts,terminals,settings}-{pt,en,es}.png
```

Do not modify screenshots to invent capabilities. The Code screen is a read-only viewer. The page states this limitation explicitly. Do not place internal audit material, user data, tokens or the private application source in this folder.

## Download

The primary CTA links to the signed universal macOS ZIP attached to the matching public GitHub Release. Update `settings.json` and regenerate `dist/` when the app version changes.

The copy identifies macOS 13+, Python 3.9+, universal Apple Silicon/Intel support and the lack of Apple notarization. Backends and coding agents remain separate installations.

## Interactions

- Locale links preserve the current section hash.
- Screenshot tabs support mouse, directional keys, Home and End.
- Native dialog lightbox supports Escape, focus return and backdrop close.
- Mobile navigation exposes expanded state and Escape close.
- The hero, product gallery, and terminal capture can be opened in the lightbox. In-page scrolling respects reduced motion.

Run the checks above and commit the generated `dist/` with the source changes. The Vercel production project tracks the repository's `main` branch.
