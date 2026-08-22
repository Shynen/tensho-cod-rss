import json
import os
import re
import requests

import argostranslate.package
import argostranslate.translate

from bs4 import BeautifulSoup, NavigableString
from email.utils import formatdate
from datetime import datetime, timezone
from urllib.parse import urljoin

from xml.etree.ElementTree import (
    Element,
    SubElement,
    ElementTree,
    indent,
    register_namespace,
)


# ============================================================
# CONFIGURATION
# ============================================================

BASE_URL = "https://www.callofduty.com"
BLOG_URL = "https://www.callofduty.com/fr/blog?count=50"

OUTPUT = "cod.rss"
DISCORD_OUTPUT = "cod-discord.xml"
CACHE_FILE = "cod_cache.json"

MAX_ARTICLES = 20

ATOM_NS = "http://www.w3.org/2005/Atom"
CONTENT_NS = "http://purl.org/rss/1.0/modules/content/"

register_namespace("atom", ATOM_NS)
register_namespace("content", CONTENT_NS)


HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; TenshoCODRSS/1.0)"
}


# ============================================================
# AFFICHAGE
# ============================================================

print("")
print("########################################")
print("# Tensho COD RSS")
print("# Cache + traduction EN -> FR")
print("########################################")
print("")


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
        ) as f:

            cache = json.load(f)

        if not isinstance(cache, dict):

            print("Cache invalide, nouveau cache.")
            return {}

        print(
            f"Cache chargé : {len(cache)} articles."
        )

        return cache

    except Exception as e:

        print(
            f"Erreur lecture cache : {e}"
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
# ARGOS EN -> FR
# ============================================================

def setup_translation():

    print(
        "Vérification du modèle Argos EN -> FR..."
    )

    installed = (
        argostranslate.translate
        .get_installed_languages()
    )

    for language in installed:

        if language.code != "en":
            continue

        for translation in language.translations_from:

            if translation.to_lang.code == "fr":

                print(
                    "Modèle EN -> FR déjà installé. 🟢"
                )

                return

    print(
        "Modèle EN -> FR absent."
    )

    print(
        "Téléchargement du modèle Argos..."
    )

    argostranslate.package.update_package_index()

    packages = (
        argostranslate.package
        .get_available_packages()
    )

    package = next(
        (
            p
            for p in packages
            if p.from_code == "en"
            and p.to_code == "fr"
        ),
        None
    )

    if package is None:

        raise RuntimeError(
            "Modèle Argos EN -> FR introuvable."
        )

    print(
        "Installation du modèle EN -> FR..."
    )

    argostranslate.package.install_from_path(
        package.download()
    )

    print(
        "Modèle EN -> FR installé. 🟢"
    )


setup_translation()


# ============================================================
# TRADUCTEUR
# ============================================================

def get_translator():

    installed = (
        argostranslate.translate
        .get_installed_languages()
    )

    english = next(
        (
            lang
            for lang in installed
            if lang.code == "en"
        ),
        None
    )

    french = next(
        (
            lang
            for lang in installed
            if lang.code == "fr"
        ),
        None
    )

    if english is None or french is None:

        raise RuntimeError(
            "Langues EN ou FR introuvables."
        )

    for translation in english.translations_from:

        if translation.to_lang.code == "fr":

            return translation

    raise RuntimeError(
        "Traduction EN -> FR introuvable."
    )


translator = get_translator()


# ============================================================
# TRADUCTION TEXTE
# ============================================================

def translate_text(text):

    if not text:
        return ""

    text = text.strip()

    if not text:
        return ""

    try:

        return translator.translate(text)

    except Exception as e:

        print(
            f"Erreur traduction : {e}"
        )

        return text


# ============================================================
# TRADUCTION HTML
# ============================================================

def translate_html_content(content):

    if not content:
        return ""

    soup = BeautifulSoup(
        content,
        "html.parser"
    )

    for text_node in soup.find_all(
        string=True
    ):

        if not isinstance(
            text_node,
            NavigableString
        ):
            continue

        parent = text_node.parent

        if parent is None:
            continue

        if parent.name in (
            "script",
            "style",
            "noscript",
            "code",
            "pre"
        ):
            continue

        original = str(
            text_node
        ).strip()

        if not original:
            continue

        if len(original) < 2:
            continue

        translated = translate_text(
            original
        )

        if translated:

            text_node.replace_with(
                str(text_node).replace(
                    original,
                    translated
                )
            )

    return str(soup)


# ============================================================
# NORMALISATION DES URLS
# ============================================================

def normalize_html_urls(content):

    if not content:
        return ""

    soup = BeautifulSoup(
        content,
        "html.parser"
    )

    # Images
    for img in soup.find_all("img"):

        src = img.get("src")

        if src:

            img["src"] = urljoin(
                BASE_URL,
                src
            )

        srcset = img.get("srcset")

        if srcset:

            new_srcset = []

            for part in srcset.split(","):

                part = part.strip()

                if not part:
                    continue

                values = part.split()

                image_url = values[0]

                absolute_url = urljoin(
                    BASE_URL,
                    image_url
                )

                if len(values) > 1:

                    new_srcset.append(
                        absolute_url
                        + " "
                        + " ".join(
                            values[1:]
                        )
                    )

                else:

                    new_srcset.append(
                        absolute_url
                    )

            img["srcset"] = ", ".join(
                new_srcset
            )

    # Liens
    for link in soup.find_all("a"):

        href = link.get("href")

        if href:

            link["href"] = urljoin(
                BASE_URL,
                href
            )

    return str(soup)


# ============================================================
# DATES
# ============================================================

MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}


