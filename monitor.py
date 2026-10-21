#!/usr/bin/env python3
"""Australian PS5 Pro stock tracker. Run through GitHub Actions; dashboard is static.

A deliberately cautious stock checker: only product-local purchase signals count, and
network failures or unrecognised page layouts are UNKNOWN (never 'available').
Retailers can change their markup or block cloud IPs, so verify checkout manually.
"""

import argparse
import html
import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from bs4 import BeautifulSoup, NavigableString

ROOT = Path(__file__).resolve().parent
RETAILERS = ROOT / 'retailers.json'
REPORT = ROOT / 'docs' / 'stock.json'
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (compatible; PersonalPS5ProStockMonitor/1.0; +https://github.com)',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-AU,en;q=0.9',
}
STOCK_NO = [
    r'\bout of stock\b', r'\bsold out\b', r'\bcurrently unavailable\b',
    r'\btemporarily unavailable\b', r'\btemporarily out of stock\b',
    r'\bnot available\b', r'\bunavailable to order\b',
    r'\bcurrently not available\b', r'\bnotify me when (?:available|back in stock)\b',
    r'\bpresold out\b',
]
STOCK_YES = [
    r'\badd to (?:cart|basket|bag)\b', r'\bbuy now\b',
    r'\bcheck out now\b',
]
PREORDER = [r'\bpre[\s-]?order(?:s|ing)?\b', r'\bprepurchase\b']
BLOCKED = [r'access denied', r'captcha', r'just a moment\.\.\.',
           r'error 403', r'verify (?:you are|that you)', r'bot detection']
PRICE_RX = re.compile(r'\$\s*([1-4][\d,]{2,5}(?:\.\d{1,2})?)')
PS5PRO_RX = re.compile(r'(?:ps5|playstation\s*5)\s*(?:®\s*)?pro', re.I)


def normal(s: Any) -> str:
    return ' '.join(str(s or '').split())


def matches(text: str, patterns: list[str]) -> bool:
    return any(re.search(p, text, re.I) for p in patterns)


def looks_like_ps5_pro(name: str) -> bool:
    return bool(PS5PRO_RX.search(normal(name)))


def structured_products(soup: BeautifulSoup) -> list[dict]:
    products = []

    def descend(o):
        if isinstance(o, list):
            for item in o:
                descend(item)
        elif isinstance(o, dict):
            typ = o.get('@type', '')
            if isinstance(typ, list):
                product = 'Product' in typ
            else:
                product = typ == 'Product' or typ.endswith('/Product')
            if product and looks_like_ps5_pro(str(o.get('name', ''))):
                products.append(o)
            for k in ('@graph', 'mainEntity', 'itemListElement'):
                if k in o:
                    descend(o[k])

    for script in soup.find_all('script', type=re.compile('ld\\+json', re.I)):
        try:
            descend(json.loads(script.string or script.get_text()))
        except (json.JSONDecodeError, TypeError, ValueError):
            continue
    return products


def offer_state(products: list[dict]) -> tuple[str | None, float | None]:
    """Trust structured availability only for a correctly identified PS5 Pro product."""
    availabilities = []
    prices = []
    for p in products:
        offers = p.get('offers', [])
        if isinstance(offers, dict):
            offers = [offers]
        for offer in offers:
            if not isinstance(offer, dict):
                continue
            a = str(offer.get('availability', '')).lower().rsplit('/', 1)[-1]
            if a:
                availabilities.append(a)
            try:
                price = float(str(offer.get('price', '')).replace(',', ''))
                if 650 <= price <= 5000:
                    prices.append(price)
            except (ValueError, TypeError):
                pass
    state = None
    if any(a in ('outofstock', 'soldout', 'discontinued') for a in availabilities):
        state = 'out_of_stock'
    elif any(a in ('preorder', 'presale') for a in availabilities):
        state = 'preorder'
    elif any(a in ('instock', 'limitedavailability', 'onlineonly') for a in availabilities):
        state = 'in_stock'
    return state, min(prices) if prices else None


