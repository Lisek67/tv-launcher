// Most między stroną launchera a rozszerzeniem.
const mark = () => { if (document.documentElement) document.documentElement.dataset.tvext = '1'; };
mark();
document.addEventListener('DOMContentLoaded', mark);
window.addEventListener('message', e => {
  if (e.source !== window || e.origin !== location.origin) return;
  const d = e.data;
  if (!d) return;
  if (d.tvLauncher === 'open') {
    if (typeof d.id !== 'string' || !/^https?:\/\//.test(d.url)) return;
    chrome.runtime.sendMessage({ type: 'open', id: d.id, url: d.url });
  } else if (d.tvLauncher === 'setkey') {      // własny skrót powrotu do launchera
    const c = d.combo;
    if (!c) chrome.storage.local.remove('homeKey');
    else if (typeof c.code === 'string' && c.code.length <= 40)
      chrome.storage.local.set({ homeKey: { code: c.code, ctrl: !!c.ctrl, alt: !!c.alt, shift: !!c.shift, meta: !!c.meta } });
  }
});
