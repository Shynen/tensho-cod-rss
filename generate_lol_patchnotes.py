import json
import os
import re
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

SOURCE_URL = (
    "https://www.leagueoflegends.com/"
    "fr-fr/news/game-updates/"
)

OUTPUT = "lol-patchnotes.xml"
DISCORD_OUTPUT = "lol-patchnotes-discord.xml"
CACHE_FILE = "lol_patchnotes_cache.json"

MAX_PATCHNOTES = 20

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
print("# Tensho League of Legends")
print("# PATCH NOTES FRANÇAISES")
print("########################################")
print("")


# ============================================================
# CACHE
# ============================================================

def load_cache():

    if not os.path.exists(CACHE_FILE):

        print("Aucun cache Patch Notes LoL trouvé.")

        return {}

    try:

        with open(
            CACHE_FILE,
            "r",
            encoding="utf-8",
        ) as f:

            data = json.load(f)

        if not isinstance(data, dict):

            return {}

        print(
            f"Cache Patch Notes LoL chargé : "
            f"{len(data)} articles."
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
        encoding="utf-8",
    ) as f:

        json.dump(
            cache,
            f,
            ensure_ascii=False,
            indent=2,
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
        str(value),
    ).strip()


def parse_date(value):

    if not value:

        return None

    value = clean_text(value)

    try:

        dt = datetime.fromisoformat(
            value.replace(
                "Z",
                "+00:00",
            )
        )

        if dt.tzinfo is None:

            dt = dt.replace(
                tzinfo=timezone.utc,
            )

        return dt

    except Exception:

        return None


def format_pubdate(dt):

    return formatdate(
        dt.timestamp(),
        usegmt=True,
    )


# ============================================================
# RECUPERATION DE LA PAGE OFFICIELLE
# ============================================================

print("")
print("========================================")
print("Ouverture de la page officielle :")
print(SOURCE_URL)
print("========================================")


try:

    response = requests.get(
        SOURCE_URL,
        headers=HEADERS,
        timeout=30,
    )

    response.raise_for_status()

except Exception as e:

    print(
        f"❌ Impossible de charger la page : {e}"
    )

    raise SystemExit(1)


soup = BeautifulSoup(
    response.text,
    "html.parser",
)


# ============================================================
# RECUPERATION DES URL
# ============================================================

all_urls = set()

# ------------------------------------------------------------
# 1. Liens HTML classiques
# ------------------------------------------------------------

for link in soup.find_all(
    "a",
    href=True,
):

    href = link.get("href")

    if not href:
        continue

    full_url = urljoin(
        BASE_URL,
        href,
    )

    full_url = full_url.rstrip("/")

    # Uniquement les articles de mises à jour du jeu
    if "/fr-fr/news/game-updates/" not in full_url:
        continue

    # Exclure la page catégorie elle-même
    if full_url == (
        BASE_URL
        + "/fr-fr/news/game-updates"
    ):
        continue

    # Une vraie patch note doit contenir patch
    if "patch" not in full_url.lower():
        continue

    # Exclure d'éventuelles pages parasites
    if (
        "patch-notes" not in full_url.lower()
        and "patchnote" not in full_url.lower()
        and "/patch-" not in full_url.lower()
    ):
        continue

    all_urls.add(full_url)


# ------------------------------------------------------------
# 2. Fallback : recherche directement dans le HTML
# ------------------------------------------------------------

if not all_urls:

    print(
        "⚠️ Aucun lien Patch Note détecté "
        "directement."
    )

    print(
        "Recherche des vraies URLs "
        "Patch Notes dans le HTML..."
    )

    html = response.text.replace(
        "\\/",
        "/",
    )

    matches = re.findall(
        r'https?://www\.leagueoflegends\.com'
        r'/fr-fr/news/game-updates/'
        r'[^"\'<>\s]+',
        html,
        re.IGNORECASE,
    )

    for url in matches:

        url = url.rstrip(
            "/,);"
        )

        if "patch" not in url.lower():
            continue

        if (
            "patch-notes" not in url.lower()
            and "patchnote" not in url.lower()
            and "/patch-" not in url.lower()
        ):
            continue

        all_urls.add(url)


# ------------------------------------------------------------
# 3. Nettoyage final
# ------------------------------------------------------------

all_urls = {
    url.rstrip("/")
    for url in all_urls
    if url.rstrip("/") != (
        BASE_URL
        + "/fr-fr/news/tags/patch-notes"
    )
}


print("")
print("########################################")
print(
    f"# URLs Patch Notes trouvées : "
    f"{len(all_urls)}"
)
print("########################################")

for url in sorted(all_urls):
    print(
        f"🟢 Patch trouvé : {url}"
    )
# ============================================================
# TRAITEMENT DES PATCH NOTES
# ============================================================

articles = []

session = requests.Session()

session.headers.update(
    HEADERS
)


