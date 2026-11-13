(() => {
  const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
  document.querySelectorAll('[data-count]').forEach(el => {
    const n = +el.dataset.count; if (reduce || !n) return; let i = 0;
    const t = setInterval(() => { i += Math.max(1, Math.ceil(n / 24)); if (i >= n) { i = n; clearInterval(t); } el.textContent = i; }, 30);
  });
  document.querySelectorAll('form.proc-form').forEach(f => f.addEventListener('submit', () => {
    const o = document.getElementById('proc'), m = document.getElementById('procmsg'), msgs = JSON.parse(f.dataset.msgs || '[]'); let k = 0;
    o.hidden = false; m.textContent = msgs[0] || 'Processando…';
    setInterval(() => { k = (k + 1) % Math.max(msgs.length, 1); m.textContent = msgs[k] || 'Processando…'; }, 1400);
  }));
})();
