# -*- coding: utf-8 -*-
"""Metadane: TMDB (opisy PL, plakaty, oceny) + opcjonalnie OMDb (IMDb / Rotten Tomatoes)."""
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

    # ---- szczegóły -------------------------------------------------------
    def details(self, kind, tmdb_id):
        d = self._get('%s/%s' % (kind, tmdb_id), append_to_response='external_ids,alternative_titles')
        if not d.get('overview') and self.lang != 'en-US':
            en = self.s.get(TMDB + '%s/%s' % (kind, tmdb_id),
                            params={'api_key': self.key, 'language': 'en-US'}, timeout=20).json()
            d['overview'] = en.get('overview', '')
        return d

    def season(self, tv_id, season):
        return self._get('tv/%s/season/%s' % (tv_id, season))

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
