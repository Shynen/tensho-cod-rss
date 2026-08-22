import re
import html
import requests

from bs4 import BeautifulSoup
from urllib.parse import urljoin
from xml.etree.ElementTree import Element, SubElement, ElementTree, indent
from datetime import datetime, timezone

import argostranslate.package
import argostranslate.translate


BASE_URL = "https://www.callofduty.com"
BLOG_URL = "https://www.callofduty.com/fr/blog?count=50"

OUTPUT = "cod.xml"
FEED_URL = "https://shynen.github.io/tensho-cod-rss/cod.xml"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; TenshoCODRSS/1.0)"
}


# =========================================================
# ARGOS TRANSLATE
# =========================================================

def setup_translation():

    print("Recherche du modèle anglais → français...")

    argostranslate.package.update_package_index()

    installed = argostranslate.translate.get_installed_languages()

    for lang in installed:
        if lang.code == "en":
            for translation in lang.translations_from:
                if translation.to_lang.code == "fr":
                    print("Modèle EN → FR déjà installé.")
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
        raise RuntimeError("Modèle Argos EN → FR introuvable.")

    print("Téléchargement du modèle EN → FR...")

    argostranslate.package.install_from_path(
        package.download()
    )

    print("Modèle EN → FR installé.")


def translate_text(text):

    if not text or not text.strip():
        return text

    text = text.strip()

    try:
        result = argostranslate.translate.translate(
            text,
            "en",
            "fr"
        )

        return result

    except Exception as e:
        print(f"Erreur traduction : {e}")
        return text


# =========================================================
# DÉTECTION ANGLAIS
# =========================================================

def looks_english(text):

    if not text:
        return False

    text_lower = text.lower()

    english_words = {
        "the",
        "and",
        "you",
        "your",
        "with",
        "for",
        "from",
        "this",
        "that",
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
        "we",
        "will",
        "get",
        "play",
        "game"
    }

    words = re.findall(r"\b[a-zA-Z]+\b", text_lower)

    if not words:
        return False

    matches = sum(
        1 for word in words
        if word in english_words
    )

    return matches >= 2


# =========================================================
# TRADUCTION HTML
# =========================================================

def translate_html_content(element):

    if element is None:
        return ""

    # On travaille sur une copie
    soup = BeautifulSoup(str(element), "html.parser")

    ignored = {
        "script",
        "style",
        "code",
        "pre"
    }

    for node in soup.find_all(string=True):

        parent = node.parent

        if parent and parent.name in ignored:
            continue

        text = str(node).strip()

        if not text:
            continue

        # Pas de traduction des URLs ou textes trop courts
        if len(text) < 3:
            continue

        if not looks_english(text):
            continue

        translated = translate_text(text)

        node.replace_with(
            str(node).replace(text, translated)
        )

    return str(soup)


# =========================================================
# EXTRACTION ARTICLE
# =========================================================

def fetch_article(url):

    print(f"Lecture : {url}")

    try:

        response = requests.get(
            url,
            headers=HEADERS,
            timeout=30
        )

        response.raise_for_status()

    except Exception as e:

        print(f"Impossible de récupérer {url}: {e}")

        return None

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    # -----------------------------------------------------
    # TITLE
    # -----------------------------------------------------

    title = ""

    og_title = soup.find(
        "meta",
        property="og:title"
    )

    if og_title and og_title.get("content"):
        title = og_title["content"].strip()

    if not title and soup.title:
        title = soup.title.get_text(
            " ",
            strip=True
        )

    # -----------------------------------------------------
    # DESCRIPTION
    # -----------------------------------------------------

    description = ""

    og_description = soup.find(
        "meta",
        property="og:description"
    )

    if og_description and og_description.get("content"):
        description = og_description["content"].strip()

    # -----------------------------------------------------
    # CONTENU
    # -----------------------------------------------------

    content = None

    # On privilégie article
    content = soup.find("article")

    # Puis les principaux conteneurs possibles
    if content is None:
        for selector in [
            "main",
            "[role='main']",
            ".article-content",
            ".blog-content",
            ".content"
        ]:

            content = soup.select_one(selector)

            if content is not None:
                break

    if content is None:
        content = soup.body

    if content is None:
        return None

    # Supprime les éléments inutiles
    for tag in content.find_all([
        "script",
        "style",
        "noscript"
    ]):
        tag.decompose()

    # -----------------------------------------------------
    # TRADUCTION
    # -----------------------------------------------------

    if looks_english(title):

        print(f"  → Titre anglais détecté : {title}")

        title = translate_text(title)

        print(f"  → Titre FR : {title}")

    if description and looks_english(description):

        print("  → Description anglaise détectée")

        description = translate_text(
            description
        )

    content_html = str(content)

    if looks_english(
        content.get_text(" ", strip=True)[:2000]
    ):

        print("  → Contenu anglais détecté")

        content_html = translate_html_content(
            content
        )

    else:

        print("  → Contenu déjà français")

    return {
        "title": title,
        "description": description,
        "content": content_html
    }


