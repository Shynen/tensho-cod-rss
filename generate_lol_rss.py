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

def parse_date(date_text):

    if not date_text:
        return None

    # ISO 8601
    try:

        dt = datetime.fromisoformat(
            date_text.replace(
                "Z",
                "+00:00"
            )
        )

        return formatdate(
            dt.timestamp(),
            usegmt=True
        )

    except Exception:
        pass

    # Date française éventuelle
    months = {
        "janvier": 1,
        "février": 2,
        "mars": 3,
        "avril": 4,
        "mai": 5,
        "juin": 6,
        "juillet": 7,
        "août": 8,
        "septembre": 9,
        "octobre": 10,
        "novembre": 11,
        "décembre": 12,
    }

    match = re.search(
        r"(\d{1,2})\s+([a-zéû]+)\s+(\d{4})",
        date_text.lower()
    )

    if match:

        day = int(match.group(1))
        month_name = match.group(2)
        year = int(match.group(3))

        month = months.get(
            month_name
        )

        if month:

            try:

                dt = datetime(
                    year,
                    month,
                    day,
                    12,
                    0,
                    0,
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
# EXTRACTION DATE
# ============================================================

def extract_date_from_element(element):

    if not element:
        return None

    # Balises time
    time_node = element.find("time")

    if time_node:

        value = (
            time_node.get("datetime")
            or
            time_node.get_text(
                " ",
                strip=True
            )
        )

        parsed = parse_date(value)

        if parsed:
            return parsed

    # Recherche dans le texte
    text = element.get_text(
        " ",
        strip=True
    )

    # ISO 8601
    match = re.search(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z",
        text
    )

    if match:

        return parse_date(
            match.group(0)
        )

    # Date française
    match = re.search(
        r"\d{1,2}\s+"
        r"(?:janvier|février|mars|avril|mai|juin|"
        r"juillet|août|septembre|octobre|novembre|décembre)"
        r"\s+\d{4}",
        text,
        re.IGNORECASE
    )

    if match:

        return parse_date(
            match.group(0)
        )

    return None


# ============================================================
# TITRES À EXCLURE
# ============================================================

EXCLUDED_TITLE_PATTERNS = [

    # Patch notes
    r"\bnotes?\s+de\s+patch\b",
    r"\bpatch\s+\d+\.\d+\b",

    # Guides
    r"\bguide\b",
    r"\bcomment\b",
    r"\bastuces?\b",
    r"\bbuild\b",

    # E-sport
    r"\besport\b",
    r"\be-sport\b",
    r"\blec\b",
    r"\bmsi\b",
    r"\bworlds\b",
    r"\bhall of legends\b",
    r"\bcompétition\b",
    r"\bcompétitions\b",
    r"\bwatch party\b",

    # Wild Rift
    r"\bwild rift\b",

]


def is_excluded(title, url):

    value = (
        title
        + " "
        + url
    ).lower()

    for pattern in EXCLUDED_TITLE_PATTERNS:

        if re.search(
            pattern,
            value,
            re.IGNORECASE
        ):
            return True

    # Exclure explicitement les notes de patch
    if "/news/tags/patch-notes/" in url:
        return True

    return False


# ============================================================
# EXTRACTION DES ARTICLES
# ============================================================

def extract_listing_articles(page_url):

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

        # Eviter les pages de catégories
        if url.rstrip("/") in (
            NEWS_URL.rstrip("/"),
            DEV_URL.rstrip("/")
        ):
            continue

        # Eviter les doublons
        if url in seen:
            continue

        title = link.get_text(
            " ",
            strip=True
        )

        if not title or len(title) < 8:
            continue

        # Filtrage
        if is_excluded(
            title,
            url
        ):
            print(
                f"   ❌ Exclu : {title}"
            )
            continue

        # Date depuis le bloc parent
        pub_date = None

        parent = link

        for _ in range(6):

            parent = parent.parent

            if parent is None:
                break

            pub_date = extract_date_from_element(
                parent
            )

            if pub_date:
                break

        seen.add(url)

        articles.append(
            {
                "url": url,
                "title": title,
                "pubDate": pub_date
            }
        )

    return articles


# ============================================================
# RECUPERATION NEWS + DEV
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


# ============================================================
# TRI
# ============================================================

def sort_key(article):

    if article.get("pubDate"):

        try:

            return datetime.strptime(
                article["pubDate"],
                "%a, %d %b %Y %H:%M:%S GMT"
            ).replace(
                tzinfo=timezone.utc
            )

        except Exception:
            pass

    return datetime(
        1970,
        1,
        1,
        tzinfo=timezone.utc
    )


unique_articles.sort(
    key=sort_key,
    reverse=True
)


articles = unique_articles[
    :MAX_ARTICLES
]


print("")
print(
    f"{len(articles)} actualités LoL retenues."
)


# ============================================================
# RECUPERATION DES PAGES POUR DESCRIPTION
# ============================================================

processed_articles = []


for index, article in enumerate(
    articles,
    start=1
):

    url = article["url"]

    print("")
    print(
        f"[{index}/{len(articles)}] "
        f"{article['title']}"
    )

    # --------------------------------------------------------
    # CACHE
    # --------------------------------------------------------

    if url in cache:

        cached = cache[url]

        print(
            "🟢 Cache utilisé."
        )

        processed_articles.append(
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
                "pubDate": (
                    cached.get(
                        "pubDate"
                    )
                    or
                    article.get(
                        "pubDate"
                    )
                )
            }
        )

        continue

    # --------------------------------------------------------
    # NOUVEL ARTICLE
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

        # Titre
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

        # Description
        description = ""

        # Meta description
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

        # Sinon premier paragraphe intéressant
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

        # Date
        pub_date = (
            article.get("pubDate")
            or
            extract_date_from_element(
                soup
            )
        )

        if not pub_date:

            pub_date = formatdate(
                datetime.now(
                    timezone.utc
                ).timestamp(),
                usegmt=True
            )

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

        processed_articles.append(
            processed
        )

    except Exception as e:

        print(
            f"⚠️ Erreur article : {e}"
        )

        # Même en cas d'erreur, on garde
        # l'article pour éviter de perdre
        # une actualité.

        fallback_date = (
            article.get(
                "pubDate"
            )
            or
            formatdate(
                datetime.now(
                    timezone.utc
                ).timestamp(),
                usegmt=True
            )
        )

        processed_articles.append(
            {
                "url": url,
                "title": article["title"],
                "description": article["title"],
                "pubDate": fallback_date
            }
        )


