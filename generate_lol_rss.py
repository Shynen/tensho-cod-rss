import json
import os
import re
import requests

from bs4 import BeautifulSoup
from datetime import datetime, timezone
from email.utils import formatdate
from urllib.parse import urljoin
from xml.etree.ElementTree import Element, SubElement, ElementTree, indent


# ============================================================
# CONFIGURATION
# ============================================================

BASE_URL = "https://www.leagueoflegends.com"

TAG_URLS = [
    "https://www.leagueoflegends.com/fr-fr/news/tags/dev/",
    "https://www.leagueoflegends.com/fr-fr/news/game-updates/",
]

OUTPUT = "lol-news.xml"
DISCORD_OUTPUT = "lol-news-discord.xml"
CACHE_FILE = "lol_cache.json"

MAX_ARTICLES = 20

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; TenshoLoLRSS/1.0)",
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
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, dict):
            return {}

        print(f"Cache LoL chargé : {len(data)} articles.")
        return data

    except Exception as e:

        print(f"⚠️ Erreur lecture cache : {e}")
        return {}


def save_cache(cache):

    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(
            cache,
            f,
            ensure_ascii=False,
            indent=2
        )


cache = load_cache()


# ============================================================
# HTTP
# ============================================================

def get_page(url):

    response = requests.get(
        url,
        headers=HEADERS,
        timeout=30
    )

    response.raise_for_status()

    return response.text


# ============================================================
# NETTOYAGE
# ============================================================

def clean_text(value):

    if not value:
        return ""

    value = re.sub(
        r"\s+",
        " ",
        str(value)
    )

    return value.strip()


# ============================================================
# DATE
# ============================================================

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
# EXTRACTION DES ARTICLES
# ============================================================

