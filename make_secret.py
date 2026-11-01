#!/usr/bin/env python3
"""Szyfruje klucze API hasłem i zapisuje je w addonie.

Użycie: python3 make_secret.py
Pyta o klucz TMDB (i opcjonalnie OMDb) oraz hasło, zapisuje
plugin.video.tb7kino/resources/data/secrets.json. Potem: podbij wersję, python3 build.py, push.
"""
import getpass
import json
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, 'plugin.video.tb7kino', 'resources', 'lib'))
import vault  # noqa: E402

OUT = os.path.join(ROOT, 'plugin.video.tb7kino', 'resources', 'data', 'secrets.json')


def main():
    data = {}
    tmdb = input('Klucz TMDB API (v3): ').strip()
    if tmdb:
        data['tmdb_key'] = tmdb
    omdb = input('Klucz OMDb (Enter = pomiń): ').strip()
    if omdb:
        data['omdb_key'] = omdb
    if not data:
        sys.exit('Nie podano żadnego klucza.')
    pw = getpass.getpass('Hasło: ')
    if len(pw) < 8:
        sys.exit('Hasło musi mieć co najmniej 8 znaków.')
    if getpass.getpass('Powtórz hasło: ') != pw:
        sys.exit('Hasła się różnią.')
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(vault.encrypt(data, pw), f, indent=1)
    print('Zapisano', os.path.relpath(OUT, ROOT))


if __name__ == '__main__':
    main()
