"""Renderiza a Biblioteca Celox como HTML estático."""

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from hashlib import sha256
from html import escape
import json
from pathlib import Path
import re
from shutil import copyfile
from tempfile import NamedTemporaryFile
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

from .conteudo import (
    ARTICLES, CASCADE, CONTEXT, GLOSSARY, HARPY_LICENSE, HARPYA,
    HARPYA_TERMS, HUB, INSTALL, KV_CACHE, MANUAL, PAGES,
    PROMPT_LIBRARY, PROMPTS, RADAR, REPO, REPO_DIR, REPOSITORIES,
    RSS, TOKENS, TRACK, VERSION, WORKFLOW,
)

ROOT = Path(__file__).resolve().parent
SNAPSHOT = ROOT / "harpya-rss.json"
NAV = [(HUB, "Recursos"), (WORKFLOW, "Guias"), (CONTEXT, "Artigos"), (PROMPT_LIBRARY, "Prompts"), (REPO_DIR, "GitHub"), (RADAR, "Radar Harpya")]

FEED_TOPICS = {
    CASCADE: ("Agentes de código", "https://arxiv.org/abs/2611.24324",
              "Compare prazo, custo e critério de sucesso antes de mudar o agente de uma tarefa. O estudo simula uma cascata de outros modelos, com custo estimado em horas de GPU."),
    KV_CACHE: ("Contexto e inferência", "https://arxiv.org/abs/2611.24969",
               "Leia para entender o custo de preservar contexto durante a inferência. O cache do modelo fica em uma camada diferente da memória Markdown que o Celox guarda por sessão."),
}


