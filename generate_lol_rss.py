import json
import os
import re
import requests

from bs4 import BeautifulSoup
from datetime import datetime, timezone
from email.utils import formatdate
from urllib.parse import urljoin
from xml.etree.ElementTree import Element, SubElement, ElementTree, indent

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError


# ============================================================
# CONFIGURATION
# ============================================================

BASE_URL = "https://www.leagueoflegends.com"

SOURCE_URLS = [
    "https://www.leagueoflegends.com/fr-fr/news/",
    "https://www.leagueoflegends.com/fr-fr/news/dev/",
]

OUTPUT = "lol-news.xml"
DISCORD_OUTPUT = "lol-news-discord.xml"
CACHE_FILE = "lol_cache.json"

MAX_ARTICLES = 20

# Nombre maximum de clics sur "VOIR PLUS"
MAX_LOAD_MORE_CLICKS = 8

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/149.0 Safari/537.36"
    ),
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
}


# ============================================================
# AFFICHAGE
# ============================================================

print("")
print("########################################")
print("# Tensho League of Legends RSS")
print("# Actualités françaises")
print("########################################")
print("")


# ============================================================
# CACHE
# ============================================================

def load_cache():

    if not os.path.exists(CACHE_FILE):
        print("Aucun cache LoL trouvé.")
        return {}

    try:

        with open(
            CACHE_FILE,
            "r",
            encoding="utf-8"
        ) as f:

            data = json.load(f)

        if not isinstance(data, dict):
            return {}

        print(
            f"Cache LoL chargé : {len(data)} articles."
        )

        return data

    except Exception as e:

        print(
            f"⚠️ Erreur lecture cache : {e}"
        )

        return {}


def save_cache(cache):

    with open(
        CACHE_FILE,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            cache,
            f,
            ensure_ascii=False,
            indent=2
        )


cache = load_cache()


# ============================================================
# OUTILS
# ============================================================

def clean_text(value):

    if not value:
        return ""

    return re.sub(
        r"\s+",
        " ",
        str(value)
    ).strip()


def parse_date(value):

    if not value:
        return None

    value = clean_text(value)

    try:

        dt = datetime.fromisoformat(
            value.replace(
                "Z",
                "+00:00"
            )
        )

        if dt.tzinfo is None:

            dt = dt.replace(
                tzinfo=timezone.utc
            )

        return dt

    except Exception:
        return None


def format_pubdate(dt):

    return formatdate(
        dt.timestamp(),
        usegmt=True
    )


# ============================================================
# PLAYWRIGHT : RECUPERATION DE TOUS LES ARTICLES
# ============================================================

def collect_article_urls(page_url):

    print("")
    print("========================================")
    print(f"Ouverture avec Playwright :")
    print(page_url)
    print("========================================")

    urls = set()

    with sync_playwright() as p:

        browser = p.chromium.launch(
            headless=True
        )

        page = browser.new_page(
            locale="fr-FR",
            user_agent=HEADERS["User-Agent"]
        )

        try:

            page.goto(
                page_url,
                wait_until="domcontentloaded",
                timeout=60000
            )

            page.wait_for_timeout(
                3000
            )

        except Exception as e:

            print(
                f"⚠️ Erreur ouverture page : {e}"
            )

            browser.close()
            return []

        # ----------------------------------------------------
        # FONCTION DE RECUPERATION DES URL
        # ----------------------------------------------------

        def collect_urls():

            links = page.locator(
                'a[href*="/fr-fr/news/"]'
            )

            count = links.count()

            before = len(urls)

            for i in range(count):

                try:

                    href = links.nth(i).get_attribute(
                        "href"
                    )

                    if not href:
                        continue

                    full_url = urljoin(
                        BASE_URL,
                        href
                    )

                    # On ne veut pas les pages catégories
                    if full_url.rstrip("/") in [
                        SOURCE_URLS[0].rstrip("/"),
                        SOURCE_URLS[1].rstrip("/"),
                    ]:
                        continue

                    if "/fr-fr/news/" not in full_url:
                        continue

                    urls.add(
                        full_url
                    )

                except Exception:
                    continue

            added = len(urls) - before

            return added

        # Premier lot
        added = collect_urls()

        print(
            f"Premier lot : {len(urls)} articles."
        )

        # ----------------------------------------------------
        # CLICS "VOIR PLUS"
        # ----------------------------------------------------

        for click_number in range(
            1,
            MAX_LOAD_MORE_CLICKS + 1
        ):

            print(
                f"🔄 Recherche du bouton "
                f"VOIR PLUS ({click_number}/"
                f"{MAX_LOAD_MORE_CLICKS})..."
            )

            # Plusieurs variantes pour être robuste
            buttons = page.get_by_text(
                "VOIR PLUS",
                exact=True
            )

            count = buttons.count()

            if count == 0:

                print(
                    "ℹ️ Plus de bouton VOIR PLUS."
                )

                break

            clicked = False

            for i in range(count):

                try:

                    button = buttons.nth(i)

                    if not button.is_visible():
                        continue

                    button.scroll_into_view_if_needed()

                    page.wait_for_timeout(
                        500
                    )

                    button.click(
                        timeout=10000
                    )

                    clicked = True

                    print(
                        "🟢 VOIR PLUS cliqué."
                    )

                    break

                except Exception:
                    continue

            if not clicked:

                print(
                    "ℹ️ Impossible de cliquer "
                    "sur VOIR PLUS."
                )

                break

            # Laisse Riot charger les nouvelles cartes
            page.wait_for_timeout(
                2500
            )

            try:

                page.wait_for_load_state(
                    "networkidle",
                    timeout=10000
                )

            except PlaywrightTimeoutError:
                pass

            added = collect_urls()

            print(
                f"Articles actuellement trouvés : "
                f"{len(urls)} "
                f"(+{added})"
            )

            # Si aucun nouvel article n'arrive,
            # on arrête pour éviter une boucle.
            if added == 0:

                print(
                    "ℹ️ Aucun nouvel article chargé."
                )

                break

        browser.close()

    print("")
    print(
        f"🟢 Total récupéré depuis cette page : "
        f"{len(urls)} URLs"
    )

    return list(urls)


