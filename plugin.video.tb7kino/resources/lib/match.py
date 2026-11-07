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


# Słowa, które w nazwie pliku kończą tytuł (rok, odcinek, jakość, wersja językowa, źródło...)
TAGS = set('''
pl plsub pldub dub dubbing lektor napisy sub subs subbed multi eng en ger de fr ita es rus
web webdl webrip dl bdrip brrip bluray blu ray dvdrip dvd dvdscr hdrip hdtv hdtc hdcam cam ts tc
xvid divx x264 x265 h264 h265 hevc avc aac ac3 dts dd dd2 dd5 ddp ddp5 eac3 atmos truehd mp3
hdr hdr10 dv sdr uhd hd fhd 4k imax repack proper rerip extended uncut unrated remastered
directors cut limited internal complete season sezon odcinek amzn nf dsnp hmax atvp hulu ma pmtp
mkv avi mp4 mov mpg mpeg ts m2ts wmv
'''.split())

RE_BOUNDARY = re.compile(r'^(?:(?:19|20)\d{2}|s\d{1,2}(?:e\d{1,3})*|e\d{1,3}|\d{1,2}x\d{1,3}|\d{3,4}p|\d{1,2}bit)$')
ARTICLES = ('the', 'a', 'an')


def _boundary(tok):
    return tok in TAGS or bool(RE_BOUNDARY.match(tok))


def _title_variants(titles):
    """Tokeny każdego tytułu (także bez przedimka) i par tytułów 'polski + oryginalny'."""
    base = []
    for t in titles:
        toks = norm(t).split()
        if not toks:
            continue
        for v in (toks, toks[1:] if toks[0] in ARTICLES and len(toks) > 1 else None):
            if v and v not in base:
                base.append(v)
    out = list(base)
    for a in base:
        for b in base:
            if a != b and a + b not in out:
                out.append(a + b)
    return out


def title_match(filename, titles):
    """Nazwa pliku zaczyna się dokładnie od tytułu, a zaraz po nim jest rok/odcinek/jakość/koniec.
    'Wonder.2017.PL' pasuje do 'Wonder', ale 'Wonder.Woman.2017' i 'Wonder.Years.S02E05' już nie."""
    ftoks = norm(re.sub(r'\.[a-z0-9]{2,4}$', ' ', filename or '', flags=re.I)).split()
    for ttoks in _title_variants(titles):
        n = len(ttoks)
        if ftoks[:n] == ttoks and (len(ftoks) == n or _boundary(ftoks[n])):
            return True
    return False


def matches(filename, titles, year=None, season=None, episode=None):
    f = norm(filename)
    if not title_match(filename, [t for t in titles if t]):
        return False
    if season is not None:
        s, e = int(season), int(episode)
        pat = r'(?:s0?%d ?e0?%d(?!\d))|(?:\b%dx0?%d(?!\d))' % (s, e, s, e)
        return bool(re.search(pat, f))
    if year:
        in_title = {y for t in titles for y in re.findall(r'\b(?:19|20)\d{2}\b', norm(t))}
        years = [int(y) for y in re.findall(r'\b(19\d{2}|20\d{2})\b', f) if y not in in_title]
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
