# WordTrove

Static word-finder site: 3–8 letter finders, word unscrambler, daily 5 letter puzzle, ~290 word-list pages, plus an llms.txt / Markdown layer for AI search. No framework, no database.

## Run it locally for testing

The `site/` folder is a complete prebuilt site, so you can test without building. Serve it over HTTP — opening `index.html` directly with `file://` will not work, because the pages use absolute paths (`/style.css`, `/data/5.txt`) and the tools `fetch()` their word lists.

```bash
cd site
python -m http.server 8788
```

Then open <http://localhost:8788/>. Any static server works equally well (`npx serve site`, `php -S localhost:8788 -t site`).

What to check:

| Page | What should happen |
|---|---|
| `/` | Type letters into the green boxes — the list narrows as you type, the meter shows the % ruled out, and a "best next guess" line appears |
| `/word-unscrambler/` | `PLANETS` is prefilled; results group by length. Try `?` for a blank tile |
| `/daily-word-puzzle/` | Six-row board, on-screen keyboard and physical typing both work; reload mid-game and your guesses come back |
| `/5-letter-words-starting-with-a/` | Full list with scores; the "open this pattern in the finder" link prefills the first box |
| `/data/5.txt` | Plain space-separated word list (served from `/data/`, cached a week by `_headers`) |

Two notes on the dev server: unknown URLs return the server's own 404 rather than `site/404/index.html` (only the real host uses that), and `_headers` is ignored, so caching and Markdown content types can only be verified after deploy.

## Rebuild from source

```bash
cd source
python3 build.py              # -> source/out/site   (copy over site/ to promote it)
python3 build.py --preview    # -> source/out/preview
```

Preview mode writes flat `.html` files with relative links, so it opens straight from the filesystem without a server — handy for a quick look, but it skips the Markdown layer and uses different URLs than production.

Needs Python 3 and the Hunspell en_US dictionary (`sudo apt install hunspell-en-us`). The build is Linux-only: it reads `/usr/share/hunspell/en_US.{aff,dic}` by absolute path and uses a glibc-only date format, so it fails on Windows and macOS. Use the prebuilt `site/` folder there, or build inside WSL or a container.

## Deploy (free)
Upload the `site/` folder to Cloudflare Pages or Netlify (drag-and-drop works). `_headers` sets caching, Markdown content types and canonical headers. `404.html` is picked up automatically.

## Change name, domain, analytics, ads
Edit CONFIG at the top of `source/build.py` and rebuild.
The Markdown/llms.txt layer is regenerated only when the SEO suite is available (env var SEO_SUITE); otherwise copy `site/llms.txt`, `site/sitemap.md` and `site/llm/` from this zip and update the domain inside them.

## After launch
1. Confirm the domain is yours and not taken; set SITE_URL.
2. Add the site to Google Search Console and Bing Webmaster Tools; submit /sitemap.xml.
3. Set GA4_ID and rebuild.
4. When traffic grows, apply to AdSense or Ezoic; paste their script into ADS_HEAD and their lines into site/ads.txt, and turn on the `.ad` slots in style.css.

`work/` holds the private research and audit notes (keyword research, keyword map, AEO/GEO findings). Never upload it.