# ============================================================
# COLLECTE DES URL
# ============================================================

all_urls = set()

for source_url in SOURCE_URLS:

    try:

        urls = collect_article_urls(
            source_url
        )

        all_urls.update(
            urls
        )

    except Exception as e:

        print(
            f"⚠️ Erreur collecte : {e}"
        )


print("")
print("########################################")
print(
    f"# URLs uniques trouvées : "
    f"{len(all_urls)}"
)
print("########################################")


# ============================================================
# FILTRAGE URL
# ============================================================

def is_excluded_url(url):

    value = url.lower()

    # ========================================================
    # PAGES CATEGORIES / NAVIGATION
    # ========================================================

    excluded_paths = [
        "/news/game-updates/",
        "/news/media/",
        "/news/community/",
        "/news/esports/",
        "/news/products/",
        "/news/tags/",
    ]

    for path in excluded_paths:

        if path in value:
            return True

    # ========================================================
    # TFT
    # ========================================================

    # Les articles TFT peuvent apparaître dans les pages
    # communes de League of Legends.
    #
    # Ils seront traités par generate_tft_rss.py.
    #

    tft_patterns = [
        "teamfight-tactics",
        "team-fight-tactics",
        "/tft/",
        "tft-",
        "-tft-",
    ]

    for pattern in tft_patterns:

        if pattern in value:
            return True

    # ========================================================
    # WILD RIFT
    # ========================================================

    if "wild-rift" in value:
        return True

    # ========================================================
    # PATCH NOTES
    # ========================================================

    patch_patterns = [
        "patch-notes",
        "patchnote",
        "patch-notes-",
    ]

    for pattern in patch_patterns:

        if pattern in value:
            return True

    return False


# ============================================================
# RECUPERATION DES PAGES ARTICLES
# ============================================================

session = requests.Session()

session.headers.update(
    HEADERS
)

articles = []

