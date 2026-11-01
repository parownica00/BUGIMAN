# -*- coding: utf-8 -*-
import os
import sys
from urllib.parse import parse_qsl, urlencode

import xbmc
import xbmcaddon
import xbmcgui
import xbmcplugin
import xbmcvfs

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'resources', 'lib'))
from tb7 import TB7, TB7Error  # noqa: E402
from meta import Meta, img  # noqa: E402
import match  # noqa: E402
import vault  # noqa: E402

ADDON = xbmcaddon.Addon()
NAME = ADDON.getAddonInfo('name')
URL = sys.argv[0]
HANDLE = int(sys.argv[1])
ARGS = dict(parse_qsl(sys.argv[2][1:]))
PROFILE = xbmcvfs.translatePath(ADDON.getAddonInfo('profile'))
SECRETS = os.path.join(os.path.dirname(__file__), 'resources', 'data', 'secrets.json')


def setting(k):
    return ADDON.getSetting(k)


def u(**kw):
    return URL + '?' + urlencode(kw)


def notify(msg, icon=xbmcgui.NOTIFICATION_INFO):
    xbmcgui.Dialog().notification(NAME, msg, icon, 5000)


def unlock_keys(ask_always=True):
    """Odszyfrowuje klucze API z sejfu hasłem i zapisuje je w ustawieniach."""
    blob = vault.load(SECRETS)
    if not blob:
        if ask_always:
            xbmcgui.Dialog().ok(NAME, 'Brak zapisanych kluczy w tej wersji addonu.')
        return False
    for attempt in range(3):
        pw = xbmcgui.Dialog().input('Hasło do kluczy API', type=xbmcgui.INPUT_ALPHANUM,
                                    option=xbmcgui.ALPHANUM_HIDE_INPUT)
        if not pw:
            return False
        try:
            keys = vault.decrypt(blob, pw)
        except ValueError:
            notify('Nieprawidłowe hasło (%d/3)' % (attempt + 1), xbmcgui.NOTIFICATION_ERROR)
            continue
        for k, v in keys.items():
            ADDON.setSetting(k, v)
        notify('Klucze API uzupełnione')
        return True
    return False


def meta():
    if not setting('tmdb_key'):
        unlock_keys(ask_always=False)
    return Meta(setting('tmdb_key'), setting('omdb_key'), setting('language'))


def check_updates():
    xbmc.executebuiltin('UpdateAddonRepos')
    xbmc.executebuiltin('UpdateLocalAddons')
    notify('Sprawdzam aktualizacje - wersja %s' % ADDON.getAddonInfo('version'))


def tb7():
    c = TB7(setting('tb7_user'), setting('tb7_pass'), PROFILE)
    c.login()
    return c


# ---- budowanie elementów listy ------------------------------------------------
def set_info(li, info, kind='video'):
    try:
        tag = li.getVideoInfoTag()
        tag.setMediaType(info.get('mediatype', 'video'))
        tag.setTitle(info.get('title', ''))
        tag.setPlot(info.get('plot', ''))
        if info.get('year'):
            tag.setYear(int(info['year']))
        if info.get('rating'):
            tag.setRating(float(info['rating']), int(info.get('votes', 0)), 'tmdb', True)
        if info.get('genre'):
            tag.setGenres(info['genre'])
        if info.get('originaltitle'):
            tag.setOriginalTitle(info['originaltitle'])
        if info.get('season') is not None:
            tag.setSeason(int(info['season']))
        if info.get('episode') is not None:
            tag.setEpisode(int(info['episode']))
        if info.get('imdb'):
            tag.setUniqueIDs({'imdb': info['imdb'], 'tmdb': str(info.get('tmdb', ''))}, 'tmdb')
    except AttributeError:  # Kodi 19
        li.setInfo('video', {k: v for k, v in info.items() if k not in ('imdb', 'tmdb', 'votes')})


def add(label, url, folder=True, info=None, art=None, playable=False, ctx=None):
    li = xbmcgui.ListItem(label)
    if info:
        set_info(li, info)
    if art:
        li.setArt(art)
    if playable:
        li.setProperty('IsPlayable', 'true')
    if ctx:
        li.addContextMenuItems(ctx)
    xbmcplugin.addDirectoryItem(HANDLE, url, li, folder)


def end(content='videos'):
    xbmcplugin.setContent(HANDLE, content)
    xbmcplugin.endOfDirectory(HANDLE)


def art_for(d):
    poster = img(d.get('poster_path'))
    return {'poster': poster, 'thumb': poster, 'icon': poster,
            'fanart': img(d.get('backdrop_path'), 'w1280')}