def update_snapshot():
    request = Request(RSS, headers={"User-Agent": "Vulcan Celox Biblioteca/1.0"})
    with urlopen(request, timeout=15) as response:
        if response.geturl() != RSS:
            raise ValueError("O RSS mudou de endereço; confira a fonte.")
        payload = response.read(2_000_001)
    if len(payload) > 2_000_000:
        raise ValueError("O RSS ultrapassou o tamanho máximo da coleta.")
    feed = ET.fromstring(payload)
    selected = {}
    for item in feed.findall("channel/item"):
        url = item.findtext("link", "")
        if url not in FEED_TOPICS or url in selected:
            continue
        title = item.findtext("title", "").strip()
        publication = parsedate_to_datetime(item.findtext("pubDate", ""))
        if not title:
            raise ValueError(f"Título ausente no RSS: {url}")
        selected[url] = {
            "url": url, "title": title, "feedDate": publication.date().isoformat(),
            "categories": [node.text for node in item.findall("category")],
        }
    # O feed é uma janela móvel. A referência já coletada continua disponível
    # quando uma notícia sai da janela; sua data original é preservada.
    previous = json.loads(SNAPSHOT.read_text(encoding="utf-8")) if SNAPSHOT.exists() else {"items": []}
    items = {item["url"]: item for item in previous["items"] if item["url"] in FEED_TOPICS}
    items.update(selected)
    if items.keys() != FEED_TOPICS.keys():
        raise ValueError("A coleta deixou referências da curadoria sem registro.")
    snapshot = {
        "feed": RSS, "fetchedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "feedSha256": sha256(payload).hexdigest(), "matchedOnRefresh": list(selected),
        "items": [items[url] for url in FEED_TOPICS],
    }
    with NamedTemporaryFile(mode="w", encoding="utf-8", dir=ROOT, delete=False) as output:
        output.write(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n")
    Path(output.name).replace(SNAPSHOT)


def topic_cards(routes):
    return "".join(
        f'<article class="resource-card"><p class="kicker">{escape(PAGES[route][2])}</p>'
        f'<h3><a href="{route}">{escape(PAGES[route][0])}</a></h3>'
        f'<p>{escape(PAGES[route][1])}</p></article>'
        for route in routes
    )


def radar_cards(snapshot):
    cards = []
    for item in snapshot["items"]:
        url, title, date = item["url"], item["title"], item["feedDate"]
        topic, primary, application = FEED_TOPICS[url]
        cards.append(f"""<article class="radar-item">
<p class="kicker">{escape(topic)} <span>·</span> <time datetime="{date}">{date[8:]}/{date[5:7]}/{date[:4]}</time></p>
<h3><a href="{escape(url)}">{escape(title)}</a></h3>
<p>{escape(application)}</p>
<div class="links"><a href="{escape(primary)}">Estudo original no arXiv</a></div>
</article>""")
    return "".join(cards)


def hub(snapshot):
    return f"""
<section class="hero wrap">
  <div class="hero-copy">
    <h1>Guias e recursos para agentes de código</h1>
    <p>Organize sessões de Claude Code e Codex no Mac, acompanhe o trabalho no Git e retome cada projeto com o contexto certo.</p>
    <div class="actions"><a class="button" href="{WORKFLOW}">Começar pelo guia no Mac</a><a class="button outline" href="{PROMPT_LIBRARY}">Explorar prompts</a></div>
    <div class="hero-meta">macOS 13+ <span></span> Apple Silicon e Intel <span></span> Código aberto</div>
  </div>
  <figure class="hero-shot">
    <div class="shot-bar"><span class="shot-dots"><i></i><i></i><i></i></span><span>Vulcan Celox</span></div>
    <img src="/assets/screens/overview-pt.png" width="1800" height="1145" alt="Tela Visão geral do Vulcan Celox, com projetos, sessões recentes e tarefas" fetchpriority="high">
    <figcaption>Interface do Celox com dados de demonstração.</figcaption>
  </figure>
</section>
<section class="wrap collection" id="biblioteca">
<div class="section-head"><h2>Do primeiro terminal à revisão</h2><p>Use os guias em um projeto de teste e leve os exemplos para o seu fluxo.</p></div>
<div class="card-grid">{topic_cards([WORKFLOW, INSTALL, TRACK, CONTEXT, PROMPT_LIBRARY, REPO_DIR])}</div>
</section>
<section class="radar-band">
<div class="wrap">
  <div class="section-head"><h2>Radar Harpya</h2><p>Pesquisa sobre agentes e modelos de linguagem com aplicações para o trabalho no Celox.</p></div>
  <div class="radar-grid">{radar_cards(snapshot)}</div>
  <p class="radar-next"><a href="{RADAR}">Ver leituras e fontes do Radar</a></p>
</div>
</section>"""


def article(route):
    title, description, kind = PAGES[route]
    sections = re.findall(r'<h2 id="([a-z-]+)">(.*?)</h2>', ARTICLES[route])
    toc = "".join(f'<li><a href="#{anchor}">{label}</a></li>' for anchor, label in sections)
    related = {
        WORKFLOW: [PROMPT_LIBRARY, TRACK],
        INSTALL: [WORKFLOW, REPO_DIR],
        CONTEXT: [PROMPT_LIBRARY, RADAR],
        TRACK: [WORKFLOW, PROMPT_LIBRARY],
    }
    return f"""
<div class="wrap read-layout">
<article class="article">
  <header class="page-heading"><p class="kicker">{kind}</p><h1>{escape(title)}</h1><p class="lead">{escape(description)}</p><p class="meta">Vulcan Celox {VERSION} · Exemplos de demonstração</p></header>
  {ARTICLES[route].strip()}
</article>
<aside class="reading-nav"><nav aria-label="Nesta página"><h2>Nesta página</h2><ol>{toc}</ol></nav></aside>
</div>
<section class="wrap related"><h2>Continue no Celox</h2><div class="card-grid compact">{topic_cards(related[route])}</div></section>"""


def resource_heading(route):
    title, description, kind = PAGES[route]
    return f'<header class="wrap page-heading"><p class="kicker">{kind}</p><h1>{escape(title)}</h1><p class="lead">{escape(description)}</p></header>'


def prompt_page(downloads):
    cards = []
    for slug, title, description, category, related, body in PROMPTS:
        download = downloads / f"{slug}.md"
        frontmatter = f"---\nid: {slug}\ntitle: {title}\ncategory: {category}\ndescricao: {description}\n---\n"
        download.write_text(frontmatter + body + "\n", encoding="utf-8")
        cards.append(f"""<article class="prompt-card" id="{slug}">
<p class="kicker">{escape(category)}</p><h2>{escape(title)}</h2><p>{escape(description)}</p>
<pre><code id="prompt-{slug}">{escape(body)}</code></pre>
<div class="links"><button type="button" class="button small copy" data-copy="prompt-{slug}">Copiar prompt</button>
<a href="{PROMPT_LIBRARY}arquivos/{slug}.md" download>Baixar Markdown</a><a href="{related}">Ver exemplo relacionado</a><span class="copy-status" role="status"></span></div>
</article>""")
    return resource_heading(PROMPT_LIBRARY) + f"""
<div class="wrap">
<p class="intro-strip">No Celox, salve o Markdown em <code>.vulcan/prompts/</code> no projeto. Ao escolher uma sessão, preencha ou confira as variáveis. O compositor cola o texto no terminal pareado e você decide quando enviar. Fora do Celox, substitua os campos entre chaves antes de usar.</p>
<nav class="jump-links" aria-label="Modelos de prompt">{"".join(f'<a href="#{slug}">{escape(title)}</a>' for slug, title, *_ in PROMPTS)}</nav>
<div class="prompt-grid">{"".join(cards)}</div>
<p class="standalone-link"><a href="{MANUAL}#prompts">Ler a documentação de prompts do Celox</a></p>
</div>"""


def repo_page():
    cards = []
    for repo, kind, summary, use, related in REPOSITORIES:
        cards.append(f"""<article class="repo-card">
<p class="kicker">{escape(kind)}</p><h2><a href="https://github.com/{repo}">{escape(repo)}</a></h2>
<p>{escape(summary)}</p><p>{escape(use)}</p>
<div class="links"><a href="https://github.com/{repo}">Abrir no GitHub</a><a href="{related}">{escape(PAGES[related][0])}</a></div>
</article>""")
    return resource_heading(REPO_DIR) + '<div class="wrap repo-grid">' + "".join(cards) + "</div>"


def radar_page(snapshot):
    collected = datetime.fromisoformat(snapshot["fetchedAt"]).astimezone(ZoneInfo("America/Fortaleza")).date().isoformat()
    return resource_heading(RADAR) + f"""
<section class="wrap collection">
  <div class="section-head"><h2>Da pesquisa à prática</h2><p>Coleta do RSS em <time datetime="{collected}">{collected[8:]}/{collected[5:7]}/{collected[:4]}</time>. Os títulos vêm do feed. A Biblioteca Celox explica como cada leitura se relaciona com o trabalho no terminal.</p></div>
  <div class="radar-grid radar-light">{radar_cards(snapshot)}</div>
  <p class="source-note">Títulos da Harpya · Mindscope Labs, reproduzidos do RSS. Consulte a autoria e as fontes em cada matéria. <a href="{HARPYA_TERMS}">Termos da Harpya</a> · <a href="{HARPY_LICENSE}">CC BY 4.0</a> · <a href="{RSS}">Assinar RSS da Harpya</a>.</p>
</section>
<section class="wrap collection">
  <div class="section-head"><h2>Leituras de base</h2></div>
  <div class="card-grid compact">
    <article class="resource-card"><h3><a href="{TOKENS}">Tokens e janela de contexto</a></h3><p>Carlos Frederico Domínguez explica como modelos dividem texto em tokens. Use essa leitura para preparar resumos curtos de retomada.</p></article>
    <article class="resource-card"><h3><a href="{GLOSSARY}">Glossário de IA da Harpya</a></h3><p>Consulte definições de embeddings, latência, quantização e tokens ao ler um estudo.</p></article>
  </div>
  <p class="standalone-link"><a href="{CONTEXT}">Ler o artigo do Celox sobre contexto e memória</a></p>
</section>"""


def metadata(route, origin):
    title, description, _ = PAGES[route]
    canonical = origin + route
    image = origin + "/assets/screens/" + {
        WORKFLOW: "terminals-pt.png",
        TRACK: "agents-pt.png",
    }.get(route, "overview-pt.png")
    image_alt = {
        WORKFLOW: "Abas de terminais no Vulcan Celox",
        TRACK: "Sessões de agentes e estado do trabalho no Vulcan Celox",
    }.get(route, "Projetos e sessões no Vulcan Celox")
    page_title = f"{title} | Vulcan Celox"
    page_type = "article" if route in ARTICLES else "website"
    crumbs = [("Vulcan Celox", "/")]
    if route != HUB:
        crumbs.append(("Biblioteca", HUB))
    crumbs.append((title, route))
    graph = [{
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": position, "name": name, "item": origin + path}
            for position, (name, path) in enumerate(crumbs, start=1)
        ],
    }]
    if route in ARTICLES:
        graph.append({
            "@type": "Article", "headline": title, "description": description,
            "image": image, "inLanguage": "pt-BR", "mainEntityOfPage": canonical,
            "author": {"@type": "Organization", "name": "Vulcan Celox", "url": origin + "/"},
        })
    schema = json.dumps({"@context": "https://schema.org", "@graph": graph}, ensure_ascii=False).replace("<", "\\u003c")
    return f"""<title>{escape(page_title)}</title>
<meta name="description" content="{escape(description)}">
<meta name="robots" content="index, follow, max-image-preview:large">
<link rel="canonical" href="{canonical}">
<meta property="og:type" content="{page_type}">
<meta property="og:site_name" content="Vulcan Celox">
<meta property="og:locale" content="pt_BR">
<meta property="og:title" content="{escape(page_title)}">
<meta property="og:description" content="{escape(description)}">
<meta property="og:url" content="{canonical}">
<meta property="og:image" content="{image}">
<meta property="og:image:width" content="1800">
<meta property="og:image:height" content="1145">
<meta property="og:image:alt" content="{image_alt}">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{escape(page_title)}">
<meta name="twitter:description" content="{escape(description)}">
<meta name="twitter:image" content="{image}">
<meta name="twitter:image:alt" content="{image_alt}">
<script type="application/ld+json">{schema}</script>"""