def extract_articles(page_url):

    print("")
    print(f"Lecture : {page_url}")

    source = get_page(page_url)

    soup = BeautifulSoup(
        source,
        "html.parser"
    )

    articles = []
    seen = set()

    # --------------------------------------------------------
    # RECHERCHE DES DATES ISO DANS LE HTML
    # --------------------------------------------------------

    html_source = str(soup)

    date_pattern = re.compile(
        r"\d{4}-\d{2}-\d{2}T"
        r"\d{2}:\d{2}:\d{2}"
        r"(?:\.\d+)?Z"
    )

    dates = date_pattern.findall(
        html_source
    )

    # --------------------------------------------------------
    # EXTRACTION DES BLOCS D'ARTICLES
    # --------------------------------------------------------

    for link in soup.find_all(
        "a",
        href=True
    ):

        href = link.get("href")

        if not href:
            continue

        if "/fr-fr/news/" not in href:
            continue

        url = urljoin(
            BASE_URL,
            href
        )

        if url in seen:
            continue

        title = clean_text(
            link.get_text(
                " ",
                strip=True
            )
        )

        if not title:
            continue

        if len(title) < 8:
            continue

        # ----------------------------------------------------
        # CHERCHE LA DATE DANS LE CONTENEUR DU LIEN
        # ----------------------------------------------------

        date_value = None

        parent = link

        for _ in range(5):

            if parent is None:
                break

            text = str(parent)

            match = date_pattern.search(
                text
            )

            if match:

                date_value = match.group(0)
                break

            parent = parent.parent

        dt = parse_date(
            date_value
        )

        # ----------------------------------------------------
        # FALLBACK : CACHE
        # ----------------------------------------------------

        if dt is None and url in cache:

            dt = parse_date(
                cache[url].get(
                    "pubDate"
                )
            )

        # ----------------------------------------------------
        # FALLBACK : PAGE ARTICLE
        # ----------------------------------------------------

        if dt is None:

            try:

                article_source = get_page(
                    url
                )

                article_soup = BeautifulSoup(
                    article_source,
                    "html.parser"
                )

                # JSON-LD
                for script in article_soup.find_all(
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

                    match = re.search(
                        r'"datePublished"\s*:\s*'
                        r'"([^"]+)"',
                        raw
                    )

                    if match:

                        dt = parse_date(
                            match.group(1)
                        )

                        if dt:
                            break

                # Meta
                if dt is None:

                    meta = article_soup.find(
                        "meta",
                        attrs={
                            "property":
                            "article:published_time"
                        }
                    )

                    if meta:

                        dt = parse_date(
                            meta.get(
                                "content"
                            )
                        )

            except Exception as e:

                print(
                    f"⚠️ Date impossible à récupérer : "
                    f"{title} ({e})"
                )

        if dt is None:

            print(
                f"⚠️ Date inconnue : {title}"
            )

            continue

        # ----------------------------------------------------
        # DESCRIPTION
        # ----------------------------------------------------

        description = ""

        if url in cache:

            description = clean_text(
                cache[url].get(
                    "description",
                    ""
                )
            )

        if not description:

            try:

                article_source = get_page(
                    url
                )

                article_soup = BeautifulSoup(
                    article_source,
                    "html.parser"
                )

                meta = article_soup.find(
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

                    meta = article_soup.find(
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

            except Exception:
                pass

        if not description:
            description = title

        # ----------------------------------------------------
        # AJOUT
        # ----------------------------------------------------

        articles.append(
            {
                "title": title,
                "url": url,
                "date": dt,
                "description": description
            }
        )

        seen.add(url)

    return articles


# ============================================================
# COLLECTE
# ============================================================

all_articles = []

for url in TAG_URLS:

    try:

        all_articles.extend(
            extract_articles(url)
        )

    except Exception as e:

        print(
            f"⚠️ Erreur page : {url}"
        )

        print(e)


print("")
print(
    f"Articles bruts trouvés : "
    f"{len(all_articles)}"
)


# ============================================================
# DEDOUBLONNAGE
# ============================================================

unique = {}

for article in all_articles:

    url = article["url"]

    if url not in unique:

        unique[url] = article

        continue

    # On garde celui avec la date la plus récente
    if article["date"] > unique[url]["date"]:

        unique[url] = article


all_articles = list(
    unique.values()
)


# ============================================================
# FILTRAGE
# ============================================================

def excluded(title, url):

    text = (
        title
        + " "
        + url
    ).lower()

    # PATCH NOTES
    patch_patterns = [
        r"notes?\s+de\s+patch",
        r"patch\s+\d+\.\d+",
        r"patch[-_]\d+[-_]\d+",
        r"/patch[-_]?notes",
    ]

    # ESPORT
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
    ]

    # GUIDES
    guide_patterns = [
        r"\bguide\b",
        r"\bbuild\b",
        r"\bastuces?\b",
        r"comment avoir",
        r"comment bien",
        r"survivre dans",
        r"phase de laning",
    ]

    for pattern in (
        patch_patterns
        +
        esport_patterns
        +
        guide_patterns
    ):

        if re.search(
            pattern,
            text,
            re.IGNORECASE
        ):

            return True

    # Wild Rift
    if "wild rift" in text:
        return True

    return False


filtered = []

for article in all_articles:

    if excluded(
        article["title"],
        article["url"]
    ):

        print(
            f"❌ Exclu : "
            f"{article['title']}"
        )

        continue

    filtered.append(
        article
    )


print("")
print(
    f"Articles après filtrage : "
    f"{len(filtered)}"
)


# ============================================================
# TRI
# ============================================================

filtered.sort(
    key=lambda x: x["date"],
    reverse=True
)


# ============================================================
# 20 PLUS RECENTS
# ============================================================

articles = filtered[
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
        f"{format_pubdate(article['date'])} - "
        f"{article['title']}"
    )


# ============================================================
# CACHE
# ============================================================

for article in articles:

    cache[
        article["url"]
    ] = {
        "title": article["title"],
        "description": article["description"],
        "pubDate": format_pubdate(
            article["date"]
        )
    }


save_cache(
    cache
)


# ============================================================
# GENERATION RSS
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
            "href": self_url,
            "rel": "self",
            "type": "application/rss+xml"
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
print("Génération de lol-news.xml...")

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
