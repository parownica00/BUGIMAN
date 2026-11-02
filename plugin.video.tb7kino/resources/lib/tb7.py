# -*- coding: utf-8 -*-
"""Klient TB7 (panel WWW - TB7 nie udostępnia publicznego API).

Przepływ:
  POST /login                    -> sesja (cookies)
  POST /mojekonto/szukaj         -> wyniki, kolejne strony GET /mojekonto/szukaj/<n>
  POST /mojekonto/sciagaj step=1 -> sprawdzenie linku (content=<link>)
  POST /mojekonto/sciagaj step=2 -> pobranie na konto (zużywa transfer), zwraca link do odtwarzania
  GET  /mojekonto/pliki          -> pliki już pobrane na konto (bez dodatkowego transferu)
"""
import json
import os
import re
import time
from datetime import datetime
from html import unescape

import requests
from urllib.parse import urljoin, urlparse
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BASE = 'https://www.tb7.pl/'
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/126.0 Safari/537.36')
COOKIE_TTL = 3 * 3600
RE_LOGGED_IN = re.compile(r'yloguj|textPremium', re.I)
VIDEO_EXT = ('.mkv', '.mp4', '.avi', '.mov', '.mpg', '.ts', '.m2ts', '.mts')


class TB7Error(Exception):
    pass


def parse_expiry(text):
    """'20:47 02.11.2026' (albo '02.11.2026 20:47') -> datetime, inaczej None."""
    t = re.search(r'(\d{1,2}):(\d{2})', text or '')
    d = re.search(r'(\d{1,2})\.(\d{1,2})\.(\d{4})', text or '')
    if not d:
        return None
    try:
        return datetime(int(d.group(3)), int(d.group(2)), int(d.group(1)),
                        int(t.group(1)) if t else 23, int(t.group(2)) if t else 59)
    except ValueError:
        return None


def _strip(html):
    return unescape(re.sub(r'<[^>]+>', '', html or '')).strip()


def size_to_mb(text):
    m = re.search(r'([\d.,]+)\s*([KMGT]?B)', text or '', re.I)
    if not m:
        return 0
    val = float(m.group(1).replace(',', '.'))
    mult = {'B': 1 / 1048576, 'KB': 1 / 1024, 'MB': 1, 'GB': 1024, 'TB': 1048576}
    return int(val * mult.get(m.group(2).upper(), 1))


def parse_rows(html):
    """Parsuje tabelę wyników wyszukiwania TB7 -> lista dict."""
    out = []
    for row in re.findall(r'<tr[^>]*>(.*?)</tr>', html or '', re.S | re.I)[1:]:
        label = re.search(r'<label[^>]*>(.*?)</label>', row, re.S | re.I)
        link = re.search(r'<input[^>]*value="([^"]+)"', row, re.I)
        cells = re.findall(r'<td[^>]*>(.*?)</td>', row, re.S | re.I)
        if not (label and link and len(cells) >= 4):
            continue
        out.append({
            'filename': _strip(label.group(1)),
            'url': unescape(link.group(1)),
            'host': _strip(cells[1]),
            'size': _strip(cells[3]),
            'size_mb': size_to_mb(_strip(cells[3])),
        })
    return out


