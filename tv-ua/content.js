// Most między stroną launchera a rozszerzeniem.
const mark = () => { if (document.documentElement) document.documentElement.dataset.tvext = '1'; };
mark();
document.addEventListener('DOMContentLoaded', mark);
window.addEventListener('message', e => {
  if (e.source !== window || e.origin !== location.origin) return;
  const d = e.data;
  if (!d || d.tvLauncher !== 'open') return;
  if (typeof d.id !== 'string' || !/^https?:\/\//.test(d.url)) return;
  chrome.runtime.sendMessage({ type: 'open', id: d.id, url: d.url });
});
