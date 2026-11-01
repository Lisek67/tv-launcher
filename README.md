# TV Launcher

Launcher w stylu Apple TV dla przeglądarki: kafelki aplikacji (YouTube, Netflix, ...), pogoda, ustawienia ekranu i czasu, zasilanie, pilot na telefon i automatyczne aktualizacje z GitHuba.

Twórca: **lissszek**

## Instalacja

### Arch Linux (GNOME / Wayland)
```bash
git clone https://github.com/Lisek67/tv-launcher.git
cd tv-launcher
bash install.sh
```
Instalator doinstaluje pakiety (`ydotool`, `wl-clipboard`, `python-gobject`), skonfiguruje usługę systemd, uprawnienia do wyłączania/restartu komputera i (opcjonalnie) autostart przeglądarki na pełnym ekranie. Jeśli poprosi o ponowne zalogowanie, zrób to - inaczej pilot na telefon nie dostanie dostępu do `/dev/uinput`.

### Windows 10/11
1. Pobierz repozytorium (Code → Download ZIP) i rozpakuj.
2. Kliknij dwukrotnie `install.bat`. Jeśli nie masz Pythona, instalator spróbuje zainstalować go przez `winget`.

W Windows nie ma ustawień ekranu i czasu (to funkcje GNOME). Reszta działa tak samo. Wersja dla Windows jest nowa, więc w razie problemów daj znać.

## Pierwsze uruchomienie
Po starcie pokaże się kreator: nawigacja, kafelki, ustawienia, pilot na telefonie i rozszerzenie przeglądarki. Wrócisz do niego w **Ustawienia → Samouczek**.

**Rozszerzenie przeglądarki (`tv-ua`)** sprawia, że aplikacje zapamiętują miejsce, w którym skończyłeś, a `Alt+Home` (lub klawisz "Strona domowa") wraca do launchera. Wczytaj je raz: `brave://extensions` (lub `chrome://extensions`) → Tryb dewelopera → Wczytaj rozpakowane → folder `tv-ua`.

## Pilot na telefonie
**Ustawienia → Pilot na telefonie** pokazuje adres i PIN. Otwórz adres w przeglądarce telefonu (ta sama sieć Wi-Fi), wpisz PIN. Strzałki, gładzik/mysz, głośność, klawiatura, uśpienie/restart/wyłączenie. Port `8766` musi być dostępny w zaporze. Ruch idzie po zwykłym HTTP w sieci domowej, więc nie korzystaj z pilota w sieciach publicznych.

## Aktualizacje
Launcher sam sprawdza, czy jest nowa wersja, i pyta, czy zaktualizować (Ustawienia → Aktualizacje). Twoje ustawienia i kafelki zostają bez zmian.

## Struktura
| Plik | Do czego |
|---|---|
| `server.py` | serwer launchera (port 8765, tylko lokalnie), aktualizacje |
| `remote.py`, `remote.html` | pilot na telefon (port 8766, PIN) |
| `app.html` | interfejs launchera, ustawienia, kreator |
| `tv-ua/` | rozszerzenie przeglądarki |
| `version.json` | wersja i repozytorium aktualizacji |
| `config.default.json` | domyślne kafelki (Twoje zmiany lądują w `config.json`) |
| `install.sh`, `install.ps1` | instalatory (Arch / Windows) |