def parse_article_date(date_text):

    if not date_text:
        return None

    match = re.search(
        r"([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})",
        date_text
    )

    if not match:
        return None

    month_name = match.group(1).lower()
    day = int(match.group(2))
    year = int(match.group(3))

    month = MONTHS.get(
        month_name
    )

    if not month:
        return None

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

        return None


# ============================================================
# EXTRACTION ARTICLE
# ============================================================

def extract_article_content(url):

    print(
        "   Téléchargement de l'article..."
    )

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
        "h1",
        class_=lambda value: (
            value and "title" in value
        )
    )

    if title_node is None:

        title_node = soup.find(
            "h1"
        )

    title = (
        title_node.get_text(
            " ",
            strip=True
        )
        if title_node
        else ""
    )

    # Date
    date_text = ""

    date_node = soup.find(
        class_=lambda value: (
            value and "dateline" in value
        )
    )

    if date_node:

        date_text = date_node.get_text(
            " ",
            strip=True
        )

    pub_date = parse_article_date(
        date_text
    )

    # Contenu principal
    content_node = soup.find(
        "main",
        id="main-content"
    )

    if content_node is None:

        content_node = soup.find(
            "main"
        )

    if content_node is None:

        content_node = soup.find(
            "article"
        )

    if content_node is None:

        print(
            "⚠️ Contenu principal introuvable."
        )

        return {
            "title": title,
            "description": "",
            "content": "",
            "pubDate": pub_date
        }

    # Nettoyage
    for tag in content_node.find_all(
        [
            "script",
            "style",
            "noscript"
        ]
    ):

        tag.decompose()

    content_html = str(
        content_node
    )

    content_html = normalize_html_urls(
        content_html
    )

    # Description
    content_soup = BeautifulSoup(
        content_html,
        "html.parser"
    )

    description = ""

    for paragraph in content_soup.find_all(
        "p"
    ):

        text = paragraph.get_text(
            " ",
            strip=True
        )

        if len(text) >= 40:

            description = text

            break

    return {
        "title": title,
        "description": description,
        "content": content_html,
        "pubDate": pub_date
    }


# ============================================================
# TELECHARGEMENT DU BLOG
# ============================================================

print(
    "Téléchargement du blog COD..."
)

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


# ============================================================
# RECUPERATION DES ARTICLES
# ============================================================

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

    articles.append(
        {
            "url": url,
            "title": title
        }
    )

    if len(articles) >= MAX_ARTICLES:
        break


print(
    f"{len(articles)} articles trouvés."
)


