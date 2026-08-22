import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from xml.etree.ElementTree import Element, SubElement, ElementTree, indent

BASE_URL = "https://www.callofduty.com"
BLOG_URL = "https://www.callofduty.com/fr/blog?count=50"
OUTPUT = "cod.rss"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; TenshoCODRSS/1.0)"
}


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

    # URLs des articles français Call of Duty
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

        articles.append({
            "title": title,
            "url": url
        })

    # Maximum 30 articles
    articles = articles[:30]

    print(f"{len(articles)} articles trouvés.")

    # -------------------------------------------------
    # Création du RSS 2.0
    # -------------------------------------------------

    rss = Element(
        "rss",
        {
            "version": "2.0",
            "xmlns:atom": "http://www.w3.org/2005/Atom"
        }
    )

    channel = SubElement(rss, "channel")

    SubElement(channel, "title").text = (
        "Call of Duty — Actualités françaises"
    )

    SubElement(channel, "link").text = BLOG_URL

    SubElement(channel, "description").text = (
        "Actualités, annonces et notes de correctif "
        "officielles Call of Duty en français."
    )

    SubElement(
        channel,
        "atom:link",
        {
            "href": "https://shynen.github.io/tensho-cod-rss/cod.rss",
            "rel": "self",
            "type": "application/rss+xml"
        }
    )

    # -------------------------------------------------
    # Articles
    # -------------------------------------------------

    for article in articles:

        item = SubElement(channel, "item")

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

        SubElement(
            item,
            "description"
        ).text = (
            f"Nouvelle publication officielle Call of Duty : "
            f"{article['title']}"
        )

    # -------------------------------------------------
    # Écriture du XML
    # -------------------------------------------------

    tree = ElementTree(rss)

    indent(tree, space="  ")

    tree.write(
        OUTPUT,
        encoding="utf-8",
        xml_declaration=True
    )

    print(f"Flux RSS généré : {OUTPUT}")


if __name__ == "__main__":
    main()
