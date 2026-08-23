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

BASE_URL = "https://www.leagueoflegends.com"
SOURCE_URL = "https://www.leagueoflegends.com/fr-fr/news/game-updates/"
OUTPUT = "lol-patchnotes.xml"
DISCORD_OUTPUT = "lol-patchnotes-discord.xml"
CACHE_FILE = "lol_patchnotes_cache.json"
MAX_PATCHNOTES = 20
MAX_LOAD_MORE_CLICKS = 8

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/149.0 Safari/537.36",
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
}

print("")
print("########################################")
print("# Tensho League of Legends")
print("# PATCH NOTES FRANÇAISES")
print("########################################")
print("")

def load_cache():
    if not os.path.exists(CACHE_FILE):
        print("Aucun cache Patch Notes LoL trouvé.")
        return {}
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {}
        print(f"Cache Patch Notes LoL chargé : {len(data)} articles.")
        return data
    except Exception as e:
        print(f"⚠️ Erreur lecture cache : {e}")
        return {}

def save_cache(cache):
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

def clean_text(value):
    if not value:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()

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
    
def is_patch_url(url):
    value = url.lower()

    # ========================================================
    # SÉPARATION STRICTE LOL / TFT
    # Ce script ne doit accepter QUE les Patch Notes LoL.
    # Les Patch Notes TFT sont gérées par generate_tft_patchnotes.py
    # ========================================================

    if "teamfighttactics.leagueoflegends.com" in value:
        return False

    if "www.leagueoflegends.com" not in value:
        return False

    if "/fr-fr/news/game-updates/" not in value:
        return False

    return bool(
        re.search(r"patch[-_]\d+[.-]\d+", value)
        or re.search(r"patch[-_]\d+[-_]\d+", value)
    )
cache = load_cache()

