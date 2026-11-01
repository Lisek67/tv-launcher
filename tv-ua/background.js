const LAUNCHER = 'http://127.0.0.1:8765/';

async function show(tab) {
  await chrome.tabs.update(tab.id, { active: true });
  await chrome.windows.update(tab.windowId, { focused: true });
}

// Otwiera aplikację: jeśli jej karta już istnieje, tylko ją pokazuje (stan zostaje), inaczej tworzy nową.
async function openApp(id, url, windowId) {
  const { apps = {} } = await chrome.storage.local.get('apps');
  if (apps[id] != null) {
    try {
      const tab = await chrome.tabs.get(apps[id]);
      if (!(tab.url || '').startsWith(LAUNCHER)) { await show(tab); return; }
    } catch (e) {}
  }
  const tab = await chrome.tabs.create({ url, active: true, windowId });
  apps[id] = tab.id;
  await chrome.storage.local.set({ apps });
}

async function goLauncher() {
  const tabs = await chrome.tabs.query({ url: LAUNCHER + '*' });
  if (tabs.length) await show(tabs[0]);
  else await chrome.tabs.create({ url: LAUNCHER, active: true });
}

chrome.runtime.onMessage.addListener((msg, sender) => {
  if (!msg) return;
  if (msg.type === 'open' && sender.tab && (sender.url || '').startsWith(LAUNCHER)) openApp(msg.id, msg.url, sender.tab.windowId);
  else if (msg.type === 'launcher') goLauncher();
});

// Skrót z menedżera skrótów Brave (zapasowy, gdy Alt+Home przechwyci strona/przeglądarka).
chrome.commands.onCommand.addListener(cmd => { if (cmd === 'launcher') goLauncher(); });
