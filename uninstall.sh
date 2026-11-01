#!/usr/bin/env bash
# Usuwa usługi launchera (także z TTY: Ctrl+Alt+F3). Pliki aplikacji i config.json zostają.
systemctl --user disable --now tv-launcher.service tv-remote.service tv-ydotoold.service 2>/dev/null
rm -f "$HOME/.config/systemd/user/tv-launcher.service" "$HOME/.config/systemd/user/tv-remote.service" "$HOME/.config/systemd/user/tv-ydotoold.service"
rm -f "$HOME/.config/autostart/tv-launcher.desktop"
systemctl --user daemon-reload 2>/dev/null
sudo rm -f /etc/sudoers.d/tv-launcher
echo "Usunięto usługi launchera. (Reguła udev dla uinput w /etc/udev/rules.d/60-uinput.rules zostaje - usuń ręcznie, jeśli chcesz.)"