# ---- menu ----------------------------------------------------------------------
def root():
    if not setting('tmdb_key') and os.path.exists(SECRETS):
        unlock_keys(ask_always=False)
    add('[B]Szukaj filmu[/B]', u(action='search', kind='movie'))
    add('[B]Szukaj serialu[/B]', u(action='search', kind='tv'))
    add('Filmy - na topie (tydzień)', u(action='list', kind='movie', name='trending'))
    add('Filmy - popularne', u(action='list', kind='movie', name='popular'))
    add('Filmy - teraz w kinach', u(action='list', kind='movie', name='now_playing'))
    add('Filmy - najwyżej oceniane', u(action='list', kind='movie', name='top_rated'))
    add('Seriale - na topie (tydzień)', u(action='list', kind='tv', name='trending'))
    add('Seriale - popularne', u(action='list', kind='tv', name='popular'))
    add('Seriale - najwyżej oceniane', u(action='list', kind='tv', name='top_rated'))
    add('Szukaj bezpośrednio w TB7', u(action='raw_search'))
    add('Moje pliki na koncie TB7', u(action='library'))
    add('Stan konta TB7', u(action='account'), folder=False)
    add('Odblokuj klucze API hasłem', u(action='unlock'), folder=False)
    add('Sprawdź aktualizacje  [COLOR gray](wersja %s)[/COLOR]' % ADDON.getAddonInfo('version'),
        u(action='update'), folder=False)
    add('Ustawienia', u(action='settings'), folder=False)
    end('files')


def list_results(kind, data, nxt=None):
    for d in data.get('results', []):
        k = d.get('media_type', kind)
        if k not in ('movie', 'tv'):
            continue
        title = d.get('title') or d.get('name') or ''
        date = d.get('release_date') or d.get('first_air_date') or ''
        year = date[:4]
        rating = d.get('vote_average') or 0
        label = '%s (%s)  [COLOR gold]★ %.1f[/COLOR]' % (title, year or '?', rating)
        info = {'title': title, 'year': year, 'plot': d.get('overview', ''), 'rating': rating,
                'votes': d.get('vote_count', 0), 'mediatype': 'movie' if k == 'movie' else 'tvshow',
                'originaltitle': d.get('original_title') or d.get('original_name')}
        target = u(action='sources', tmdb=d['id']) if k == 'movie' else u(action='seasons', tmdb=d['id'])
        add(label, target, info=info, art=art_for(d))
    if nxt and data.get('page', 1) < data.get('total_pages', 1):
        add('[I]Następna strona >>[/I]', nxt)
    end('movies' if kind == 'movie' else 'tvshows')


def do_search(kind):
    q = ARGS.get('q') or xbmcgui.Dialog().input('Szukaj ' + ('filmu' if kind == 'movie' else 'serialu'))
    if not q:
        return xbmcplugin.endOfDirectory(HANDLE, succeeded=False)
    page = int(ARGS.get('page', 1))
    list_results(kind, meta().search(kind, q, page),
                 u(action='search', kind=kind, q=q, page=page + 1))


def do_list(kind, name):
    page = int(ARGS.get('page', 1))
    list_results(kind, meta().listing(kind, name, page),
                 u(action='list', kind=kind, name=name, page=page + 1))


def seasons(tv_id):
    d = meta().details('tv', tv_id)
    for s in d.get('seasons', []):
        if s.get('season_number', 0) == 0:
            continue
        a = art_for(d)
        if s.get('poster_path'):
            a.update(poster=img(s['poster_path']), thumb=img(s['poster_path']))
        add('%s  (%s odc.)' % (s.get('name'), s.get('episode_count', '?')),
            u(action='episodes', tmdb=tv_id, season=s['season_number']),
            info={'title': s.get('name'), 'plot': s.get('overview') or d.get('overview', ''),
                  'mediatype': 'season', 'season': s['season_number']}, art=a)
    end('seasons')


def episodes(tv_id, season):
    m = meta()
    d = m.details('tv', tv_id)
    sd = m.season(tv_id, season)
    for e in sd.get('episodes', []):
        a = art_for(d)
        if e.get('still_path'):
            a['thumb'] = img(e['still_path'], 'w300')
        label = '%dx%02d  %s' % (int(season), e['episode_number'], e.get('name', ''))
        add(label, u(action='sources', tmdb=tv_id, season=season, episode=e['episode_number']),
            info={'title': e.get('name'), 'plot': e.get('overview', ''), 'rating': e.get('vote_average'),
                  'season': int(season), 'episode': e['episode_number'], 'mediatype': 'episode'}, art=a)
    end('episodes')