def collect_patch_urls():
    print("")
    print("========================================")
    print("Ouverture avec Playwright :")
    print(SOURCE_URL)
    print("========================================")

    urls = set()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(locale="fr-FR", user_agent=HEADERS["User-Agent"])

        try:
            page.goto(SOURCE_URL, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(3000)
        except Exception as e:
            print(f"❌ Erreur ouverture page : {e}")
            browser.close()
            return []

        def collect_visible_urls():
            links = page.locator('a[href*="/fr-fr/news/game-updates/"]')
            before = len(urls)
            for i in range(links.count()):
                try:
                    href = links.nth(i).get_attribute("href")
                    if not href:
                        continue
                    full_url = urljoin(BASE_URL, href).rstrip("/")
                    if is_patch_url(full_url):
                        urls.add(full_url)
                except Exception:
                    pass
            return len(urls) - before

        collect_visible_urls()
        print(f"Premier lot : {len(urls)} Patch Notes détectées.")

        for click_number in range(1, MAX_LOAD_MORE_CLICKS + 1):
            if len(urls) >= MAX_PATCHNOTES:
                break

            print(f"🔄 Recherche du bouton VOIR PLUS ({click_number}/{MAX_LOAD_MORE_CLICKS})...")
            buttons = page.get_by_text("VOIR PLUS", exact=True)

            if buttons.count() == 0:
                print("ℹ️ Plus de bouton VOIR PLUS.")
                break

            clicked = False
            for i in range(buttons.count()):
                try:
                    button = buttons.nth(i)
                    if not button.is_visible():
                        continue
                    button.scroll_into_view_if_needed()
                    page.wait_for_timeout(500)
                    button.click(timeout=10000)
                    clicked = True
                    print("🟢 VOIR PLUS cliqué.")
                    break
                except Exception:
                    pass

            if not clicked:
                print("ℹ️ Impossible de cliquer sur VOIR PLUS.")
                break

            page.wait_for_timeout(2500)
            try:
                page.wait_for_load_state("networkidle", timeout=10000)
            except PlaywrightTimeoutError:
                pass

            added = collect_visible_urls()
            print(f"Patch Notes actuellement trouvées : {len(urls)} (+{added})")
            if added == 0:
                print("ℹ️ Aucun nouveau Patch Note chargé.")
                break

        browser.close()

    print(f"🟢 Total Patch Notes récupérées : {len(urls)}")
    return list(urls)

all_urls = set(collect_patch_urls())

print("")
print("########################################")
print(f"# URLs Patch Notes trouvées : {len(all_urls)}")
print("########################################")

for url in sorted(all_urls):
    print(f"🟢 Patch trouvé : {url}")

articles = []
session = requests.Session()
session.headers.update(HEADERS)

for index, url in enumerate(all_urls, start=1):
    print("")
    print(f"[{index}/{len(all_urls)}] {url}")

    try:
        response = session.get(url, timeout=30)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
    except Exception as e:
        print(f"⚠️ Impossible de charger : {e}")
        continue

    title = ""
    h1 = soup.find("h1")
    if h1:
        title = clean_text(h1.get_text(" ", strip=True))

    if not title:
        meta = soup.find("meta", attrs={"property": "og:title"})
        if meta:
            title = clean_text(meta.get("content"))

    if not title:
        title = url.rstrip("/").split("/")[-1].replace("-", " ").strip().title()

    combined = (title + " " + url).lower()
    if "patch" not in combined:
        print(f"❌ Pas identifié comme Patch Note : {title}")
        continue

    dt = None

    for script in soup.find_all("script", type="application/ld+json"):
        raw = script.string or script.get_text()
        if not raw:
            continue
        for value in re.findall(r'"datePublished"\s*:\s*"([^"]+)"', raw):
            dt = parse_date(value)
            if dt:
                break
        if dt:
            break

    if not dt:
        for attrs in [
            {"property": "article:published_time"},
            {"property": "og:published_time"},
        ]:
            meta = soup.find("meta", attrs=attrs)
            if meta:
                dt = parse_date(meta.get("content"))
                if dt:
                    break

    if not dt:
        for node in soup.find_all("time"):
            dt = parse_date(node.get("datetime"))
            if dt:
                break

    if not dt and url in cache:
        dt = parse_date(cache[url].get("pubDate"))

    if not dt:
        print("⚠️ Date introuvable.")
        continue

    description = ""
    meta = soup.find("meta", attrs={"name": "description"})
    if meta:
        description = clean_text(meta.get("content"))

    if not description:
        meta = soup.find("meta", attrs={"property": "og:description"})
        if meta:
            description = clean_text(meta.get("content"))

    if not description:
        description = title

    articles.append({
        "title": title,
        "url": url,
        "description": description,
        "date": dt,
    })

    print(f"🟢 {format_pubdate(dt)} - {title}")

unique_articles = {}
for article in articles:
    url = article["url"]
    if url not in unique_articles or article["date"] > unique_articles[url]["date"]:
        unique_articles[url] = article

articles = list(unique_articles.values())
articles.sort(key=lambda article: article["date"], reverse=True)
articles = articles[:MAX_PATCHNOTES]

print("")
print("########################################")
print(f"# {len(articles)} Patch Notes retenues")
print("########################################")
print("")

for index, article in enumerate(articles, start=1):
    print(f"{index:02d}. {format_pubdate(article['date'])} - {article['title']}")

for article in articles:
    cache[article["url"]] = {
        "title": article["title"],
        "description": article["description"],
        "pubDate": format_pubdate(article["date"]),
    }

save_cache(cache)

now = formatdate(datetime.now(timezone.utc).timestamp(), usegmt=True)

def create_rss(filename, title, description, articles_to_use):
    rss = Element("rss", {"version": "2.0"})
    channel = SubElement(rss, "channel")
    SubElement(channel, "title").text = title
    SubElement(channel, "link").text = SOURCE_URL
    SubElement(channel, "description").text = description
    SubElement(channel, "lastBuildDate").text = now

    for article in articles_to_use:
        item = SubElement(channel, "item")
        SubElement(item, "title").text = article["title"]
        SubElement(item, "link").text = article["url"]
        SubElement(item, "guid", {"isPermaLink": "true"}).text = article["url"]
        SubElement(item, "pubDate").text = format_pubdate(article["date"])
        SubElement(item, "description").text = article["description"]

    tree = ElementTree(rss)
    indent(tree, space="  ")
    tree.write(filename, encoding="utf-8", xml_declaration=True)

print("")
print("Génération de lol-patchnotes.xml...")
create_rss(
    OUTPUT,
    "League of Legends — Patch Notes",
    "Notes de patch officielles françaises de League of Legends.",
    articles,
)
print("🟢 lol-patchnotes.xml généré.")

print("")
print("Génération de lol-patchnotes-discord.xml...")
create_rss(
    DISCORD_OUTPUT,
    "League of Legends — Patch Notes",
    "Dernière note de patch officielle française de League of Legends.",
    articles[:1],
)
print("🟢 lol-patchnotes-discord.xml généré.")

print("")
print("########################################")
print("# LOL PATCH NOTES RSS TERMINÉ")
print("########################################")
print("")
