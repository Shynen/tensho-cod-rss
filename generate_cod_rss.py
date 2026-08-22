import os
import re
import json
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
    register_namespace
)

import argostranslate.package
import argostranslate.translate


# ============================================================
# CONFIGURATION
# ============================================================

BASE_URL = "https://www.callofduty.com"
BLOG_URL = "https://www.callofduty.com/fr/blog?count=50"

OUTPUT = "cod.rss"
CACHE_FILE = "cod_cache.json"

FEED_URL = "https://shynen.github.io/tensho-cod-rss/cod.rss"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; TenshoCODRSS/1.0)"
}

CONTENT_NS = "http://purl.org/rss/1.0/modules/content/"
ATOM_NS = "http://www.w3.org/2005/Atom"

register_namespace("content", CONTENT_NS)
register_namespace("atom", ATOM_NS)


# ============================================================
# ARGOS
# ============================================================

def setup_translation():

    print("Vérification du modèle Argos EN -> FR...")

    installed = argostranslate.translate.get_installed_languages()

    # Vérifie d'abord si le modèle existe déjà
    for language in installed:

        if language.code != "en":
            continue

        for translation in language.translations_from:

            if translation.to_lang.code == "fr":

                print("Modèle EN -> FR déjà installé. ♻️")
                return

    # Le modèle n'existe pas : on met à jour l'index
    print("Modèle EN -> FR absent.")
    print("Téléchargement du modèle Argos...")

    try:
        argostranslate.package.update_package_index()
    except Exception as e:
        print(f"Erreur lors de la mise à jour de l'index : {e}")
        raise

    packages = argostranslate.package.get_available_packages()

    package = next(
        (
            p for p in packages
            if p.from_code == "en"
            and p.to_code == "fr"
        ),
        None
    )

    if package is None:
        raise RuntimeError(
            "Modèle Argos EN -> FR introuvable."
        )

    print("Installation du modèle EN -> FR...")

    argostranslate.package.install_from_path(
        package.download()
    )

    print("Modèle EN -> FR installé. ✅")

    for language in installed:

        if language.code != "en":
            continue

        for translation in language.translations_from:

            if translation.to_lang.code == "fr":

                print("Modèle EN -> FR déjà installé.")
                return

    packages = argostranslate.package.get_available_packages()

    package = next(
        (
            p for p in packages
            if p.from_code == "en"
            and p.to_code == "fr"
        ),
        None
    )

    if package is None:
        raise RuntimeError(
            "Modèle Argos EN -> FR introuvable."
        )

    print("Installation du modèle EN -> FR...")

    argostranslate.package.install_from_path(
        package.download()
    )

    print("Modèle EN -> FR installé.")


def translate_text(text):

    if not text or not text.strip():
        return text

    try:

        result = argostranslate.translate.translate(
            text.strip(),
            "en",
            "fr"
        )

        return result or text

    except Exception as e:

        print(f"Erreur traduction : {e}")
        return text


# ============================================================
# DÉTECTION ANGLAIS
# ============================================================

ENGLISH_WORDS = {
    "the", "and", "you", "your", "with", "for",
    "from", "this", "that", "these", "those",
    "everything", "know", "open", "beta",
    "season", "update", "new", "coming",
    "available", "details", "about", "what",
    "when", "where", "will", "how", "play",
    "game", "games", "content", "multiplayer",
    "campaign", "weapons", "weapon", "operator",
    "launch", "weekend", "intel", "event",
    "events", "rewards", "reward", "battle",
    "pass", "store", "players", "player",
    "system", "systems", "feature", "features",
    "community", "soon", "first", "second",
    "third", "early", "access", "need",
    "learn", "introducing", "overview",
    "reveal", "revealed", "announcement",
    "announcements"
}


def looks_english(text):

    if not text:
        return False

    words = re.findall(
        r"\b[a-zA-Z]+\b",
        text.lower()
    )

    if len(words) < 3:
        return False

    matches = sum(
        1 for word in words
        if word in ENGLISH_WORDS
    )

    if matches >= 2:
        return True

    phrases = [
        "open beta",
        "everything you need to know",
        "weekend one",
        "early access",
        "initial intel",
        "next highlights",
        "gameplay systems",
        "preorder benefits",
        "game editions",
        "battle pass",
        "season update",
        "season reloaded"
    ]

    lower = text.lower()

    return any(
        phrase in lower
        for phrase in phrases
    )


# ============================================================
# TRADUCTION HTML
# ============================================================