for index, url in enumerate(
    all_urls,
    start=1,
):

    print("")
    print(
        f"[{index}/{len(all_urls)}] "
        f"{url}"
    )

    try:

        page_response = session.get(
            url,
            timeout=30,
        )

        page_response.raise_for_status()

        page_soup = BeautifulSoup(
            page_response.text,
            "html.parser",
        )

    except Exception as e:

        print(
            f"⚠️ Impossible de charger : {e}"
        )

        continue


    # ========================================================
    # TITRE
    # ========================================================

    title = ""

    h1 = page_soup.find(
        "h1"
    )

    if h1:

        title = clean_text(
            h1.get_text(
                " ",
                strip=True,
            )
        )


    if not title:

        og_title = page_soup.find(
            "meta",
            attrs={
                "property":
                "og:title",
            },
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
            .split("/")[-1]
            .replace(
                "-",
                " ",
            )
            .strip()
            .title()
        )


    # ========================================================
    # SECURITE : VERIFICATION PATCH
    # ========================================================

    combined_title_url = (
        title
        + " "
        + url
    ).lower()


    if (
        "patch" not in combined_title_url
        and
        "patchnote" not in combined_title_url
    ):

        print(
            f"❌ Pas identifié comme Patch Note : "
            f"{title}"
        )

        continue


    # ========================================================
    # DATE
    # ========================================================

    dt = None


    # JSON-LD

    for script in page_soup.find_all(
        "script",
        type="application/ld+json",
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
            raw,
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

        meta_candidates = [
            {
                "property":
                "article:published_time",
            },
            {
                "property":
                "og:published_time",
            },
        ]


        for attrs in meta_candidates:

            meta = page_soup.find(
                "meta",
                attrs=attrs,
            )


            if meta:

                dt = parse_date(
                    meta.get(
                        "content"
                    )
                )


                if dt:

                    break


    # TIME

    if not dt:

        for node in page_soup.find_all(
            "time"
        ):

            dt = parse_date(
                node.get(
                    "datetime"
                )
            )


            if dt:

                break


    # CACHE

    if not dt:

        cached = cache.get(
            url
        )


        if cached:

            dt = parse_date(
                cached.get(
                    "pubDate"
                )
            )


    if not dt:

        print(
            "⚠️ Date introuvable."
        )

        continue


    # ========================================================
    # DESCRIPTION
    # ========================================================

    description = ""


    meta = page_soup.find(
        "meta",
        attrs={
            "name":
            "description",
        },
    )


    if meta:

        description = clean_text(
            meta.get(
                "content"
            )
        )


    if not description:

        meta = page_soup.find(
            "meta",
            attrs={
                "property":
                "og:description",
            },
        )


        if meta:

            description = clean_text(
                meta.get(
                    "content"
                )
            )


    if not description:

        description = title


    # ========================================================
    # AJOUT
    # ========================================================

    articles.append(
        {
            "title":
            title,

            "url":
            url,

            "description":
            description,

            "date":
            dt,
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
    reverse=True,
)


# ============================================================
# LIMITATION
# ============================================================

articles = articles[
    :MAX_PATCHNOTES
]


# ============================================================
# AFFICHAGE FINAL
# ============================================================

print("")
print("########################################")
print(
    f"# {len(articles)} Patch Notes retenues"
)
print("########################################")
print("")


for index, article in enumerate(
    articles,
    start=1,
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
        ),
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
    usegmt=True,
)


def create_rss(
    filename,
    title,
    description,
    articles_to_use,
):

    rss = Element(
        "rss",
        {
            "version":
            "2.0",

            "xmlns:atom":
            "http://www.w3.org/2005/Atom",
        },
    )


    channel = SubElement(
        rss,
        "channel",
    )


    SubElement(
        channel,
        "title",
    ).text = title


    SubElement(
        channel,
        "link",
    ).text = SOURCE_URL


    SubElement(
        channel,
        "description",
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
            "application/rss+xml",
        },
    )


    SubElement(
        channel,
        "lastBuildDate",
    ).text = now


    for article in articles_to_use:

        item = SubElement(
            channel,
            "item",
        )


        SubElement(
            item,
            "title",
        ).text = article["title"]


        SubElement(
            item,
            "link",
        ).text = article["url"]


        SubElement(
            item,
            "guid",
            {
                "isPermaLink":
                "true",
            },
        ).text = article["url"]


        SubElement(
            item,
            "pubDate",
        ).text = format_pubdate(
            article["date"]
        )


        SubElement(
            item,
            "description",
        ).text = article["description"]


    tree = ElementTree(
        rss
    )


    indent(
        tree,
        space="  ",
    )


    tree.write(
        filename,
        encoding="utf-8",
        xml_declaration=True,
    )


# ============================================================
# FLUX PRINCIPAL
# ============================================================

print("")
print(
    "Génération de lol-patchnotes.xml..."
)


create_rss(
    OUTPUT,
    "League of Legends — Patch Notes",
    "Notes de patch officielles françaises de League of Legends.",
    articles,
)


print(
    "🟢 lol-patchnotes.xml généré."
)


# ============================================================
# FLUX DISCORD
# ============================================================

print("")
print(
    "Génération de lol-patchnotes-discord.xml..."
)


create_rss(
    DISCORD_OUTPUT,
    "League of Legends — Patch Notes",
    "Dernière note de patch officielle française de League of Legends.",
    articles[:1],
)


print(
    "🟢 lol-patchnotes-discord.xml généré."
)


# ============================================================
# FIN
# ============================================================

print("")
print("########################################")
print("# LOL PATCH NOTES RSS TERMINÉ")
print("########################################")
print("")
