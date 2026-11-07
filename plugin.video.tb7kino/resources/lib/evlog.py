# -*- coding: utf-8 -*-
"""Dziennik zdarzeń odtwarzania (diagnostyka): krótkie wpisy z godziną w profilu addonu.

Piszą do niego usługa (proxy, odtwarzacz) i plugin; menu 'Dziennik odtwarzania' go pokazuje.
"""
import os
import re
import threading
import time

MAX_LINES = 400
_lock = threading.Lock()
_path = [None]


def init(profile_dir):
    _path[0] = os.path.join(profile_dir, 'events.log')
    try:
        os.makedirs(profile_dir, exist_ok=True)
    except Exception:
        pass


def short(text, n=140):
    """Bez długich adresów i tokenów: zostaje host i nazwa pliku."""
    text = re.sub(r'https?://([^/\s\'"]+)/[^\s\'"]*/([^/\s\'"?]+)', r'\1/…/\2', str(text))
    text = re.sub(r'(HTTPS?ConnectionPool\(host=)', '', text)
    return text if len(text) <= n else text[:n] + '…'


def write(msg):
    if not _path[0]:
        return
    line = '%s  %s\n' % (time.strftime('%d.%m %H:%M:%S'), short(msg))
    with _lock:
        try:
            with open(_path[0], 'a', encoding='utf-8') as f:
                f.write(line)
            if os.path.getsize(_path[0]) > MAX_LINES * 220:
                with open(_path[0], encoding='utf-8') as f:
                    lines = f.readlines()[-MAX_LINES // 2:]
                with open(_path[0], 'w', encoding='utf-8') as f:
                    f.writelines(lines)
        except Exception:
            pass


def read(last=80):
    try:
        with open(_path[0], encoding='utf-8') as f:
            return f.readlines()[-last:]
    except Exception:
        return []


def clear():
    try:
        os.remove(_path[0])
    except Exception:
        pass