def translate_html(html_content):

    if not html_content:
        return ""

    soup = BeautifulSoup(
        html_content,
        "html.parser"
    )

    ignored = {
        "script",
        "style",
        "code",
        "pre"
    }

    for node in list(
        soup.find_all(string=True)
    ):

        parent = node.parent

        if parent and parent.name in ignored:
            continue

        text = str(node)
        stripped = text.strip()

        if len(stripped) < 3:
            continue

        if not looks_english(stripped):
            continue

        translated = translate_text(
            stripped
        )

        if translated != stripped:

            prefix = text[
                :len(text) - len(text.lstrip())
            ]

            suffix = text[
                len(text.rstrip()):
            ]

            node.replace_with(
                prefix + translated + suffix
            )

    return str(soup)


# ============================================================
# EXTRACTION ARTICLE
# ============================================================

def fetch_article(url):

    print()
    print(f"Nouvel article : {url}")

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

    # --------------------------------------------------------
    # TITRE
    # --------------------------------------------------------

    title = ""

    og_title = soup.find(
        "meta",
        property="og:title"
    )

    if og_title:
        title = og_title.get(
            "content",
            ""
        ).strip()

    if not title:

        h1 = soup.find("h1")

        if h1:
            title = h1.get_text(
                " ",
                strip=True
            )

    if not title and soup.title:

        title = soup.title.get_text(
            " ",
            strip=True
        )

    # --------------------------------------------------------
    # DESCRIPTION
    # --------------------------------------------------------

    description = ""

    og_description = soup.find(
        "meta",
        property="og:description"
    )

    if og_description:

        description = og_description.get(
            "content",
            ""
        ).strip()

    # --------------------------------------------------------
    # CONTENU
    # --------------------------------------------------------

    content = soup.find("article")

    if content is None:

        for selector in [
            "main",
            "[role='main']",
            ".article-content",
            ".blog-content",
            ".content"
        ]:

            content = soup.select_one(
                selector
            )

            if content is not None:
                break

    if content is None:
        content = soup.body

    if content is None:

        return {
            "title": title,
            "description": description,
            "content": ""
        }

    for tag in content.find_all([
        "script",
        "style",
        "noscript"
    ]):
        tag.decompose()

    content_html = str(content)

    # --------------------------------------------------------
    # TRADUCTION
    # --------------------------------------------------------

    if looks_english(title):

        print(f"Titre anglais : {title}")

        title = translate_text(title)

        print(f"Titre FR : {title}")

    if description and looks_english(description):

        print("Description anglaise -> traduction.")

        description = translate_text(
            description
        )

    plain = content.get_text(
        " ",
        strip=True
    )

    if looks_english(plain[:5000]):

        print("Contenu anglais -> traduction.")

        content_html = translate_html(
            content_html
        )

    else:

        print("Contenu déjà français.")

    return {
        "title": title,
        "description": description,
        "content": content_html
    }


# ============================================================
# CACHE
# ============================================================

def load_cache():

    if not os.path.exists(CACHE_FILE):

        print("Aucun cache trouvé.")

        return {}

    try:

        with open(
            CACHE_FILE,
            "r",
            encoding="utf-8"
        ) as file:

            cache = json.load(file)

        print(
            f"Cache chargé : {len(cache)} articles."
        )

        return cache

    except Exception as e:

        print(
            f"Cache illisible, nouveau cache : {e}"
        )

        return {}


def save_cache(cache):

    with open(
        CACHE_FILE,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            cache,
            file,
            ensure_ascii=False,
            indent=2
        )

    print(
        f"Cache sauvegardé : {len(cache)} articles."
    )


# ============================================================
# RÉCUPÉRATION BLOG
# ============================================================

def get_articles():

    print("Téléchargement du blog COD...")

    response = requests.get(
        BLOG_URL,
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

    pattern = re.compile(
        r"^/fr/blog/\d{4}/"
    )

    for link in soup.find_all(
        "a",
        href=True
    ):

        href = link["href"]

        if not pattern.match(href):
            continue

        url = urljoin(
            BASE_URL,
            href
        )

        if url in seen:
            continue

        title = link.get_text(
            " ",
            strip=True
        )

        if not title or len(title) < 8:
            continue

        seen.add(url)

        parent = link
        date_text = ""

        for _ in range(5):

            parent = parent.parent

            if parent is None:
                break

            text = parent.get_text(
                " ",
                strip=True
            )

            match = re.search(
                r"(janvier|février|mars|avril|mai|juin|juillet|août|septembre|octobre|novembre|décembre)"
                r"\s+\d{1,2},?\s+\d{4}",
                text,
                re.IGNORECASE
            )

            if match:

                date_text = match.group(0)
                break

        articles.append({
            "title": title,
            "url": url,
            "date": date_text
        })

    articles = articles[:20]

    print(
        f"{len(articles)} articles trouvés."
    )

    return articles


# ============================================================
# DATE RSS
# ============================================================

def convert_date(date_text):

    if not date_text:
        return None

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
        "décembre": 12
    }

    match = re.search(
        r"(janvier|février|mars|avril|mai|juin|juillet|août|septembre|octobre|novembre|décembre)"
        r"\s+(\d{1,2}),?\s+(\d{4})",
        date_text,
        re.IGNORECASE
    )

    if not match:
        return None

    month = months.get(
        match.group(1).lower()
    )

    if not month:
        return None

    try:

        date = datetime(
            int(match.group(3)),
            month,
            int(match.group(2)),
            tzinfo=timezone.utc
        )

        return formatdate(
            date.timestamp(),
            usegmt=True
        )

    except Exception:
        return None


