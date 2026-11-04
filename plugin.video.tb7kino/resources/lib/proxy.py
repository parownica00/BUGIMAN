# -*- coding: utf-8 -*-
"""Lokalne proxy HTTP dla odtwarzania z hostingów TB7.

Kodi łączy się z 127.0.0.1, a proxy pobiera dane z serwera hostingu. Zasada jak w serwisach
streamingowych: film się nie zamyka. Gdy połączenie z hostingiem zostanie zerwane albo zniknie
internet, proxy cierpliwie (do MAX_WAIT) łączy się ponownie od tego samego bajtu - Kodi w tym
czasie pokazuje kółko buforowania - a gdy dane wrócą, odtwarzanie idzie dalej. Wygasły link
(403/404/410) proxy wymienia na nowy z konta TB7 (resolver). Gdy Kodi sam połączy się ponownie
w środku filmu, proxy odpowiada od razu z zapamiętanych danych (rozmiar, typ), bez czekania na
hosting. Moduł nie zależy od Kodi, więc da się go testować poza nim.
"""
import re
import select
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

CHUNK = 64 * 1024
DEAD = (401, 403, 404, 410)
START_ATTEMPTS = 3      # pierwsze otwarcie pliku: szybki błąd zamiast długiego kółka
MAX_WAIT = 15 * 60      # tyle proxy czeka na powrót połączenia w trakcie filmu (s)
RESOLVE_EVERY = 60      # co ile sekund nieudanych prób pobrać nowy link z konta (s)
NOTIFY_AFTER = 8        # po ilu sekundach przerwy pokazać "czekam na połączenie" (s)
PASS_HEADERS = ('Last-Modified', 'ETag')


class UpstreamError(Exception):
    pass


def parse_content_range(value):
    m = re.match(r'bytes\s+(\d+)-(\d+)/(\d+|\*)', value or '')
    if not m:
        return None
    total = int(m.group(3)) if m.group(3) != '*' else None
    return int(m.group(1)), int(m.group(2)), total