class TB7:
    def __init__(self, user, password, profile_dir):
        self.user, self.password = user, password
        self.cookie_file = os.path.join(profile_dir, 'tb7_cookies.json')
        self.s = requests.Session()
        self.s.headers.update({'User-Agent': UA, 'Accept-Language': 'pl-PL,pl;q=0.9'})

    # ---- sesja ---------------------------------------------------------
    def _load_cookies(self):
        try:
            with open(self.cookie_file) as f:
                data = json.load(f)
            if time.time() - data.get('ts', 0) < COOKIE_TTL and data.get('user') == self.user:
                self.s.cookies.update(data['cookies'])
                return True
        except Exception:
            pass
        return False

    def _save_cookies(self):
        try:
            os.makedirs(os.path.dirname(self.cookie_file), exist_ok=True)
            with open(self.cookie_file, 'w') as f:
                json.dump({'ts': time.time(), 'user': self.user,
                           'cookies': self.s.cookies.get_dict()}, f)
        except Exception:
            pass

    def login(self, force=False):
        if not self.user or not self.password:
            raise TB7Error('Uzupełnij login i hasło TB7 w ustawieniach.')
        if not force and self._load_cookies():
            if RE_LOGGED_IN.search(self.s.get(BASE, timeout=20).text):
                return True
        self.s.cookies.clear()
        r = self.s.post(BASE + 'login', data={'login': self.user, 'password': self.password},
                        allow_redirects=False, timeout=20)
        ok = r.status_code in (301, 302, 303, 307, 308) or \
            bool(RE_LOGGED_IN.search(self.s.get(BASE, timeout=20).text))
        if not ok:
            raise TB7Error('Logowanie do TB7 nieudane - sprawdź login i hasło.')
        self._save_cookies()
        return True

    # ---- konto -------------------------------------------------------------
    def account_info(self):
        """Zwraca tekst z pozostałym transferem (np. '45,3 GB')."""
        html = self.s.get(BASE, timeout=20).text
        box = re.search(r'class="textPremium"(.*?)</div>', html, re.S | re.I)
        if not box:
            return ''
        bolds = re.findall(r'<b[^>]*>(.*?)</b>', box.group(1), re.S | re.I)
        return _strip(bolds[-1]) if bolds else ''

    def remaining_mb(self):
        return size_to_mb(self.account_info())

    # ---- wyszukiwanie ------------------------------------------------------
    def search(self, query, max_pages=5):
        html = self.s.post(BASE + 'mojekonto/szukaj', data={'search': query, 'type': '1'},
                           timeout=45).text
        rows = parse_rows(html)
        pages = re.search(r'class="page-list"(.+?)</div>', html, re.S | re.I)
        n = len(re.findall('href=', pages.group(1))) if pages else 1
        for p in range(2, min(n, max_pages) + 1):
            rows += parse_rows(self.s.get(BASE + 'mojekonto/szukaj/%d' % p, timeout=30).text)
        seen, out = set(), []
        for r in rows:
            if r['url'] not in seen and r['filename'].lower().endswith(VIDEO_EXT):
                seen.add(r['url'])
                out.append(r)
        return out

    def library(self):
        """Pliki już pobrane na konto: lista (filename, link, wygasa)."""
        html = self.s.get(BASE + 'mojekonto/pliki', timeout=30).text
        table = re.search(r'<table[^>]*class="list"[^>]*>(.*?)</table>', html, re.S | re.I)
        out = []
        if not table:
            return out
        for row in re.findall(r'<tr[^>]*>(.*?)</tr>', table.group(1), re.S | re.I)[1:]:
            link = re.search(r'<input[^>]*value="([^"]+)"', row, re.I)
            cells = [_strip(c) for c in re.findall(r'<td[^>]*>(.*?)</td>', row, re.S | re.I)]
            if not link:
                continue
            url = unescape(link.group(1))
            name = cells[1] if len(cells) > 1 and cells[1] else url.rstrip('/').split('/')[-1]
            name = re.sub(r'^(?:\.\.\.|…)?/?', '', name.replace('\\', '/').split('/')[-1]).strip()
            expires = cells[3] if len(cells) > 3 else ''
            when = parse_expiry(expires)
            out.append({'filename': name, 'url': url, 'expires': expires, 'expires_at': when,
                        'expired': bool(when and when <= datetime.now())})
        return out

    # ---- pobranie / link do odtwarzania -------------------------------
    def get_stream(self, url):
        """Krok 1 + 2 w /mojekonto/sciagaj. Zużywa transfer!"""
        r1 = self.s.post(BASE + 'mojekonto/sciagaj', data={'step': '1', 'content': url}, timeout=45).text
        if 'ymagane dodatkowe' in r1:
            raise TB7Error('Za mało transferu na koncie TB7.')
        if 'value="Wgraj linki"' not in r1:
            raise TB7Error('Link jest nieaktywny.')
        r2 = self.s.post(BASE + 'mojekonto/sciagaj', data={'step': '2', '0': 'on'}, timeout=60).text
        hrefs = []
        for div in re.findall(r'<div[^>]*class="download"[^>]*>(.*?)</div>', r2, re.S | re.I):
            hrefs += re.findall(r'<a[^>]*href="([^"]+)"', div, re.I)
        if not hrefs:
            if 'Nieaktywne linki' in r2:
                raise TB7Error('Link okazał się nieaktywny.')
            raise TB7Error('Nie udało się wygenerować linku (brak transferu?).')
        return self.playable(hrefs[1] if len(hrefs) > 1 else hrefs[0])

    def playable(self, link):
        """Link dla odtwarzacza. Serwery hostingów (np. twojplik) mają wadliwe certyfikaty SSL,
        więc - jak FanFilm - nie weryfikujemy ich przy pobieraniu samego wideo."""
        link = unescape(link).replace('%2F', '-')
        try:
            h = self.s.head(link, allow_redirects=False, timeout=20, verify=False)
            if h.status_code in (301, 302, 303, 307, 308) and h.headers.get('Location'):
                link = urljoin(link, h.headers['Location'])
        except Exception:
            pass
        return link + '|User-Agent=' + requests.utils.quote(UA) + '&Connection=close&verifypeer=false'

    def check(self, stream):
        """Sprawdza, czy link do wideo działa: (True, opis) albo (False, przyczyna).

        Pobiera tylko pierwszy bajt (Range 0-0), więc praktycznie nie zużywa transferu.
        """
        url = stream.split('|')[0]
        host = urlparse(url).netloc or url[:40]
        try:
            r = self.s.get(url, headers={'Range': 'bytes=0-0'}, stream=True, timeout=25,
                           verify=False, allow_redirects=True)
            status, ctype = r.status_code, (r.headers.get('Content-Type') or '').lower()
            r.close()
        except requests.RequestException as e:
            return False, '%s (%s)' % (type(e).__name__, host)
        if status >= 400:
            return False, 'HTTP %d (%s)' % (status, host)
        if 'text/html' in ctype:
            return False, 'strona zamiast pliku (%s)' % host
        return True, 'HTTP %d (%s)' % (status, host)