# ============================================================
# TRAITEMENT + CACHE
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

    # Article déjà en cache
    if url in cache:

        cached = cache[url]

        print(
            f"🟢 Cache utilisé : "
            f"{article['title']}"
        )

        cached_content = cached.get(
            "content",
            ""
        )

        cached_content = normalize_html_urls(
            cached_content
        )

        processed_article = {
            "url": url,
            "title": cached.get(
                "title",
                article["title"]
            ),
            "description": cached.get(
                "description",
                ""
            ),
            "content": cached_content,
            "pubDate": cached.get(
                "pubDate"
            )
        }

        processed_articles.append(
            processed_article
        )

        cache[url] = {
            "title": processed_article["title"],
            "description": processed_article["description"],
            "content": processed_article["content"],
            "pubDate": processed_article["pubDate"]
        }

        continue

    # Nouvel article
    print(
        "🆕 Nouvel article détecté."
    )

    data = extract_article_content(
        url
    )

    original_title = (
        data["title"]
        or
        article["title"]
    )

    original_description = (
        data["description"]
    )

    original_content = (
        data["content"]
    )

    print(
        "   Traduction du titre..."
    )

    translated_title = translate_text(
        original_title
    )

    print(
        "   Traduction de la description..."
    )

    translated_description = translate_text(
        original_description
    )

    print(
        "   Traduction du contenu..."
    )

    translated_content = (
        translate_html_content(
            original_content
        )
    )

    translated_content = (
        normalize_html_urls(
            translated_content
        )
    )

    cache[url] = {
        "title": translated_title,
        "description": translated_description,
        "content": translated_content,
        "pubDate": data.get(
            "pubDate"
        )
    }

    save_cache(
        cache
    )

    processed_articles.append(
        {
            "url": url,
            "title": translated_title,
            "description": translated_description,
            "content": translated_content,
            "pubDate": data.get(
                "pubDate"
            )
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
# CREATION RSS
# ============================================================
def create_rss(
    output_file,
    rss_title,
    rss_description,
    feed_url,
    articles_to_include,
    include_content=True,
    minimal=False
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
    ).text = rss_title

    SubElement(
        channel,
        "link"
    ).text = BLOG_URL

    SubElement(
        channel,
        "description"
    ).text = rss_description

    # --------------------------------------------------------
    # FLUX DISCORD MINIMAL
    # --------------------------------------------------------

    for article in articles_to_include:

        item = SubElement(
            channel,
            "item"
        )

        # Titre
        SubElement(
            item,
            "title"
        ).text = article["title"]

        # Lien
        SubElement(
            item,
            "link"
        ).text = article["url"]

        # GUID
        SubElement(
            item,
            "guid"
        ).text = article["url"]

        # DATE OBLIGATOIRE POUR READYBOT
        SubElement(
            item,
            "pubDate"
        ).text = (
            article.get("pubDate")
            or now
        )

        # Description
        SubElement(
            item,
            "description"
        ).text = (
            article.get("description")
            or
            article["title"]
        )
    # --------------------------------------------------------
    # RSS COMPLET
    # --------------------------------------------------------

    else:

        atom_link = SubElement(
            channel,
            f"{{{ATOM_NS}}}link"
        )

        atom_link.set(
            "href",
            feed_url
        )

        atom_link.set(
            "rel",
            "self"
        )

        atom_link.set(
            "type",
            "application/rss+xml"
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
                    "isPermaLink": "true"
                }
            ).text = article["url"]

            if article.get("pubDate"):

                SubElement(
                    item,
                    "pubDate"
                ).text = article["pubDate"]

            SubElement(
                item,
                "description"
            ).text = (
                article.get("description")
                or article["title"]
            )

            if include_content:

                content = article.get(
                    "content",
                    ""
                )

                if content:

                    content_element = SubElement(
                        item,
                        f"{{{CONTENT_NS}}}encoded"
                    )

                    content_element.text = content

    # --------------------------------------------------------
    # ECRITURE
    # --------------------------------------------------------

    tree = ElementTree(rss)

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
# RSS COMPLET : 20 ARTICLES
# ============================================================

print("")
print("########################################")
print("# Génération du RSS complet")
print("########################################")

create_rss(
    OUTPUT,
    "Call of Duty — Actualités françaises",
    "Actualités, annonces et notes de correctif officielles Call of Duty en français.",
    "https://shynen.github.io/tensho-cod-rss/cod.rss",
    processed_articles,
    include_content=True
)

print(
    f"🟢 {len(processed_articles)} articles "
    f"écrits dans {OUTPUT}"
)


# ============================================================
# RSS DISCORD : 1 SEUL ARTICLE
# ============================================================

print("")
print("########################################")
print("# Génération du RSS Discord")
print("########################################")

discord_articles = []

if processed_articles:

    discord_articles = [
        processed_articles[0]
    ]

# ------------------------------------------------------------
# IMPORTANT :
# Pas de content:encoded pour Readybot.
# ------------------------------------------------------------

create_rss(
    DISCORD_OUTPUT,
    "Call of Duty Actualités",
    "Dernières actualités Call of Duty.",
    "https://shynen.github.io/tensho-cod-rss/cod-discord.xml",
    discord_articles,
    include_content=False,
    minimal=True
)

print(
    "🟢 Flux Discord généré : "
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