for index, url in enumerate(
    candidate_urls,
    start=1
):

    print("")
    print(
        f"[{index}/{len(candidate_urls)}] "
        f"{url}"
    )

    # --------------------------------------------------------
    # CACHE
    # --------------------------------------------------------

    cached = cache.get(
        url
    )

    cached_date = None

    if cached:

        cached_date = parse_date(
            cached.get(
                "pubDate"
            )
        )

    # --------------------------------------------------------
    # PAGE ARTICLE
    # --------------------------------------------------------

    try:

        response = session.get(
            url,
            timeout=30
        )

        response.raise_for_status()

        soup = BeautifulSoup(
            response.text,
            "html.parser"
        )

    except Exception as e:

        print(
            f"⚠️ Impossible de charger : {e}"
        )

        continue

    # --------------------------------------------------------
    # TITRE
    # --------------------------------------------------------

    title = ""

    h1 = soup.find(
        "h1"
    )

    if h1:

        title = clean_text(
            h1.get_text(
                " ",
                strip=True
            )
        )

    if not title:

        og_title = soup.find(
            "meta",
            attrs={
                "property":
                "og:title"
            }
        )

        if og_title:

            title = clean_text(
                og_title.get(
                    "content"
                )
            )

    if not title:

        title = (
            url.rstrip("/")
            .split("/")
            [-1]
            .replace(
                "-",
                " "
            )
            .strip()
            .title()
        )

    # --------------------------------------------------------
    # DATE
    # --------------------------------------------------------

    dt = None

    # JSON-LD
    for script in soup.find_all(
        "script",
        type="application/ld+json"
    ):

        raw = (
            script.string
            or
            script.get_text()
        )

        if not raw:
            continue

        matches = re.findall(
            r'"datePublished"\s*:\s*"([^"]+)"',
            raw
        )

        for value in matches:

            dt = parse_date(
                value
            )

            if dt:
                break

        if dt:
            break

    # Meta
    if not dt:

        for attrs in [
            {
                "property":
                "article:published_time"
            },
            {
                "property":
                "og:published_time"
            },
        ]:

            meta = soup.find(
                "meta",
                attrs=attrs
            )

            if meta:

                dt = parse_date(
                    meta.get(
                        "content"
                    )
                )

                if dt:
                    break

    # time
    if not dt:

        for node in soup.find_all(
            "time"
        ):

            dt = parse_date(
                node.get(
                    "datetime"
                )
            )

            if dt:
                break

    # Cache en dernier recours
    if not dt:

        dt = cached_date

    if not dt:

        print(
            "⚠️ Date introuvable."
        )

        continue

    # --------------------------------------------------------
    # DESCRIPTION
    # --------------------------------------------------------

    description = ""

    meta = soup.find(
        "meta",
        attrs={
            "name":
            "description"
        }
    )

    if meta:

        description = clean_text(
            meta.get(
                "content"
            )
        )

    if not description:

        meta = soup.find(
            "meta",
            attrs={
                "property":
                "og:description"
            }
        )

        if meta:

            description = clean_text(
                meta.get(
                    "content"
                )
            )

    if not description:

        description = title

    # --------------------------------------------------------
    # CATEGORIES / FILTRES
    # --------------------------------------------------------

    combined = (
        title
        + " "
        + url
        + " "
        + description
    ).lower()

    excluded = False

    # ========================================================
    # TFT
    # ========================================================

    # Les actualités TFT doivent être traitées
    # uniquement par le futur flux TFT.
    tft_patterns = [
        r"\btft\b",
        r"teamfight tactics",
        r"team-fight tactics",
        r"teamfight-tactics",
        r"/tft/",
        r"tft-",
        r"-tft\b",
    ]

    # ========================================================
    # PATCH NOTES
    # ========================================================

    patch_patterns = [
        r"notes?\s+de\s+patch",
        r"patch\s+\d+\.\d+",
        r"patch[-_]\d+[-_]\d+",
        r"patch-notes",
        r"patchnote",
        r"notes?\s+du\s+patch",
    ]

    # ========================================================
    # ESPORT
    # ========================================================

    esport_patterns = [
        r"\blec\b",
        r"\bmsi\b",
        r"\bworlds\b",
        r"\besport\b",
        r"\be-sport\b",
        r"hall of legends",
        r"watch party",
        r"compétition",
        r"compétitions",
        r"joueur professionnel",
        r"équipe professionnelle",
    ]

    # ========================================================
    # GUIDES
    # ========================================================

    guide_patterns = [
        r"\bguide\b",
        r"\bbuild\b",
        r"\bastuces?\b",
        r"comment avoir",
        r"comment bien",
        r"survivre dans",
        r"phase de laning",
        r"guide des",
        r"guide pour",
    ]

    # ========================================================
    # CONTENU HORS ACTUALITES
    # ========================================================

    excluded_content_patterns = [
        r"produits dérivés",
        r"merchandising",
        r"merchandise",
        r"goodies",
        r"fond d'écran",
        r"wallpaper",
    ]

    # ========================================================
    # APPLICATION DES FILTRES
    # ========================================================

    all_filters = (
        tft_patterns
        +
        patch_patterns
        +
        esport_patterns
        +
        guide_patterns
        +
        excluded_content_patterns
    )

    for pattern in all_filters:

        if re.search(
            pattern,
            combined,
            re.IGNORECASE
        ):

            excluded = True

            print(
                f"❌ Exclu : {title}"
            )

            break

    if excluded:

        continue

    # --------------------------------------------------------
    # AJOUT
    # --------------------------------------------------------

    articles.append(
        {
            "title": title,
            "url": url,
            "description": description,
            "date": dt
        }
    )

    print(
        f"🟢 {format_pubdate(dt)} "
        f"- {title}"
    )


