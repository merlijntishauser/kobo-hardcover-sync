// kobo-hardcover-sync page behaviour. Everything degrades without JS: forms submit
// normally and the theme follows the system.

// Theme switch: Light / Auto / Dark, remembered per browser. The inline
// script in <head> applies the stored choice before first paint.
(function () {
  const root = document.documentElement;
  const current = () => root.dataset.theme || 'auto';
  // The browser's own bar: the page colour of the theme in force, also when
  // it was chosen here against the system's.
  const bar = () => { const bg = getComputedStyle(root).getPropertyValue('--bg').trim();
    document.querySelectorAll('meta[name="theme-color"]').forEach(m => { m.removeAttribute('media'); m.content = bg; }); };
  const paint = () => { document.querySelectorAll('.theme button').forEach(b =>
    b.setAttribute('aria-pressed', String(b.dataset.set === current()))); bar(); };
  matchMedia('(prefers-color-scheme: dark)').addEventListener('change', bar);
  document.querySelectorAll('.theme button').forEach(b => b.addEventListener('click', () => {
    if (b.dataset.set === 'auto') delete root.dataset.theme; else root.dataset.theme = b.dataset.set;
    try { localStorage.setItem('kobo-theme', b.dataset.set); } catch (e) {}
    paint();
  }));
  paint();
})();

// Row switches save in the background and redraw only their own row, so the
// page keeps its place.
function redraw(tr, d) {
  tr.className = d.syncs ? 'on' : 'off';
  tr.querySelector('td.book').innerHTML = d.book;
  if (d.hc) tr.querySelector('td.hc > div').innerHTML = d.hc;
  else tr.querySelector('.act').outerHTML = d.status;
}
async function post(form, url) {
  return fetch(url, { method: 'POST', body: new FormData(form), headers: { 'X-Requested-With': 'fetch' } });
}
document.querySelectorAll('select.rowmode').forEach(sel => sel.addEventListener('change', async () => {
  const r = await post(sel.form, '/mode');
  if (!r.ok) { sel.form.submit(); return; }
  redraw(sel.closest('tr'), await r.json());
}));
document.querySelectorAll('form.stateform').forEach(f => {
  const save = async () => {
    f.querySelector('.rowdate').hidden = !['finished', 'rereading'].includes(f.state.value);
    const r = await post(f, '/state');
    if (!r.ok) { alert(await r.text()); return; }
    redraw(f.closest('tr'), await r.json());
  };
  f.querySelector('.rowstate').addEventListener('change', save);
  f.querySelector('.rowdate').addEventListener('change', save);
});
// Confirmations, delegated: forms inside the details dialog arrive later.
// The question names the chosen setting where the form has one ({mode}).
function ask(f) {
  const sel = f.querySelector('select[name="mode"]');
  return confirm(f.dataset.confirm.replace('{mode}', sel ? sel.selectedOptions[0].text : ''));
}
// A form that was confirmed here says so, and the server does not ask again.
document.addEventListener('submit', ev => {
  const f = ev.target;
  if (!f.dataset || !f.dataset.confirm) return;
  if (!ask(f)) { ev.preventDefault(); return; }
  if (!f.elements.confirmed) {
    const i = document.createElement('input');
    i.type = 'hidden'; i.name = 'confirmed'; i.value = '1';
    f.append(i);
  }
});

// A sign-in that waits for approval on Hardcover: ask every few seconds
// whether it has come, and show the page again when it has. Without JS the
// "I have approved it" button asks the same question.
(function () {
  const box = document.querySelector('[data-poll]');
  if (!box) return;
  const ask = async wait => {
    await new Promise(r => setTimeout(r, wait * 1000));
    try {
      const r = await fetch(box.dataset.poll, { method: 'POST', headers: { 'X-Requested-With': 'fetch' } });
      const d = r.ok ? await r.json() : { done: true };
      if (d.done) { location.href = d.to || '/settings#hardcover'; return; }
      ask(d.wait || wait);
    } catch (e) { ask(wait); }
  };
  ask(Number(box.dataset.every) || 5);
})();

