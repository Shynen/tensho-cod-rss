import re
import html
import requests
from bs4 import BeautifulSoup
from email.utils import formatdate
from datetime import datetime, timezone
from urllib.parse import urljoin
from xml.etree.ElementTree import Element, SubElement, ElementTree, indent

BASE_URL = "https://www.callofduty.com"
BLOG_URL = "https://www.callofduty.com/fr/blog?count=50"
OUTPUT = "cod.xml"

headers = {
    "User-Agent": "Mozilla/5.0 (compatible; TenshoCODRSS/1.0)"
}

response = requests.get(BLOG_URL, headers=headers, timeout=30)
response.raise_for_status()

soup = BeautifulSoup(response.text, "html.parser")

articles = []
seen = set()

pattern = re.compile(r"^/fr/blog/\d{4}/")

for link in soup.find_all("a", href=True):
    href = link["href"]

    if not pattern.match(href):
        continue

    url = urljoin(BASE_URL, href)

    if url in seen:
        continue

    title = link.get_text(" ", strip=True)

    if not title or len(title) < 8:
        continue

    seen.add(url)

    # Recherche d'une date dans le bloc parent
    parent = link
    date_text = ""

    for _ in range(5):
        parent = parent.parent
        if parent is None:
            break

        text = parent.get_text(" ", strip=True)

        match = re.search(
            r"(janvier|février|mars|avril|mai|juin|juillet|août|septembre|octobre|novembre|décembre)\s+\d{1,2},?\s+\d{4}",
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

# Limite aux 20 articles les plus récents trouvés
articles = articles[:20]

rss = Element(
    "rss",
    {
        "version": "2.0",
        "xmlns:atom": "http://www.w3.org/2005/Atom"
    }
)

channel = SubElement(rss, "channel")

SubElement(channel, "title").text = "Call of Duty — Actualités FR"
SubElement(channel, "link").text = BLOG_URL
SubElement(channel, "description").text = (
    "Actualités, annonces et patch notes officiels Call of Duty en français."
)

SubElement(
    channel,
    "atom:link",
    {
        "href": "https://shynen.github.io/tensho-cod-rss/cod.xml",
        "rel": "self",
        "type": "application/rss+xml"
    }
)

now = formatdate(datetime.now(timezone.utc).timestamp(), usegmt=True)
SubElement(channel, "lastBuildDate").text = now

for article in articles:
    item = SubElement(channel, "item")

    SubElement(item, "title").text = article["title"]
    SubElement(item, "link").text = article["url"]
    SubElement(item, "guid", {"isPermaLink": "true"}).text = article["url"]

    if article["date"]:
        SubElement(item, "pubDate").text = article["date"]

    SubElement(
        item,
        "description"
    ).text = f"Nouvelle publication officielle Call of Duty : {article['title']}"

tree = ElementTree(rss)
indent(tree, space="  ")
tree.write(OUTPUT, encoding="utf-8", xml_declaration=True)

print(f"{len(articles)} articles ajoutés dans {OUTPUT}")
