import json, os, re, requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta
from email.utils import formatdate
from urllib.parse import urljoin
from xml.etree.ElementTree import Element, SubElement, ElementTree, indent
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

BASE_URL = 'https://teamfighttactics.leagueoflegends.com'
SOURCE_URLS = [f'{BASE_URL}/fr-fr/news/']
OUTPUT = 'tft-news.xml'
DISCORD_OUTPUT = 'tft-news-discord.xml'
CACHE_FILE = 'tft_cache.json'
MAX_ARTICLES = 20
MAX_LOAD_MORE_CLICKS = 8
HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0 Safari/537.36', 'Accept-Language': 'fr-FR,fr;q=0.9,en;q=0.8'}

print('\n########################################\n# Tensho Teamfight Tactics RSS\n# Actualités françaises\n########################################\n')

def clean_text(v): return re.sub(r'\s+', ' ', str(v or '')).strip()
def parse_date(v):
    if not v: return None
    try:
        d = datetime.fromisoformat(clean_text(v).replace('Z', '+00:00'))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception: return None
def format_pubdate(d): return formatdate(d.timestamp(), usegmt=True)

def load_cache():
    if not os.path.exists(CACHE_FILE):
        print('Aucun cache TFT trouvé.')
        return {}
    try:
        with open(CACHE_FILE, encoding='utf-8') as f: data = json.load(f)
        print(f"Cache TFT chargé : {len(data)} articles.")
        return data if isinstance(data, dict) else {}
    except Exception as e:
        print(f'⚠️ Erreur lecture cache : {e}')
        return {}

def save_cache(c):
    with open(CACHE_FILE, 'w', encoding='utf-8') as f: json.dump(c, f, ensure_ascii=False, indent=2)
cache = load_cache()

def is_excluded_url(url):
    value = url.lower().rstrip('/')
    if not value.startswith(BASE_URL + '/'): return True
    if value == BASE_URL + '/fr-fr/news': return True
    for p in ['wild-rift','valorant','legends-of-runeterra']:
        if p in value: return True
    for path in ['/news/game-updates','/news/media','/news/community','/news/esports','/news/products','/news/tags','/news/lore','/news/riot-games','/news/merch']:
        if value.endswith(path): return True
    for p in ['patch-notes','patchnote','notes-de-patch','notes-du-patch']:
        if p in value: return True
    return False

def collect_article_urls(page_url):
    print('\n========================================\nOuverture avec Playwright :')
    print(page_url)
    print('========================================')
    urls = set()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(locale='fr-FR', user_agent=HEADERS['User-Agent'])
        try:
            page.goto(page_url, wait_until='domcontentloaded', timeout=60000)
            page.wait_for_timeout(3000)
        except Exception as e:
            print(f'⚠️ Erreur ouverture page : {e}'); browser.close(); return []
        def collect():
            links = page.locator('a[href*="/fr-fr/news/"]')
            before = len(urls)
            for i in range(links.count()):
                try:
                    href = links.nth(i).get_attribute('href')
                    if not href: continue
                    u = urljoin(BASE_URL, href).rstrip('/')
                    if '/fr-fr/news/' in u and u != page_url.rstrip('/'): urls.add(u)
                except Exception: pass
            return len(urls) - before
        collect(); print(f'Premier lot : {len(urls)} articles.')
        for n in range(1, MAX_LOAD_MORE_CLICKS + 1):
            print(f'🔄 Recherche du bouton VOIR PLUS ({n}/{MAX_LOAD_MORE_CLICKS})...')
            buttons = page.get_by_text('VOIR PLUS', exact=True)
            clicked = False
            for i in range(buttons.count()):
                try:
                    b = buttons.nth(i)
                    if b.is_visible():
                        b.scroll_into_view_if_needed(); page.wait_for_timeout(500); b.click(timeout=10000); clicked = True; print('🟢 VOIR PLUS cliqué.'); break
                except Exception: pass
            if not clicked:
                print('ℹ️ Impossible de cliquer sur VOIR PLUS.'); break
            page.wait_for_timeout(2500)
            try: page.wait_for_load_state('networkidle', timeout=10000)
            except PlaywrightTimeoutError: pass
            added = collect(); print(f'Articles actuellement trouvés : {len(urls)} (+{added})')
            if added == 0: break
        browser.close()
    print(f'🟢 Total récupéré depuis cette page : {len(urls)} URLs')
    return list(urls)

all_urls = set()
for source in SOURCE_URLS:
    all_urls.update(collect_article_urls(source))
print('\n########################################')
print(f'# URLs uniques trouvées : {len(all_urls)}')
print('########################################')
candidate_urls = [u for u in all_urls if not is_excluded_url(u)]
print(f'URLs candidates après premier filtrage : {len(candidate_urls)}')