# ============================================================
# GÉNÉRATION RSS
# ============================================================

def generate_feed(articles, cache):

    print()
    print("Génération du RSS...")

    rss = Element(
        "rss",
        {
            "version": "2.0",
            "xmlns:atom": ATOM_NS
        }
    )

    # UNE SEULE déclaration content
    rss.set(
        f"{{{CONTENT_NS}}}encoded",
        ""
    )

    # On supprime l'attribut temporaire :
    del rss.attrib[
        f"{{{CONTENT_NS}}}encoded"
    ]

    # Namespace content manuel
    rss.attrib[
        "xmlns:content"
    ] = CONTENT_NS

    channel = SubElement(
        rss,
        "channel"
    )

    SubElement(
        channel,
        "title"
    ).text = (
        "Call of Duty — Actualités françaises"
    )

    SubElement(
        channel,
        "link"
    ).text = BLOG_URL

    SubElement(
        channel,
        "description"
    ).text = (
        "Actualités, annonces et notes de correctif "
        "officielles Call of Duty en français."
    )

    SubElement(
        channel,
        "atom:link",
        {
            "href": FEED_URL,
            "rel": "self",
            "type": "application/rss+xml"
        }
    )

    now = formatdate(
        datetime.now(
            timezone.utc
        ).timestamp(),
        usegmt=True
    )

    SubElement(
        channel,
        "lastBuildDate"
    ).text = now

    successful = 0

    # ========================================================
    # ARTICLES
    # ========================================================

    for article in articles:

        url = article["url"]

        # ----------------------------------------------------
        # CACHE
        # ----------------------------------------------------

        if url in cache:

            print()
            print(
                f"♻️ Cache utilisé : {article['title']}"
            )

            data = cache[url]

        else:

            print()
            print(
                f"🆕 Nouvel article : {article['title']}"
            )

            try:

                data = fetch_article(
                    url
                )

                if data is None:
                    continue

                # Sauvegarde immédiate dans le cache
                cache[url] = data

            except Exception as e:

                print(
                    f"Erreur article : {e}"
                )

                continue

        # ----------------------------------------------------
        # ITEM RSS
        # ----------------------------------------------------

        item = SubElement(
            channel,
            "item"
        )

        SubElement(
            item,
            "title"
        ).text = data["title"]

        SubElement(
            item,
            "link"
        ).text = url

        SubElement(
            item,
            "guid",
            {
                "isPermaLink": "true"
            }
        ).text = url

        rss_date = convert_date(
            article["date"]
        )

        if rss_date:

            SubElement(
                item,
                "pubDate"
            ).text = rss_date

        description = (
            data["description"]
            or
            f"Nouvelle publication officielle "
            f"Call of Duty : {data['title']}"
        )

        SubElement(
            item,
            "description"
        ).text = description

        if data.get("content"):

            content_element = SubElement(
                item,
                f"{{{CONTENT_NS}}}encoded"
            )

            content_element.text = (
                data["content"]
            )

        successful += 1

    # --------------------------------------------------------
    # NETTOYAGE CACHE
    # --------------------------------------------------------

    current_urls = {
        article["url"]
        for article in articles
    }

    cache = {
        url: data
        for url, data in cache.items()
        if url in current_urls
    }

    save_cache(cache)

    # --------------------------------------------------------
    # ÉCRITURE
    # --------------------------------------------------------

    tree = ElementTree(
        rss
    )

    indent(
        tree,
        space="  "
    )

    tree.write(
        OUTPUT,
        encoding="utf-8",
        xml_declaration=True
    )

    print()
    print(
        f"✅ {successful} articles dans {OUTPUT}"
    )


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    print()
    print("########################################")
    print("# Tensho COD RSS")
    print("# Cache + traduction EN -> FR")
    print("########################################")
    print()

    setup_translation()

    articles = get_articles()

    if not articles:

        raise RuntimeError(
            "Aucun article trouvé."
        )

    cache = load_cache()

    generate_feed(
        articles,
        cache
    )

    print()
    print("Terminé.")