class Stream:
    """Jeden plik do odtwarzania: aktualny URL, nagłówki, resolver nowego linku i znany rozmiar."""

    def __init__(self, url, headers=None, resolver=None, log=print):
        self.url = url
        self.headers = dict(headers or {})
        self.resolver = resolver
        self.log = log
        self.lock = threading.Lock()
        self.session = requests.Session()
        self.session.verify = False  # wadliwe certyfikaty hostingów - tak samo jak Kodi z verifypeer=false
        self.last_error = ''
        self.size = None            # całkowity rozmiar pliku, gdy już znany
        self.ctype = None
        self.last_resolve = 0.0

    def _reresolve(self):
        if not self.resolver:
            return False
        self.last_resolve = time.time()
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

    def _learn(self, r, start):
        cr = parse_content_range(r.headers.get('Content-Range'))
        if r.status_code == 206 and cr and cr[2] is not None:
            self.size = cr[2]
        elif r.status_code == 200 and start == 0 and r.headers.get('Content-Length'):
            self.size = int(r.headers['Content-Length'])
        ct = r.headers.get('Content-Type') or ''
        if ct and 'text/html' not in ct.lower():
            self.ctype = ct

    def try_open(self, start, end=None):
        """Jedna próba GET z Range. Zwraca odpowiedź albo None (przyczyna w last_error)."""
        with self.lock:
            url, headers = self.url, dict(self.headers)
        headers['Range'] = 'bytes=%d-%s' % (start, '' if end is None else end)
        try:
            r = self.session.get(url, headers=headers, stream=True, timeout=(10, 15), verify=False)
        except requests.RequestException as e:
            self.last_error = type(e).__name__
            self.log('%s -> %r' % (headers['Range'], e))
            return None
        if r.status_code in (200, 206) and not (r.status_code == 200 and start > 0):
            if 'text/html' in (r.headers.get('Content-Type') or '').lower() and self.size:
                r.close()  # strona błędu zamiast dalszej części pliku
                self.last_error = 'strona HTML'
                return None
            self._learn(r, start)
            return r
        r.close()
        self.last_error = 'HTTP %d' % r.status_code
        self.log('%s -> HTTP %d' % (headers['Range'], r.status_code))
        if r.status_code in DEAD:
            self._reresolve()
        return None

    def open(self, start, end=None, attempts=START_ATTEMPTS):
        """Kilka szybkich prób (start odtwarzania)."""
        for attempt in range(attempts):
            r = self.try_open(start, end)
            if r is not None:
                return r
            if attempt == 1 and time.time() - self.last_resolve > 5:
                self._reresolve()
            if attempt < attempts - 1:
                time.sleep(1)
        raise UpstreamError('nie udało się połączyć z serwerem pliku')

    def open_patient(self, start, end, gone, notify=None):
        """Czeka na powrót połączenia (do MAX_WAIT), dopóki Kodi trzyma połączenie."""
        t0, delay, warned = time.time(), 1.0, False
        while True:
            r = self.try_open(start, end)
            if r is not None:
                if warned and notify:
                    notify('Połączenie wróciło - odtwarzam dalej', False)
                return r
            waited = time.time() - t0
            if waited > MAX_WAIT:
                raise UpstreamError('brak połączenia od %d min' % (MAX_WAIT // 60))
            if not warned and waited >= NOTIFY_AFTER and notify:
                notify('Brak połączenia z serwerem (%s) - czekam...' % self.last_error, True)
                warned = True
            if time.time() - self.last_resolve > RESOLVE_EVERY and waited > 10:
                self._reresolve()
            end_sleep = time.time() + delay
            while time.time() < end_sleep:
                if gone():
                    raise UpstreamError('odtwarzanie zatrzymane')
                time.sleep(0.25)
            delay = min(delay * 1.5, 5.0)


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    server_version = 'TB7KinoProxy'

    def log_message(self, fmt, *args):
        pass

    def do_HEAD(self):
        self._serve(head=True)

    def do_GET(self):
        self._serve(head=False)

    def _client_gone(self):
        """Kodi zamknął połączenie (stop / przewinięcie)? W trakcie odpowiedzi Kodi nic nie wysyła,
        więc 'gotowe do czytania' oznacza tu zamknięcie gniazda."""
        try:
            readable, _, _ = select.select([self.connection], [], [], 0)
            if not readable:
                return False
            return self.connection.recv(1, socket.MSG_PEEK) == b''
        except Exception:
            return True

    def _serve(self, head):
        m = re.match(r'/play/([0-9a-f]+)(?:/|$)', self.path)
        st = self.server.lookup(m.group(1)) if m else None
        if st is None:
            self.send_error(404)
            return

        client_range = re.match(r'bytes=(\d+)-(\d*)$', self.headers.get('Range', '').strip())
        start = int(client_range.group(1)) if client_range else 0
        end = int(client_range.group(2)) if client_range and client_range.group(2) else None

        r = None
        if st.size is None:
            # pierwsze otwarcie: rozmiar poznamy dopiero od serwera
            try:
                r = st.open(start, end)
            except UpstreamError as e:
                self.server.log('start %d: %s (%s)' % (start, e, st.last_error))
                self.server.notify('Serwer pliku nie odpowiada (%s)' % (st.last_error or e), True)
                self.send_error(502, 'Upstream unavailable')  # nagłówek HTTP musi być w ASCII
                return

        if st.size is not None:
            size = st.size
            last = size - 1 if end is None else min(end, size - 1)
            if start > last:
                if r is not None:
                    r.close()
                self.send_response(416)
                self.send_header('Content-Range', 'bytes */%d' % size)
                self.send_header('Content-Length', '0')
                self.end_headers()
                return
            stop = last + 1
            if client_range:
                self.send_response(206)
                self.send_header('Content-Range', 'bytes %d-%d/%d' % (start, last, size))
            else:
                self.send_response(200)
            self.send_header('Content-Length', str(stop - start))
        else:
            # serwer nie podał rozmiaru - przekazujemy, co wiemy
            stop = start + int(r.headers['Content-Length']) if r.headers.get('Content-Length') else None
            self.send_response(200)
            if stop is not None:
                self.send_header('Content-Length', str(stop - start))
        self.send_header('Content-Type', st.ctype or 'application/octet-stream')
        if r is not None:
            for h in PASS_HEADERS:
                if r.headers.get(h):
                    self.send_header(h, r.headers[h])
        self.send_header('Accept-Ranges', 'bytes')
        self.end_headers()
        if head:
            if r is not None:
                r.close()
            return

        pos = start
        it = r.iter_content(CHUNK) if r is not None else None
        try:
            while stop is None or pos < stop:
                chunk = None
                if it is not None:
                    try:
                        chunk = next(it)
                    except StopIteration:
                        if stop is None:
                            break
                    except Exception as e:
                        self.server.log('zerwane przy bajcie %d: %r' % (pos, e))
                if not chunk:
                    if r is not None:
                        r.close()
                    try:
                        r = st.open_patient(pos, None if stop is None else stop - 1,
                                            self._client_gone, self.server.notify)
                    except UpstreamError as e:
                        self.server.log('koniec czekania od bajtu %d: %s' % (pos, e))
                        r = None
                        break
                    it = r.iter_content(CHUNK)
                    if pos != start:
                        self.server.log('wznowiono od bajtu %d' % pos)
                    continue
                if stop is not None and pos + len(chunk) > stop:
                    chunk = chunk[:stop - pos]
                try:
                    self.wfile.write(chunk)
                except Exception:
                    break  # Kodi zamknął połączenie (stop, przewijanie)
                pos += len(chunk)
        finally:
            if r is not None:
                r.close()
        self.close_connection = True


class ProxyServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, lookup, log=print, port=0, notify=None):
        ThreadingHTTPServer.__init__(self, ('127.0.0.1', port), Handler)
        self.lookup = lookup
        self.log = log
        self._notify = notify
        self._last_note = (None, 0.0)

    def notify(self, msg, error=True):
        if not self._notify:
            return
        if self._last_note[0] == msg and time.time() - self._last_note[1] < 20:
            return  # ten sam komunikat z kilku połączeń naraz
        self._last_note = (msg, time.time())
        try:
            self._notify(msg, error)
        except Exception as e:  # powiadomienie nigdy nie może przerwać odtwarzania
            self.log('powiadomienie: %r' % (e,))

    @property
    def port(self):
        return self.server_address[1]