session = requests.Session(); session.headers.update(HEADERS)
articles = []
for index, url in enumerate(candidate_urls, 1):
    print(f'\n[{index}/{len(candidate_urls)}] {url}')
    cached = cache.get(url, {})
    cached_date = parse_date(cached.get('pubDate'))
    try:
        r = session.get(url, timeout=30); r.raise_for_status(); soup = BeautifulSoup(r.text, 'html.parser')
    except Exception as e:
        print(f'⚠️ Impossible de charger : {e}'); continue
    title = clean_text(soup.find('h1').get_text(' ', strip=True)) if soup.find('h1') else ''
    if not title:
        m = soup.find('meta', attrs={'property':'og:title'}); title = clean_text(m.get('content')) if m else ''
    if not title: title = url.rstrip('/').split('/')[-1].replace('-', ' ').title()
    dt = None
    for script in soup.find_all('script', type='application/ld+json'):
        raw = script.string or script.get_text()
        for v in re.findall(r'"datePublished"\s*:\s*"([^"]+)"', raw or ''):
            dt = parse_date(v)
            if dt: break
        if dt: break
    if not dt:
        for attrs in [{'property':'article:published_time'}, {'property':'og:published_time'}]:
            m = soup.find('meta', attrs=attrs)
            if m: dt = parse_date(m.get('content'))
            if dt: break
    if not dt:
        for node in soup.find_all('time'):
            dt = parse_date(node.get('datetime'))
            if dt: break
    if not dt: dt = cached_date
    if not dt:
        print('⚠️ Date introuvable.'); continue
    m = soup.find('meta', attrs={'name':'description'}) or soup.find('meta', attrs={'property':'og:description'})
    description = clean_text(m.get('content')) if m else title
    combined = f'{title} {url} {description}'.lower()
    patch_patterns = [r'notes?\s+de\s+patch', r'patch\s+\d+\.\d+', r'patch[-_]\d+[-_]\d+', r'patch-notes', r'patchnote', r'notes?\s+du\s+patch']
    esport_patterns = [r'/esports/', r'\besports\b', r'\besport\b', r'\be-sport\b', r'\bworlds\b', r'\bregional\b', r'championship', r"tactician.?s crown", r'pro circuit', r'paris open', r'vegas open', r'compete tft', r'\bcompétition\b', r'\bcompétitions\b']
    guide_patterns = [r'\bguide\b', r'\bbuild\b', r'\bastuces?\b', r'comment jouer', r'comment bien', r'conseils']
    other_patterns = [r'produits dérivés', r'merchandising', r'merchandise', r'goodies', r"fond d'écran", r'wallpaper']
    excluded = False
    for pattern in patch_patterns + esport_patterns + guide_patterns + other_patterns:
        if re.search(pattern, combined, re.IGNORECASE):
            print(f'❌ Exclu : {title}'); excluded = True; break
    if excluded: continue
    articles.append({'title':title,'url':url,'description':description,'date':dt})
    print(f'🟢 {format_pubdate(dt)} - {title}')

unique = {a['url']: a for a in articles}
articles = list(unique.values())
cutoff = datetime.now(timezone.utc) - timedelta(days=90)
recent = []
for a in articles:
    d = a['date'] if a['date'].tzinfo else a['date'].replace(tzinfo=timezone.utc)
    if d >= cutoff: recent.append(a)
    else: print(f"❌ Trop ancien : {format_pubdate(d)} - {a['title']}")
articles = sorted(recent, key=lambda a:a['date'], reverse=True)[:MAX_ARTICLES]

print('\n########################################')
print(f'# {len(articles)} actualités retenues')
print('########################################\n')
for i,a in enumerate(articles,1): print(f"{i:02d}. {format_pubdate(a['date'])} - {a['title']}")
for a in articles: cache[a['url']] = {'title':a['title'],'description':a['description'],'pubDate':format_pubdate(a['date'])}
save_cache(cache)

def create_rss(filename, title, description, items):
    rss = Element('rss', {'version':'2.0','xmlns:atom':'http://www.w3.org/2005/Atom'})
    ch = SubElement(rss,'channel')
    SubElement(ch,'title').text = title
    SubElement(ch,'link').text = f'{BASE_URL}/fr-fr/news/'
    SubElement(ch,'description').text = description
    SubElement(ch,'atom:link', {'href':f'https://shynen.github.io/tensho-cod-rss/{filename}','rel':'self','type':'application/rss+xml'})
    SubElement(ch,'lastBuildDate').text = formatdate(datetime.now(timezone.utc).timestamp(), usegmt=True)
    for a in items:
        item = SubElement(ch,'item')
        SubElement(item,'title').text = a['title']
        SubElement(item,'link').text = a['url']
        SubElement(item,'guid', {'isPermaLink':'true'}).text = a['url']
        SubElement(item,'pubDate').text = format_pubdate(a['date'])
        SubElement(item,'description').text = a['description']
    tree = ElementTree(rss); indent(tree, space='  '); tree.write(filename, encoding='utf-8', xml_declaration=True)

print('\nGénération de tft-news.xml...')
create_rss(OUTPUT, 'Teamfight Tactics — Actualités', 'Actualités officielles françaises de Teamfight Tactics.', articles)
print('🟢 tft-news.xml généré.')
print('\nGénération de tft-news-discord.xml...')
create_rss(DISCORD_OUTPUT, 'Teamfight Tactics Actualités', 'Dernière actualité officielle de Teamfight Tactics.', articles[:1])
print('🟢 tft-news-discord.xml généré.')
print('\n########################################\n# TFT RSS TERMINÉ\n########################################\n')
