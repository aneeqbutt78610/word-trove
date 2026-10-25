# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Build the production site -> source/out/site (Linux only, see Platform constraints)
cd source && python3 build.py

# Build a self-contained flat preview -> source/out/preview (no Markdown layer, relative links)
cd source && python3 build.py --preview

# Regenerate the word-frequency table used for "common first" ordering
cd source && python3 freq.py          # overwrites source/freq.txt

# Serve the committed prebuilt site for manual testing (works on any OS)
cd site && python -m http.server 8788
```

There is no test suite, linter, package manager, or build config — the generator is plain Python 3 stdlib and the site is plain HTML/CSS/JS.

## Platform constraints

`build.py` only runs on Linux. Two hard dependencies:

- `load_words()` reads `/usr/share/hunspell/en_US.aff` and `.dic` by absolute path (`sudo apt install hunspell-en-us`).
- `TODAY_H` uses the glibc-only `%-d` strftime directive, which raises `ValueError: Invalid format string` on Windows.

On Windows/macOS, test against the committed `site/` snapshot with `python -m http.server` instead of rebuilding.

## Architecture

### One generator, two output formats per page

`source/build.py` is the entire build system. Each page function (`finder_page`, `list_page`, `unscramble_page`, `daily_page`, `lists_page`, `simple`) builds an HTML body string and a parallel Markdown body, then calls `page(slug, title, desc, body, ld, md=...)`. `page()` writes the HTML file, appends to `SITEMAP`, and records the Markdown mirror in `MDPAGES`. Facts that appear in both (word counts, highest-scoring word, FAQ answers) are computed once and interpolated into both — keep them derived, never retyped.

`CONFIG` at the top of `build.py` (site name, `SITE_URL`, email, `GA4_ID`, `ADS_HEAD`, `LENGTHS`) is the only place these values live; everything downstream reads them.

### The Markdown / llms.txt layer is externally generated

`markdown_layer()` writes an `inventory.json` and shells out to an SEO suite tool at `$SEO_SUITE/scripts/manage_markdown_site.py` (`build`, `validate`, `hints`) which produces `llms.txt`, `llm/pages/*.md`, `llm/topics/`, `sitemap.md`, plus the robots.txt and sitemap.xml hint blocks. If that script is absent the build prints a warning and skips the layer entirely — the committed `site/llms.txt`, `site/sitemap.md` and `site/llm/` are then stale artifacts that must be hand-edited (notably the domain) rather than regenerated.

### Prod vs preview URL modes

`u()`, `asset()` and `canon()` switch on the `PREVIEW` flag: production emits clean directory URLs (`/5-letter-words/`, written as `slug/index.html`), preview emits flat relative files (`5-letter-words.html`). Every link, asset reference and canonical must go through these helpers — a hardcoded path breaks one of the two modes.

### Thin-page gating is load-bearing in two places

`MIN_LIST = 5` plus `has_start(n, c)` / `has_end(n, c)` decide both whether a letter page is generated (loop in `main()`) and whether anything links to it (`az_strip`, `az_md`, footer, cross-length chips). Any new link to a letter page must consult the same predicate or it emits a dead link. This is why letters are missing from some strips (no 4-letter words ending in Q, etc.).

### Word list pipeline and its frequency bias

`load_words()` parses the Hunspell `.aff` affix rules itself, expands every `.dic` root into derived forms (including cross-product prefix+suffix), drops non-lowercase entries (removes proper nouns), keeps 3–8 ASCII letters, subtracts `blocklist.txt`, and sorts by count from `freq.txt` so lists read "most common first".

`freq.txt` is built by `freq.py` from ~50 MB of local `/usr/share/doc` and man pages, so it is biased toward technical vocabulary. Two hardcoded workarounds compensate: a `freq.pop()` list that demotes distro/jargon words from popular ordering, and a `jargon` stop-list that keeps them out of the daily puzzle answer pool. Both are marked with `# ponytail:` comments noting that swapping `freq.txt` for a general-English frequency list removes the need for them. If you change `freq.txt`, revisit both lists and the "How 'common first' ordering works" copy in `info_pages()`.

### Client runtime

`source/src/app.js` is a single IIFE with three tools dispatched by the `data-tool` attribute on a section: `finder`, `unscramble`, `daily`. Word lists are lazy-fetched and memoized from `data/{n}.txt` (space-separated, already frequency-ordered — so the "Common first" sort option is a no-op `null` sorter that preserves file order). The server renders the first 60 words so the page is useful before JS runs; the client replaces that list on first interaction.

Scrabble tile values are duplicated: `SCORE` in `build.py` and `V` in `app.js`. They must stay in sync or server-rendered and client-rendered scores diverge.

Daily puzzle: answer index is `(dayNum * 7919) % answers.length` where `dayNum` counts days from 2026-01-01 UTC, with answers from `data/daily.txt`. Changing the length of the answers list reshuffles every past and future puzzle. Progress and stats live in localStorage under `wt-day` and `wt-stats`; there is no server state.

## Repository layout

- `source/` — generator, data inputs (`blocklist.txt`, `freq.txt`) and client assets (`src/style.css`, `src/app.js`, `src/favicon.svg`, `src/_headers`).
- `site/` — committed prebuilt deployable snapshot (322 entries). Note the generator writes to `source/out/site`, not here; promoting a build means replacing `site/` manually.
- `work/` — private SEO/AEO/GEO research and audit notes, indexed by `work/index.md`. Never deploy this directory.

## Deployment

Upload `site/` to Cloudflare Pages or Netlify. `_headers` (assembled from `source/src/_headers` plus generated cache, content-type and per-Markdown canonical `Link` rules) and `404.html` are picked up automatically by both hosts. Note that `python -m http.server` does *not* serve `site/404/index.html` for unknown paths, so 404 behavior can only be verified on the real host or an equivalent static server.