def page_context(soup: BeautifulSoup, item: dict) -> str:
    """Use product-local text. Never mistake nav or the next product's cart button."""
    if item.get('mode') == 'listing':
        text = normal(soup.get_text(' ', strip=True))
        target = item.get('match', item['name'])
        idx = text.lower().find(target.lower())
        if idx < 0:
            return ''
        # Harvey Norman category cards use a 'Compare' boundary. If it disappears,
        # safest to report UNKNOWN instead of inheriting the next item's button.
        tail = text[idx + len(target):idx + len(target) + 450]
        boundary = re.search(r'\bCompare\b', tail, re.I)
        if not boundary:
            return ''
        return text[max(0, idx - 22):idx + len(target)] + ' ' + tail[:boundary.start()]

    title = soup.find('h1')
    if not title:
        title = soup.find('h2', string=re.compile('(?:PS5|PlayStation 5).*Pro', re.I))
    if not title:
        return ''
    heading = normal(title.get_text(' ', strip=True))
    if not looks_like_ps5_pro(heading):
        return ''
    fragments = [heading]
    char_count = len(heading)
    for node in title.next_elements:
        if not isinstance(node, NavigableString):
            continue
        if node.parent and node.parent.name in ('script', 'style', 'noscript'):
            continue
        value = normal(node)
        if not value:
            continue
        fragments.append(value)
        char_count += len(value) + 1
        if char_count >= 1800:
            break
    return normal(' '.join(fragments))[:1800]


def price_from_context(context: str, structured_price: float | None) -> float | None:
    if structured_price is not None:
        return structured_price
    values = []
    for value in PRICE_RX.findall(context):
        try:
            price = float(value.replace(',', ''))
            if 650 <= price <= 5000:
                values.append(price)
        except ValueError:
            continue
    return min(values) if values else None


def parse_page(item: dict, raw_html: str) -> dict:
    soup = BeautifulSoup(raw_html, 'html.parser')
    for el in soup(['style', 'noscript']):
        el.decompose()
    context = page_context(soup, item)
    result = {'status': 'unknown', 'price_aud': None, 'reason': 'No reliable stock signal found.'}
    if not context:
        result['reason'] = 'PS5 Pro product listing not found; layout may have changed.'
        return result
    if matches(context[:400], BLOCKED):
        result['reason'] = 'Retailer returned a verification or blocking page.'
        return result
    structured = [] if item.get('mode') == 'listing' else structured_products(soup)
    structured_state, structured_price = offer_state(structured)
    result['price_aud'] = price_from_context(context, structured_price)
    # Retailer-specific negative messages are more reliable than stale/invisible
    # add-to-cart buttons or cached JSON-LD availability.
    if matches(context, STOCK_NO):
        result.update(status='out_of_stock', reason='Retailer shows out of stock / unavailable.')
    elif matches(context[:650], PREORDER):
        result.update(status='preorder', reason='Pre-order offered; not confirmed ready-to-ship stock.')
    elif structured_state == 'out_of_stock':
        result.update(status='out_of_stock', reason='Product structured data reports out of stock.')
    elif structured_state == 'preorder':
        result.update(status='preorder', reason='Product structured data reports pre-order.')
    elif matches(context, STOCK_YES):
        result.update(status='in_stock', reason='Product listing shows an active purchase button (checkout not verified).')
    elif structured_state == 'in_stock':
        result.update(status='in_stock', reason='Product structured data reports availability (checkout not verified).')
    return result


def load_json(path: Path, fallback: Any):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return fallback


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')


def get_item(item: dict, session: requests.Session, now: str) -> dict:
    result = {**item, 'status': 'unknown', 'price_aud': None,
              'checked_at': now, 'http_status': None,
              'reason': 'Stock check has not completed.'}
    try:
        response = session.get(item.get('check_url', item['url']), timeout=18, headers=HEADERS,
                               allow_redirects=True)
        result['http_status'] = response.status_code
        if response.status_code in (403, 429, 503):
            result['reason'] = f'Retailer blocked or rate-limited the check (HTTP {response.status_code}).'
        elif response.status_code != 200:
            result['reason'] = f'Retailer returned HTTP {response.status_code}.'
        elif matches(response.text[:3000], BLOCKED) and len(response.content) < 16000:
            result['reason'] = 'Retailer returned a security/anti-bot check.'
        else:
            result.update(parse_page(item, response.text))
    except requests.RequestException as exc:
        result['reason'] = f'Network request failed: {str(exc)[:160]}'
    return result


def telegram(message: str) -> bool:
    token = os.getenv('TELEGRAM_BOT_TOKEN', '').strip()
    chat = os.getenv('TELEGRAM_CHAT_ID', '').strip()
    if not (token and chat):
        return False
    try:
        r = requests.post(f'https://api.telegram.org/bot{token}/sendMessage',
                          json={'chat_id': chat, 'text': message, 'parse_mode': 'HTML',
                                'disable_web_page_preview': False}, timeout=15)
        r.raise_for_status()
        if not r.json().get('ok'):
            raise RuntimeError('Telegram returned ok=false')
        return True
    except (requests.RequestException, ValueError, RuntimeError) as exc:
        logging.warning('Telegram notification failed: %s', exc)
        return False


