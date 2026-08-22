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

FEED_URL = "https://shynen.github.io/tensho-cod-rss/cod.rss"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; TenshoCODRSS/1.0)"
}


# ============================================================
# NAMESPACES RSS
# ============================================================

CONTENT_NS = "http://purl.org/rss/1.0/modules/content/"
ATOM_NS = "http://www.w3.org/2005/Atom"

register_namespace("content", CONTENT_NS)
register_namespace("atom", ATOM_NS)


# ============================================================
# ARGOS TRANSLATE
# ============================================================

def setup_translation():

    print("========================================")
    print("Préparation de la traduction EN -> FR")
    print("========================================")

    try:
        argostranslate.package.update_package_index()
    except Exception as e:
        print(f"Impossible de mettre à jour l'index Argos : {e}")

    installed_languages = (
        argostranslate.translate.get_installed_languages()
    )

    english_language = None

    for language in installed_languages:
        if language.code == "en":
            english_language = language
            break

    if english_language:

        for translation in english_language.translations_from:

            if translation.to_lang.code == "fr":

                print("Modèle EN -> FR déjà installé.")
                return

    print("Modèle EN -> FR absent.")
    print("Recherche du modèle Argos...")

    packages = argostranslate.package.get_available_packages()

    package = None

    for candidate in packages:

        if (
            candidate.from_code == "en"
            and candidate.to_code == "fr"
        ):
            package = candidate
            break

    if package is None:

        raise RuntimeError(
            "Impossible de trouver le modèle Argos EN -> FR."
        )

    print("Téléchargement du modèle EN -> FR...")

    argostranslate.package.install_from_path(
        package.download()
    )

    print("Modèle EN -> FR installé.")


# ============================================================
# TRADUCTION D'UN TEXTE
# ============================================================

def translate_text(text):

    if not text:
        return text

    text = text.strip()

    if not text:
        return text

    try:

        translated = argostranslate.translate.translate(
            text,
            "en",
            "fr"
        )

        if translated:
            return translated

    except Exception as e:

        print(
            f"Erreur pendant la traduction : {e}"
        )

    return text


# ============================================================
# DÉTECTION SIMPLE DE L'ANGLAIS
# ============================================================

