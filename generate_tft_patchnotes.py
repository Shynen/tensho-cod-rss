import json
import os
import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from email.utils import formatdate
from urllib.parse import urljoin
from xml.etree.ElementTree import Element, SubElement, ElementTree, indent
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/149.0 Safari/537.36",
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
}

def clean_text(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()

def parse_date(value):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(clean_text(value).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None

def format_pubdate(dt):
    return formatdate(dt.timestamp(), usegmt=True)

def load_cache(path):
    if not os.path.exists(path):
        print("Aucun cache trouvé.")
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        print(f"Cache chargé : {len(data)} articles.")
        return data if isinstance(data, dict) else {}
    except Exception as e:
        print(f"⚠️ Erreur cache : {e}")
        return {}

def save_cache(path, cache):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

def extract_article(page_soup, url, cache):
    title = ""
    h1 = page_soup.find("h1")
    if h1:
        title = clean_text(h1.get_text(" ", strip=True))
    if not title:
        meta = page_soup.find("meta", attrs={"property": "og:title"})
        if meta:
            title = clean_text(meta.get("content"))
    if not title:
        title = url.rstrip("/").split("/")[-1].replace("-", " ").strip().title()

    dt = None
    for script in page_soup.find_all("script", type="application/ld+json"):
        raw = script.string or script.get_text()
        for value in re.findall(r'"datePublished"\s*:\s*"([^"]+)"', raw or ""):
            dt = parse_date(value)
            if dt:
                break
        if dt:
            break

    if not dt:
        for attrs in [{"property": "article:published_time"}, {"property": "og:published_time"}]:
            meta = page_soup.find("meta", attrs=attrs)
            if meta:
                dt = parse_date(meta.get("content"))
                if dt:
                    break

    if not dt:
        for node in page_soup.find_all("time"):
            dt = parse_date(node.get("datetime"))
            if dt:
                break

    if not dt and url in cache:
        dt = parse_date(cache[url].get("pubDate"))

    if not dt:
        return None

    description = ""
    meta = page_soup.find("meta", attrs={"name": "description"})
    if meta:
        description = clean_text(meta.get("content"))
    if not description:
        meta = page_soup.find("meta", attrs={"property": "og:description"})
        if meta:
            description = clean_text(meta.get("content"))
    if not description:
        description = title

    return {"title": title, "url": url, "description": description, "date": dt}

def create_rss(filename, title, link, description, articles):
    now = formatdate(datetime.now(timezone.utc).timestamp(), usegmt=True)
    rss = Element("rss", {"version": "2.0"})
    channel = SubElement(rss, "channel")
    SubElement(channel, "title").text = title
    SubElement(channel, "link").text = link
    SubElement(channel, "description").text = description
    SubElement(channel, "lastBuildDate").text = now

    for article in articles:
        item = SubElement(channel, "item")
        SubElement(item, "title").text = article["title"]
        SubElement(item, "link").text = article["url"]
        SubElement(item, "guid", {"isPermaLink": "true"}).text = article["url"]
        SubElement(item, "pubDate").text = format_pubdate(article["date"])
        SubElement(item, "description").text = article["description"]

    tree = ElementTree(rss)
    indent(tree, space="  ")
    tree.write(filename, encoding="utf-8", xml_declaration=True)

def scrape_patch_urls(source_url, allowed_host, url_regex, max_articles=20, max_clicks=8):
    print("")
    print("========================================")
    print("Ouverture avec Playwright :")
    print(source_url)
    print("========================================")

    urls = set()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(locale="fr-FR", user_agent=HEADERS["User-Agent"])
        try:
            page.goto(source_url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(3000)
        except Exception as e:
            print(f"❌ Erreur ouverture page : {e}")
            browser.close()
            return []

        def collect():
            links = page.locator('a[href*="/fr-fr/news/game-updates/"]')
            before = len(urls)
            for i in range(links.count()):
                try:
                    href = links.nth(i).get_attribute("href")
                    if not href:
                        continue
                    full = urljoin(source_url, href).rstrip("/")
                    if allowed_host in full.lower() and re.search(url_regex, full.lower()):
                        urls.add(full)
                except Exception:
                    pass
            return len(urls) - before

        collect()
        print(f"Premier lot : {len(urls)} Patch Notes détectées.")

        for n in range(1, max_clicks + 1):
            if len(urls) >= max_articles:
                break
            print(f"🔄 Recherche du bouton VOIR PLUS ({n}/{max_clicks})...")
            buttons = page.get_by_text("VOIR PLUS", exact=True)
            clicked = False
            for i in range(buttons.count()):
                try:
                    b = buttons.nth(i)
                    if b.is_visible():
                        b.scroll_into_view_if_needed()
                        page.wait_for_timeout(400)
                        b.click(timeout=10000)
                        clicked = True
                        print("🟢 VOIR PLUS cliqué.")
                        break
                except Exception:
                    pass
            if not clicked:
                print("ℹ️ Plus de bouton VOIR PLUS.")
                break
            page.wait_for_timeout(2200)
            try:
                page.wait_for_load_state("networkidle", timeout=8000)
            except PlaywrightTimeoutError:
                pass
            added = collect()
            print(f"Patch Notes actuellement trouvées : {len(urls)} (+{added})")
            if added == 0:
                break

        browser.close()

    print(f"🟢 Total Patch Notes récupérées : {len(urls)}")
    return list(urls)

BASE_URL = "https://teamfighttactics.leagueoflegends.com"
SOURCE_URL = "https://teamfighttactics.leagueoflegends.com/fr-fr/news/game-updates/"
OUTPUT = "tft-patchnotes.xml"
DISCORD_OUTPUT = "tft-patchnotes-discord.xml"
CACHE_FILE = "tft_patchnotes_cache.json"
MAX_PATCHNOTES = 20

print("")
print("########################################")
print("# Tensho Teamfight Tactics")
print("# PATCH NOTES FRANÇAISES")
print("########################################")

cache = load_cache(CACHE_FILE)

all_urls = set(scrape_patch_urls(
    SOURCE_URL,
    "teamfighttactics.leagueoflegends.com",
    r"/teamfight-tactics-patch-\d+-\d+$|/teamfight-tactics-patch-\d+-\d+-notes$",
    MAX_PATCHNOTES,
))

print("")
print("########################################")
print(f"# URLs Patch Notes TFT trouvées : {len(all_urls)}")
print("########################################")

for url in sorted(all_urls):
    print(f"🟢 TFT : {url}")

session = requests.Session()
session.headers.update(HEADERS)
articles = []

for index, url in enumerate(all_urls, 1):
    print(f"\n[{index}/{len(all_urls)}] {url}")
    try:
        r = session.get(url, timeout=30)
        r.raise_for_status()
        article = extract_article(BeautifulSoup(r.text, "html.parser"), url, cache)
    except Exception as e:
        print(f"⚠️ Erreur : {e}")
        continue

    if article:
        articles.append(article)
        print(f"🟢 {format_pubdate(article['date'])} - {article['title']}")

unique = {a["url"]: a for a in articles}
articles = sorted(unique.values(), key=lambda a: a["date"], reverse=True)[:MAX_PATCHNOTES]

print("")
print("########################################")
print(f"# {len(articles)} Patch Notes TFT retenues")
print("########################################")
for i, a in enumerate(articles, 1):
    print(f"{i:02d}. {format_pubdate(a['date'])} - {a['title']}")

for a in articles:
    cache[a["url"]] = {
        "title": a["title"],
        "description": a["description"],
        "pubDate": format_pubdate(a["date"]),
    }
save_cache(CACHE_FILE, cache)

print("\nGénération de tft-patchnotes.xml...")
create_rss(
    OUTPUT,
    "Teamfight Tactics — Patch Notes",
    SOURCE_URL,
    "Notes de patch officielles françaises de Teamfight Tactics.",
    articles,
)
print("🟢 tft-patchnotes.xml généré.")

print("Génération de tft-patchnotes-discord.xml...")
create_rss(
    DISCORD_OUTPUT,
    "Teamfight Tactics — Patch Notes",
    SOURCE_URL,
    "Dernière note de patch officielle française de Teamfight Tactics.",
    articles[:1],
)
print("🟢 tft-patchnotes-discord.xml généré.")

print("")
print("########################################")
print("# TFT PATCH NOTES RSS TERMINÉ")
print("########################################")
