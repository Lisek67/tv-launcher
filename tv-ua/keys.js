// Klawisz "Strona domowa" (BrowserHome) lub Alt+Home na stronach aplikacji:
// wróć do launchera, NIE nawigując tej karty (stan aplikacji zostaje).
window.addEventListener('keydown', e => {
  const home = e.key === 'BrowserHome' || e.code === 'BrowserHome';
  const altHome = e.altKey && !e.ctrlKey && !e.shiftKey && !e.metaKey && (e.key === 'Home' || e.code === 'Home');
  if (home || altHome) {
    e.preventDefault();
    e.stopImmediatePropagation();
    chrome.runtime.sendMessage({ type: 'launcher' });
  }
}, true);
