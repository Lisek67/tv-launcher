#!/usr/bin/env bash
# TV Launcher - instalator dla Arch Linux (GNOME / Wayland).
# Uruchom RAZ jako zwykły użytkownik (nie root):  bash install.sh
# Można go bezpiecznie uruchomić ponownie (np. po aktualizacji).
set -e
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[ "$(id -u)" = 0 ] && { echo "Uruchom jako zwykły użytkownik, bez sudo."; exit 1; }
say() { printf '\n\033[1m== %s ==\033[0m\n' "$1"; }
ask_yn() { local a; read -r -p "$1 [T/n] " a || true; [[ -z "$a" || "$a" =~ ^[TtYy] ]]; }

say "TV Launcher: instalacja"
NEED_RELOGIN=0

# 1. Zależności -----------------------------------------------------------
say "1/5 Pakiety"
if command -v pacman >/dev/null; then
  MISSING=()
  for p in python ydotool wl-clipboard python-gobject; do pacman -Qi "$p" >/dev/null 2>&1 || MISSING+=("$p"); done
  if [ ${#MISSING[@]} -gt 0 ]; then
    echo "Instaluję: ${MISSING[*]} (zapyta o hasło sudo)"
    sudo pacman -S --needed --noconfirm "${MISSING[@]}"
  else
    echo "Wszystkie pakiety są już zainstalowane."
  fi
else
  echo "Brak pacmana - zainstaluj ręcznie: python, ydotool, wl-clipboard, python-gobject."
fi
command -v python3 >/dev/null || { echo "Brak python3"; exit 1; }

# 2. Dostęp do /dev/uinput (ydotool: pilot, ukrywanie kursora) -------------
say "2/5 Wstrzykiwanie klawiszy (ydotool)"
if [ ! -w /dev/uinput ]; then
  echo 'KERNEL=="uinput", GROUP="input", MODE="0660", OPTIONS+="static_node=uinput"' | sudo tee /etc/udev/rules.d/60-uinput.rules >/dev/null
  sudo usermod -aG input "$USER"
  sudo udevadm control --reload-rules
  sudo udevadm trigger /dev/uinput 2>/dev/null || true
  NEED_RELOGIN=1
  echo "Dodano regułę udev i grupę 'input' - wymaga ponownego zalogowania."
fi
UNIT_DIR="$HOME/.config/systemd/user"
mkdir -p "$UNIT_DIR"
if systemctl --user cat ydotool.service >/dev/null 2>&1; then
  systemctl --user enable --now ydotool.service 2>/dev/null || true
else
  cat > "$UNIT_DIR/tv-ydotoold.service" <<UNIT
[Unit]
Description=ydotoold (TV Launcher)

[Service]
ExecStart=/usr/bin/ydotoold --socket-path=%t/.ydotool_socket
Restart=always

[Install]
WantedBy=default.target
UNIT
  systemctl --user daemon-reload
  systemctl --user enable --now tv-ydotoold.service 2>/dev/null || true
fi

# 3. sudo bez hasła (tylko czas + zasilanie) -------------------------------
say "3/5 Uprawnienia (czas i zasilanie)"
RULE="$USER ALL=(root) NOPASSWD: /usr/bin/timedatectl, /usr/bin/systemctl poweroff, /usr/bin/systemctl reboot, /usr/bin/systemctl suspend"
echo "$RULE" | sudo tee /etc/sudoers.d/tv-launcher >/dev/null
sudo chmod 440 /etc/sudoers.d/tv-launcher
sudo visudo -cf /etc/sudoers.d/tv-launcher >/dev/null || { sudo rm -f /etc/sudoers.d/tv-launcher; echo "Reguła sudo odrzucona."; }

# 4. Usługa launchera ------------------------------------------------------
say "4/5 Usługa systemd"
# stara, osobna usługa pilota nie jest już potrzebna (pilot działa w tym samym procesie)
systemctl --user disable --now tv-remote.service 2>/dev/null || true
rm -f "$UNIT_DIR/tv-remote.service"
cat > "$UNIT_DIR/tv-launcher.service" <<UNIT
[Unit]
Description=TV Launcher
After=network.target

[Service]
Type=simple
WorkingDirectory=$DIR
ExecStart=/usr/bin/python3 $DIR/server.py
Restart=always
RestartSec=2

[Install]
WantedBy=default.target
UNIT
systemctl --user daemon-reload
systemctl --user enable tv-launcher.service
systemctl --user restart tv-launcher.service

# 5. Przeglądarka na pełnym ekranie przy starcie systemu -------------------
say "5/5 Autostart przeglądarki"
BROWSER=""
for b in brave brave-browser chromium google-chrome-stable microsoft-edge-stable; do
  if command -v "$b" >/dev/null; then BROWSER="$(command -v "$b")"; break; fi
done
if [ -z "$BROWSER" ]; then
  echo "Nie znaleziono Brave/Chromium/Chrome - pomijam. Otwórz ręcznie: http://127.0.0.1:8765/"
elif [ -t 0 ] && ask_yn "Uruchamiać launcher w $(basename "$BROWSER") na pełnym ekranie po zalogowaniu?"; then
  mkdir -p "$HOME/.config/autostart"
  cat > "$HOME/.config/autostart/tv-launcher.desktop" <<DESK
[Desktop Entry]
Type=Application
Name=TV Launcher
Exec=$BROWSER --start-fullscreen --load-extension=$DIR/tv-ua file://$DIR/index.html
X-GNOME-Autostart-Delay=2
DESK
  echo "Dodano autostart ($HOME/.config/autostart/tv-launcher.desktop)."
fi

sleep 1.5
echo
if curl -s -m 3 http://127.0.0.1:8765/ping >/dev/null; then
  echo "OK: launcher działa: http://127.0.0.1:8765/ (startuje sam po zalogowaniu)."
else
  echo "Usługa zainstalowana, ale nie odpowiada. Sprawdź: journalctl --user -u tv-launcher -e"
fi
echo "Pilot na telefon używa portu 8766. Przy zaporze: sudo ufw allow 8766/tcp   (albo: sudo firewall-cmd --add-port=8766/tcp --permanent)"
echo "Zarządzanie: systemctl --user status|restart|stop tv-launcher"
[ "$NEED_RELOGIN" = 1 ] && echo -e "\n\033[1;33mWYLOGUJ SIĘ I ZALOGUJ PONOWNIE\033[0m - dopiero wtedy pilot na telefon i ukrywanie kursora dostaną dostęp do /dev/uinput."
echo "Pierwsze uruchomienie pokaże kreator konfiguracji."
exit 0
