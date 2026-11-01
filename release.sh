#!/usr/bin/env bash
# Wydanie nowej wersji (dla twórcy). Wymaga: git, gh (GitHub CLI, po `gh auth login`).
# Użycie:  bash release.sh 1.1.0 notes.md          (plik z listą zmian)
#          bash release.sh 1.1.0 $'- Nowy kreator\n- Poprawki pilota'
set -e
V="$1"; NOTES="$2"
[ -z "$V" ] && { echo "Użycie: bash release.sh 1.1.0 [plik_zmian.md | \"tekst zmian\"]"; exit 1; }
cd "$(dirname "${BASH_SOURCE[0]}")"
command -v gh >/dev/null || { echo "Zainstaluj GitHub CLI: sudo pacman -S github-cli, potem: gh auth login"; exit 1; }
python3 - "$V" <<'PY'
import json, sys
p = 'version.json'
d = json.load(open(p, encoding='utf-8'))
d['version'] = sys.argv[1]
with open(p, 'w', encoding='utf-8') as f:
    json.dump(d, f, indent=2, ensure_ascii=False); f.write('\n')
PY
git add -A
git commit -m "v$V"
git tag "v$V"
git push
git push origin "v$V"
if [ -f "$NOTES" ]; then gh release create "v$V" --title "v$V" --notes-file "$NOTES"
else gh release create "v$V" --title "v$V" --notes "${NOTES:-Nowa wersja v$V}"; fi
echo "Wydano v$V. Launchery znajomych zobaczą aktualizację przy następnym sprawdzeniu."
