import json
import os
import re
import requests

from bs4 import BeautifulSoup
from email.utils import formatdate
from datetime import datetime, timezone
from urllib.parse import urljoin

from xml.etree.ElementTree import (
    Element,
    SubElement,
    ElementTree,
    indent,
)


# ============================================================
# CONFIGURATION
# ============================================================

BASE_URL = "https://www.leagueoflegends.com"

NEWS_URL = "https://www.leagueoflegends.com/fr-fr/news/"
DEV_URL = "https://www.leagueoflegends.com/fr-fr/news/dev/"

OUTPUT = "lol-news.xml"
DISCORD_OUTPUT = "lol-news-discord.xml"
CACHE_FILE = "lol_cache.json"

MAX_ARTICLES = 20

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; TenshoLoLRSS/1.0)"
}


# ============================================================
# AFFICHAGE
# ============================================================

print("")
print("########################################")
print("# Tensho League of Legends RSS")
print("# Actualités FR")
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
            cache = json.load(f)

        if not isinstance(cache, dict):
            return {}

        print(
            f"Cache LoL chargé : {len(cache)} articles."
        )

        return cache

    except Exception as e:

        print(
            f"Erreur lecture cache LoL : {e}"
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
# DATE
# ============================================================

def parse_date(value):

    if not value:
        return None

    value = value.strip()

    # ISO 8601
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

        return formatdate(
            dt.timestamp(),
            usegmt=True
        )

    except Exception:
        pass

    # Format RSS classique
    try:

        dt = datetime.strptime(
            value,
            "%a, %d %b %Y %H:%M:%S GMT"
        ).replace(
            tzinfo=timezone.utc
        )

        return formatdate(
            dt.timestamp(),
            usegmt=True
        )

    except Exception:
        pass

    return None


# ============================================================
# EXTRACTION DATE DEPUIS UNE PAGE ARTICLE
# ============================================================

def extract_article_date(soup):

    # --------------------------------------------------------
    # 1. JSON-LD
    # --------------------------------------------------------

    for script in soup.find_all(
        "script",
        type="application/ld+json"
    ):

        try:

            data = json.loads(
                script.string or script.get_text()
            )

            data_list = (
                data
                if isinstance(data, list)
                else [data]
            )

            for obj in data_list:

                if not isinstance(obj, dict):
                    continue

                date_value = (
                    obj.get("datePublished")
                    or obj.get("dateCreated")
                )

                parsed = parse_date(
                    date_value
                )

                if parsed:
                    return parsed

        except Exception:
            continue

    # --------------------------------------------------------
    # 2. Meta article:published_time
    # --------------------------------------------------------

    meta_selectors = [

        {
            "property":
            "article:published_time"
        },

        {
            "name":
            "article:published_time"
        },

        {
            "property":
            "og:published_time"
        },

        {
            "name":
            "date"
        },

    ]

    for attrs in meta_selectors:

        node = soup.find(
            "meta",
            attrs=attrs
        )

        if node:

            parsed = parse_date(
                node.get("content")
            )

            if parsed:
                return parsed

    # --------------------------------------------------------
    # 3. Balises <time>
    # --------------------------------------------------------

    for time_node in soup.find_all(
        "time"
    ):

        value = (
            time_node.get("datetime")
            or
            time_node.get_text(
                " ",
                strip=True
            )
        )

        parsed = parse_date(
            value
        )

        if parsed:
            return parsed

    # --------------------------------------------------------
    # 4. Recherche ISO dans le HTML
    # --------------------------------------------------------

    html_text = str(soup)

    matches = re.findall(
        r"\d{4}-\d{2}-\d{2}T"
        r"\d{2}:\d{2}:\d{2}"
        r"(?:\.\d+)?"
        r"(?:Z|[+-]\d{2}:\d{2})",
        html_text
    )

    for value in matches:

        parsed = parse_date(
            value
        )

        if parsed:
            return parsed

    return None


# ============================================================
# EXTRACTION DES ARTICLES DEPUIS UNE LISTE
# ============================================================

def extract_listing_articles(page_url):

    print("")
    print(
        f"Téléchargement : {page_url}"
    )

    response = requests.get(
        page_url,
        headers=HEADERS,
        timeout=30
    )

    response.raise_for_status()

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    articles = []
    seen = set()

    for link in soup.find_all(
        "a",
        href=True
    ):

        href = link["href"]

        if not href.startswith(
            "/fr-fr/news/"
        ):
            continue

        url = urljoin(
            BASE_URL,
            href
        )

        # Pages de catégories
        if url.rstrip("/") in (
            NEWS_URL.rstrip("/"),
            DEV_URL.rstrip("/")
        ):
            continue

        if url in seen:
            continue

        title = link.get_text(
            " ",
            strip=True
        )

        if not title or len(title) < 8:
            continue

        # ----------------------------------------------------
        # FILTRAGE DES CONTENUS INUTILES
        # ----------------------------------------------------

        value = (
            title
            + " "
            + url
        ).lower()

        excluded = False

        excluded_patterns = [

            # Patch notes
            r"notes?\s+de\s+patch",
            r"patch\s+\d+\.\d+",
            r"patch-\d+-\d+",
            r"patch-notes",

            # Guides
            r"\bguide\b",
            r"\bbuild\b",
            r"\bastuces?\b",
            r"comment avoir",
            r"comment bien",
            r"survivre dans",
            r"phase de laning",

            # Esport
            r"\besport\b",
            r"\be-sport\b",
            r"\blec\b",
            r"\bmsi\b",
            r"\bworlds\b",
            r"hall of legends",
            r"watch party",
            r"compétition",
            r"compétitions",

            # Wild Rift
            r"wild rift",

        ]

        for pattern in excluded_patterns:

            if re.search(
                pattern,
                value,
                re.IGNORECASE
            ):

                excluded = True
                break

        if excluded:

            print(
                f"❌ Exclu : {title}"
            )

            continue

        seen.add(url)

        articles.append(
            {
                "url": url,
                "title": title
            }
        )

    return articles


# ============================================================
# RECUPERATION DES LISTES
# ============================================================

all_articles = []

all_articles.extend(
    extract_listing_articles(
        NEWS_URL
    )
)

all_articles.extend(
    extract_listing_articles(
        DEV_URL
    )
)


# ============================================================
# DEDOUBLONNAGE
# ============================================================

unique_articles = []
seen_urls = set()

for article in all_articles:

    if article["url"] in seen_urls:
        continue

    seen_urls.add(
        article["url"]
    )

    unique_articles.append(
        article
    )


print("")
print(
    f"{len(unique_articles)} articles candidats."
)


# ============================================================
# RECUPERATION DES VRAIES DATES
# ============================================================

dated_articles = []


for index, article in enumerate(
    unique_articles,
    start=1
):

    url = article["url"]

    print("")
    print(
        f"[{index}/{len(unique_articles)}] "
        f"{article['title']}"
    )

    # --------------------------------------------------------
    # CACHE
    # --------------------------------------------------------

    if url in cache:

        cached = cache[url]

        cached_date = cached.get(
            "pubDate"
        )

        # Si le cache possède déjà une vraie date,
        # on la réutilise.
        if cached_date:

            print(
                f"🟢 Cache utilisé : "
                f"{cached_date}"
            )

            dated_articles.append(
                {
                    "url": url,
                    "title": cached.get(
                        "title",
                        article["title"]
                    ),
                    "description": cached.get(
                        "description",
                        article["title"]
                    ),
                    "pubDate": cached_date
                }
            )

            continue

    # --------------------------------------------------------
    # TELECHARGEMENT ARTICLE
    # --------------------------------------------------------

    try:

        response = requests.get(
            url,
            headers=HEADERS,
            timeout=30
        )

        response.raise_for_status()

        soup = BeautifulSoup(
            response.text,
            "html.parser"
        )

        # ----------------------------------------------------
        # TITRE
        # ----------------------------------------------------

        title_node = soup.find(
            "h1"
        )

        title = (
            title_node.get_text(
                " ",
                strip=True
            )
            if title_node
            else article["title"]
        )

        # ----------------------------------------------------
        # DATE REELLE
        # ----------------------------------------------------

        pub_date = extract_article_date(
            soup
        )

        if not pub_date:

            print(
                "⚠️ Date introuvable."
            )

            # On ne met surtout PAS la date actuelle.
            # L'article serait alors considéré comme nouveau.
            continue

        print(
            f"📅 Date : {pub_date}"
        )

        # ----------------------------------------------------
        # DESCRIPTION
        # ----------------------------------------------------

        description = ""

        meta = soup.find(
            "meta",
            attrs={
                "name": "description"
            }
        )

        if meta:

            description = (
                meta.get("content")
                or ""
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

                description = (
                    meta.get("content")
                    or ""
                )

        if not description:

            for paragraph in soup.find_all(
                "p"
            ):

                text = paragraph.get_text(
                    " ",
                    strip=True
                )

                if len(text) >= 60:

                    description = text
                    break

        if not description:

            description = title

        processed = {
            "url": url,
            "title": title,
            "description": description,
            "pubDate": pub_date
        }

        cache[url] = {
            "title": title,
            "description": description,
            "pubDate": pub_date
        }

        save_cache(
            cache
        )

        dated_articles.append(
            processed
        )

    except Exception as e:

        print(
            f"⚠️ Erreur : {e}"
        )


# ============================================================
# TRI PAR DATE REELLE
# ============================================================

def sort_key(article):

    try:

        dt = datetime.strptime(
            article["pubDate"],
            "%a, %d %b %Y %H:%M:%S GMT"
        )

        return dt.replace(
            tzinfo=timezone.utc
        )

    except Exception:

        return datetime(
            1970,
            1,
            1,
            tzinfo=timezone.utc
        )


dated_articles.sort(
    key=sort_key,
    reverse=True
)


# ============================================================
# 20 PLUS RECENTS
# ============================================================

articles = dated_articles[
    :MAX_ARTICLES
]


print("")
print("########################################")
print(
    f"# {len(articles)} actualités retenues"
)
print("########################################")


for index, article in enumerate(
    articles,
    start=1
):

    print(
        f"{index:02d}. "
        f"{article['pubDate']} - "
        f"{article['title']}"
    )


# ============================================================
# DATE DE GENERATION
# ============================================================

now = formatdate(
    datetime.now(
        timezone.utc
    ).timestamp(),
    usegmt=True
)


# ============================================================
# GENERATION RSS
# ============================================================

def create_rss(
    output_file,
    title,
    description,
    articles_to_include
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
    ).text = NEWS_URL

    SubElement(
        channel,
        "description"
    ).text = description

    # --------------------------------------------------------
    # ATOM SELF
    # --------------------------------------------------------

    self_url = (
        "https://shynen.github.io/"
        "tensho-cod-rss/"
        f"{output_file}"
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

    # --------------------------------------------------------
    # ARTICLES
    # --------------------------------------------------------

    for article in articles_to_include:

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
                "isPermaLink": "true"
            }
        ).text = article["url"]

        # IMPORTANT POUR READYBOT
        SubElement(
            item,
            "pubDate"
        ).text = article["pubDate"]

        SubElement(
            item,
            "description"
        ).text = (
            article.get(
                "description"
            )
            or
            article["title"]
        )

    tree = ElementTree(
        rss
    )

    indent(
        tree,
        space="  "
    )

    tree.write(
        output_file,
        encoding="utf-8",
        xml_declaration=True
    )


# ============================================================
# RSS COMPLET
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
    f"🟢 {OUTPUT} généré."
)


# ============================================================
# RSS DISCORD
# ============================================================

print("")
print("Génération de lol-news-discord.xml...")

discord_articles = []

if articles:

    # UNE SEULE ACTUALITE
    discord_articles = [
        articles[0]
    ]

create_rss(
    DISCORD_OUTPUT,
    "League of Legends Actualités",
    "Dernière actualité officielle de League of Legends.",
    discord_articles
)

print(
    f"🟢 {DISCORD_OUTPUT} généré."
)


# ============================================================
# SAUVEGARDE CACHE
# ============================================================

save_cache(
    cache
)


# ============================================================
# FIN
# ============================================================

print("")
print("########################################")
print("# LOl RSS TERMINÉ")
print("########################################")
print("")
