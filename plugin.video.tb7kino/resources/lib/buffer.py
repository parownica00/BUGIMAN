# -*- coding: utf-8 -*-
"""Bufor startowy (start w pauzie aż zbierze się N sekund zapasu) i dobór pamięci bufora Kodi."""
import json
import os
import re
import time

import xbmc
import xbmcgui
import xbmcvfs


# ---- bufor startowy -------------------------------------------------------------
def buffered_seconds(player):
    """Ile sekund filmu jest wczytane przed bieżącą pozycją (None gdy Kodi nie podaje)."""
    try:
        total = player.getTotalTime()
        cur = player.getTime()
        cache = float(xbmc.getInfoLabel('Player.ProgressCache') or 0)
    except Exception:
        return None
    if total <= 0 or cache <= 0:
        return None
    return max(0.0, cache * total / 100.0 - cur)


def prebuffer(seconds, title):
    """Wywoływane po setResolvedUrl: pauzuje start i czeka na zapas bufora."""
    if not seconds:
        return
    player, mon = xbmc.Player(), xbmc.Monitor()
    t0 = time.time()
    while not player.isPlayingVideo():
        if mon.waitForAbort(0.25) or time.time() - t0 > 60:
            return
    if not xbmc.getCondVisibility('Player.Paused'):
        player.pause()

    dlg = xbmcgui.DialogProgress()
    dlg.create(title or 'Buforowanie', 'Buforowanie...')
    start = last_change = time.time()
    last = -1.0
    try:
        while player.isPlayingVideo() and not mon.abortRequested():
            if dlg.iscanceled():
                break
            now = time.time()
            b = buffered_seconds(player)
            if b is not None:
                if b > last + 0.5:
                    last, last_change = b, now
                dlg.update(min(100, int(100 * b / seconds)),
                           'Bufor: %d z %d s\n[COLOR gray]Anuluj = odtwarzaj od razu[/COLOR]' % (b, seconds))
                if b >= seconds or now - last_change > 15:  # cel osiągnięty albo bufor pełny / stoi
                    break
            else:
                wait = min(seconds, 30)  # Kodi nie podaje stanu bufora - czekamy krótko wg czasu
                dlg.update(min(100, int(100 * (now - start) / wait)), 'Buforowanie...')
                if now - start >= wait:
                    break
            if now - start > max(seconds * 4, 90):
                break
            if mon.waitForAbort(0.5):
                return
    finally:
        dlg.close()
    if player.isPlayingVideo() and xbmc.getCondVisibility('Player.Paused'):
        player.pause()


