# -*- coding: utf-8 -*-
"""Dopasowanie nazw plików z TB7 do tytułu z TMDB + rozpoznanie jakości/wersji językowej."""
import re
import unicodedata
from urllib.parse import unquote

PL = str.maketrans('łŁ', 'lL')


def norm(text):
    text = unicodedata.normalize('NFKD', (text or '').translate(PL))
    text = ''.join(c for c in text if not unicodedata.combining(c)).lower()
    text = text.replace('&', ' and ')
    return re.sub(r'[^a-z0-9]+', ' ', text).strip()


def _tokens(title):
    stop = {'the', 'a', 'an', 'of', 'i', 'w', 'z', 'and'}
    toks = [t for t in norm(title).split() if t not in stop]
    return toks or norm(title).split()


def matches(filename, titles, year=None, season=None, episode=None):
    f = norm(filename)
    ftoks = set(f.split())
    if not any(all(t in ftoks for t in _tokens(t)) for t in titles if t):
        return False
    if season is not None:
        s, e = int(season), int(episode)
        pat = r'(?:s0?%d ?e0?%d(?!\d))|(?:\b%dx0?%d(?!\d))' % (s, e, s, e)
        return bool(re.search(pat, f))
    if year:
        years = [int(y) for y in re.findall(r'\b(19\d{2}|20\d{2})\b', f)]
        if years and all(abs(y - int(year)) > 1 for y in years):
            return False
    return True


def quality(filename):
    f = filename.lower()
    if re.search(r'2160p|\b4k\b|uhd', f):
        return '4K', 4
    if '1080' in f:
        return '1080p', 3
    if '720' in f:
        return '720p', 2
    if re.search(r'480p|dvdrip|xvid|\bsd\b', f):
        return 'SD', 1
    return '?', 0


def language(filename):
    f = norm(filename)
    tags = []
    if re.search(r'\bdub(bing)?\b', f):
        tags.append('Dubbing')
    if re.search(r'\blektor\b|\bpl lektor\b', f):
        tags.append('Lektor')
    if re.search(r'\bnapisy\b|\bsub(s|bed)? ?pl\b|\bplsub', f):
        tags.append('Napisy')
    if not tags and re.search(r'\bpl\b|\bpolish\b', f):
        tags.append('PL')
    return ' '.join(tags)


RE_CRC = re.compile(r'\.[0-9a-f]{3}(\.(?:avi|mkv|mp4|mpg|mov|ts|mts|m2ts))$', re.I)


def _variants(name):
    name = unquote(name or '').strip()
    out = {norm(name)}
    stripped = RE_CRC.sub(r'\1', name)
    if stripped != name:
        out.add(norm(stripped))
    return {v for v in out if v}


def same_file(a, b):
    """Czy dwie nazwy oznaczają ten sam plik (z tolerancją na kod CRC TWOJPLIK)."""
    return bool(_variants(a) & _variants(b))
