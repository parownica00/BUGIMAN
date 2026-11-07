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
import evlog  # noqa: E402
import buffer  # noqa: E402
import match  # noqa: E402
from tb7 import TB7  # noqa: E402

WIN = xbmcgui.Window(10000)
PROP = 'tb7kino.'
STREAMS = {}
LOCK = threading.Lock()


def log(msg):
    xbmc.log('[TB7 Kino proxy] %s' % msg, xbmc.LOGINFO)
    evlog.write('proxy: %s' % msg)


def fmt(sec):
    sec = int(sec or 0)
    return '%d:%02d:%02d' % (sec // 3600, sec % 3600 // 60, sec % 60)


class PlayerWatch(xbmc.Player):
    """Zapisuje w dzienniku, jak i w której minucie film się skończył."""

    def __init__(self):
        xbmc.Player.__init__(self)
        self.pos = self.total = 0.0
        self.cache = ''
        self.file = ''
        self.active = False

    def poll(self):
        if self.active and self.isPlayingVideo():
            try:
                self.pos, self.total = self.getTime(), self.getTotalTime()
                self.cache = xbmc.getInfoLabel('Player.ProgressCache')
            except Exception:
                pass

    def where(self):
        return '%s z %s (bufor do %s%%)' % (fmt(self.pos), fmt(self.total), self.cache or '?')

    def onAVStarted(self):
        try:
            self.file = self.getPlayingFile()
        except Exception:
            self.file = ''
        self.active = 'tb7kino' in self.file or '127.0.0.1' in self.file or 'plugin.video.tb7kino' in self.file \
            or bool(WIN.getProperty(PROP + 'playing'))
        if self.active:
            self.pos = 0.0
            evlog.write('START: %s' % self.file.split('|')[0])

    def onPlayBackStopped(self):
        if self.active:
            evlog.write('ZATRZYMANY przez użytkownika przy %s' % self.where())
        self.active = False
        WIN.clearProperty(PROP + 'playing')

    def onPlayBackEnded(self):
        if self.active:
            early = self.total and self.pos < self.total - 120
            evlog.write('%s przy %s' % ('!!! FILM ZAMKNIĘTY PRZEDWCZEŚNIE (Kodi uznał, że plik się skończył)'
                                         if early else 'KONIEC filmu', self.where()))
        self.active = False
        WIN.clearProperty(PROP + 'playing')

    def onPlayBackError(self):
        if self.active:
            evlog.write('!!! BŁĄD ODTWARZACZA Kodi przy %s' % self.where())
        self.active = False
        WIN.clearProperty(PROP + 'playing')


KODI_OPTIONS = ('verifypeer', 'connection', 'seekable', 'noshout')


def split_stream(stream):
    """'url|Naglowek=wartosc&...' -> (url, {naglowki HTTP}) bez opcji samego Kodi."""
    url, _, hdr = stream.partition('|')
    return url, {k: v for k, v in parse_qsl(hdr) if k.lower() not in KODI_OPTIONS}


def notify(msg, error=True):
    xbmc.log('[TB7 Kino proxy] %s' % msg, xbmc.LOGWARNING if error else xbmc.LOGINFO)
    xbmcgui.Dialog().notification('TB7 Kino', msg,
                                  xbmcgui.NOTIFICATION_WARNING if error else xbmcgui.NOTIFICATION_INFO, 6000)


def tune_kodi_network():
    """Jednorazowo: Kodi ma czekać na dane zamiast zamykać film po 20 s bez danych."""
    if xbmcaddon.Addon().getSetting('use_proxy') == 'false':
        return
    try:
        if buffer.ensure_network():
            log('zapisano ustawienia sieci w advancedsettings.xml')
            xbmcgui.Dialog().notification(
                'TB7 Kino', 'Zrestartuj Kodi raz, żeby filmy się nie zamykały przy zerwaniu sieci',
                xbmcgui.NOTIFICATION_INFO, 10000)
    except Exception as e:
        log('ustawienia sieci: %r' % (e,))


def make_resolver(name):
    def resolve():
        if not name:
            return None
        addon = xbmcaddon.Addon()
        c = TB7(addon.getSetting('tb7_user'), addon.getSetting('tb7_pass'),
                xbmcvfs.translatePath(addon.getAddonInfo('profile')))
        c.login()
        owned = [x for x in c.library() if not x['expired'] and
                 (match.same_file(x['filename'], name) or match.same_file(x['url_name'], name))]
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
    evlog.init(xbmcvfs.translatePath(xbmcaddon.Addon().getAddonInfo('profile')))
    tune_kodi_network()
    server = proxy.ProxyServer(lookup, log, notify=notify)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    WIN.setProperty(PROP + 'port', str(server.port))
    log('działa na porcie %d' % server.port)
    watch = PlayerWatch()
    mon = xbmc.Monitor()
    while not mon.waitForAbort(1):
        watch.poll()
    WIN.clearProperty(PROP + 'port')
    server.shutdown()
    server.server_close()
    log('zatrzymano')


if __name__ == '__main__':
    main()