# ---- dobór pamięci bufora ---------------------------------------------------------
def _rpc(method, **params):
    r = json.loads(xbmc.executeJSONRPC(json.dumps(
        {'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params})))
    if 'error' in r:
        raise RuntimeError(r['error'].get('message', 'JSON-RPC error'))
    return r.get('result')


def ram_mb():
    m = re.search(r'(\d+)', xbmc.getInfoLabel('System.Memory(total)') or '')
    return int(m.group(1)) if m else 0


def target_mb(ram):
    if ram >= 3500:
        return 512
    if ram >= 1800:
        return 256
    return 128


def _label_mb(label):
    m = re.search(r'([\d.,]+)\s*(GB|MB)', label or '', re.I)
    if not m:
        return None
    v = float(m.group(1).replace(',', '.'))
    return int(v * 1024) if m.group(2).upper() == 'GB' else int(v)


def _label_factor(label):
    m = re.search(r'([\d.,]+)\s*x', label or '', re.I)
    return float(m.group(1).replace(',', '.')) if m else None


def _pick(setting, wanted, parse):
    """Wybiera wartość ustawienia Kodi najbliższą (i nie większą) od celu."""
    opts = setting.get('options') or []
    best = None
    for o in opts:
        n = parse(o.get('label', ''))
        if n is None:
            continue
        if n <= wanted and (best is None or n > best[0]):
            best = (n, o['value'], o['label'])
    if best:
        return best[1], best[2]
    if 'minimum' in setting and 'maximum' in setting:
        v = max(setting['minimum'], min(setting['maximum'], wanted))
        return v, str(v)
    return None, None


def setup_cache(addon_name):
    """Kodi 20+: ustawienia GUI przez JSON-RPC. Kodi 19: advancedsettings.xml."""
    ram = ram_mb()
    want = target_mb(ram)
    dlg = xbmcgui.Dialog()
    found = {}
    for params in ({'level': 'expert', 'filter': {'section': 'services', 'category': 'filecache'}},
                   {'level': 'expert'}):
        try:
            res = _rpc('Settings.GetSettings', **params)
            found = {s['id']: s for s in (res or {}).get('settings', []) if s.get('id', '').startswith('filecache.')}
        except Exception:
            found = {}
        if found:
            break
    kodi_major = int((re.match(r'(\d+)', xbmc.getInfoLabel('System.BuildVersion') or '') or [0, 0])[1] or 0)

    if not found and kodi_major >= 20:
        dlg.ok(addon_name, 'Ustaw ręcznie: Ustawienia → Usługi → Buforowanie (poziom Ekspert):\n'
                           'rozmiar pamięci [B]%d MB[/B], współczynnik odczytu [B]20x[/B]. Potem restart Kodi.' % want)
        return

    if 'filecache.memorysize' in found:
        mem_val, mem_label = _pick(found['filecache.memorysize'], want, _label_mb)
        rf = found.get('filecache.readfactor')
        rf_val, rf_label = _pick(rf, 20, _label_factor) if rf else (None, None)
        if mem_val is None:
            dlg.ok(addon_name, 'Nie udało się odczytać opcji bufora. Ustaw ręcznie:\n'
                               'Ustawienia → Usługi → Buforowanie (poziom Ekspert).')
            return
        if not dlg.yesno(addon_name, 'Pamięć urządzenia: %s MB\n\nUstawić bufor na [B]%s[/B]%s?'
                         % (ram or '?', mem_label, (' i odczyt [B]%s[/B]' % rf_label) if rf_val is not None else '')):
            return
        _rpc('Settings.SetSettingValue', setting='filecache.memorysize', value=mem_val)
        if rf_val is not None:
            _rpc('Settings.SetSettingValue', setting='filecache.readfactor', value=rf_val)
        dlg.ok(addon_name, 'Gotowe. Zrestartuj Kodi, żeby nowy bufor zaczął działać.')
        return

    # Kodi 19: advancedsettings.xml
    path = xbmcvfs.translatePath('special://userdata/advancedsettings.xml')
    if not dlg.yesno(addon_name, 'Pamięć urządzenia: %s MB\n\nZapisać bufor [B]%d MB[/B] i odczyt [B]20x[/B] '
                                 'w advancedsettings.xml?' % (ram or '?', want)):
        return
    block = ('<cache>\n        <memorysize>%d</memorysize>\n        <readfactor>20</readfactor>\n'
             '    </cache>' % (want * 1024 * 1024))
    xml = ''
    if os.path.exists(path):
        with open(path, encoding='utf-8') as f:
            xml = f.read()
        with open(path + '.bak', 'w', encoding='utf-8') as f:
            f.write(xml)
    if '<advancedsettings' not in xml:
        xml = '<advancedsettings version="1.0">\n    %s\n</advancedsettings>\n' % block
    elif re.search(r'<cache>.*?</cache>', xml, re.S):
        xml = re.sub(r'<cache>.*?</cache>', block, xml, flags=re.S)
    else:
        xml = xml.replace('</advancedsettings>', '    %s\n</advancedsettings>' % block)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(xml)
    dlg.ok(addon_name, 'Zapisano. Zrestartuj Kodi, żeby nowy bufor zaczął działać.')


# ---- cierpliwe połączenia sieciowe Kodi (advancedsettings.xml) --------------------
NETWORK = {
    'curlclienttimeout': '30',   # s na nawiązanie połączenia (domyślnie 10)
    'curllowspeedtime': '300',   # s bez danych, zanim Kodi zerwie odtwarzanie (domyślnie 20)
    'curlretries': '10',         # ponowne próby po błędzie sieci (domyślnie 2)
}


def ensure_network(path=None):
    """Dopisuje/aktualizuje <network> w advancedsettings.xml. Zwraca True, gdy plik się zmienił
    (wtedy potrzebny jest jednorazowy restart Kodi)."""
    path = path or xbmcvfs.translatePath('special://userdata/advancedsettings.xml')
    xml = ''
    if os.path.exists(path):
        with open(path, encoding='utf-8') as f:
            xml = f.read()
    original = xml
    if '<advancedsettings' not in xml:
        xml = '<advancedsettings version="1.0">\n</advancedsettings>\n'
    net = re.search(r'<network>(.*?)</network>', xml, re.S)
    body = net.group(1) if net else '\n'
    for tag, value in NETWORK.items():
        current = re.search(r'<%s>\s*(\d+)\s*</%s>' % (tag, tag), body)
        if current and int(current.group(1)) >= int(value):
            continue  # użytkownik ma już równie cierpliwe (albo większe) ustawienie
        if current:
            body = body.replace(current.group(0), '<%s>%s</%s>' % (tag, value, tag))
        else:
            body = body.rstrip() + '\n        <%s>%s</%s>\n    ' % (tag, value, tag)
    block = '<network>%s</network>' % body
    if net:
        xml = xml.replace(net.group(0), block)
    else:
        xml = re.sub(r'</advancedsettings>', '    %s\n</advancedsettings>' % block, xml, count=1)
    if xml == original:
        return False
    if original and not os.path.exists(path + '.tb7kino.bak'):
        with open(path + '.tb7kino.bak', 'w', encoding='utf-8') as f:
            f.write(original)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(xml)
    return True