ENGLISH_WORDS = {
    "the",
    "and",
    "you",
    "your",
    "with",
    "for",
    "from",
    "this",
    "that",
    "these",
    "those",
    "everything",
    "know",
    "open",
    "beta",
    "season",
    "update",
    "new",
    "coming",
    "available",
    "details",
    "about",
    "what",
    "when",
    "where",
    "will",
    "how",
    "play",
    "game",
    "games",
    "content",
    "multiplayer",
    "campaign",
    "weapons",
    "weapon",
    "operator",
    "launch",
    "weekend",
    "intel",
    "event",
    "events",
    "rewards",
    "reward",
    "battle",
    "pass",
    "store",
    "players",
    "player",
    "system",
    "systems",
    "feature",
    "features",
    "seasonal",
    "community",
    "coming",
    "soon",
    "first",
    "second",
    "third",
    "early",
    "access",
    "everything",
    "need",
    "learn",
    "introducing",
    "overview",
    "reveal",
    "revealed",
    "announcement",
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

    matches = 0

    for word in words:

        if word in ENGLISH_WORDS:
            matches += 1

    # Quelques mots anglais évidents
    if matches >= 2:
        return True

    # Cas d'un titre court du type :
    # "Modern Warfare 4 Open Beta"
    obvious_phrases = [
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

    lower_text = text.lower()

    for phrase in obvious_phrases:

        if phrase in lower_text:
            return True

    return False


# ============================================================
# TRADUCTION DU HTML
# ============================================================

def translate_html(html_content):

    if not html_content:
        return ""

    soup = BeautifulSoup(
        html_content,
        "html.parser"
    )

    ignored_tags = {
        "script",
        "style",
        "code",
        "pre"
    }

    text_nodes = list(
        soup.find_all(string=True)
    )

    for node in text_nodes:

        parent = node.parent

        if parent is not None:

            if parent.name in ignored_tags:
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

        if translated and translated != stripped:

            # Conservation des espaces autour du texte
            prefix = text[
                :len(text) - len(text.lstrip())
            ]

            suffix = text[
                len(text.rstrip()):
            ]

            node.replace_with(
                prefix
                + translated
                + suffix
            )

    return str(soup)


# ============================================================
# EXTRACTION DU CONTENU D'UN ARTICLE
# ============================================================

def fetch_article(url):

    print()
    print("----------------------------------------")
    print(f"Article : {url}")
    print("----------------------------------------")

    try:

        response = requests.get(
            url,
            headers=HEADERS,
            timeout=30
        )

        response.raise_for_status()

    except Exception as e:

        print(
            f"Impossible de récupérer l'article : {e}"
        )

        return None

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

    content = None

    # On privilégie <article>
    content = soup.find("article")

    # Puis différentes structures possibles
    if content is None:

        selectors = [
            "main",
            "[role='main']",
            ".article-content",
            ".blog-content",
            ".content"
        ]

        for selector in selectors:

            content = soup.select_one(
                selector
            )

            if content is not None:
                break

    # Dernier recours
    if content is None:

        content = soup.body

    if content is None:

        return {
            "title": title,
            "description": description,
            "content": ""
        }

    # --------------------------------------------------------
    # NETTOYAGE
    # --------------------------------------------------------

    for tag in content.find_all([
        "script",
        "style",
        "noscript"
    ]):

        tag.decompose()

    content_html = str(content)

    # --------------------------------------------------------
    # TRADUCTION DU TITRE
    # --------------------------------------------------------

    if looks_english(title):

        print(
            f"Titre anglais détecté : {title}"
        )

        title = translate_text(
            title
        )

        print(
            f"Titre français : {title}"
        )

    else:

        print(
            f"Titre déjà français : {title}"
        )

    # --------------------------------------------------------
    # TRADUCTION DE LA DESCRIPTION
    # --------------------------------------------------------

    if description:

        if looks_english(description):

            print(
                "Description anglaise détectée."
            )

            description = translate_text(
                description
            )

    # --------------------------------------------------------
    # TRADUCTION DU CONTENU
    # --------------------------------------------------------

    plain_content = content.get_text(
        " ",
        strip=True
    )

    # On regarde une partie assez importante
    # pour déterminer la langue
    sample = plain_content[:5000]

    if looks_english(sample):

        print(
            "Contenu anglais détecté -> traduction."
        )

        content_html = translate_html(
            content_html
        )

    else:

        print(
            "Contenu déjà français."
        )

    return {
        "title": title,
        "description": description,
        "content": content_html
    }


# ============================================================
# RÉCUPÉRATION DES ARTICLES DU BLOG
# ============================================================

def get_articles():

    print()
    print("========================================")
    print("Téléchargement du blog Call of Duty")
    print("========================================")

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

    # Même logique que le script original
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

        # ----------------------------------------------------
        # Recherche d'une date
        # ----------------------------------------------------

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

    # Même limite que le script original
    articles = articles[:20]

    print()
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

    month_name = match.group(1).lower()
    day = int(match.group(2))
    year = int(match.group(3))

    month = months.get(
        month_name
    )

    if not month:
        return None

    try:

        date = datetime(
            year,
            month,
            day,
            tzinfo=timezone.utc
        )

        return formatdate(
            date.timestamp(),
            usegmt=True
        )

    except Exception:
        return None


# ============================================================
# GÉNÉRATION DU RSS
# ============================================================

def generate_feed(articles):

    print()
    print("========================================")
    print("Génération du RSS")
    print("========================================")

    rss = Element(
        "rss",
        {
            "version": "2.0",
            "xmlns:atom": ATOM_NS,
            "xmlns:content": CONTENT_NS
        }
    )

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

    # ========================================================
    # ARTICLES
    # ========================================================

    successful = 0

    for article in articles:

        data = fetch_article(
            article["url"]
        )

        if data is None:
            continue

        item = SubElement(
            channel,
            "item"
        )

        # ----------------------------------------------------
        # TITRE
        # ----------------------------------------------------

        SubElement(
            item,
            "title"
        ).text = data["title"]

        # ----------------------------------------------------
        # LIEN
        # ----------------------------------------------------

        SubElement(
            item,
            "link"
        ).text = article["url"]

        # ----------------------------------------------------
        # GUID
        # ----------------------------------------------------

        SubElement(
            item,
            "guid",
            {
                "isPermaLink": "true"
            }
        ).text = article["url"]

        # ----------------------------------------------------
        # DATE
        # ----------------------------------------------------

        rss_date = convert_date(
            article["date"]
        )

        if rss_date:

            SubElement(
                item,
                "pubDate"
            ).text = rss_date

        # ----------------------------------------------------
        # DESCRIPTION
        # ----------------------------------------------------

        description = (
            data["description"]
            or
            f"Nouvelle publication officielle Call of Duty : "
            f"{data['title']}"
        )

        SubElement(
            item,
            "description"
        ).text = description

        # ----------------------------------------------------
        # CONTENU COMPLET
        # ----------------------------------------------------

        if data["content"]:

            content_element = SubElement(
                item,
                f"{{{CONTENT_NS}}}encoded"
            )

            content_element.text = (
                data["content"]
            )

        successful += 1

    # ========================================================
    # ÉCRITURE
    # ========================================================

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
    print("========================================")
    print(
        f"✅ {successful} articles générés"
    )
    print(
        f"✅ Fichier : {OUTPUT}"
    )
    print("========================================")


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    print()
    print("########################################")
    print("# Tensho COD RSS")
    print("# Traduction automatique EN -> FR")
    print("########################################")
    print()

    setup_translation()

    articles = get_articles()

    if not articles:

        raise RuntimeError(
            "Aucun article trouvé sur le blog Call of Duty."
        )

    generate_feed(
        articles
    )

    print()
    print("Terminé.")
