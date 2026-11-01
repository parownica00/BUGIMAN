# TB7 Kino – addon Kodi (19+)

Wyszukiwarka filmów i seriali oparta o TMDB (polskie opisy, plakaty, oceny), która szuka plików na **Twoim koncie premium TB7** i odtwarza je w Kodi.

## Instalacja z repozytorium (z automatycznymi aktualizacjami)
1. Kodi → Ustawienia → System → Dodatki → włącz **Nieznane źródła**.
2. Ustawienia → Menedżer plików → **Dodaj źródło** → adres `https://parownica00.github.io/BUGIMAN/`, nazwa `tb7kino`.
3. Dodatki → **Zainstaluj z pliku ZIP** → `tb7kino` → `repository.tb7kino-x.x.x.zip`.
4. Dodatki → **Zainstaluj z repozytorium** → *TB7 Kino - repozytorium* → Dodatki wideo → **TB7 Kino**.
5. W ustawieniach addonu wpisz login i hasło TB7 oraz klucz TMDB (opcjonalnie OMDb).

## Jak działa
- Menu: wyszukiwanie filmów i seriali, listy „na topie”, „popularne” i „najwyżej oceniane”, bezpośrednie wyszukiwanie w TB7, pliki na koncie, stan transferu.
- Po wybraniu tytułu dodatek szuka w TB7 po polskim i oryginalnym tytule z rokiem (dla seriali `SxxEyy`), filtruje wyniki, sortuje je wg jakości i rozmiaru oraz oznacza wersję (Lektor, Dubbing, Napisy).
- Przed pobraniem pliku dodatek pyta, ile transferu zużyje. Pliki, które już są na koncie, oznacza jako **NA KONCIE** i odtwarza bez dodatkowego transferu.

## Wydanie nowej wersji
1. Zmień kod w `plugin.video.tb7kino/` i podbij `version` w jego `addon.xml`.
2. Uruchom `python3 build.py`.
3. `git add -A && git commit -m "wersja X" && git push`. Kodi pobierze aktualizację sam.

## Struktura
- `plugin.video.tb7kino/` – źródła addonu
- `repository.tb7kino/` – addon repozytorium (wskazuje na GitHub Pages)
- `zips/` – wygenerowane ZIP-y, `addons.xml` i `addons.xml.md5` (nie edytuj ręcznie)
- `build.py` – generator repozytorium

## Uwagi
- TB7 nie ma API, więc dodatek korzysta z panelu WWW. Jeśli TB7 zmieni wygląd strony, poprawki trzeba będzie zrobić w `plugin.video.tb7kino/resources/lib/tb7.py`.
- Sesja jest zapamiętywana na 3 godziny w profilu dodatku.