# ============================================================
# DEDOUBLONNAGE
# ============================================================

unique_articles = {}

for article in articles:

    url = article["url"]

    if url not in unique_articles:

        unique_articles[url] = article

    else:

        existing = unique_articles[url]

        if article["date"] > existing["date"]:

            unique_articles[url] = article


articles = list(
    unique_articles.values()
)


# ============================================================
# TRI
# ============================================================

articles.sort(
    key=lambda article:
    article["date"],
    reverse=True
)


# ============================================================
# 20 PLUS RECENTS
# ============================================================

articles = articles[
    :MAX_ARTICLES
]


print("")
print("########################################")
print(
    f"# {len(articles)} actualités retenues"
)
print("########################################")
print("")


for index, article in enumerate(
    articles,
    start=1
):

    print(
        f"{index:02d}. "
        f"{format_pubdate(article['date'])} "
        f"- {article['title']}"
    )


# ============================================================
# CACHE
# ============================================================

for article in articles:

    cache[
        article["url"]
    ] = {
        "title":
        article["title"],

        "description":
        article["description"],

        "pubDate":
        format_pubdate(
            article["date"]
        )
    }


save_cache(
    cache
)


# ============================================================
# RSS
# ============================================================

now = formatdate(
    datetime.now(
        timezone.utc
    ).timestamp(),
    usegmt=True
)


def create_rss(
    filename,
    title,
    description,
    articles_to_use
):

    rss = Element(
        "rss",
        {
            "version": "2.0",
            "xmlns:atom":
            "http://www.w3.org/2005/Atom"
        }
    )

    channel = SubElement(
        rss,
        "channel"
    )

    SubElement(
        channel,
        "title"
    ).text = title

    SubElement(
        channel,
        "link"
    ).text = (
        "https://www.leagueoflegends.com/"
        "fr-fr/news/"
    )

    SubElement(
        channel,
        "description"
    ).text = description

    self_url = (
        "https://shynen.github.io/"
        "tensho-cod-rss/"
        + filename
    )

    SubElement(
        channel,
        "atom:link",
        {
            "href":
            self_url,

            "rel":
            "self",

            "type":
            "application/rss+xml"
        }
    )

    SubElement(
        channel,
        "lastBuildDate"
    ).text = now

    for article in articles_to_use:

        item = SubElement(
            channel,
            "item"
        )

        SubElement(
            item,
            "title"
        ).text = article["title"]

        SubElement(
            item,
            "link"
        ).text = article["url"]

        SubElement(
            item,
            "guid",
            {
                "isPermaLink":
                "true"
            }
        ).text = article["url"]

        SubElement(
            item,
            "pubDate"
        ).text = format_pubdate(
            article["date"]
        )

        SubElement(
            item,
            "description"
        ).text = article["description"]

    tree = ElementTree(
        rss
    )

    indent(
        tree,
        space="  "
    )

    tree.write(
        filename,
        encoding="utf-8",
        xml_declaration=True
    )


# ============================================================
# FLUX PRINCIPAL
# ============================================================

print("")
print(
    "Génération de lol-news.xml..."
)

create_rss(
    OUTPUT,
    "League of Legends — Actualités",
    "Actualités officielles françaises de League of Legends.",
    articles
)

print(
    "🟢 lol-news.xml généré."
)


# ============================================================
# FLUX DISCORD
# ============================================================

print("")
print(
    "Génération de lol-news-discord.xml..."
)

create_rss(
    DISCORD_OUTPUT,
    "League of Legends Actualités",
    "Dernière actualité officielle de League of Legends.",
    articles[:1]
)

print(
    "🟢 lol-news-discord.xml généré."
)


# ============================================================
# FIN
# ============================================================

print("")
print("########################################")
print("# LOL RSS TERMINÉ")
print("########################################")
print("")
