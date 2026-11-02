# -*- coding: utf-8 -*-
"""Usługa TB7 Kino: lokalne proxy, które wznawia zerwane połączenia podczas odtwarzania."""
import json
import os
import sys
import threading
from urllib.parse import parse_qsl

import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'resources', 'lib'))
import proxy  # noqa: E402
import match  # noqa: E402
from tb7 import TB7  # noqa: E402

WIN = xbmcgui.Window(10000)
PROP = 'tb7kino.'
STREAMS = {}
LOCK = threading.Lock()


def log(msg):
    xbmc.log('[TB7 Kino proxy] %s' % msg, xbmc.LOGINFO)


KODI_OPTIONS = ('verifypeer', 'connection', 'seekable', 'noshout')


def split_stream(stream):
    """'url|Naglowek=wartosc&...' -> (url, {naglowki HTTP}) bez opcji samego Kodi."""
    url, _, hdr = stream.partition('|')
    return url, {k: v for k, v in parse_qsl(hdr) if k.lower() not in KODI_OPTIONS}


def notify(msg):
    xbmc.log('[TB7 Kino proxy] %s' % msg, xbmc.LOGERROR)
    xbmcgui.Dialog().notification('TB7 Kino', msg, xbmcgui.NOTIFICATION_ERROR, 6000)


def make_resolver(name):
    def resolve():
        if not name:
            return None
        addon = xbmcaddon.Addon()
        c = TB7(addon.getSetting('tb7_user'), addon.getSetting('tb7_pass'),
                xbmcvfs.translatePath(addon.getAddonInfo('profile')))
        c.login()
        owned = [x for x in c.library() if match.norm(x['filename']) == match.norm(name)]
        if not owned:
            log('nowy link: pliku nie ma już na koncie')
            return None
        return split_stream(c.playable(owned[0]['url']))
    return resolve


def lookup(token):
    with LOCK:
        if token in STREAMS:
            return STREAMS[token]
        raw = WIN.getProperty(PROP + 's.' + token)
        if not raw:
            return None
        info = json.loads(raw)
        url, headers = split_stream(info['stream'])
        st = proxy.Stream(url, headers, make_resolver(info.get('name')), log)
        STREAMS[token] = st
        return st


def main():
    server = proxy.ProxyServer(lookup, log, notify=notify)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    WIN.setProperty(PROP + 'port', str(server.port))
    log('działa na porcie %d' % server.port)
    xbmc.Monitor().waitForAbort()
    WIN.clearProperty(PROP + 'port')
    server.shutdown()
    server.server_close()
    log('zatrzymano')


if __name__ == '__main__':
    main()
