import json
import os
import re
import html
import requests

from bs4 import BeautifulSoup
from datetime import datetime, timezone
from email.utils import formatdate
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
# REQUETE HTTP
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
# NORMALISATION
# ============================================================

def clean_text(value):

    if not value:
        return ""

    value = html.unescape(
        str(value)
    )

    value = re.sub(
        r"\s+",
        " ",
        value
    )

    return value.strip()


# ============================================================
# DATE
# ============================================================

def parse_datetime(value):

    if not value:
        return None

    value = clean_text(value)

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

        return dt

    except Exception:
        pass

    # YYYY-MM-DD
    try:

        return datetime.strptime(
            value,
            "%Y-%m-%d"
        ).replace(
            tzinfo=timezone.utc
        )

    except Exception:
        pass

    return None


def format_pubdate(dt):

    return formatdate(
        dt.timestamp(),
        usegmt=True
    )


# ============================================================
# EXTRACTION DES DONNEES JSON
# ============================================================

def walk_json(
    value,
    results
):

    if isinstance(
        value,
        dict
    ):

        results.append(
            value
        )

        for child in value.values():

            walk_json(
                child,
                results
            )

    elif isinstance(
        value,
        list
    ):

        for child in value:

            walk_json(
                child,
                results
            )


def extract_json_objects(
    soup
):

    objects = []

    # --------------------------------------------------------
    # JSON-LD
    # --------------------------------------------------------

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

        try:

            data = json.loads(
                raw
            )

            walk_json(
                data,
                objects
            )

        except Exception:
            continue

    # --------------------------------------------------------
    # SCRIPTS JAVASCRIPT / NEXT DATA
    # --------------------------------------------------------

    for script in soup.find_all(
        "script"
    ):

        raw = script.string

        if not raw:
            continue

        raw = raw.strip()

        if len(raw) < 100:
            continue

        # Dates + URLs présentes dans les données
        # embarquées de Riot.
        if (
            "leagueoflegends.com/fr-fr/news/"
            not in raw
            and
            "datePublished"
            not in raw
        ):
            continue

        # Extraction de petits objets JSON
        # contenant les informations d'article.
        matches = re.findall(
            r'\{[^{}]{0,5000}'
            r'"(?:datePublished|publishedAt|publishDate)"'
            r'\s*:\s*"[^"]+"'
            r'[^{}]{0,5000}\}',
            raw,
            re.DOTALL
        )

        for match in matches:

            try:

                data = json.loads(
                    match
                )

                walk_json(
                    data,
                    objects
                )

            except Exception:
                continue

    return objects


# ============================================================
# EXTRACTION DES ARTICLES D'UNE PAGE
# ============================================================

def extract_articles_from_page(
    page_url
):

    print("")
    print(
        f"Lecture de : {page_url}"
    )

    source = get_page(
        page_url
    )

    soup = BeautifulSoup(
        source,
        "html.parser"
    )

    candidates = []

    # --------------------------------------------------------
    # 1. DONNEES JSON / STRUCTUREES
    # --------------------------------------------------------

    json_objects = extract_json_objects(
        soup
    )

    for obj in json_objects:

        title = clean_text(
            obj.get("title")
            or
            obj.get("headline")
            or
            obj.get("name")
        )

        url = (
            obj.get("url")
            or
            obj.get("link")
            or
            obj.get("canonicalUrl")
        )

        date_value = (
            obj.get("datePublished")
            or
            obj.get("publishedAt")
            or
            obj.get("publishDate")
            or
            obj.get("date")
        )

        if not title or not url:
            continue

        if not isinstance(
            url,
            str
        ):
            continue

        if (
            "/fr-fr/news/"
            not in url
        ):
            continue

        url = urljoin(
            BASE_URL,
            url
        )

        dt = parse_datetime(
            date_value
        )

        if not dt:
            continue

        candidates.append(
            {
                "title": title,
                "url": url,
                "date": dt,
                "category": clean_text(
                    obj.get("category")
                    or
                    obj.get("contentType")
                    or
                    obj.get("type")
                ),
            }
        )

    # --------------------------------------------------------
    # 2. LIENS CLASSIQUES
    # --------------------------------------------------------

    # Cette partie sert de secours si Riot change
    # légèrement sa structure JSON.
    for link in soup.find_all(
        "a",
        href=True
    ):

        href = link.get(
            "href"
        )

        if not href:
            continue

        if (
            "/fr-fr/news/"
            not in href
        ):
            continue

        url = urljoin(
            BASE_URL,
            href
        )

        title = clean_text(
            link.get_text(
                " ",
                strip=True
            )
        )

        if (
            not title
            or
            len(title) < 8
        ):
            continue

        candidates.append(
            {
                "title": title,
                "url": url,
                "date": None,
                "category": "",
            }
        )

    return candidates


