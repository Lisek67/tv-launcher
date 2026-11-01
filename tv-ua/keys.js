// Klawisz "Strona domowa", Alt+Home lub własny skrót z Ustawień launchera:
// wróć do launchera, NIE nawigując tej karty (stan aplikacji zostaje).
let custom = null;
try {
  chrome.storage.local.get('homeKey', r => { custom = (r && r.homeKey) || null; });
  chrome.storage.onChanged.addListener((ch, area) => { if (area === 'local' && ch.homeKey) custom = ch.homeKey.newValue || null; });
} catch (e) {}
window.addEventListener('keydown', e => {
  const home = e.key === 'BrowserHome' || e.code === 'BrowserHome';
  const altHome = e.altKey && !e.ctrlKey && !e.shiftKey && !e.metaKey && (e.key === 'Home' || e.code === 'Home');
  const mine = custom && e.code === custom.code && !!e.ctrlKey === !!custom.ctrl && !!e.altKey === !!custom.alt &&
               !!e.shiftKey === !!custom.shift && !!e.metaKey === !!custom.meta;
  if (home || altHome || mine) {
    e.preventDefault();
    e.stopImmediatePropagation();
    chrome.runtime.sendMessage({ type: 'launcher' });
  }
}, true);