# ---- źródła TB7 -----------------------------------------------------------------
def titles_for(d, kind):
    t = [d.get('title') or d.get('name'), d.get('original_title') or d.get('original_name')]
    alt = d.get('alternative_titles', {})
    for a in alt.get('titles', []) + alt.get('results', []):
        if a.get('iso_3166_1') in ('PL', 'US', 'GB'):
            t.append(a.get('title'))
    seen, out = set(), []
    for x in t:
        if x and match.norm(x) not in seen:
            seen.add(match.norm(x))
            out.append(x)
    return out


def sources(tmdb_id, season=None, episode=None):
    kind = 'tv' if season else 'movie'
    m = meta()
    d = m.details(kind, tmdb_id)
    titles = titles_for(d, kind)
    year = (d.get('release_date') or d.get('first_air_date') or '')[:4]
    imdb = d.get('imdb_id') or d.get('external_ids', {}).get('imdb_id')

    if season:
        tag = 'S%02dE%02d' % (int(season), int(episode))
        queries = ['%s %s' % (t, tag) for t in titles[:2]]
    else:
        queries = ['%s %s' % (t, year) for t in titles[:2]] + titles[:1]

    try:
        c = tb7()
        found, seen = [], set()
        dlg = xbmcgui.DialogProgress()
        dlg.create(NAME, 'Szukam w TB7...')
        for i, q in enumerate(queries):
            if dlg.iscanceled():
                break
            dlg.update(int(100 * i / len(queries)), 'Szukam: ' + q)
            for r in c.search(q):
                if r['url'] not in seen:
                    seen.add(r['url'])
                    found.append(r)
        dlg.close()
        lib_names = {match.norm(x['filename']) for x in c.library()}
        left = c.account_info()
    except TB7Error as e:
        return error(str(e))

    min_mb = int(setting('min_size_mb') or 0)
    found = [r for r in found if r['size_mb'] >= min_mb]
    if setting('strict_filter') == 'true':
        found = [r for r in found if match.matches(r['filename'], titles, year, season, episode)]
    found.sort(key=lambda r: (match.quality(r['filename'])[1], r['size_mb']), reverse=True)

    # nagłówek z opisem i ocenami
    ratings = ['TMDB %.1f' % (d.get('vote_average') or 0)]
    for k, v in m.omdb_ratings(imdb).items():
        ratings.append('%s %s' % (k, v))
    genres = ', '.join(g['name'] for g in d.get('genres', []))
    plot = '[B]%s[/B]\n%s\n\n%s' % (' | '.join(ratings), genres, d.get('overview', ''))
    head_title = titles[0] + (' %s' % ('S%02dE%02d' % (int(season), int(episode))) if season else ' (%s)' % year)
    add('[COLOR gold]ⓘ %s  •  %s[/COLOR]' % (head_title, ' | '.join(ratings)),
        u(action='plot', title=head_title, text=plot), folder=False,
        info={'title': head_title, 'plot': plot}, art=art_for(d))
    add('[COLOR gray]Transfer na koncie: %s  •  znaleziono: %d[/COLOR]' % (left or '?', len(found)),
        u(action='noop'), folder=False)

    base_info = {'title': titles[0], 'plot': plot, 'year': year, 'imdb': imdb, 'tmdb': tmdb_id,
                 'rating': d.get('vote_average'), 'mediatype': 'episode' if season else 'movie',
                 'genre': [g['name'] for g in d.get('genres', [])]}
    if season:
        base_info.update(season=int(season), episode=int(episode))
    for r in found:
        q, _ = match.quality(r['filename'])
        lang = match.language(r['filename'])
        on_acc = match.norm(r['filename']) in lib_names
        label = '[B]%s[/B] %s | %s | %s%s\n%s' % (
            q, ('[COLOR lime]%s[/COLOR]' % lang) if lang else '', r['size'], r['host'],
            '  [COLOR cyan]NA KONCIE[/COLOR]' if on_acc else '', r['filename'])
        add(label.replace('\n', '  •  '), u(action='play', link=r['url'], size=r['size'], name=r['filename']),
            folder=False, playable=True, info=base_info, art=art_for(d))
    if not found:
        add('[I]Brak pasujących plików - spróbuj „Szukaj bezpośrednio w TB7”[/I]',
            u(action='raw_search', q=titles[0]), folder=True)
    end('videos')