# ============================================================
# FILTRAGE
# ============================================================

def is_excluded(article):

    title = clean_text(
        article.get("title")
    )

    url = article.get(
        "url",
        ""
    )

    category = clean_text(
        article.get(
            "category",
            ""
        )
    )

    text = (
        title
        + " "
        + url
        + " "
        + category
    ).lower()

    # --------------------------------------------------------
    # PATCH NOTES
    # --------------------------------------------------------

    patch_patterns = [

        r"notes?\s+de\s+patch",
        r"patch\s+\d+\.\d+",
        r"patch[-_]\d+[-_]\d+",
        r"/patch[-_]?notes",
    ]

    # --------------------------------------------------------
    # ESPORT
    # --------------------------------------------------------

    esport_patterns = [

        r"hall of legends",
        r"\blec\b",
        r"\bmsi\b",
        r"\bworlds\b",
        r"\besport\b",
        r"\be-sport\b",
        r"watch party",
        r"compétition",
        r"compétitions",
        r"joueur professionnel",
    ]

    # --------------------------------------------------------
    # GUIDES
    # --------------------------------------------------------

    guide_patterns = [

        r"\bguide\b",
        r"\bbuild\b",
        r"comment avoir",
        r"comment bien",
        r"astuces?",
        r"survivre dans",
        r"phase de laning",
    ]

    for pattern in patch_patterns:

        if re.search(
            pattern,
            text,
            re.IGNORECASE
        ):

            return True

    for pattern in esport_patterns:

        if re.search(
            pattern,
            text,
            re.IGNORECASE
        ):

            return True

    for pattern in guide_patterns:

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


# ============================================================
# COLLECTE
# ============================================================

raw_articles = []

for page_url in (
    NEWS_URL,
    DEV_URL
):

    try:

        raw_articles.extend(
            extract_articles_from_page(
                page_url
            )
        )

    except Exception as e:

        print(
            f"⚠️ Erreur sur {page_url} : {e}"
        )


print("")
print(
    f"Articles bruts trouvés : "
    f"{len(raw_articles)}"
)


# ============================================================
# DEDOUBLONNAGE
# ============================================================

unique = {}

for article in raw_articles:

    url = article["url"]

    if url not in unique:

        unique[url] = article

        continue

    # On préfère une entrée ayant une date.
    if (
        unique[url].get("date")
        is None
        and
        article.get("date")
        is not None
    ):

        unique[url] = article


raw_articles = list(
    unique.values()
)


# ============================================================
# FILTRAGE
# ============================================================

filtered = []