# =========================================================
# RÉCUPÉRATION DU BLOG
# =========================================================

def get_articles():

    print("Téléchargement du blog Call of Duty...")

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

        href = link["href"].strip()

        if not pattern.match(href):
            continue

        url = urljoin(
            BASE_URL,
            href
        )

        if url in seen:
            continue

        seen.add(url)

        title = link.get_text(
            " ",
            strip=True
        )

        if not title or len(title) < 8:
            continue

        articles.append({
            "url": url,
            "title": title
        })

    return articles[:15]


# =========================================================
# GÉNÉRATION ATOM
# =========================================================

def generate_feed(articles):

    ATOM_NS = (
        "http://www.w3.org/2005/Atom"
    )

    feed = Element(
        f"{{{ATOM_NS}}}feed",
        {
            "xml:lang": "fr-fr"
        }
    )

    SubElement(
        feed,
        f"{{{ATOM_NS}}}id"
    ).text = FEED_URL

    SubElement(
        feed,
        f"{{{ATOM_NS}}}title"
    ).text = (
        "Call of Duty — Actualités françaises"
    )

    SubElement(
        feed,
        f"{{{ATOM_NS}}}updated"
    ).text = datetime.now(
        timezone.utc
    ).isoformat()

    SubElement(
        feed,
        f"{{{ATOM_NS}}}link",
        {
            "href":
                "https://www.callofduty.com/fr/blog",
            "rel": "alternate",
            "type": "text/html"
        }
    )

    SubElement(
        feed,
        f"{{{ATOM_NS}}}link",
        {
            "href": FEED_URL,
            "rel": "self",
            "type": "application/atom+xml"
        }
    )

    for article in articles:

        data = fetch_article(
            article["url"]
        )

        if data is None:
            continue

        timestamp = datetime.now(
            timezone.utc
        ).isoformat()

        entry = SubElement(
            feed,
            f"{{{ATOM_NS}}}entry"
        )

        SubElement(
            entry,
            f"{{{ATOM_NS}}}id"
        ).text = article["url"]

        SubElement(
            entry,
            f"{{{ATOM_NS}}}title"
        ).text = data["title"]

        SubElement(
            entry,
            f"{{{ATOM_NS}}}link",
            {
                "href": article["url"],
                "rel": "alternate",
                "type": "text/html"
            }
        )

        SubElement(
            entry,
            f"{{{ATOM_NS}}}category",
            {
                "term": "News"
            }
        )

        SubElement(
            entry,
            f"{{{ATOM_NS}}}published"
        ).text = timestamp

        SubElement(
            entry,
            f"{{{ATOM_NS}}}updated"
        ).text = timestamp

        author = SubElement(
            entry,
            f"{{{ATOM_NS}}}author"
        )

        SubElement(
            author,
            f"{{{ATOM_NS}}}name"
        ).text = "Call of Duty"

        SubElement(
            entry,
            f"{{{ATOM_NS}}}content",
            {
                "type": "html"
            }
        ).text = data["content"]

        SubElement(
            entry,
            f"{{{ATOM_NS}}}summary"
        ).text = (
            data["description"]
            or data["title"]
        )

    tree = ElementTree(feed)

    indent(
        tree,
        space="  "
    )

    tree.write(
        OUTPUT,
        encoding="utf-8",
        xml_declaration=True
    )

    print(
        f"Flux Atom généré : {OUTPUT}"
    )


# =========================================================
# MAIN
# =========================================================

if __name__ == "__main__":

    setup_translation()

    articles = get_articles()

    print(
        f"{len(articles)} articles trouvés."
    )

    generate_feed(articles)