// Help: a static dialog.
document.querySelectorAll('[data-open]').forEach(b => b.addEventListener('click', () => {
  const d = document.getElementById(b.dataset.open);
  if (d && d.showModal) d.showModal();
}));
document.querySelectorAll('dialog').forEach(d => d.addEventListener('click', ev => { if (ev.target === d) d.close(); }));

// Details: one dialog, filled from /details/<book> on demand. Without JS
// the Details link opens the same content as a page.
(function () {
  const box = document.getElementById('details');
  if (!box || !box.showModal) return;
  const body = box.querySelector('.dbody');
  document.addEventListener('click', async ev => {
    const a = ev.target.closest && ev.target.closest('a.details');
    if (!a || ev.metaKey || ev.ctrlKey || ev.shiftKey) return;
    ev.preventDefault();
    const r = await fetch(a.href, { headers: { 'X-Requested-With': 'fetch' } });
    if (!r.ok) { location.href = a.href; return; }
    body.innerHTML = await r.text();
    box.showModal();
  });
  box.addEventListener('click', ev => { if (ev.target === box) box.close(); });
  // Forms in the dialog (Use, Search Hardcover, Remove) work in place: the
  // dialog and the row refresh, the dialog stays open.
  box.addEventListener('submit', async ev => {
    const f = ev.target;
    if (f.method.toLowerCase() !== 'post') return;
    ev.preventDefault();
    ev.stopPropagation();
    if (f.dataset.confirm && !ask(f)) return;
    const data = new FormData(f);
    const btn = f.querySelector('button'); if (btn) btn.disabled = true;
    const r = await fetch(f.action, { method: 'POST', body: data, headers: { 'X-Requested-With': 'fetch' } });
    if (!r.ok) { if (btn) btn.disabled = false; alert(await r.text()); return; }
    const d = await r.json();
    body.innerHTML = d.details;
    const tr = document.getElementById('b-' + data.get('id'));
    if (tr) redraw(tr, d);
    const sel = body.querySelector('select[name="choice"]'); if (sel) sel.focus();
  });
})();

// Lightbox: a click on a cover shows it large. Delegated, because rows are
// redrawn in place. The small cover shows at once and is swapped for the
// large one when that has loaded.
(function () {
  const box = document.getElementById('lightbox');
  if (!box || !box.showModal) return;          // no <dialog>: the link opens the image
  const img = box.querySelector('img'), cap = box.querySelector('figcaption');
  let wanted = '';
  document.addEventListener('click', ev => {
    const a = ev.target.closest && ev.target.closest('a.coverlink');
    if (!a || ev.metaKey || ev.ctrlKey || ev.shiftKey) return;
    ev.preventDefault();
    wanted = a.href;
    img.src = a.querySelector('img').currentSrc || a.querySelector('img').src;
    img.alt = 'Cover of ' + a.dataset.title;
    cap.innerHTML = '';
    const b = document.createElement('b'); b.textContent = a.dataset.title;
    cap.append(b, document.createTextNode(a.dataset.author || ''));
    const big = new Image();
    big.onload = () => { if (wanted === a.href) img.src = a.href; };
    big.src = a.href;
    box.showModal();
  });
  box.addEventListener('click', ev => { if (ev.target === box) box.close(); });   // the backdrop
  box.addEventListener('close', () => { wanted = ''; img.removeAttribute('src'); });
})();

// Filters on a phone: folded behind one line that names the chosen one.
// The stylesheet only folds them once this script says it can unfold them.
(function () {
  const bar = document.querySelector('.toolbar'), btn = document.querySelector('.ftoggle');
  const panel = document.getElementById('fpanel');
  if (!bar || !btn || !panel) return;
  bar.classList.add('js');
  btn.addEventListener('click', () => {
    btn.setAttribute('aria-expanded', String(panel.classList.toggle('open')));
  });
})();