for article in raw_articles:

    if is_excluded(
        article
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
# RECUPERATION DES DATES MANQUANTES
# ============================================================

final_articles = []

for index, article in enumerate(
    filtered,
    start=1
):

    url = article["url"]

    title = article["title"]

    print("")
    print(
        f"[{index}/{len(filtered)}] "
        f"{title}"
    )

    # --------------------------------------------------------
    # DATE DEJA RECUPEREE
    # --------------------------------------------------------

    if article.get("date"):

        dt = article["date"]

        print(
            f"📅 Date liste : "
            f"{format_pubdate(dt)}"
        )

    else:

        # ----------------------------------------------------
        # CACHE
        # ----------------------------------------------------

        cached = cache.get(
            url
        )

        cached_date = (
            cached.get("pubDate")
            if cached
            else None
        )

        dt = parse_datetime(
            cached_date
        )

        if dt:

            print(
                f"🟢 Cache utilisé : "
                f"{cached_date}"
            )

        else:

            # ------------------------------------------------
            # PAGE ARTICLE
            # ------------------------------------------------

            try:

                article_source = get_page(
                    url
                )

                article_soup = BeautifulSoup(
                    article_source,
                    "html.parser"
                )

                # JSON-LD
                date_value = None

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

                    try:

                        data = json.loads(
                            raw
                        )

                        objects = []

                        walk_json(
                            data,
                            objects
                        )

                        for obj in objects:

                            candidate = (
                                obj.get(
                                    "datePublished"
                                )
                                or
                                obj.get(
                                    "dateCreated"
                                )
                            )

                            if candidate:

                                date_value = candidate
                                break

                        if date_value:
                            break

                    except Exception:
                        continue

                dt = parse_datetime(
                    date_value
                )

                # Meta
                if not dt:

                    meta = article_soup.find(
                        "meta",
                        attrs={
                            "property":
                            "article:published_time"
                        }
                    )

                    if not meta:

                        meta = article_soup.find(
                            "meta",
                            attrs={
                                "property":
                                "og:published_time"
                            }
                        )

                    if meta:

                        dt = parse_datetime(
                            meta.get(
                                "content"
                            )
                        )

                # <time>
                if not dt:

                    for node in article_soup.find_all(
                        "time"
                    ):

                        dt = parse_datetime(
                            node.get(
                                "datetime"
                            )
                            or
                            node.get_text(
                                " ",
                                strip=True
                            )
                        )

                        if dt:
                            break

                if not dt:

                    print(
                        "⚠️ Date introuvable."
                    )

                    continue

                print(
                    f"📅 Date article : "
                    f"{format_pubdate(dt)}"
                )

            except Exception as e:

                print(
                    f"⚠️ Erreur article : {e}"
                )

                continue

    # --------------------------------------------------------
    # DESCRIPTION
    # --------------------------------------------------------

    description = ""

    cached = cache.get(
        url
    )

    if cached:

        description = clean_text(
            cached.get(
                "description",
                ""
            )
        )

    # Si description absente,
    # on récupère la page.
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

    # --------------------------------------------------------
    # AJOUT
    # --------------------------------------------------------

    pub_date = format_pubdate(
        dt
    )

    processed = {
        "title": title,
        "url": url,
        "description": description,
        "pubDate": pub_date
    }

    final_articles.append(
        processed
    )

    cache[url] = {
        "title": title,
        "description": description,
        "pubDate": pub_date
    }


# ============================================================
# TRI CHRONOLOGIQUE
# ============================================================

def sort_key(article):

    dt = parse_datetime(
        article["pubDate"]
    )

    if not dt:

        return datetime(
            1970,
            1,
            1,
            tzinfo=timezone.utc
        )

    return dt


final_articles.sort(
    key=sort_key,
    reverse=True
)


# ============================================================
# 20 PLUS RECENTS
# ============================================================

articles = final_articles[
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
        f"{article['pubDate']} - "
        f"{article['title']}"
    )


# ============================================================
# SAUVEGARDE CACHE
# ============================================================

save_cache(
    cache
)


# ============================================================
# DATE GENERATION
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
    feed_title,
    feed_description,
    feed_url,
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
    ).text = feed_title

    SubElement(
        channel,
        "link"
    ).text = NEWS_URL

    SubElement(
        channel,
        "description"
    ).text = feed_description

    SubElement(
        channel,
        "atom:link",
        {
            "href": feed_url,
            "rel": "self",
            "type": "application/rss+xml"
        }
    )

    SubElement(
        channel,
        "lastBuildDate"
    ).text = now

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
                "isPermaLink":
                "true"
            }
        ).text = article["url"]

        SubElement(
            item,
            "pubDate"
        ).text = article["pubDate"]

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
        output_file,
        encoding="utf-8",
        xml_declaration=True
    )


# ============================================================
# RSS PRINCIPAL
# ============================================================

print("")
print(
    "Génération de lol-news.xml..."
)

create_rss(
    OUTPUT,
    "League of Legends — Actualités",
    "Actualités officielles françaises de League of Legends.",
    "https://shynen.github.io/"
    "tensho-cod-rss/"
    "lol-news.xml",
    articles
)

print(
    f"🟢 {OUTPUT} généré."
)


# ============================================================
# RSS DISCORD
# ============================================================

print("")
print(
    "Génération de lol-news-discord.xml..."
)

discord_articles = (
    articles[:1]
    if articles
    else []
)

create_rss(
    DISCORD_OUTPUT,
    "League of Legends Actualités",
    "Dernière actualité officielle de League of Legends.",
    "https://shynen.github.io/"
    "tensho-cod-rss/"
    "lol-news-discord.xml",
    discord_articles
)

print(
    f"🟢 {DISCORD_OUTPUT} généré."
)


# ============================================================
# FIN
# ============================================================

print("")
print("########################################")
print("# LOL RSS TERMINÉ")
print("########################################")
print("")