def discord(message: str) -> bool:
    webhook = os.getenv('DISCORD_WEBHOOK_URL', '').strip()
    if not webhook:
        return False
    try:
        r = requests.post(webhook, json={'content': re.sub(r'<[^>]+>', '', message)[:1950]},
                          timeout=15)
        r.raise_for_status()
        return True
    except requests.RequestException as exc:
        logging.warning('Discord notification failed: %s', exc)
        return False


def send_notification(item: dict, test: bool = False) -> bool:
    prefix = 'TEST — ' if test else ''
    status_label = 'PRE-ORDER OPEN' if item['status'] == 'preorder' else 'STOCK DETECTED'
    price = f"AU${item['price_aud']:,.2f}" if item.get('price_aud') is not None else 'Price not detected'
    msg = (f'<b>{prefix}PS5 Pro {status_label}</b>\n'
           f"{html.escape(item['retailer'])} — {html.escape(item['name'])}\n"
           f"Condition: {item['condition'].title()} | {price}\n"
           f"<a href=\"{html.escape(item['url'], quote=True)}\">View product</a>\n"
           'Check shipping/pickup availability at checkout.')
    return telegram(msg) or discord(msg)


def update_report(catalog: list[dict], previous: dict, observations: list[dict],
                  notify_preorders: bool, now: str, notify: bool = True) -> dict:
    before = {i.get('id'): i for i in previous.get('items', [])}
    events = list(previous.get('events', []))[-39:]
    current = []
    for obs in observations:
        old = before.get(obs['id'], {})
        prev_status = old.get('status', 'not_checked')
        status = obs['status']
        # Unknown must NOT reset alert suppression; blocked requests should not
        # repeatedly trigger new alerts when they briefly recover.
        alerted = bool(old.get('alerted', False))
        if status in ('out_of_stock', 'preorder') and status != prev_status:
            alerted = False
        elif status == 'out_of_stock':
            alerted = False
        qualifies = status == 'in_stock' or (status == 'preorder' and notify_preorders)
        if qualifies and not alerted and notify:
            if send_notification(obs):
                alerted = True
                logging.info('Alert sent for %s', obs['id'])
            else:
                logging.warning('No alert delivered for %s. Configure Telegram or Discord Secrets.', obs['id'])
        if status != prev_status and status != 'unknown':
            events.append({'at': now, 'id': obs['id'], 'retailer': obs['retailer'],
                           'name': obs['name'], 'status': status})
        current.append({**obs, 'alerted': alerted})
    return {'updated_at': now, 'check_interval_minutes': 15,
            'note': 'Purchase indicators are not a guarantee of Australian delivery or in-store stock.',
            'items': current, 'events': events[-40:]}


def main():
    parser = argparse.ArgumentParser(description='PS5 Pro AU cloud stock watcher')
    parser.add_argument('--test-notification', action='store_true',
                        help='Send an example notification without checking stock')
    parser.add_argument('--no-notify', action='store_true',
                        help='Check stock without sending alerts or changing the alerted flag')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
    catalog = load_json(RETAILERS, [])
    if not catalog:
        raise SystemExit('retailers.json is empty or could not be opened')
    if args.test_notification:
        item = {**catalog[0], 'status': 'in_stock', 'price_aud': 1399.0}
        if not send_notification(item, test=True):
            raise SystemExit('Could not deliver test alert. Check GitHub Secrets and Actions logs.')
        print('Test notification delivered.')
        return
    prev = load_json(REPORT, {})
    checked_at = iso_now()
    with requests.Session() as session:
        observations = []
        for item in catalog:
            result = get_item(item, session, checked_at)
            logging.info('%-19s %-15s %s', item['id'], result['status'], result['reason'])
            observations.append(result)
    notify_preorders = os.getenv('NOTIFY_PREORDERS', 'false').lower() in ('true', '1', 'yes')
    updated = update_report(catalog, prev, observations, notify_preorders,
                            checked_at, notify=not args.no_notify)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(updated, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    known = [i for i in updated['items'] if i['status'] != 'unknown']
    logging.info('Completed %s checks; %s with identified status.', len(observations), len(known))


if __name__ == '__main__':
    main()
