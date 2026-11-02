# -*- coding: utf-8 -*-
"""Lokalne proxy HTTP dla odtwarzania z hostingów TB7.

Kodi łączy się z 127.0.0.1, a proxy pobiera dane z serwera hostingu. Gdy połączenie
z hostingiem zostanie zerwane (np. serwer zamknął je w trakcie długiej pauzy), proxy
łączy się ponownie z nagłówkiem Range od miejsca, w którym przerwało, więc Kodi
niczego nie zauważa. Gdy link wygaśnie (403/404/410), proxy prosi resolver o nowy.
Moduł nie zależy od Kodi, więc da się go testować poza nim.
"""
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

CHUNK = 64 * 1024
DEAD = (401, 403, 404, 410)
OPEN_ATTEMPTS = 6
START_ATTEMPTS = 3  # na starcie krócej, żeby nie trzymać kółka ładowania
MAX_RESUMES = 20
PASS_HEADERS = ('Content-Type', 'Last-Modified', 'ETag')


class UpstreamError(Exception):
    pass


def parse_content_range(value):
    m = re.match(r'bytes\s+(\d+)-(\d+)/(\d+|\*)', value or '')
    if not m:
        return None
    total = int(m.group(3)) if m.group(3) != '*' else None
    return int(m.group(1)), int(m.group(2)), total


class Stream:
    """Jeden plik do odtwarzania: aktualny URL, nagłówki i resolver nowego linku."""

    def __init__(self, url, headers=None, resolver=None, log=print):
        self.url = url
        self.headers = dict(headers or {})
        self.resolver = resolver
        self.log = log
        self.lock = threading.Lock()
        self.session = requests.Session()
        self.session.verify = False  # wadliwe certyfikaty hostingów - tak samo jak Kodi z verifypeer=false
        self.last_error = ''

    def _reresolve(self):
        if not self.resolver:
            return False
        try:
            new = self.resolver()
        except Exception as e:  # resolver nie może wywrócić odtwarzania
            self.log('nowy link: błąd %r' % (e,))
            new = None
        if not new:
            return False
        with self.lock:
            self.url, self.headers = new[0], dict(new[1] or {})
        self.log('nowy link z konta TB7')
        return True

    def open(self, start, end=None, attempts=None):
        """GET z Range bytes=start-end; ponawia, w razie potrzeby pobiera nowy link."""
        rng = 'bytes=%d-%s' % (start, '' if end is None else end)
        resolved, delay = False, 1
        attempts = attempts or OPEN_ATTEMPTS
        for attempt in range(attempts):
            with self.lock:
                url, headers = self.url, dict(self.headers)
            headers['Range'] = rng
            status = None
            try:
                r = self.session.get(url, headers=headers, stream=True, timeout=(15, 30), verify=False)
                status = r.status_code
                if status in (200, 206):
                    if status == 200 and start > 0:
                        r.close()
                        raise UpstreamError('serwer nie obsługuje wznawiania (Range)')
                    return r
                r.close()
                self.last_error = 'HTTP %d' % status
                self.log('%s -> HTTP %d' % (rng, status))
            except requests.RequestException as e:
                self.last_error = type(e).__name__
                self.log('%s -> %r' % (rng, e))
            if attempt == attempts - 1:
                break
            if not resolved and (status in DEAD or attempt >= 1):
                resolved = True
                if self._reresolve():
                    continue
            time.sleep(delay)
            delay = min(delay * 2, 8)
        raise UpstreamError('nie udało się połączyć z serwerem pliku')


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    server_version = 'TB7KinoProxy'

    def log_message(self, fmt, *args):
        pass

    def do_HEAD(self):
        self._serve(head=True)

    def do_GET(self):
        self._serve(head=False)

    def _serve(self, head):
        m = re.match(r'/play/([0-9a-f]+)(?:/|$)', self.path)
        st = self.server.lookup(m.group(1)) if m else None
        if st is None:
            self.send_error(404)
            return

        client_range = re.match(r'bytes=(\d+)-(\d*)$', self.headers.get('Range', '').strip())
        start = int(client_range.group(1)) if client_range else 0
        end = int(client_range.group(2)) if client_range and client_range.group(2) else None
        try:
            r = st.open(start, end, START_ATTEMPTS)
        except UpstreamError as e:
            self.server.log('start %d: %s (%s)' % (start, e, st.last_error))
            self.server.notify('Serwer pliku nie odpowiada (%s)' % (st.last_error or e))
            self.send_error(502, 'Upstream unavailable')  # nagłówek HTTP musi być w ASCII
            return

        # długość i nagłówki odpowiedzi dla Kodi
        stop = None  # bajt końcowy (wyłączny)
        cr = parse_content_range(r.headers.get('Content-Range'))
        if r.status_code == 206 and cr:
            a, b, total = cr
            stop = b + 1
            if client_range:
                self.send_response(206)
                self.send_header('Content-Range', 'bytes %d-%d/%s' % (a, b, total if total is not None else '*'))
                self.send_header('Content-Length', str(b - a + 1))
            else:
                self.send_response(200)
                if total is not None:
                    self.send_header('Content-Length', str(total))
        else:
            self.send_response(200)
            if r.headers.get('Content-Length'):
                stop = start + int(r.headers['Content-Length'])
                self.send_header('Content-Length', r.headers['Content-Length'])
        for h in PASS_HEADERS:
            if r.headers.get(h):
                self.send_header(h, r.headers[h])
        self.send_header('Accept-Ranges', 'bytes')
        self.end_headers()
        if head:
            r.close()
            return

        pos, resumes = start, 0
        it = r.iter_content(CHUNK)
        try:
            while stop is None or pos < stop:
                try:
                    chunk = next(it)
                except StopIteration:
                    chunk = None
                    if stop is None:
                        break
                except Exception as e:
                    chunk = None
                    self.server.log('zerwane przy bajcie %d: %r' % (pos, e))
                if not chunk:
                    r.close()
                    resumes += 1
                    if resumes > MAX_RESUMES:
                        self.server.log('za dużo wznowień, przerywam')
                        break
                    try:
                        r = st.open(pos, None if stop is None else stop - 1)
                    except UpstreamError as e:
                        self.server.log('wznowienie od %d nieudane: %s' % (pos, e))
                        break
                    it = r.iter_content(CHUNK)
                    self.server.log('wznowiono od bajtu %d' % pos)
                    continue
                if stop is not None and pos + len(chunk) > stop:
                    chunk = chunk[:stop - pos]
                try:
                    self.wfile.write(chunk)
                except Exception:
                    break  # Kodi zamknął połączenie (stop, przewijanie)
                pos += len(chunk)
                resumes = 0
        finally:
            r.close()
        self.close_connection = True


class ProxyServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, lookup, log=print, port=0, notify=None):
        ThreadingHTTPServer.__init__(self, ('127.0.0.1', port), Handler)
        self.lookup = lookup
        self.log = log
        self.notify = notify or (lambda msg: None)

    @property
    def port(self):
        return self.server_address[1]
