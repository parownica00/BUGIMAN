#!/usr/bin/env python3
"""Buduje repozytorium Kodi: zips/<id>/<id>-<wersja>.zip, zips/addons.xml(.md5) i index.html.

Użycie: podbij version w <addon>/addon.xml, uruchom `python3 build.py`, zrób commit i push.
"""
import hashlib
import os
import re
import shutil
import zipfile

ROOT = os.path.dirname(os.path.abspath(__file__))
ADDONS = ['plugin.video.tb7kino', 'repository.tb7kino']
ZIPS = os.path.join(ROOT, 'zips')
SKIP_DIRS = {'__pycache__', '.git'}


def addon_xml(addon):
    with open(os.path.join(ROOT, addon, 'addon.xml'), encoding='utf-8') as f:
        return f.read()


def version(xml):
    return re.search(r'<addon[^>]*\bversion="([^"]+)"', xml).group(1)


def build_zip(addon, ver):
    out_dir = os.path.join(ZIPS, addon)
    if os.path.isdir(out_dir):
        shutil.rmtree(out_dir)
    os.makedirs(out_dir)
    path = os.path.join(out_dir, '%s-%s.zip' % (addon, ver))
    src = os.path.join(ROOT, addon)
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as z:
        for base, dirs, files in os.walk(src):
            dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
            for name in sorted(files):
                if name.endswith('.pyc'):
                    continue
                full = os.path.join(base, name)
                z.write(full, os.path.join(addon, os.path.relpath(full, src)))
    for asset in ('icon.png', 'fanart.jpg'):
        if os.path.exists(os.path.join(src, asset)):
            shutil.copy(os.path.join(src, asset), out_dir)
    return path


def main():
    os.makedirs(ZIPS, exist_ok=True)
    parts = []
    repo_zip = None
    for addon in ADDONS:
        xml = addon_xml(addon)
        ver = version(xml)
        z = build_zip(addon, ver)
        if addon.startswith('repository.'):
            repo_zip = z
        parts.append(re.sub(r'^<\?xml[^>]*\?>\s*', '', xml).strip())
        print('zbudowano', os.path.relpath(z, ROOT))

    addons = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<addons>\n%s\n</addons>\n' % '\n'.join(parts)
    with open(os.path.join(ZIPS, 'addons.xml'), 'w', encoding='utf-8') as f:
        f.write(addons)
    with open(os.path.join(ZIPS, 'addons.xml.md5'), 'w') as f:
        f.write(hashlib.md5(addons.encode('utf-8')).hexdigest())

    # kopia ZIP-a repozytorium w katalogu głównym + index.html dla menedżera plików Kodi
    for old in os.listdir(ROOT):
        if old.startswith('repository.') and old.endswith('.zip'):
            os.remove(os.path.join(ROOT, old))
    name = os.path.basename(repo_zip)
    shutil.copy(repo_zip, os.path.join(ROOT, name))
    with open(os.path.join(ROOT, 'index.html'), 'w', encoding='utf-8') as f:
        f.write('<!DOCTYPE html>\n<html><head><meta charset="utf-8"><title>TB7 Kino</title></head>\n'
                '<body>\n<a href="%s">%s</a>\n</body></html>\n' % (name, name))
    print('addons.xml + md5 + index.html gotowe')


if __name__ == '__main__':
    main()