def website_page(route, content, origin):
    active = {INSTALL: WORKFLOW, TRACK: CONTEXT}.get(route, route)
    current = "page" if active == route else "location"
    menu = "".join(f'<a href="{url}"{" aria-current=" + current if active == url else ""}>{label}</a>' for url, label in NAV)
    breadcrumb = "" if route == HUB else f'<nav class="wrap breadcrumb" aria-label="Navegação estrutural"><a href="{HUB}">Biblioteca</a><span aria-hidden="true">/</span><span>{PAGES[route][2]}</span></nav>'
    copy_script = '<script src="/assets/editorial.js" defer></script>' if route == PROMPT_LIBRARY else ""
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
{metadata(route, origin)}
<link rel="icon" type="image/png" href="/assets/brand/favicon.png">
<link rel="stylesheet" href="/assets/editorial.css">
{copy_script}
</head>
<body>
<a class="skip" href="#conteudo">Pular para o conteúdo</a>
<header class="top">
  <div class="top-inner wrap">
    <a class="brand" href="/"><img src="/assets/brand/logo-primary.svg" width="175" height="40" alt="Vulcan Celox"></a>
    <nav class="nav" aria-label="Navegação principal">{menu}</nav>
    <a class="button small header-download" href="{INSTALL}">Baixar para Mac</a>
  </div>
</header>
{breadcrumb}
<main id="conteudo">{content}</main>
<footer class="foot">
  <div class="wrap foot-inner">
    <a href="{HUB}">Biblioteca Celox</a><a href="/">Site oficial</a><a href="{REPO}">Código e manual</a><a href="{HARPYA}/">Harpya</a>
  </div>
</footer>
</body>
</html>"""


def build(dist, origin):
    snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    if snapshot["feed"] != RSS or [item["url"] for item in snapshot["items"]] != list(FEED_TOPICS):
        raise ValueError("Confira a origem e a ordem das referências Harpya.")
    downloads = dist / PROMPT_LIBRARY.strip("/") / "arquivos"
    downloads.mkdir(parents=True, exist_ok=True)
    for name in ("editorial.css", "editorial.js"):
        copyfile(ROOT / name, dist / "assets" / name)
    bodies = {route: article(route) for route in ARTICLES}
    bodies.update({
        HUB: hub(snapshot), PROMPT_LIBRARY: prompt_page(downloads),
        REPO_DIR: repo_page(), RADAR: radar_page(snapshot),
    })
    for route in PAGES:
        target = dist / route.strip("/") / "index.html"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(website_page(route, bodies[route], origin), encoding="utf-8")
