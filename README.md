# TB7 Kino – addon Kodi (19+)

Wyszukiwarka filmów i seriali oparta o TMDB (polskie opisy, plakaty, oceny), która szuka plików na **Twoim koncie premium TB7** i odtwarza je w Kodi.

## Instalacja
1. Kodi → Ustawienia → System → Dodatki → włącz **Nieznane źródła**.
2. Dodatki → Zainstaluj z pliku ZIP → `plugin.video.tb7kino-1.0.0.zip`.
3. Otwórz ustawienia dodatku i wpisz:
   - login i hasło TB7,
   - klucz **TMDB API v3** (themoviedb.org → Ustawienia → API),
   - opcjonalnie klucz **OMDb** (omdbapi.com), który dodaje oceny IMDb i Rotten Tomatoes.

## Jak działa
- Menu: wyszukiwanie filmów i seriali, listy „na topie”, „popularne” i „najwyżej oceniane”, bezpośrednie wyszukiwanie w TB7, pliki na koncie, stan transferu.
- Po wybraniu tytułu dodatek szuka w TB7 po polskim i oryginalnym tytule z rokiem (dla seriali `SxxEyy`), filtruje wyniki, sortuje je wg jakości i rozmiaru oraz oznacza wersję (Lektor, Dubbing, Napisy).
- Na górze listy widać oceny (TMDB, IMDb, RT) i opis. Kliknięcie otwiera pełny opis.
- Przed pobraniem pliku dodatek pyta, ile transferu zużyje. Pliki, które już są na koncie, oznacza jako **NA KONCIE** i odtwarza bez dodatkowego transferu.

## Uwagi
- TB7 nie ma API, więc dodatek korzysta z panelu WWW. Jeśli TB7 zmieni wygląd strony, poprawki trzeba będzie zrobić w `resources/lib/tb7.py`.
- Sesja jest zapamiętywana na 3 godziny w profilu dodatku.
- Filtr „tylko pasujące do tytułu” można wyłączyć w ustawieniach.
