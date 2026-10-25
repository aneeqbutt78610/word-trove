(() => {
  const $ = s => document.querySelector(s), $$ = s => [...document.querySelectorAll(s)];
  const V = { a:1,b:3,c:3,d:2,e:1,f:4,g:2,h:4,i:1,j:8,k:5,l:1,m:3,n:1,o:1,p:3,q:10,r:1,s:1,t:1,u:1,v:4,w:4,x:8,y:4,z:10 };
  const score = w => [...w].reduce((s, c) => s + V[c], 0);
  const letters = s => s.toLowerCase().replace(/[^a-z]/g, '');
  const PAGE = 100;

  // theme toggle
  const root = document.documentElement;
  $('#theme').onclick = () => {
    const dark = root.dataset.theme ? root.dataset.theme === 'dark' : matchMedia('(prefers-color-scheme: dark)').matches;
    root.dataset.theme = dark ? 'light' : 'dark';
    try { localStorage.setItem('theme', root.dataset.theme) } catch (e) {}
  };

  // highlight current nav item
  const pg = $('main').dataset.page;
  $$('.nav a').forEach(a => { if (a.dataset.k === pg) a.classList.add('on') });

  // copy word / email
  const toast = msg => { const t = $('#toast'); t.textContent = msg; t.classList.add('show'); clearTimeout(t._h); t._h = setTimeout(() => t.classList.remove('show'), 1400) };
  const copy = txt => navigator.clipboard ? navigator.clipboard.writeText(txt).then(() => toast(`Copied ${txt}`), () => toast(txt)) : toast(txt);
  document.addEventListener('click', e => {
    const t = e.target.closest('.t, [data-copy]');
    if (t) copy(t.dataset.copy || t.querySelector('b').textContent.toUpperCase());
  });

  // ---------- cookie consent (Google Consent Mode v2) ----------
  // The inline head script defaults every visitor to denied and applies a stored accept before
  // gtag loads; this asks, records the choice for a year and updates consent live. No gtag
  // (GA4_ID unset) means no banner. GPC / Do Not Track count as "reject" and skip the banner.
  // When the build has ads on, the footer button carries data-cc-ads and one choice covers both.
  if (window.gtag) {
    const CK = 'wt-consent', YEAR = 31536e6;
    const saved = (() => { try { const c = JSON.parse(localStorage.getItem(CK)); return c && Date.now() - c.t < YEAR ? c : null } catch (e) { return null } })();
    const optOut = navigator.globalPrivacyControl === true || navigator.doNotTrack === '1';
    const ads = !!$('[data-cc-ads]');
    const policy = $('.foot a[href*="privacy-policy"]');
    // first-party cookies only: Google's doubleclick.net cookies can't be removed from this domain
    const dropCookies = () => document.cookie.split(';').map(c => c.split('=')[0].trim()).filter(n => /^(_ga|__gads|__gpi|__eoi)/.test(n)).forEach(n =>
      ['', location.hostname, '.' + location.hostname].forEach(d => { document.cookie = `${n}=; Max-Age=0; path=/${d ? '; domain=' + d : ''}` }));
    let box;
    const choose = a => {
      const v = a ? 'granted' : 'denied';
      try { localStorage.setItem(CK, JSON.stringify({ a, t: Date.now() })) } catch (e) {}
      gtag('consent', 'update', ads ? { analytics_storage: v, ad_storage: v, ad_user_data: v, ad_personalization: v } : { analytics_storage: v });
      if (!a) dropCookies();
      box.hidden = true;
    };
    const ask = focus => {
      if (!box) {
        box = document.createElement('section');
        box.className = 'cc';
        box.setAttribute('aria-label', 'Cookie consent');
        box.innerHTML = `<p>${ads
          ? "We'd like to use cookies for Google Analytics, to learn which pages help people, and for personalised ads from Google, which keep the site free. They're only set if you accept; otherwise you'll see non-personalised ads."
          : "We'd like to use Google Analytics cookies to learn which pages help people. They're only set if you accept."} Your puzzle progress and theme stay in your browser either way.${policy ? ` <a href="${policy.getAttribute('href')}">Privacy policy</a>` : ''}</p><div class="cc-b"><button type="button" data-cc="0">Reject</button><button type="button" data-cc="1">Accept</button></div>`;
        box.addEventListener('click', e => { const b = e.target.closest('[data-cc]'); if (b) choose(b.dataset.cc === '1') });
        document.body.append(box);
      }
      box.hidden = false;
      if (focus) box.querySelector('button').focus();   // opened from the footer: move focus to the choice
    };
    if (!saved && !optOut) ask(false);
    $$('[data-cc-open]').forEach(b => { b.onclick = () => ask(true) });
  }

  // ---------- ads ----------
  // Runs after the head consent default, so each unit is requested with the visitor's consent state.
  $$('ins.adsbygoogle').forEach(() => { try { (window.adsbygoogle = window.adsbygoogle || []).push({}) } catch (e) {} });

  const cache = {};
  const load = src => cache[src] ||= fetch(src).then(r => { if (!r.ok) throw r.status; return r.text() }).then(t => t.split(' '));
  const tile = (w, i) => `<li class="t" style="--i:${Math.min(i, 40)}"><b>${w}</b><i>${score(w)}</i></li>`;
  const sorters = { c: null, a: (x, y) => x < y ? -1 : 1, s: (x, y) => score(y) - score(x) || (x < y ? -1 : 1) };
  const debounce = (f, ms = 120) => { let h; return () => { clearTimeout(h); h = setTimeout(f, ms) } };
  const fail = () => { $('#out').innerHTML = '<li class="empty">Word list could not load. Check your connection and try again.</li>' };

  // ---------- finder ----------
  const finder = $('[data-tool="finder"]');
  if (finder) {
    const n = +finder.dataset.len, boxes = $$('.box'), inc = $('#inc'), exc = $('#exc');
    const out = $('#out'), more = $('#more'), count = $('#count'), sort = $('#sort'), title = $('#rtitle');
    let list = [], shown = 0;

    const draw = () => {
      const next = list.slice(shown, shown + PAGE);
      out.insertAdjacentHTML('beforeend', next.map((w, i) => tile(w, i)).join(''));
      shown += next.length;
      more.hidden = shown >= list.length;
    };
    const run = async () => {
      const known = boxes.map(b => letters(b.value)[0] || '');
      const want = letters(inc.value), bad = new Set(letters(exc.value));
      known.forEach(c => bad.delete(c)); [...want].forEach(c => bad.delete(c));
      const need = {}; for (const c of want) need[c] = (need[c] || 0) + 1;
      const active = known.some(Boolean) || want || bad.size;
      let words;
      try { words = await load(finder.dataset.src) } catch (e) { return fail() }
      list = words.filter(w => {
        for (let i = 0; i < n; i++) if (known[i] && w[i] !== known[i]) return false;
        for (const c of bad) if (w.includes(c)) return false;
        for (const c in need) if (w.split(c).length - 1 < need[c]) return false;
        return true;
      });
      meter(words.length, list.length, active);
      hint(words, list, known, active);
      if (sorters[sort.value]) list = [...list].sort(sorters[sort.value]);
      title.textContent = active ? `${n} letter words that match` : `All ${n} letter words`;
      count.textContent = `${list.length.toLocaleString()} words`;
      out.innerHTML = list.length ? '' : '<li class="empty">No words match. Try removing a letter.</li>';
      shown = 0; draw();
    };
    const live = debounce(run);

    // goal-gradient meter: real share of the dictionary ruled out
    const meter = (total, left, active) => {
      const pct = active ? Math.round((1 - left / total) * 1000) / 10 : 0;
      $('#mbar').style.width = pct + '%';
      $('#mtext').textContent = !active ? `${total.toLocaleString()} possible words. Add a letter to start narrowing.`
        : left === 1 ? `Solved: one word left out of ${total.toLocaleString()}.`
        : `${left.toLocaleString()} of ${total.toLocaleString()} words left. You've ruled out ${pct}%.`;
    };
    // best next guess: word whose letters split the remaining candidates most evenly
    const hint = (words, left, known, active) => {
      const h = $('#hint');
      if (!active || left.length < 3) { h.hidden = true; return }
      const f = {};
      for (const w of left) for (const c of new Set(w)) f[c] = (f[c] || 0) + 1;
      const val = c => (f[c] || 0) * (left.length - (f[c] || 0));
      let best = '', bs = -1;
      for (const w of words.slice(0, 2500)) { let s = 0; for (const c of new Set(w)) s += val(c); if (s > bs) { bs = s; best = w } }
      h.innerHTML = `Best next guess: <button type="button" class="t inline"><b>${best}</b></button> <span>its letters split the ${left.length.toLocaleString()} remaining words most evenly.</span>`;
      h.hidden = false;
    };

    boxes.forEach((b, i) => {
      b.addEventListener('input', () => {
        b.value = letters(b.value).slice(-1).toUpperCase();
        b.classList.toggle('full', !!b.value);
        if (b.value && boxes[i + 1]) boxes[i + 1].focus();
        live();
      });
      b.addEventListener('keydown', e => {
        if (e.key === 'Backspace' && !b.value && boxes[i - 1]) boxes[i - 1].focus();
        if (e.key === 'ArrowRight' && boxes[i + 1]) boxes[i + 1].focus();
        if (e.key === 'ArrowLeft' && boxes[i - 1]) boxes[i - 1].focus();
      });
    });
    [inc, exc].forEach(el => el.addEventListener('input', live));
    sort.addEventListener('change', run);
    more.onclick = draw;
    $('#go').onclick = () => { run(); $('#results').scrollIntoView({ behavior: 'smooth' }) };
    $('#reset').onclick = () => { boxes.forEach(b => { b.value = ''; b.classList.remove('full') }); inc.value = exc.value = ''; run(); boxes[0].focus() };

    // ?k=a.... pattern from list pages
    const k = new URLSearchParams(location.search).get('k');
    if (k) { [...k.slice(0, n)].forEach((c, i) => { if (/[a-z]/i.test(c)) { boxes[i].value = c.toUpperCase(); boxes[i].classList.add('full') } }); run() }
  }

  // ---------- unscrambler ----------
  const uns = $('[data-tool="unscramble"]');
  if (uns) {
    const inp = $('#letters'), out = $('#out'), count = $('#count'), title = $('#rtitle');
    const run = async () => {
      const raw = inp.value.toLowerCase().replace(/[^a-z?]/g, '').slice(0, 12);
      const q = Math.min(3, (raw.match(/\?/g) || []).length), have = {};
      for (const c of raw.replace(/\?/g, '')) have[c] = (have[c] || 0) + 1;
      const len = raw.replace(/\?/g, '').length + q;
      if (len < 3) { out.innerHTML = '<p class="empty">Type at least 3 letters.</p>'; count.textContent = ''; return }
      const sizes = [8, 7, 6, 5, 4, 3].filter(s => s <= len);
      let lists;
      try { lists = await Promise.all(sizes.map(s => load(uns.dataset.src + s + '.txt'))) } catch (e) { return fail() }
      let total = 0, htmlOut = '';
      lists.forEach((words, j) => {
        const hits = words.filter(w => {
          let miss = 0; const used = {};
          for (const c of w) { used[c] = (used[c] || 0) + 1; if (used[c] > (have[c] || 0) && ++miss > q) return false }
          return true;
        }).sort(sorters.s);
        if (!hits.length) return;
        total += hits.length;
        htmlOut += `<h3 class="gh">${sizes[j]} letter words <span>${hits.length}</span></h3><ul class="tiles">${hits.slice(0, 120).map(tile).join('')}</ul>`;
      });
      title.textContent = `Words from ${raw.toUpperCase()}`;
      count.textContent = `${total.toLocaleString()} words`;
      out.innerHTML = htmlOut || '<p class="empty">No words found. Add a ? blank tile or more letters.</p>';
    };
    inp.addEventListener('input', debounce(run, 180));
    $('#go').onclick = run;
    $('#reset').onclick = () => { inp.value = ''; inp.focus(); run() };
    $('#shuffle').onclick = () => {
      const a = [...inp.value];
      for (let i = a.length - 1; i > 0; i--) { const j = Math.floor(Math.random() * (i + 1)); [a[i], a[j]] = [a[j], a[i]] }
      inp.value = a.join(''); inp.classList.remove('shake'); void inp.offsetWidth; inp.classList.add('shake');
    };
  }

  // ---------- daily puzzle ----------
  const store = { get(k, d) { try { return JSON.parse(localStorage.getItem(k)) ?? d } catch (e) { return d } },
                  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)) } catch (e) {} } };
  const dayKey = (d = new Date()) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  const dayNum = () => Math.floor((Date.UTC(...dayKey().split('-').map((x, i) => i === 1 ? x - 1 : +x)) - Date.UTC(2026, 0, 1)) / 864e5) + 1;
  const played = store.get('wt-day', {}).date === dayKey() && store.get('wt-day', {}).done;
  const dot = $('.daily-link .dot'); if (dot && !played) dot.hidden = false;

  const game = $('[data-tool="daily"]');
  if (game) {
    const board = $('#board'), msg = $('#gmsg'), end = $('#gend');
    let answer = '', guesses = [], cur = '', mode = 'daily', valid = new Set(), answers = [], over = false;
    for (let r = 0; r < 6; r++) board.insertAdjacentHTML('beforeend', `<div class="grow">${'<span class="cell"></span>'.repeat(5)}</div>`);
    const rows = [...board.children];

    const grade = (g, a) => {
      const res = Array(5).fill('miss'), left = {};
      for (let i = 0; i < 5; i++) g[i] === a[i] ? res[i] = 'hit' : left[a[i]] = (left[a[i]] || 0) + 1;
      for (let i = 0; i < 5; i++) if (res[i] !== 'hit' && left[g[i]] > 0) { res[i] = 'near'; left[g[i]]-- }
      return res;
    };
    const paintKey = (c, st) => {
      if (!/^[a-z]$/.test(c)) return;   // keep tampered state out of the selector string
      const k = $(`.key[data-k="${c}"]`); if (!k) return;
      const rank = { miss: 1, near: 2, hit: 3 };
      if ((rank[st] || 0) > (rank[k.dataset.st] || 0)) { k.dataset.st = st; k.className = `key ${st}` }
    };
    const drawRow = (r, word, res, animate) => {
      [...rows[r].children].forEach((cell, i) => {
        cell.textContent = word[i] || '';
        cell.classList.toggle('filled', !!word[i]);
        if (res) { cell.style.setProperty('--i', i); cell.classList.add('rev', res[i]); if (!animate) cell.style.animation = 'none' }
      });
      if (res) [...word].forEach((c, i) => paintKey(c, res[i]));
    };
    const say = t => { msg.textContent = t };
    const stats = () => store.get('wt-stats', { played: 0, wins: 0, streak: 0, max: 0, last: '' });
    const showEnd = () => {
      const s = stats();
      $('#s-played').textContent = s.played; $('#s-win').textContent = s.played ? Math.round(s.wins / s.played * 100) + '%' : '0%';
      $('#s-streak').textContent = s.streak; $('#s-max').textContent = s.max;
      $('#lookup').href = $('#lookup').getAttribute('href').split('?')[0] + '?k=' + answer;
      end.hidden = false;
    };
    const finish = win => {
      over = true;
      say(win ? ['Genius!', 'Magnificent!', 'Impressive!', 'Splendid!', 'Great!', 'Phew!'][guesses.length - 1] : `The word was ${answer.toUpperCase()}.`);
      if (mode === 'daily') {
        const s = stats(), today = dayKey(), y = new Date(); y.setDate(y.getDate() - 1);
        if (s.lastPlayed !== today) {
          s.played++; s.lastPlayed = today;
          if (win) { s.wins++; s.streak = s.last === dayKey(y) ? s.streak + 1 : 1; s.last = today; s.max = Math.max(s.max, s.streak) }
          else s.streak = 0;
          store.set('wt-stats', s);
        }
        store.set('wt-day', { date: today, guesses, done: true });
        if (dot) dot.hidden = true;
      }
      showEnd();
    };
    const submit = () => {
      if (over) return;
      if (cur.length < 5) { say('Not enough letters.'); rows[guesses.length].classList.add('shake'); setTimeout(() => rows[guesses.length]?.classList.remove('shake'), 500); return }
      if (!valid.has(cur)) { say(`${cur.toUpperCase()} isn't in the word list.`); rows[guesses.length].classList.add('shake'); setTimeout(() => rows[guesses.length]?.classList.remove('shake'), 500); return }
      const res = grade(cur, answer);
      drawRow(guesses.length, cur, res, true);
      guesses.push(cur); cur = '';
      if (mode === 'daily') store.set('wt-day', { date: dayKey(), guesses, done: false });
      if (res.every(x => x === 'hit')) setTimeout(() => finish(true), 1500);
      else if (guesses.length === 6) setTimeout(() => finish(false), 1500);
      else say(`${6 - guesses.length} ${guesses.length === 5 ? 'guess' : 'guesses'} left.`);
    };
    const press = k => {
      if (over || !answer) return;
      if (k === 'enter') return submit();
      if (k === 'del' || k === 'backspace') cur = cur.slice(0, -1);
      else if (/^[a-z]$/.test(k) && cur.length < 5) cur += k;
      drawRow(guesses.length, cur);
    };
    $('#kb').addEventListener('click', e => { const b = e.target.closest('.key'); if (b) press(b.dataset.k) });
    document.addEventListener('keydown', e => { if (e.ctrlKey || e.metaKey || e.altKey || e.target.matches('input,select,textarea')) return; const k = e.key.toLowerCase(); if (k === 'enter' || k === 'backspace' || /^[a-z]$/.test(k)) { e.preventDefault(); press(k) } });

    const start = (m) => {
      mode = m; guesses = []; cur = ''; over = false; end.hidden = true;
      rows.forEach(r => [...r.children].forEach(c => { c.className = 'cell'; c.textContent = ''; c.style.animation = '' }));
      $$('.key').forEach(k => { k.className = k.classList.contains('wide') ? 'key wide' : 'key'; delete k.dataset.st });
      if (m === 'daily') {
        const n = dayNum();
        answer = answers[((n * 7919) % answers.length + answers.length) % answers.length];
        $('#gnum').textContent = `Puzzle #${n}`; $('#gmode').textContent = 'Daily';
        const saved = store.get('wt-day', {}) || {};
        // localStorage is user-writable: accept only six-or-fewer five-letter words back,
        // otherwise a hand-edited wt-day throws mid-render and leaves a blank board.
        if (saved.date === dayKey()) {
          guesses = (Array.isArray(saved.guesses) ? saved.guesses : []).filter(g => /^[a-z]{5}$/.test(g)).slice(0, 6);
          guesses.forEach((g, i) => drawRow(i, g, grade(g, answer), false));
        }
        if (saved.date === dayKey() && saved.done) { over = true; say(guesses.at(-1) === answer ? 'You solved today\'s word. Come back tomorrow!' : `Today's word was ${answer.toUpperCase()}.`); showEnd() }
        else say(guesses.length ? `${6 - guesses.length} guesses left.` : 'Type or tap letters, then press Enter.');
      } else {
        answer = answers[Math.floor(Math.random() * answers.length)];
        $('#gmode').textContent = 'Practice'; say('Practice round: this one does not affect your streak.');
      }
    };
    const tick = () => {
      const now = new Date(), mid = new Date(now); mid.setHours(24, 0, 0, 0);
      const s = Math.floor((mid - now) / 1000), p = x => String(x).padStart(2, '0');
      $('#countdown').textContent = `${p(Math.floor(s / 3600))}:${p(Math.floor(s % 3600 / 60))}:${p(s % 60)}`;
    };
    tick(); setInterval(tick, 1000);
    $('#practice').onclick = () => start('practice');
    $('#share').onclick = () => {
      const lines = guesses.map(g => grade(g, answer).map(x => ({ hit: '🟩', near: '🟨', miss: '⬜' })[x]).join(''));
      const won = guesses.at(-1) === answer;
      copy(`WordTrove ${mode === 'daily' ? '#' + dayNum() : 'practice'} ${won ? guesses.length : 'X'}/6\n${lines.join('\n')}\n${location.origin}${location.pathname}`);
    };
    Promise.all([load(game.dataset.src), load(game.dataset.ans)]).then(([all, ans]) => { valid = new Set(all); answers = ans; start('daily') }, () => say('The word list could not load. Check your connection and refresh.'));
  }
})();