def raw_search():
    q = ARGS.get('q') or xbmcgui.Dialog().input('Fraza do wyszukania w TB7')
    if not q:
        return xbmcplugin.endOfDirectory(HANDLE, succeeded=False)
    try:
        rows = tb7().search(q, max_pages=8)
    except TB7Error as e:
        return error(str(e))
    rows.sort(key=lambda r: r['size_mb'], reverse=True)
    for r in rows:
        add('%s  [COLOR gray]%s | %s[/COLOR]' % (r['filename'], r['size'], r['host']),
            u(action='play', link=r['url'], size=r['size'], name=r['filename']),
            folder=False, playable=True, info={'title': r['filename']})
    end('videos')


def library():
    try:
        files = tb7().library()
    except TB7Error as e:
        return error(str(e))
    for f in files:
        add('%s  [COLOR gray]wygasa: %s[/COLOR]' % (f['filename'], f['expires'] or '?'),
            u(action='play_lib', link=f['url']), folder=False, playable=True,
            info={'title': f['filename']})
    end('videos')


def play(link, size, name):
    try:
        c = tb7()
        owned = [x for x in c.library() if match.norm(x['filename']) == match.norm(name)]
        if owned:  # plik już na koncie - bez zużywania transferu
            stream = c.playable(owned[0]['url'])
        else:
            if setting('confirm_buy') == 'true':
                left = c.account_info()
                if not xbmcgui.Dialog().yesno(
                        NAME, '%s\n\nPobranie zużyje [B]%s[/B] transferu.\nPozostało: [B]%s[/B]\n\nKontynuować?'
                        % (name, size, left or '?')):
                    return xbmcplugin.setResolvedUrl(HANDLE, False, xbmcgui.ListItem())
            stream = c.get_stream(link)
    except TB7Error as e:
        notify(str(e), xbmcgui.NOTIFICATION_ERROR)
        return xbmcplugin.setResolvedUrl(HANDLE, False, xbmcgui.ListItem())
    li = xbmcgui.ListItem(path=stream)
    xbmcplugin.setResolvedUrl(HANDLE, True, li)


def play_lib(link):
    try:
        stream = tb7().playable(link)
    except TB7Error as e:
        notify(str(e), xbmcgui.NOTIFICATION_ERROR)
        return xbmcplugin.setResolvedUrl(HANDLE, False, xbmcgui.ListItem())
    xbmcplugin.setResolvedUrl(HANDLE, True, xbmcgui.ListItem(path=stream))


def account():
    try:
        left = tb7().account_info()
        xbmcgui.Dialog().ok(NAME, 'Zalogowano jako: [B]%s[/B]\nPozostały transfer: [B]%s[/B]'
                            % (setting('tb7_user'), left or 'nie udało się odczytać'))
    except TB7Error as e:
        xbmcgui.Dialog().ok(NAME, str(e))


def error(msg):
    xbmcgui.Dialog().ok(NAME, msg)
    xbmcplugin.endOfDirectory(HANDLE, succeeded=False)


def router():
    a = ARGS.get('action')
    try:
        if not a:
            root()
        elif a == 'search':
            do_search(ARGS['kind'])
        elif a == 'list':
            do_list(ARGS['kind'], ARGS['name'])
        elif a == 'seasons':
            seasons(ARGS['tmdb'])
        elif a == 'episodes':
            episodes(ARGS['tmdb'], ARGS['season'])
        elif a == 'sources':
            sources(ARGS['tmdb'], ARGS.get('season'), ARGS.get('episode'))
        elif a == 'raw_search':
            raw_search()
        elif a == 'library':
            library()
        elif a == 'play':
            play(ARGS['link'], ARGS.get('size', '?'), ARGS.get('name', ''))
        elif a == 'play_lib':
            play_lib(ARGS['link'])
        elif a == 'account':
            account()
        elif a == 'plot':
            xbmcgui.Dialog().textviewer(ARGS.get('title', ''), ARGS.get('text', ''))
        elif a == 'unlock':
            unlock_keys()
        elif a == 'update':
            check_updates()
        elif a == 'settings':
            ADDON.openSettings()
    except ValueError as e:  # brak klucza TMDB itp.
        xbmcgui.Dialog().ok(NAME, str(e))
        if a in ('search', 'list', 'seasons', 'episodes', 'sources'):
            xbmcplugin.endOfDirectory(HANDLE, succeeded=False)
    except Exception as e:
        xbmc.log('[%s] %r' % (NAME, e), xbmc.LOGERROR)
        notify('Błąd: %s' % e, xbmcgui.NOTIFICATION_ERROR)


if __name__ == '__main__':
    router()
