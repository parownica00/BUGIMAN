# TB7 Kino – addon Kodi (19+)

Wyszukiwarka filmów i seriali oparta o TMDB (polskie opisy, plakaty, oceny), która szuka plików na **Twoim koncie premium TB7** i odtwarza je w Kodi.

## Instalacja z repozytorium (z automatycznymi aktualizacjami)
1. Kodi → Ustawienia → System → Dodatki → włącz **Nieznane źródła**.
2. Ustawienia → Menedżer plików → **Dodaj źródło** → adres `https://parownica00.github.io/BUGIMAN/`, nazwa `tb7kino`.
3. Dodatki → **Zainstaluj z pliku ZIP** → `tb7kino` → `repository.tb7kino-x.x.x.zip`.
4. Dodatki → **Zainstaluj z repozytorium** → *TB7 Kino - repozytorium* → Dodatki wideo → **TB7 Kino**.
5. Otwórz addon: poprosi o hasło do kluczy API i sam uzupełni klucz TMDB. W ustawieniach wpisz login i hasło TB7.

## Jak działa
- Menu: wyszukiwanie filmów i seriali, **kategorie** (western, horror, komedia...; w każdej: popularne / najwyżej oceniane / najnowsze), listy „na topie”, „popularne” i „najwyżej oceniane”, bezpośrednie wyszukiwanie w TB7, pliki na koncie, stan transferu.
- Po wybraniu tytułu dodatek szuka w TB7 po polskim i oryginalnym tytule z rokiem (dla seriali `SxxEyy`), filtruje wyniki (nazwa pliku musi zaczynać się od tytułu, a zaraz po nim musi być rok, odcinek albo jakość, więc dla „Wonder” nie pokaże „Wonder Woman”), sortuje je wg jakości i rozmiaru oraz oznacza wersję (Lektor, Dubbing, Napisy).
- Szczegóły tytułu: opis z reżyserią i obsadą, **Obsada i ekipa** (zdjęcia, role; aktor → jego filmografia), **Zwiastun** z YouTube (najpierw polski). Te same opcje są w menu kontekstowym na liście filmów, a ekran Informacje w Kodi pokazuje obsadę i przycisk zwiastunu.
- **Bufor startowy** (Ustawienia → Odtwarzanie): film startuje w pauzie, aż zbierze się 30/60/120 s zapasu, potem rusza sam. Anuluj = odtwarzaj od razu.
- **Odporne odtwarzanie** (domyślnie włączone): film idzie przez lokalne proxy w addonie i nie zamyka się przy problemach z siecią. Gdy serwer hostingu zerwie połączenie albo zniknie internet, Kodi pokazuje kółko buforowania, a proxy przez maks. 15 minut łączy się ponownie od tego samego miejsca (wygasły link wymienia na nowy z konta TB7). Usługa addonu jednorazowo dopisuje w `advancedsettings.xml` cierpliwsze limity sieci Kodi (`curllowspeedtime` 300 s, `curlretries` 10, `curlclienttimeout` 30 s; kopia: `advancedsettings.xml.tb7kino.bak`) - wymaga jednego restartu Kodi.
- **Ustaw buforowanie**: dobiera pamięć bufora Kodi do RAM urządzenia (Kodi 20+ przez ustawienia, Kodi 19 przez `advancedsettings.xml`). Wymaga restartu Kodi.
- Przed pobraniem pliku dodatek pyta, ile transferu zużyje. Pliki, które już są na koncie, oznacza jako **NA KONCIE** i odtwarza bez dodatkowego transferu.

## Klucze API na hasło
Klucze TMDB/OMDb są zaszyfrowane hasłem w `plugin.video.tb7kino/resources/data/secrets.json` (PBKDF2-SHA256 200k + HMAC). Plik jest publiczny, więc liczy się siła hasła.
- Gdy addon nie ma klucza TMDB, przy otwarciu sam poprosi o hasło i uzupełni ustawienia.
- Ręcznie: menu **Odblokuj klucze API hasłem**.
- Zmiana kluczy lub hasła: `python3 make_secret.py`, podbij wersję, `python3 build.py`, push.

## Wydanie nowej wersji
1. Zmień kod w `plugin.video.tb7kino/` i podbij `version` w jego `addon.xml`.
2. Uruchom `python3 build.py`.
3. `git add -A && git commit -m "wersja X" && git push`. Kodi pobierze aktualizację sam (albo menu **Sprawdź aktualizacje**).

## Struktura
- `plugin.video.tb7kino/` – źródła addonu
- `repository.tb7kino/` – addon repozytorium (wskazuje na GitHub Pages)
- `zips/` – wygenerowane ZIP-y, `addons.xml` i `addons.xml.md5` (nie edytuj ręcznie)
- `build.py` – generator repozytorium

## Uwagi
- TB7 nie ma API, więc dodatek korzysta z panelu WWW. Jeśli TB7 zmieni wygląd strony, poprawki trzeba będzie zrobić w `plugin.video.tb7kino/resources/lib/tb7.py`.
- Sesja jest zapamiętywana na 3 godziny w profilu dodatku.
