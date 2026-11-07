# -*- coding: utf-8 -*-
"""Metadane: TMDB (opisy PL, plakaty, oceny) + opcjonalnie OMDb (IMDb / Rotten Tomatoes)."""
import time

import requests

TMDB = 'https://api.themoviedb.org/3/'
IMG = 'https://image.tmdb.org/t/p/'


class Meta:
    def __init__(self, tmdb_key, omdb_key='', lang='pl-PL'):
        if not tmdb_key:
            raise ValueError('Uzupełnij klucz TMDB API w ustawieniach.')
        self.key, self.omdb, self.lang = tmdb_key.strip(), omdb_key.strip(), lang or 'pl-PL'
        self.s = requests.Session()

    def _get(self, path, **params):
        params.update(api_key=self.key, language=self.lang)
        r = self.s.get(TMDB + path, params=params, timeout=20)
        r.raise_for_status()
        return r.json()

    # ---- listy -----------------------------------------------------------
    def search(self, kind, query, page=1):
        return self._get('search/%s' % kind, query=query, page=page, include_adult='false')

    def listing(self, kind, name, page=1):
        """name: popular | top_rated | trending | now_playing | on_the_air"""
        if name == 'trending':
            return self._get('trending/%s/week' % kind, page=page)
        return self._get('%s/%s' % (kind, name), page=page)

    def genres(self, kind):
        return self._get('genre/%s/list' % kind).get('genres', [])

    def discover(self, kind, genre, sort='popular', page=1):
        """sort: popular | top_rated | newest"""
        params = {'with_genres': genre, 'page': page, 'include_adult': 'false'}
        date_field = 'primary_release_date' if kind == 'movie' else 'first_air_date'
        if sort == 'top_rated':
            params.update({'sort_by': 'vote_average.desc', 'vote_count.gte': 300})
        elif sort == 'newest':
            params.update({'sort_by': date_field + '.desc', 'vote_count.gte': 20,
                           date_field + '.lte': time.strftime('%Y-%m-%d')})
        else:
            params.update({'sort_by': 'popularity.desc', 'vote_count.gte': 50})
        return self._get('discover/%s' % kind, **params)

    # ---- szczegóły -------------------------------------------------------
    def details(self, kind, tmdb_id):
        d = self._get('%s/%s' % (kind, tmdb_id),
                      append_to_response='external_ids,alternative_titles,credits,videos',
                      include_video_language='pl,en,null')
        if not d.get('overview') and self.lang != 'en-US':
            en = self.s.get(TMDB + '%s/%s' % (kind, tmdb_id),
                            params={'api_key': self.key, 'language': 'en-US'}, timeout=20).json()
            d['overview'] = en.get('overview', '')
        return d

    def season(self, tv_id, season):
        return self._get('tv/%s/season/%s' % (tv_id, season))

    def person(self, person_id):
        p = self._get('person/%s' % person_id, append_to_response='combined_credits')
        if not p.get('biography') and self.lang != 'en-US':
            en = self.s.get(TMDB + 'person/%s' % person_id,
                            params={'api_key': self.key, 'language': 'en-US'}, timeout=20).json()
            p['biography'] = en.get('biography', '')
        return p

    def omdb_ratings(self, imdb_id):
        if not (self.omdb and imdb_id):
            return {}
        try:
            j = self.s.get('https://www.omdbapi.com/', params={'apikey': self.omdb, 'i': imdb_id},
                           timeout=15).json()
            out = {}
            if j.get('imdbRating') not in (None, 'N/A'):
                out['IMDb'] = '%s (%s głosów)' % (j['imdbRating'], j.get('imdbVotes', '?'))
            for r in j.get('Ratings', []):
                if r.get('Source') == 'Rotten Tomatoes':
                    out['RT'] = r.get('Value')
            return out
        except Exception:
            return {}


def img(path, size='w500'):
    return IMG + size + path if path else ''


def trailer_key(d):
    """Najlepszy zwiastun z YouTube: oficjalny trailer, najlepiej po polsku."""
    vids = [v for v in d.get('videos', {}).get('results', []) if v.get('site') == 'YouTube' and v.get('key')]
    if not vids:
        return None

    def score(v):
        return (v.get('type') == 'Trailer', v.get('iso_639_1') == 'pl',
                bool(v.get('official')), v.get('type') == 'Teaser', v.get('size') or 0)
    return max(vids, key=score)['key']


def cast_list(d, limit=30):
    return [{'id': c.get('id'), 'name': c.get('name', ''), 'role': c.get('character', ''),
             'thumb': img(c.get('profile_path'), 'w185')}
            for c in d.get('credits', {}).get('cast', [])[:limit]]


def crew(d):
    """Reżyseria / twórcy i scenariusz."""
    c = d.get('credits', {}).get('crew', [])
    directors = [x['name'] for x in c if x.get('job') == 'Director']
    if not directors:
        directors = [x['name'] for x in d.get('created_by', [])]
    writers = []
    for x in c:
        if x.get('job') in ('Screenplay', 'Writer', 'Novel') and x['name'] not in writers:
            writers.append(x['name'])
    return directors, writers[:4]
