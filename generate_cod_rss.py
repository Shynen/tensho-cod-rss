import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from xml.etree.ElementTree import Element, SubElement, ElementTree, indent
from datetime import datetime, timezone

BASE_URL = "https://www.callofduty.com"
BLOG_URL = "https://www.callofduty.com/fr/blog?count=50"
OUTPUT = "cod.xml"
FEED_URL = "https://shynen.github.io/tensho-cod-rss/cod.xml"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; TenshoCODRSS/1.0)"
}


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def main():

    print("Téléchargement du blog Call of Duty...")

    response = requests.get(
        BLOG_URL,
        headers=HEADERS,
        timeout=30
    )

    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    articles = []
    seen = set()

    pattern = re.compile(r"^/fr/blog/\d{4}/")

    for link in soup.find_all("a", href=True):

        href = link["href"].strip()

        if not pattern.match(href):
            continue

        url = urljoin(BASE_URL, href)

        if url in seen:
            continue

        title = link.get_text(" ", strip=True)

        if not title or len(title) < 8:
            continue

        seen.add(url)

        # Cherche un résumé éventuel dans le bloc parent
        summary = ""

        parent = link

        for _ in range(4):

            parent = parent.parent

            if parent is None:
                break

            text = parent.get_text(" ", strip=True)

            if len(text) > len(title) + 20:
                summary = text
                break

        if not summary:
            summary = title

        articles.append({
            "title": title,
            "url": url,
            "summary": summary
        })

    # Limite aux 30 dernières entrées trouvées
    articles = articles[:30]

    print(f"{len(articles)} articles trouvés.")

    # =====================================================
    # ATOM
    # =====================================================

    ATOM_NS = "http://www.w3.org/2005/Atom"

    feed = Element(
        f"{{{ATOM_NS}}}feed",
        {
            "xml:lang": "fr-fr"
        }
    )

    # ID du flux
    SubElement(
        feed,
        f"{{{ATOM_NS}}}id"
    ).text = FEED_URL

    # Titre
    SubElement(
        feed,
        f"{{{ATOM_NS}}}title"
    ).text = "Call of Duty — Actualités françaises"

    # Date de mise à jour
    SubElement(
        feed,
        f"{{{ATOM_NS}}}updated"
    ).text = now_iso()

    # Lien vers le site officiel
    SubElement(
        feed,
        f"{{{ATOM_NS}}}link",
        {
            "href": "https://www.callofduty.com/fr/blog",
            "rel": "alternate",
            "type": "text/html"
        }
    )

    # Lien du flux lui-même
    SubElement(
        feed,
        f"{{{ATOM_NS}}}link",
        {
            "href": FEED_URL,
            "rel": "self",
            "type": "application/atom+xml"
        }
    )

    # =====================================================
    # ENTRÉES
    # =====================================================

    for article in articles:

        entry = SubElement(
            feed,
            f"{{{ATOM_NS}}}entry"
        )

        # ID unique basé sur l'URL
        SubElement(
            entry,
            f"{{{ATOM_NS}}}id"
        ).text = article["url"]

        # Titre
        SubElement(
            entry,
            f"{{{ATOM_NS}}}title"
        ).text = article["title"]

        # URL
        SubElement(
            entry,
            f"{{{ATOM_NS}}}link",
            {
                "href": article["url"],
                "rel": "alternate",
                "type": "text/html"
            }
        )

        # Catégorie
        SubElement(
            entry,
            f"{{{ATOM_NS}}}category",
            {
                "term": "News"
            }
        )

        # Date
        timestamp = now_iso()

        SubElement(
            entry,
            f"{{{ATOM_NS}}}published"
        ).text = timestamp

        SubElement(
            entry,
            f"{{{ATOM_NS}}}updated"
        ).text = timestamp

        # Auteur
        author = SubElement(
            entry,
            f"{{{ATOM_NS}}}author"
        )

        SubElement(
            author,
            f"{{{ATOM_NS}}}name"
        ).text = "Call of Duty"

        # Contenu
        SubElement(
            entry,
            f"{{{ATOM_NS}}}content",
            {
                "type": "html"
            }
        ).text = (
            f"<p>{article['summary']}</p>"
            f"<p><a href=\"{article['url']}\">"
            f"Lire l'article officiel"
            f"</a></p>"
        )

        # Résumé
        SubElement(
            entry,
            f"{{{ATOM_NS}}}summary"
        ).text = article["summary"]

    # =====================================================
    # ÉCRITURE
    # =====================================================

    tree = ElementTree(feed)

    indent(tree, space="  ")

    tree.write(
        OUTPUT,
        encoding="utf-8",
        xml_declaration=True
    )

    print(f"Flux Atom généré : {OUTPUT}")


if __name__ == "__main__":
    main()