save_cache(
    cache
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
    feed_url,
    articles_to_include
):

    rss = Element(
        "rss",
        {
            "version": "2.0"
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
            "guid"
        ).text = article["url"]

        # Readybot aime avoir un timestamp
        SubElement(
            item,
            "pubDate"
        ).text = (
            article.get("pubDate")
            or now
        )

        SubElement(
            item,
            "description"
        ).text = (
            article.get("description")
            or article["title"]
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
print("########################################")
print("# Génération LoL News")
print("########################################")

create_rss(
    OUTPUT,
    "League of Legends — Actualités",
    "Actualités officielles françaises de League of Legends.",
    "https://shynen.github.io/tensho-cod-rss/lol-news.xml",
    processed_articles
)

print(
    f"🟢 {len(processed_articles)} articles "
    f"écrits dans {OUTPUT}"
)


# ============================================================
# RSS DISCORD
# ============================================================

print("")
print("########################################")
print("# Génération LoL Discord")
print("########################################")

discord_articles = []

if processed_articles:

    discord_articles = [
        processed_articles[0]
    ]


create_rss(
    DISCORD_OUTPUT,
    "League of Legends Actualités",
    "Dernières actualités officielles de League of Legends.",
    "https://shynen.github.io/tensho-cod-rss/lol-news-discord.xml",
    discord_articles
)

print(
    f"🟢 Flux Discord généré : "
    f"{DISCORD_OUTPUT}"
)


# ============================================================
# FIN
# ============================================================

print("")
print("########################################")
print("# TERMINÉ")
print("########################################")
print("")
