#!/usr/bin/env python3
"""Static site generator for WordTrove.
Usage: python3 build.py            -> out/site   (deploy this folder) + out/private (work files, never upload)
       python3 build.py --preview  -> out/preview (flat .html files, relative links, no Markdown layer)
"""
import base64, hashlib, html, json, os, re, shutil, subprocess, sys
from collections import Counter
from datetime import date

# ---------------- CONFIG: change these, then rebuild ----------------
SITE_NAME = "WordTrove"
SITE_URL = "https://word-trove.netlify.app"      # your real domain, https, no trailing slash
EMAIL = "hello@wordtrove.app"
OWNER = "WordTrove editorial team"      # who maintains the content (shown in Markdown files)
GSC_VERIFY = "5lh5U4vN7c49gHNKccb-U83lNsyciPI-t-EHPENubko"   # Google Search Console HTML-tag token (home page only)
GA4_ID = "G-ZKTGZ6ZKS4"   # GA4 measurement ID; "" removes the tag, its CSP entries and the privacy-policy section
ADSENSE_ID = "ca-pub-1126177067663911"   # AdSense publisher ID: site-ownership meta on every page + ads.txt line. Serves no ads by itself
GTM_ID = "GTM-N4GB3SKT"   # Google Tag Manager container; "" removes it. Loads after the consent default in GA_JS
ADSENSE_SLOT = "3863718145"   # AdSense display unit placed once per page by with_ad(); "" = no ads at all
ADS_HEAD = (f'<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client={ADSENSE_ID}" '
            f'crossorigin="anonymous"></script>') if ADSENSE_ID and ADSENSE_SLOT else ""
WEBFONTS = True      # False = no Google Fonts request at all (system fonts only, zero third parties)
SUITE = os.environ.get("SEO_SUITE", "")   # path to the SEO suite checkout; empty = skip the Markdown layer
LENGTHS = range(3, 9)
# --------------------------------------------------------------------
# Privacy note: GA4_ID, ADS_HEAD and WEBFONTS each add a third party that sees visitor IPs.
# info_pages() writes the privacy policy from these three values, so the policy always
# describes what the build actually ships. Turning one on without rebuilding makes the
# policy wrong. ADS_HEAD's CSP entries live in csp() below and switch on with it.

PREVIEW = "--preview" in sys.argv
ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "out", "preview" if PREVIEW else "site")
PRIV = os.path.join(ROOT, "out", "private")
TODAY = date.today().isoformat()
TODAY_H = date.today().strftime("%B %-d, %Y")
REV = f"build-{TODAY}"
ABC = "abcdefghijklmnopqrstuvwxyz"
SCORE = dict(zip(ABC, [1,3,3,2,1,4,2,4,1,8,5,1,3,1,1,3,10,1,1,1,1,4,4,8,4,10]))
NUM = {3:"Three",4:"Four",5:"Five",6:"Six",7:"Seven",8:"Eight"}
HERO = {3:"FUN",4:"PLAY",5:"WORDS",6:"LETTER",7:"PUZZLES",8:"SOLUTION"}
DICT_NOTE = "SCOWL-based Hunspell en_US dictionary (Debian release 2020.12.07, size 70)"

esc = html.escape
score = lambda w: sum(SCORE[c] for c in w)

# ---------- safe HTML emission ----------
# json.dumps does not escape "<", so any string reaching JSON-LD that contains "</script>"
# would close the block and let the rest execute as HTML. Escaping "<" keeps the JSON valid
# (< is the same character to a JSON parser) and makes the breakout impossible.
def ldjson(x):
    return json.dumps(x, separators=(",", ":")).replace("<", "\\u003c")

# Inline scripts are pinned by CSP hash, so they live here as single constants: edit one and
# the hash follows automatically. Anything added here must stay byte-identical on every page.
THEME_JS = "try{var t=localStorage.getItem('theme');if(t)document.documentElement.dataset.theme=t}catch(e){}"
# Google Consent Mode v2: everything starts denied for every visitor. A stored "accept" from
# the banner in app.js (wt-consent, re-asked after a year) is the only thing that grants
# analytics_storage, and the ad signals too when ads are on (otherwise they stay denied).
_AD = "g" if ADS_HEAD else "'denied'"
GA_JS = (f"window.dataLayer=window.dataLayer||[];function gtag(){{dataLayer.push(arguments)}}"
         f"var c;try{{c=JSON.parse(localStorage.getItem('wt-consent'))}}catch(e){{}}"
         f"var g=c&&c.a&&Date.now()-c.t<31536e6?'granted':'denied';"
         f"gtag('consent','default',{{analytics_storage:g,ad_storage:{_AD},ad_user_data:{_AD},ad_personalization:{_AD}}});"
         f"gtag('set','ads_data_redaction',true);"
         f"gtag('js',new Date());gtag('config','{GA4_ID}');") if GA4_ID else ""
# Google's container snippet, minified. It shares dataLayer with GA_JS and comes after it, so every
# tag fired from the container sees the consent default. Tags added in GTM still need CSP entries.
GTM_JS = ("(function(w,d,s,l,i){w[l]=w[l]||[];w[l].push({'gtm.start':new Date().getTime(),event:'gtm.js'});"
          "var f=d.getElementsByTagName(s)[0],j=d.createElement(s),dl=l!='dataLayer'?'&l='+l:'';j.async=true;"
          "j.src='https://www.googletagmanager.com/gtm.js?id='+i+dl;f.parentNode.insertBefore(j,f);})"
          f"(window,document,'script','dataLayer','{GTM_ID}');") if GTM_ID else ""

def sha(s):
    return "'sha256-" + base64.b64encode(hashlib.sha256(s.encode()).digest()).decode() + "'"

def csp():
    """Content-Security-Policy matching exactly what this build emits."""
    scripts = (["'self'", sha(THEME_JS)] + ([sha(GA_JS)] if GA4_ID else []) + ([sha(GTM_JS)] if GTM_ID else [])
               + (["https://www.googletagmanager.com"] if GA4_ID or GTM_ID else []))
    frames = ["https://www.googletagmanager.com"] if GTM_ID else []   # GTM's <noscript> iframe
    styles = ["'self'", "'unsafe-inline'"] + (["https://fonts.googleapis.com"] if WEBFONTS else [])
    fonts = ["'self'"] + (["https://fonts.gstatic.com"] if WEBFONTS else [])
    # Google's documented GA4 CSP: hits go to regional *.google-analytics.com / *.analytics.google.com hosts
    connect = ["'self'"] + (["https://*.google-analytics.com", "https://*.analytics.google.com", "https://*.googletagmanager.com"] if GA4_ID else [])
    imgs = ["'self'", "data:"] + (["https://*.google-analytics.com", "https://*.googletagmanager.com"] if GA4_ID else [])
    if ADS_HEAD:
        # AdSense spreads across many Google hosts (and rotates them), so its families are allowed by
        # wildcard. Ad creatives and tracking pixels come from arbitrary advertiser CDNs, hence https: for images.
        ad_hosts = ["https://*.googlesyndication.com", "https://*.doubleclick.net", "https://*.google.com", "https://*.gstatic.com",
                    "https://*.googleadservices.com", "https://*.googletagservices.com", "https://*.adtrafficquality.google"]
        # AdSense injects inline scripts into about:srcdoc ad frames, which inherit this policy, and their
        # content varies, so they can't be hash-pinned (Google doesn't support hash CSPs for AdSense).
        # Browsers ignore 'unsafe-inline' while any hash is listed, so ads-on drops the hashes.
        scripts = ["'self'", "'unsafe-inline'"] + scripts[scripts.index("https://www.googletagmanager.com"):] + ad_hosts
        connect += ad_hosts
        frames += ad_hosts
        imgs = ["'self'", "data:", "https:"]
    # 'unsafe-inline' in style-src covers the style="--i:N" tile-stagger attributes only;
    # no inline <style> blocks are emitted. Inline *scripts* are hash-pinned, not unsafe-inline.
    return "; ".join([
        "default-src 'self'",
        "script-src " + " ".join(scripts),
        "style-src " + " ".join(styles),
        "font-src " + " ".join(fonts),
        "connect-src " + " ".join(connect),
        "img-src " + " ".join(imgs),
        *(["frame-src " + " ".join(frames)] if frames else []),
        "base-uri 'none'",       # stops an injected <base> from re-pointing every relative URL
        "object-src 'none'",
        "frame-ancestors 'none'", # clickjacking
        "form-action 'none'",     # the site has no forms; block exfiltration via injected ones
        "upgrade-insecure-requests",
    ])

# ---------- dictionary: expand hunspell en_US affixes ----------
def load_words():
    aff, rules = open("/usr/share/hunspell/en_US.aff", encoding="utf-8").read().splitlines(), {}
    i = 0
    while i < len(aff):
        p = aff[i].split()
        if len(p) == 4 and p[0] in ("PFX", "SFX") and p[3].isdigit():
            kind, flag, cross, n = p[0], p[1], p[2] == "Y", int(p[3])
            lst = []
            for line in aff[i+1:i+1+n]:
                _, _, strip, add, cond = line.split()[:5]
                strip = "" if strip == "0" else strip
                add = "" if add == "0" else add.split("/")[0]
                lst.append((strip, add, re.compile(("^" + cond) if kind == "PFX" else (cond + "$"))))
            rules[flag] = (kind, cross, lst)
            i += n
        i += 1

    def apply(w, kind, lst):
        for strip, add, rx in lst:
            if rx.search(w):
                if kind == "SFX" and w.endswith(strip): yield w[:len(w)-len(strip)] + add
                elif kind == "PFX" and w.startswith(strip): yield add + w[len(strip):]

    base, derived = set(), set()
    for line in open("/usr/share/hunspell/en_US.dic", encoding="utf-8").read().splitlines()[1:]:
        w, _, flags = line.partition("/")
        if not w or not w[0].islower(): continue           # skip proper nouns
        base.add(w)
        sfx = [f for f in flags if f in rules and rules[f][0] == "SFX"]
        pfx = [f for f in flags if f in rules and rules[f][0] == "PFX"]
        s_forms = []
        for f in sfx:
            forms = list(apply(w, "SFX", rules[f][2])); derived.update(forms)
            if rules[f][1]: s_forms += forms
        for f in pfx:
            derived.update(apply(w, "PFX", rules[f][2]))
            if rules[f][1]:
                for sw in s_forms: derived.update(apply(sw, "PFX", rules[f][2]))
    block = set(open(os.path.join(ROOT, "blocklist.txt")).read().split())
    ok = lambda w: w.isascii() and w.isalpha() and w.islower() and 3 <= len(w) <= 8 and w not in block
    # ponytail: frequency comes from ~50MB of local docs/man pages (freq.py), so it leans technical;
    # swap freq.txt for a general-English frequency list for better "common first" order
    freq = {}
    for line in open(os.path.join(ROOT, "freq.txt")):
        w, c = line.split(); freq[w] = int(c)
    for w in "jammy focal noble clang regex multi tuple macro ditto libs bionic xenial trusty".split(): freq.pop(w, None)
    by_len = {n: [] for n in LENGTHS}
    for w in sorted(base | derived, key=lambda w: (-freq.get(w, 0), w not in base, w)):
        if ok(w): by_len[len(w)].append(w)
    # ponytail: jargon stop-list for daily answers because freq.txt is tech-heavy; a general frequency list removes the need
    jargon = set("latex intel gnome meson peter parse setup proxy queue cache flaky expat tuple debug codec admin pixel cisco ascii unix linux mutex regex fstab mkdir chmod xterm emacs vimrc perl ghazi scudo kukri equiv burke unary abase stein swain radix inter xerox theta gamma colon".split())
    answers = [w for w in by_len[5] if w in base and freq.get(w, 0) >= 20 and not w.endswith("s") and w not in jargon]
    return by_len, answers

WORDS, ANSWERS = load_words()
TOTAL = sum(len(v) for v in WORDS.values())

# ---------- url helpers (prod = clean folders, preview = flat files) ----------
def u(slug=""):
    if PREVIEW: return (slug or "index") + ".html"
    return "/" + (slug + "/" if slug else "")
def asset(p): return p if PREVIEW else "/" + p
def canon(slug=""): return SITE_URL + "/" + (slug + "/" if slug else "")
def finder_slug(n): return "" if n == 5 else f"{n}-letter-words"
def start_slug(n, c): return f"{n}-letter-words-starting-with-{c}"
def end_slug(n, c): return f"{n}-letter-words-ending-in-{c}"
STARTS = {n: {c: [w for w in WORDS[n] if w[0] == c] for c in ABC} for n in LENGTHS}
ENDS = {n: {c: [w for w in WORDS[n] if w[-1] == c] for c in ABC} for n in LENGTHS}
MIN_LIST = 5   # don't publish thin pages
has_start = lambda n, c: len(STARTS[n][c]) >= MIN_LIST
has_end = lambda n, c: len(ENDS[n][c]) >= MIN_LIST

# ---------- tiny markdown -> html for hand-written pages ----------
def md2html(md):
    def href(t):
        t = u(t.strip("/")) if t.startswith("/") else t
        # esc(..., quote=False) above leaves " intact, so an unescaped URL could close the
        # href attribute and add an event handler. Escape quotes, and allow only schemes that
        # cannot execute: anything else (javascript:, data:, vbscript:) becomes "#".
        scheme = re.match(r"\s*([a-zA-Z][a-zA-Z0-9+.\-]*):", t)
        if scheme and scheme.group(1).lower() not in ("http", "https", "mailto"): t = "#"
        # & < > are already escaped by the esc(..., quote=False) above; escaping again here
        # would turn &amp; into &amp;amp; and break query strings. Only the quotes are missing.
        return t.replace('"', "&quot;").replace("'", "&#x27;")
    inline = lambda s: re.sub(r"\[([^\]]+)\]\(([^)]+)\)", lambda m: f'<a href="{href(m.group(2))}">{m.group(1)}</a>', re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", esc(s, quote=False)))
    out, lst = [], []
    for block in md.strip().split("\n\n"):
        b = block.strip()
        if b.startswith("## "): out.append(f"<h2>{inline(b[3:])}</h2>")
        elif b.startswith("- "): out.append("<ul>" + "".join(f"<li>{inline(x[2:])}</li>" for x in b.split("\n")) + "</ul>")
        elif b.startswith("|"):
            rows = [r.strip("|").split("|") for r in b.split("\n") if not set(r) <= set("|- ")]
            out.append('<div class="tw"><table><thead><tr>' + "".join(f"<th>{inline(c.strip())}</th>" for c in rows[0]) + "</tr></thead><tbody>" +
                       "".join("<tr>" + "".join(f"<td>{inline(c.strip())}</td>" for c in r) + "</tr>" for r in rows[1:]) + "</tbody></table></div>")
        else: out.append(f"<p>{inline(b)}</p>")
    return "\n".join(out)

# ---------- layout ----------
def tiles(word, pattern=None, cls="hero-tiles"):
    pattern = pattern or ["hit" if i % 3 == 0 else "near" if i % 3 == 1 else "" for i in range(len(word))]
    t = "".join(f'<span class="ht {pattern[i]}" style="--i:{i}">{esc(ch) if ch != "_" else ""}</span>' for i, ch in enumerate(word))
    return f'<div class="{cls}" aria-hidden="true">{t}</div>'

def crumbs(items):
    full = [("Home", "")] + items
    ld = {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": i+1, "name": n, "item": canon(s)} for i, (n, s) in enumerate(full)]}
    links = " / ".join(f'<a href="{u(s)}">{esc(n)}</a>' if i < len(full)-1 else f'<span aria-current="page">{esc(n)}</span>'
                       for i, (n, s) in enumerate(full))
    return (f'<nav class="crumbs" aria-label="Breadcrumb">{links}</nav>' if items else ""), ld

def faq_block(qa):
    ld = {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
        {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": re.sub("<[^>]+>", "", a)}} for q, a in qa]}
    body = "".join(f"<details><summary>{esc(q)}</summary><p>{a}</p></details>" for q, a in qa)
    return f'<section class="prose faq"><h2>Frequently asked questions</h2>{body}</section>', ld

def faq_md(qa):
    return "## Frequently asked questions\n\n" + "\n\n".join(f"### {q}\n\n{re.sub('<[^>]+>', '', a).replace('**','')}" for q, a in qa)

def source_line():
    return (f'<p class="src">Updated <time datetime="{TODAY}">{TODAY_H}</time> · Word list: {DICT_NOTE.split(" (")[0]} · '
            f'<a href="{u("how-our-word-list-works")}">How our word list works</a></p>')

def az_strip(n, kind, current=None):
    out = []
    for c in ABC:
        ok = has_start(n, c) if kind == "start" else has_end(n, c)
        slug = start_slug(n, c) if kind == "start" else end_slug(n, c)
        if not ok: out.append(f'<span class="az off">{c.upper()}</span>')
        elif c == current: out.append(f'<span class="az on" aria-current="page">{c.upper()}</span>')
        else: out.append(f'<a class="az" href="{u(slug)}">{c.upper()}</a>')
    return '<div class="azs">' + "".join(out) + "</div>"

def az_md(n, kind):
    return " · ".join(f"[{c.upper()}]({canon(start_slug(n, c) if kind == 'start' else end_slug(n, c))})"
                      for c in ABC if (has_start(n, c) if kind == "start" else has_end(n, c)))

ORG = {"@context": "https://schema.org", "@type": "Organization", "@id": SITE_URL + "/#org", "name": SITE_NAME,
       "url": SITE_URL + "/", "logo": SITE_URL + "/logo.png", "email": EMAIL,
       "description": f"{SITE_NAME} is an independent, free word finder and daily word puzzle for Wordle, Scrabble and other word games."}
SITE_LD = {"@context": "https://schema.org", "@type": "WebSite", "@id": SITE_URL + "/#site", "name": SITE_NAME,
           "url": SITE_URL + "/", "publisher": {"@id": SITE_URL + "/#org"}, "inLanguage": "en"}

SITEMAP, MDPAGES = [], []

NO_ADS = {"privacy-policy", "terms", "contact", "404"}   # legal/error pages: AdSense discourages ads there

def with_ad(slug, body):
    """Place the one AdSense unit: after a tool's results, before the explanatory prose, so it never sits
    among inputs or tiles. The daily puzzle puts it before its FAQ, away from the on-screen keyboard
    (taps that land on an ad by accident count as invalid clicks). Plain pages get it at the end.
    app.js pushes each unit to adsbygoogle, so there is no inline script to hash."""
    if not ADS_HEAD or slug in NO_ADS: return body
    ad = (f'<aside class="ad" aria-label="Advertisement"><ins class="adsbygoogle" style="display:block" '
          f'data-ad-client="{esc(ADSENSE_ID)}" data-ad-slot="{esc(ADSENSE_SLOT)}" data-ad-format="auto" '
          f'data-full-width-responsive="true"></ins></aside>')
    mark = ('<section class="prose faq">' if 'data-tool="daily"' in body else
            '<section class="prose' if 'class="results"' in body else None)
    i = body.find(mark) if mark else -1
    return body[:i] + ad + body[i:] if i >= 0 else body + ad

def page(slug, title, desc, body, ld=(), preload=None, h_index=True, md=None):
    """md = (md_title, purpose, topic, markdown_body) for the public Markdown mirror"""
    body = with_ad(slug, body)
    ga = (f'<script async src="https://www.googletagmanager.com/gtag/js?id={esc(GA4_ID)}"></script>'
          f"<script>{GA_JS}</script>") if GA4_ID else ""
    webpage = {"@context": "https://schema.org", "@type": "WebPage", "@id": canon(slug) + "#page", "url": canon(slug), "name": title,
               "description": desc, "isPartOf": {"@id": SITE_URL + "/#site"}, "dateModified": TODAY, "inLanguage": "en"}
    lds = "".join(f'<script type="application/ld+json">{ldjson(x)}</script>'
                  for x in [webpage, *ld] + ([ORG, SITE_LD] if slug == "" else []))
    pre = f'<link rel="preload" href="{asset(preload)}" as="fetch" crossorigin>' if preload else ""
    alt = f'<link rel="alternate" type="text/markdown" href="{SITE_URL}/llm/pages/{slug or "home"}.md">' if md and not PREVIEW else ""
    # WEBFONTS=False removes the only third party the site contacts. style.css already names
    # system fallbacks for both families, so the page just renders in those instead.
    fonts = ("""
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" referrerpolicy="no-referrer" href="https://fonts.googleapis.com/css2?family=Atkinson+Hyperlegible:wght@400;700&family=Unbounded:wght@600;800&display=swap">""" if WEBFONTS else "")
    gsc = f'\n<meta name="google-site-verification" content="{esc(GSC_VERIFY)}" />' if GSC_VERIFY and slug == "" else ""
    gsc += f'\n<meta name="google-adsense-account" content="{esc(ADSENSE_ID)}">' if ADSENSE_ID else ""
    gtm = f"<script>{GTM_JS}</script>" if GTM_ID else ""
    gtm_ns = (f'<noscript><iframe src="https://www.googletagmanager.com/ns.html?id={esc(GTM_ID)}" height="0" width="0" '
              f'style="display:none;visibility:hidden"></iframe></noscript>\n') if GTM_ID else ""
    head = f"""{ga}{gtm}<title>{esc(title)}</title>
<meta name="claude:viewport-fit-sides" content="cover">
<meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{canon(slug)}">
<meta name="robots" content="{'index,follow,max-snippet:-1' if h_index else 'noindex'}">{gsc}
<meta name="theme-color" content="#1b2433">
<meta property="og:type" content="website"><meta property="og:site_name" content="{esc(SITE_NAME)}">
<meta property="og:title" content="{esc(title)}"><meta property="og:description" content="{esc(desc)}">
<meta property="og:url" content="{canon(slug)}"><meta property="og:image" content="{SITE_URL}/logo.png"><meta name="twitter:card" content="summary">
<link rel="icon" href="{asset('favicon.ico')}" sizes="48x48"><link rel="icon" href="{asset('favicon-32x32.png')}" type="image/png" sizes="32x32">
<link rel="apple-touch-icon" href="{asset('apple-touch-icon.png')}"><link rel="manifest" href="{asset('site.webmanifest')}">{alt}
<meta name="referrer" content="strict-origin-when-cross-origin">{fonts}
<link rel="stylesheet" href="{asset('style.css')}">{pre}
<script>{THEME_JS}</script>
{"" if slug in NO_ADS else ADS_HEAD}{lds}"""
    nav_l = "".join(f'<a href="{u(finder_slug(n))}" data-k="{finder_slug(n) or "home"}">{n}</a>' for n in LENGTHS)
    foot_az = "".join(f'<a href="{u(start_slug(5,c))}">{c.upper()}</a>' for c in ABC if has_start(5, c))
    content = f"""{gtm_ns}<a class="skip" href="#main">Skip to content</a>
<header class="top"><div class="wrap bar">
<a class="logo" href="{u()}" aria-label="{SITE_NAME} home"><img class="lt" src="{asset('logo-mark.png')}" width="38" height="34" alt=""><span>Word<em>Trove</em></span></a>
<nav class="nav" aria-label="Main"><span class="nl">Letters</span>{nav_l}<a href="{u('word-unscrambler')}" data-k="word-unscrambler">Unscramble</a><a href="{u('daily-word-puzzle')}" data-k="daily-word-puzzle" class="daily-link">Daily<span class="dot" hidden></span></a><a href="{u('word-lists')}" data-k="word-lists">Lists</a></nav>
<button class="theme" id="theme" type="button" aria-label="Switch light or dark theme"><span></span></button>
</div></header>
<main id="main" class="wrap" data-page="{slug or 'home'}"{" data-ads" if ADS_HEAD else ""}>{body}</main>
<footer class="foot"><div class="wrap">
<div class="fcols">
<div><p class="fh">Word finders</p>{''.join(f'<a href="{u(finder_slug(n))}">{n} letter word finder</a>' for n in LENGTHS)}<a href="{u('word-unscrambler')}">Word unscrambler</a><a href="{u('daily-word-puzzle')}">Daily word puzzle</a></div>
<div><p class="fh">5 letter words starting with</p><div class="fz">{foot_az}</div><a href="{u('word-lists')}">All word lists →</a></div>
<div><p class="fh">{SITE_NAME}</p><a href="{u('about')}">About</a><a href="{u('how-our-word-list-works')}">How our word list works</a><a href="{u('contact')}">Contact</a><a href="{u('privacy-policy')}">Privacy policy</a><a href="{u('terms')}">Terms of use</a></div>
</div>
<p class="copy">© {date.today().year} {SITE_NAME}. Independent word finder for Wordle, Scrabble and every word game. Not affiliated with The New York Times, Hasbro or Mattel.</p>
</div></footer>
<div class="toast" id="toast" role="status" aria-live="polite"></div>
<script src="{asset('app.js')}" defer></script>"""
    if PREVIEW and slug == "":   # artifact preview wraps the entry page itself and needs a short name
        doc = head.replace(f"<title>{esc(title)}</title>", f"<title>{SITE_NAME}</title>", 1) + "\n" + content
    else:
        doc = f'<!doctype html>\n<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">\n{head}</head><body>\n{content}\n</body></html>'
    path = os.path.join(OUT, (slug or "index") + ".html") if PREVIEW else os.path.join(OUT, slug, "index.html")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "w", encoding="utf-8").write(doc)
    if slug != "404" and h_index: SITEMAP.append(canon(slug))
    if md: MDPAGES.append({"id": slug or "home", "url": canon(slug), "title": md[0], "purpose": md[1], "topic": md[2], "body": md[3]})

def word_list(words):
    return '<ul class="wl">' + "".join(f'<li>{w}<sup>{score(w)}</sup></li>' for w in words) + "</ul>"

def words_md(words, per=12):
    up = [w.upper() for w in words]
    return "\n".join(", ".join(up[i:i+per]) for i in range(0, len(up), per))

# ---------- pages ----------
def finder_page(n):
    slug, ws = finder_slug(n), WORDS[n]
    kw = f"{n} Letter Word Finder"
    title = f"{kw} – {n} Letter Words With These Letters" + (" | Wordle Solver" if n == 5 else "")
    desc = (f"Find 5 letter words with these letters in seconds. Enter green, yellow and grey letters to solve Wordle, "
            f"Scrabble and crossword puzzles. {len(ws):,} words, free, no sign-up.") if n == 5 else (
            f"Free {n} letter word finder: type the letters you know and instantly see every {n} letter word that fits, "
            f"with Scrabble points. Search {len(ws):,} {NUM[n].lower()} letter words.")
    boxes = "".join(f'<input class="box" id="k{i}" maxlength="1" autocomplete="off" autocapitalize="characters" inputmode="text" aria-label="Letter {i+1}">' for i in range(n))
    crumb, cld = crumbs([] if n == 5 else [(kw, slug)])
    top = ws[:60]
    best = max(ws, key=score)
    novowel = sum(1 for w in ws if not set(w) & set("aeiou"))
    games = "Wordle, Quordle and Scrabble" if n == 5 else "Scrabble, Words With Friends and crosswords"
    answer = (f"{SITE_NAME}'s {n} letter word finder searches {len(ws):,} {NUM[n].lower()} letter words. "
              f"Type letters you know into their positions, add letters that are in the word, and remove letters that aren't. "
              f"Every matching word appears instantly with its Scrabble score.")
    qa = [
        (f"How many {n} letter words are there?", f"The {SITE_NAME} word list has {len(ws):,} playable {n} letter words. {novowel:,} of them have no A, E, I, O or U. Counts differ between dictionaries; see how our word list works."),
        (f"What is the highest scoring {n} letter word?", f"<strong>{best.upper()}</strong> scores {score(best)} points with standard English Scrabble tile values, before board bonuses."),
        (f"How do I find {n} letter words with these letters?", "Type letters you know the position of into the green boxes, letters that are in the word but in the wrong spot into the yellow field, and letters that are not in the word into the grey field. The list updates as you type."),
        (f"Is the {SITE_NAME} word finder free?", f"Yes. {SITE_NAME} is free, needs no account, and runs searches in your browser on any phone or computer."),
    ]
    if n == 5:
        qa.insert(2, ("What is the best first word for Wordle?", "A strong first guess tests the most common letters. SLATE, CRANE and RAISE each cover five frequent, different letters. After your first guess, use the best next guess suggestion that appears under the finder."))
    fq, fld = faq_block(qa)
    others = "".join(f'<a class="chip" href="{u(finder_slug(m))}">{m} letter words</a>' for m in LENGTHS if m != n)
    body = f"""{crumb}
<section class="hero">{tiles(HERO[n])}
<h1>{kw}</h1>
<p class="lede">Find {n} letter words with these letters. Fill in what you know and the list narrows as you type, ready for {games}.</p></section>
<section class="tool" data-tool="finder" data-len="{n}" data-src="{asset(f'data/{n}.txt')}" aria-label="{kw}">
<div class="field"><label class="lab hit" for="k0">Correct spot <small>letters you know the position of</small></label><div class="boxes" style="--n:{n}">{boxes}</div></div>
<div class="row2">
<div class="field"><label class="lab near" for="inc">In the word <small>wrong spot</small></label><input class="txt" id="inc" autocomplete="off" placeholder="e.g. RA"></div>
<div class="field"><label class="lab miss" for="exc">Not in the word</label><input class="txt" id="exc" autocomplete="off" placeholder="e.g. TOSH"></div>
</div>
<div class="meter" aria-live="polite"><div class="mbar"><i id="mbar"></i></div><p id="mtext">{len(ws):,} possible words. Add a letter to start narrowing.</p></div>
<p class="hint" id="hint" hidden></p>
<div class="actions"><button class="btn" type="button" id="go">Find words</button><button class="btn ghost" type="button" id="reset">Reset</button></div>
</section>
<div class="ad ad-top"></div>
<section class="results" id="results" aria-live="polite">
<div class="rhead"><h2 id="rtitle">Popular {n} letter words</h2><div class="rtools"><span class="count" id="count">{len(ws):,} words</span>
<label class="sr" for="sort">Sort</label><select id="sort"><option value="c">Common first</option><option value="a">A to Z</option><option value="s">Highest score</option></select></div></div>
<ul class="tiles" id="out">{''.join(f'<li class="t"><b>{w}</b><i>{score(w)}</i></li>' for w in top)}</ul>
<button class="btn ghost more" id="more" type="button" hidden>Show more</button>
</section>
<a class="promo" href="{u('daily-word-puzzle')}"><span class="pt">{tiles('DAILY', ['hit','near','','hit',''], 'mini-tiles')}</span><span><b>Today's WordTrove puzzle</b><small>One 5 letter word, six guesses, a new word every midnight. Keep your streak going.</small></span><span class="go">Play →</span></a>
<section class="prose answer"><h2>Quick answer</h2><p>{answer}</p>{source_line()}</section>
<section class="prose">
<h2>How to use the {n} letter word finder</h2>
<ol class="steps"><li><strong>Green boxes.</strong> Type each letter you know into its exact spot. Leave the rest empty.</li>
<li><strong>In the word.</strong> Add letters that appear but whose position you don't know yet.</li>
<li><strong>Not in the word.</strong> Add every letter you have ruled out.</li>
<li><strong>Pick a word.</strong> Tap any tile to copy it. The small number is its Scrabble score. The best next guess line suggests the word that splits the remaining list most evenly.</li></ol>
<p>Every search runs in your browser, so results appear instantly even on a slow connection.</p>
<h2>{n} letter words by first and last letter</h2>
<p>Browse complete lists of {NUM[n].lower()} letter words starting with any letter:</p>{az_strip(n, 'start')}
<p>Or ending in a letter:</p>{az_strip(n, 'end')}
<h2>Other word lengths</h2><div class="chips">{others}<a class="chip" href="{u('word-unscrambler')}">Word unscrambler</a></div>
</section>
{fq}"""
    lds = [cld, fld, {"@context": "https://schema.org", "@type": "WebApplication", "name": f"{SITE_NAME} {kw}",
           "url": canon(slug), "applicationCategory": "GameApplication", "operatingSystem": "Any", "isAccessibleForFree": True,
           "publisher": {"@id": SITE_URL + "/#org"}, "offers": {"@type": "Offer", "price": "0", "priceCurrency": "USD"}}]
    md = f"""## Quick answer

{answer}

Canonical tool: [{kw}]({canon(slug)})

## How to use the {n} letter word finder

1. Green boxes: type each letter you know into its exact position.
2. In the word: add letters that appear in the word but whose position is unknown.
3. Not in the word: add every letter you have ruled out.
4. Pick a word from the list. Each word shows its Scrabble score.

## Key facts

- {NUM[n]} letter words in the {SITE_NAME} list: {len(ws):,}
- Words with no A, E, I, O or U: {novowel:,}
- Highest scoring {n} letter word: {best.upper()} ({score(best)} points, standard English Scrabble tile values)
- Updated: {TODAY}

## Most common {n} letter words

{words_md(ws[:120])}

## {n} letter words by first letter

{az_md(n, 'start')}

## {n} letter words by last letter

{az_md(n, 'end')}

{faq_md(qa)}

## Source and method

Word list: {DICT_NOTE}, filtered as described in [How our word list works]({canon('how-our-word-list-works')}). Game dictionaries such as Wordle, NWL and Collins differ, so a listed word may not be accepted by every game."""
    page(slug, title, desc, body, lds, preload=f"data/{n}.txt", md=(kw, f"Find {n} letter words with known, included and excluded letters", "word-finders", md))

def list_page(n, c, kind):
    ws = STARTS[n][c] if kind == "start" else ENDS[n][c]
    L = c.upper()
    rel = "starting with" if kind == "start" else "ending in"
    phrase = f"{n} Letter Words {'Starting With' if kind == 'start' else 'Ending in'} {L}"
    slug = start_slug(n, c) if kind == "start" else end_slug(n, c)
    title = f"{phrase} ({len(ws):,} Words) – Full List With Scores"
    best = max(ws, key=score)
    vow = [w for w in ws if sum(ch in "aeiou" for ch in w) >= (3 if n >= 5 else 2)]
    common = ws[:8]
    desc = (f"All {len(ws):,} {n} letter words {'that start with' if kind == 'start' else 'that end in'} {L}, like "
            f"{', '.join(w.upper() for w in common[:3])}. Sorted list with Scrabble points for Wordle and word games.")
    pat = (c + "." * (n - 1)) if kind == "start" else ("." * (n - 1) + c)
    pattern = list(L + "_" * (n - 1)) if kind == "start" else list("_" * (n - 1) + L)
    colors = ["hit" if ch != "_" else "" for ch in pattern]
    other_slug = end_slug(n, c) if kind == "start" else start_slug(n, c)
    other_ok = has_end(n, c) if kind == "start" else has_start(n, c)
    crumb, cld = crumbs([(f"{n} Letter Word Finder", finder_slug(n)), (phrase, slug)])
    answer = (f"There are {len(ws):,} {n} letter words {rel} {L} in the {SITE_NAME} word list. "
              f"The most common are {', '.join(w.upper() for w in common[:5])}. "
              f"The highest scoring is {best.upper()} at {score(best)} Scrabble points.")
    qa = [(f"How many {phrase.lower()} are there?", f"There are {len(ws):,} {phrase.lower()} in the {SITE_NAME} word list, which is based on the SCOWL English dictionary."),
          (f"What is the highest scoring {n} letter word {rel} {L}?", f"<strong>{best.upper()}</strong> is worth {score(best)} points with standard English Scrabble tile values.")]
    if vow: qa.append((f"Which {phrase.lower()} have the most vowels?", ", ".join(w.upper() for w in vow[:6]) + " each contain several vowels, which makes them useful for testing letters in Wordle."))
    fq, fld = faq_block(qa)
    lens = "".join(f'<a class="chip" href="{u(start_slug(m, c) if kind == "start" else end_slug(m, c))}">{m} letters</a>'
                   for m in LENGTHS if m != n and (has_start(m, c) if kind == "start" else has_end(m, c)))
    item_ld = {"@context": "https://schema.org", "@type": "ItemList", "name": phrase, "numberOfItems": len(ws),
               "itemListElement": [{"@type": "ListItem", "position": i+1, "name": w.upper()} for i, w in enumerate(ws[:20])]}
    body = f"""{crumb}
<section class="hero">{tiles(''.join(pattern), colors)}
<h1>{phrase}</h1>
<p class="lede"><strong>{answer}</strong> Need to narrow it down? <a href="{u(finder_slug(n))}?k={pat}">Open this pattern in the {n} letter word finder</a>.</p>
<div class="stats"><div><b>{len(ws):,}</b><span>words</span></div><div><b>{best.upper()}</b><span>top score · {score(best)} pts</span></div><div><b>{len(set(w[1 if kind=='start' else -2] for w in ws))}</b><span>different {'second' if kind=='start' else 'second-to-last'} letters</span></div></div>
{source_line()}
</section>
<div class="ad ad-top"></div>
<section class="results"><div class="rhead"><h2>All {phrase.lower()}</h2><span class="count">Most common first</span></div>{word_list(ws)}</section>
<section class="prose"><h2>{n} letter words {rel} other letters</h2>{az_strip(n, kind, c)}
<h2>More lists for the letter {L}</h2><div class="chips">{lens}{f'<a class="chip" href="{u(other_slug)}">{n} letter words {"ending in" if kind == "start" else "starting with"} {L}</a>' if other_ok else ''}</div></section>
{fq}"""
    md = f"""## Quick answer

{answer}

Canonical list: [{phrase}]({canon(slug)})

## Key facts

- Words in this list: {len(ws):,}
- Highest scoring: {best.upper()} ({score(best)} points)
- Order: most common first, using word frequency in an English text corpus
- Updated: {TODAY}

## All {phrase.lower()}

{words_md(ws)}

{faq_md(qa)}

## Source and method

Word list: {DICT_NOTE}. Method and limits: [How our word list works]({canon('how-our-word-list-works')}). To filter this list by more letters, use the [{n} letter word finder]({canon(finder_slug(n))})."""
    page(slug, title, desc, body, [cld, fld, item_ld], md=(phrase, f"Complete list of {n} letter words {rel} {L} with Scrabble scores", "word-lists", md))

def solve(letters):
    have, q = Counter(c for c in letters if c != "?"), letters.count("?")
    res = []
    for n in sorted(LENGTHS, reverse=True):
        if n > len(letters): continue
        for w in WORDS[n]:
            need = Counter(w)
            if sum(max(0, need[k] - have[k]) for k in need) <= q: res.append(w)
    return res

def unscramble_page():
    slug, ex = "word-unscrambler", "planets"
    res = solve(ex)
    groups = {}
    for w in res: groups.setdefault(len(w), []).append(w)
    pre = "".join(f'<h3 class="gh">{n} letter words <span>{len(g)}</span></h3><ul class="tiles">' +
                  "".join(f'<li class="t"><b>{w}</b><i>{score(w)}</i></li>' for w in sorted(g, key=score, reverse=True)[:40]) + "</ul>"
                  for n, g in groups.items())
    crumb, cld = crumbs([("Word Unscrambler", slug)])
    qa = [("How does the WordTrove word unscrambler work?", "It checks every word in the WordTrove list and keeps the ones you can spell with your letters, using each letter only as many times as you typed it."),
          ("Can I use blank tiles?", "Yes. Type a question mark (?) for each blank tile or wildcard, up to three."),
          ("How many letters can I enter?", "Up to 12 letters. Results show words from 3 to 8 letters long, longest first.")]
    fq, fld = faq_block(qa)
    answer = (f"To unscramble letters, type them into the {SITE_NAME} word unscrambler. It lists every word from 3 to 8 letters you can spell "
              f"with those letters, longest and highest scoring first. Use ? for a blank tile. For example, PLANETS makes {len(res)} words.")
    body = f"""{crumb}
<section class="hero">{tiles('SHUFFLE', ['near','','hit','','near','hit',''])}
<h1>Word Unscrambler</h1>
<p class="lede">Unscramble letters into words. Type your tiles, add ? for blanks, and see every word you can make, longest and highest scoring first.</p></section>
<section class="tool" data-tool="unscramble" data-src="{asset('data/')}" aria-label="Word unscrambler">
<div class="field"><label class="lab hit" for="letters">Your letters <small>use ? for a blank tile</small></label>
<input class="txt big" id="letters" maxlength="12" autocomplete="off" value="{ex.upper()}"></div>
<div class="actions"><button class="btn" type="button" id="go">Unscramble</button><button class="btn ghost" type="button" id="shuffle">Shuffle tiles</button><button class="btn ghost" type="button" id="reset">Clear</button></div>
</section>
<div class="ad ad-top"></div>
<section class="results" id="results" aria-live="polite"><div class="rhead"><h2 id="rtitle">Words from {ex.upper()}</h2><span class="count" id="count">{len(res):,} words</span></div>
<div id="out">{pre}</div></section>
<section class="prose answer"><h2>Quick answer</h2><p>{answer}</p>{source_line()}</section>
<section class="prose"><h2>Unscramble letters for any word game</h2>
<p>Stuck on a rack in Scrabble or Words With Friends, a jumble in the newspaper, or an anagram clue? Enter the letters and pick from the list. Each tile shows its Scrabble score so you can see the best play at a glance. Tap a word to copy it.</p>
<p>Know where some letters go? Use the <a href="{u()}">5 letter word finder</a> or pick another length: {' '.join(f'<a href="{u(finder_slug(n))}">{n}</a>' for n in LENGTHS if n != 5)}.</p></section>
{fq}"""
    md = f"""## Quick answer

{answer}

Canonical tool: [Word Unscrambler]({canon(slug)})

## Example: words from PLANETS

""" + "\n\n".join(f"{n} letter words ({len(g)}): {', '.join(w.upper() for w in sorted(g, key=score, reverse=True)[:30])}" for n, g in groups.items()) + f"""

{faq_md(qa)}

## Source and method

Word list: {DICT_NOTE}. Method: [How our word list works]({canon('how-our-word-list-works')})."""
    page(slug, "Word Unscrambler – Unscramble Letters Into Words Instantly", "Unscramble letters to find every word you can make. Supports blank tiles (?), shows Scrabble points and sorts longest words first. Free unscrambler for Scrabble, Wordle and jumbles.", body, [cld, fld], md=("Word Unscrambler", "Unscramble letters into every possible 3 to 8 letter word", "word-finders", md))

def daily_page():
    slug = "daily-word-puzzle"
    crumb, cld = crumbs([("Daily Word Puzzle", slug)])
    qa = [("How does the WordTrove daily puzzle work?", "Guess the hidden 5 letter word in six tries. After each guess, green tiles are right letters in the right spot, yellow tiles are in the word but in another spot, and grey tiles are not in the word."),
          ("When is there a new puzzle?", "A new word starts at midnight in your own time zone. A countdown under the board shows how long is left."),
          ("Where are my streak and stats saved?", "In your browser on this device only. WordTrove has no accounts and does not send your guesses anywhere. Clearing site data resets them."),
          ("Can I play more than once a day?", "Yes. After the daily puzzle, press Practice round for unlimited random words. Practice rounds do not change your streak.")]
    fq, fld = faq_block(qa)
    def key(k):
        label = {"enter": "Enter", "del": "⌫"}.get(k, k)
        wide = " wide" if k in ("enter", "del") else ""
        return f'<button type="button" class="key{wide}" data-k="{k}" aria-label="{"Delete" if k == "del" else label}">{label}</button>'
    keys = "".join('<div class="kr">' + "".join(key(k) for k in row) + "</div>"
                   for row in [list("qwertyuiop"), list("asdfghjkl"), ["enter", *"zxcvbnm", "del"]])
    body = f"""{crumb}
<section class="hero slim">{tiles('GUESS', ['','near','hit','','hit'])}<h1>Daily Word Puzzle</h1>
<p class="lede">Guess today's 5 letter word in six tries. A new word every midnight, your streak saved on this device.</p></section>
<section class="game" data-tool="daily" data-src="{asset('data/5.txt')}" data-ans="{asset('data/daily.txt')}" aria-label="Daily word puzzle">
<div class="gbar"><span id="gnum">Puzzle</span><span id="gmode">Daily</span></div>
<div class="board" id="board" aria-live="polite"></div>
<p class="gmsg" id="gmsg">Type or tap letters, then press Enter.</p>
<div class="kb" id="kb">{keys}</div>
<div class="gend" id="gend" hidden>
<div class="gstats"><div><b id="s-played">0</b><span>played</span></div><div><b id="s-win">0%</b><span>won</span></div><div><b id="s-streak">0</b><span>streak</span></div><div><b id="s-max">0</b><span>best streak</span></div></div>
<p class="next">Next word in <b id="countdown">--:--:--</b></p>
<div class="actions"><button class="btn" type="button" id="share">Copy result</button><button class="btn ghost" type="button" id="practice">Practice round</button><a class="btn ghost" id="lookup" href="{u()}">Open word finder</a></div>
</div>
</section>
<section class="prose answer"><h2>How to play</h2><p>{qa[0][1]} You can check which words fit your clues with the <a href="{u()}">5 letter word finder</a> after the puzzle, but no peeking.</p></section>
{fq}"""
    md = f"""## How to play

{qa[0][1]}

Canonical game page: [Daily Word Puzzle]({canon(slug)})

## Key facts

- Word length: 5 letters. Guesses allowed: 6.
- New puzzle: every midnight in the player's local time zone.
- Guesses are checked against {len(WORDS[5]):,} five letter words; answers come from a smaller list of {len(ANSWERS):,} common words.
- Streaks and stats are stored only in the player's browser.

{faq_md(qa)}"""
    page(slug, "Daily Word Puzzle – Guess the 5 Letter Word in 6 Tries | WordTrove", "Play the free WordTrove daily word puzzle: guess the hidden 5 letter word in six tries, keep your streak, and share your result. New word every midnight.",
         body, [cld, fld], md=("Daily Word Puzzle", "Rules and facts for the daily 5 letter word guessing game", "games", md))

def lists_page():
    slug = "word-lists"
    secs = "".join(f'<h2>{n} letter words</h2><p class="sub">Starting with</p>{az_strip(n, "start")}<p class="sub">Ending in</p>{az_strip(n, "end")}' for n in LENGTHS)
    crumb, cld = crumbs([("Word Lists", slug)])
    body = f"""{crumb}<section class="hero">{tiles('LISTS', ['hit','','near','','hit'])}<h1>Word Lists by Letter</h1>
<p class="lede">Every word list on {SITE_NAME}: {NUM[3].lower()} to {NUM[8].lower()} letter words, grouped by first and last letter, with Scrabble points.</p></section>
<section class="prose">{secs}</section>"""
    md = f"## Quick answer\n\n{SITE_NAME} publishes complete word lists for 3 to 8 letter words, grouped by first letter and by last letter. Each list shows words most common first with Scrabble scores.\n\n" + \
         "\n\n".join(f"## {n} letter words\n\nStarting with: {az_md(n, 'start')}\n\nEnding in: {az_md(n, 'end')}" for n in LENGTHS)
    page(slug, "Word Lists – 3 to 8 Letter Words by First and Last Letter", "Browse complete lists of 3, 4, 5, 6, 7 and 8 letter words starting with or ending in any letter A to Z, with Scrabble scores.", body, [cld],
         md=("Word Lists by Letter", "Index of every word list by length, first letter and last letter", "word-lists", md))

def simple(slug, h1, desc, md_body, topic="about-site", purpose=None):
    crumb, cld = crumbs([(h1, slug)])
    page(slug, f"{h1} | {SITE_NAME}", desc, f'{crumb}<section class="hero slim"><h1>{h1}</h1></section><section class="prose">{md2html(md_body)}</section>', [cld],
         md=(h1, purpose or desc.rstrip("."), topic, md_body.replace("](/", f"]({SITE_URL}/")))

def privacy_md():
    """Privacy policy body. Every conditional piece is emitted only when the build actually does
    what it describes (GA4_ID, ADS_HEAD, WEBFONTS), so the policy can never claim collection that
    isn't happening or omit one that is. Module level, with no word-list dependency, so the page
    can be re-rendered on its own."""
    ga, ads, fonts = bool(GA4_ID), bool(ADS_HEAD), WEBFONTS
    ga_cookie = "_ga_" + GA4_ID.removeprefix("G-")
    gtm = bool(GTM_ID)
    google_uses = ((["Google Analytics"] if ga else []) + (["Google Tag Manager"] if gtm else [])
                   + (["Google Fonts"] if fonts else []) + (["Google AdSense advertising"] if ads else []))
    L = lambda *parts: "\n".join(p for p in parts if p)   # join lines, dropping disabled ones
    tracked = "Google Analytics and personalised ads" if ads else "Google Analytics"

    summary = L(
        "- No accounts, no sign-up, and nothing you type into the word tools ever leaves your browser.",
        f"- {tracked} run only if you click **Accept** in the cookie banner. Change your mind any time with [Cookie settings]({SITE_URL}/privacy-policy/#cookie-settings)." if ga else
        "- We run no analytics and set no tracking cookies.",
        "- Ads are shown by Google AdSense. Without your consent they are non-personalised." if ads else "",
        "- We do not sell your personal information." if ads else
        "- We do not sell your personal information, use it to profile you or share it for targeted advertising.",
        "- We honor Global Privacy Control and Do Not Track signals." if ga else "",
        "- Fonts load from Google Fonts, which receives your IP address." if fonts else "")

    collect = L(
        "| Data | Where it comes from | Why we use it | Legal basis (GDPR) |",
        "|---|---|---|---|",
        "| IP address, browser type, page requested and time | Server logs kept by our host, Netlify | Deliver the site, keep it secure and stop abuse | Legitimate interests |",
        "| Pages viewed, device and browser type, approximate location (city or country) and referring site | Google Analytics, only after you accept | Learn which pages are useful and fix problems | Consent |" if ga else "",
        "| IP address, device and browser type, page viewed, approximate location, and advertising cookie IDs if you accept | Google AdSense, when a page shows an ad | Show the ads that pay for the site, measure them and prevent fraud | Consent for ad cookies and personalised ads; legitimate interests for non-personalised ads and fraud prevention |" if ads else "",
        "| IP address and browser user-agent | Google Fonts, when a page loads its fonts | Show the site's typefaces | Legitimate interests |" if fonts else "",
        "| Your email address and message | You, when you email us | Reply to you | Legitimate interests |")

    storage = L(
        "| Name | Type | Set by | Purpose | Expires | Consent needed |",
        "|---|---|---|---|---|---|",
        "| _ga | Cookie | Google Analytics | Tells visits from different browsers apart | 2 years | Yes |" if ga else "",
        f"| {ga_cookie} | Cookie | Google Analytics | Keeps track of the current visit | 2 years | Yes |" if ga else "",
        "| __gads, __gpi | Cookie | Google AdSense | Measures ads and limits how often you see the same one | 13 months | Yes |" if ads else "",
        "| IDE, DSID | Cookie on doubleclick.net | Google | Personalises and measures ads across sites | IDE 13 months in the EEA and UK, up to 2 years elsewhere; DSID 2 weeks | Yes |" if ads else "",
        "| wt-consent | Local storage | " + SITE_NAME + " | Remembers your cookie choice | 12 months | No, strictly necessary |" if ga else "",
        "| theme | Local storage | " + SITE_NAME + " | Remembers light or dark mode | Until you clear site data | No, strictly necessary |",
        "| wt-day, wt-stats | Local storage | " + SITE_NAME + " | Saves daily puzzle progress, streak and stats | Until you clear site data | No, strictly necessary |")

    analytics = f"""
## Google Analytics

We use Google Analytics 4 with Google Consent Mode. Until you click **Accept**, no analytics cookies are set and Google receives only cookieless signals without identifiers, which it uses to estimate overall traffic. After you accept, Google Analytics sets the cookies listed above and records the pages you view, your device and browser type, approximate location and the site that referred you. Google Analytics 4 does not log or store IP addresses. We have not enabled Google signals or advertising features, so this data is not used for ads. We keep analytics data for no longer than 14 months.

Google processes this data on our behalf. See [how Google uses information from sites that use its services](https://policies.google.com/technologies/partner-sites).""" if ga else ""
    if gtm:
        analytics += """

## Google Tag Manager

We use Google Tag Manager to manage the measurement tags on this site. Tag Manager itself sets no cookies, but loading it means Google receives your IP address and browser details. Every tag it runs follows your cookie choice: nothing that needs consent fires until you click **Accept**."""

    advertising = """
## Advertising

We show ads from Google AdSense to keep the site free. Google and its partners use cookies and similar technologies to show ads, measure them, limit how often you see the same ad and prevent fraud. **Personalised ads, based on your past visits to this and other websites, are shown only if you click Accept.** Otherwise Google shows non-personalised or limited ads, chosen from the page you are reading and your approximate location. See [how Google uses information from sites that use its services](https://policies.google.com/technologies/partner-sites) and [how Google uses cookies in advertising](https://policies.google.com/technologies/ads).

You can also manage ad personalisation in [My Ad Center](https://myadcenter.google.com) and opt out of many ad networks at [aboutads.info](https://optout.aboutads.info) or [youronlinechoices.eu](https://www.youronlinechoices.eu).""" if ads else """
## Advertising

We show no ads, set no advertising cookies and do not share data for targeted advertising."""

    thirdparty = """
## Fonts

Page text is set in webfonts served by Google Fonts. Your browser requests those font files directly from fonts.googleapis.com and fonts.gstatic.com, which means Google receives your IP address and browser user-agent. We send no referring URL with those requests and Google Fonts sets no cookies.""" if fonts else ""

    providers = L(
        "- **Netlify, Inc.** (United States) hosts the site. [Netlify privacy policy](https://www.netlify.com/privacy/)",
        f"- **Google LLC** (United States) provides {', '.join(google_uses[:-1]) + ' and ' + google_uses[-1] if len(google_uses) > 1 else google_uses[0]}. [Google privacy policy](https://policies.google.com/privacy)" if google_uses else "")

    gpc = """
## Global Privacy Control and Do Not Track

If your browser sends a Global Privacy Control (GPC) or Do Not Track signal, we treat it as a choice to opt out: {tracked} stay off and we don't show the cookie banner. You can still turn them on with [Cookie settings]({SITE_URL}/privacy-policy/#cookie-settings) if you want to.""" if ga else ""
    gpc = gpc.replace("{tracked}", tracked).replace("{SITE_URL}", SITE_URL)

    us_sale = (f"We do not sell personal information for money. Personalised ads from Google may count as sharing for cross-context behavioral advertising, or as targeted advertising, under some state laws. They are shown only if you click **Accept**, and we treat a Global Privacy Control signal as an opt-out. To opt out at any time, choose **Reject** in [Cookie settings]({SITE_URL}/privacy-policy/#cookie-settings)."
               if ads else
               "**We do not sell or share personal information and do not use it for targeted advertising or profiling**, and we have not done so in the past 12 months.")

    keep_ga = (("- Analytics data is kept for up to 14 months, then deleted automatically.\n" if ga else "")
               + ("- Google keeps advertising data under [its own retention policy](https://policies.google.com/technologies/retention).\n" if ads else ""))
    cookie_kind = "Analytics and advertising cookies are" if ads else "Analytics cookies are"
    dropped = "Google Analytics and AdSense cookies set on this site" if ads else "Google Analytics cookies"
    withdraw = "consent for analytics and personalised ads" if ads else "analytics consent"

    # disabled sections leave blank runs behind; collapse them so md2html emits no empty <p>
    return re.sub(r"\n{3,}", "\n\n", f"""
Effective {TODAY}. This policy explains what personal data {SITE_NAME} ("we", "us") collects when you use {SITE_URL}, why we collect it, and the choices and rights you have wherever you live. It is written to meet the EU and UK General Data Protection Regulation (GDPR), the California Consumer Privacy Act as amended by the CPRA, other US state privacy laws, Brazil's LGPD, Canada's PIPEDA and Quebec Law 25, and similar laws in other countries.

## Summary

{summary}

## Who is responsible

{SITE_NAME} is the controller of the personal data described in this policy. Contact us about privacy at **{EMAIL}**.

## What we collect and why

{collect}

We don't collect your searches, unscrambles or puzzle guesses: they are processed entirely in your browser and are never sent to us or anyone else. We don't ask for your name and we don't collect sensitive personal data.

## Cookies and local storage

Strictly necessary storage is used without asking because it only does what you asked for. {cookie_kind + " set only after you click **Accept**." if ga else "We set no cookies."}

{storage}

Local storage stays on your device and we cannot read it. {f"To change your choice, use [Cookie settings]({SITE_URL}/privacy-policy/#cookie-settings). If you withdraw consent, we delete the {dropped} from your browser. " if ga else ""}You can also block or delete cookies and site data in your browser settings.
{analytics}
{advertising}
{thirdparty}

## Who we share data with

We don't sell, rent or trade personal data. We disclose it only to the service providers below, who process it for the purposes in this policy, or when the law requires it.

{providers}

## International transfers

Our service providers are based in the United States, so your data may be processed outside your country. For transfers from the European Economic Area, the UK and Switzerland we rely on the EU-US Data Privacy Framework and its UK and Swiss extensions where the provider is certified, and on the European Commission's Standard Contractual Clauses otherwise.

## How long we keep data

- Server logs are kept by Netlify for a limited period under its own retention policy.
{keep_ga}- Emails are kept until your question is resolved, and no longer than 2 years.
- Local storage stays on your device until you clear it{", and your cookie choice expires after 12 months" if ga else ""}.

## Your rights

Wherever you live, you can ask us what personal data we hold about you and ask us to correct it, delete it or stop using it. {f"You can withdraw {withdraw} at any time with [Cookie settings]({SITE_URL}/privacy-policy/#cookie-settings). Withdrawing doesn't affect processing that already happened. " if ga else ""}Email **{EMAIL}** to make a request. We reply within 30 days, or within 45 days where US state law allows. We may ask a question to confirm the request is yours. Because we collect so little, we often hold no data linked to you, and we will tell you if so. We will never treat you differently for using your rights.

## Europe, the UK and Switzerland

Under the GDPR, the UK GDPR and the Swiss FADP you have the right to access, rectify and erase your data, to restrict or object to its processing, to data portability, and to withdraw consent. Our legal bases are listed in the table above. You may also complain to your data protection authority, such as the [ICO](https://ico.org.uk) in the UK or your national authority listed by the [European Data Protection Board](https://www.edpb.europa.eu/about-edpb/about-edpb/members_en).

## California and other US states

Under the CCPA as amended by the CPRA, and the privacy laws of states including Virginia, Colorado, Connecticut, Utah, Texas and Oregon, you have the right to know, access, correct and delete your personal information, and to opt out of its sale, its sharing for cross-context behavioral advertising, targeted advertising and profiling. {us_sale}

In the past 12 months we collected these categories of personal information: identifiers (IP address{", analytics cookie IDs" if ga else ""}{", advertising cookie IDs" if ads else ""}) and internet activity (server logs{", ad requests" if ads else ""}{", and pages viewed if you accepted analytics" if ga else ""}), from the sources and for the purposes in the table above. We do not collect sensitive personal information. You may use an authorized agent to make a request on your behalf.
{gpc}

## Other countries

People in Brazil (LGPD), Canada (PIPEDA and Quebec Law 25), Australia (Privacy Act 1988), New Zealand (Privacy Act 2020), India (Digital Personal Data Protection Act 2023), Japan (APPI), South Korea (PIPA), Singapore (PDPA), South Africa (POPIA) and many other countries have similar rights to access, correct and delete personal data, withdraw consent and complain to a regulator. Email us to use them. We handle every request the same way, wherever it comes from.

## Children

The site is for a general audience and is not directed at children. We don't knowingly collect personal information from children under 13, or under 16 in the EEA and UK. If you believe a child has sent us personal information, email us and we will delete it.

## Security

The site is served only over HTTPS, uses a strict Content Security Policy and loads scripts only from its own domain{" and Google" if ga or ads or gtm else ""}. No system is perfectly secure, but we collect as little as possible so there is little to protect.

## Changes

We will update this policy when our practices change and change the effective date at the top.

## Contact

Questions or requests about privacy: **{EMAIL}**.""")

def info_pages():
    counts = "\n".join(f"| {n} letters | {len(WORDS[n]):,} | {max(WORDS[n], key=score).upper()} ({score(max(WORDS[n], key=score))}) |" for n in LENGTHS)
    simple("how-our-word-list-works", "How Our Word List Works", f"Where the {SITE_NAME} word list comes from, how it is filtered and scored, and its limits.", f"""
## Quick answer

{SITE_NAME} uses the {DICT_NOTE}. We expand its root words into plurals and other inflected forms, keep lowercase words of 3 to 8 letters, and remove proper nouns, abbreviations and offensive words. The result is {TOTAL:,} words.

## Source dictionary

The list starts from [SCOWL](https://wordlist.aspell.net/), the Spell Checker Oriented Word Lists maintained by Kevin Atkinson, as packaged for Hunspell en_US by Debian (release 2020.12.07, size 70). Size 70 includes common and moderately rare words but leaves out the most obscure entries.

## How we filter it

- Expand each root word with the dictionary's own affix rules, such as plural -s and past tense -ed.
- Keep only words written in lowercase letters a to z, which removes proper nouns, abbreviations and words with apostrophes.
- Keep words from 3 to 8 letters long.
- Remove a short list of slurs and profanity.

## Word counts

| Length | Words | Highest scoring |
|---|---|---|
{counts}

## How scores are calculated

Each word's score is the sum of standard English Scrabble tile values: A, E, I, L, N, O, R, S, T and U are 1; D and G are 2; B, C, M and P are 3; F, H, V, W and Y are 4; K is 5; J and X are 8; Q and Z are 10. Board bonuses are not included.

## How "common first" ordering works

Words are ranked by how often they appear in an English text corpus of about 50 MB of software documentation and manual pages. This ranks everyday words first but leans slightly toward technical vocabulary. Words that never appear in that corpus are listed alphabetically after it.

## Limits

- This is not the official Scrabble dictionary (NWL or Collins) or the Wordle answer list. A word we list may not be accepted by a given game, and some game words are missing.
- Words longer than 8 letters are not included.

Updated {TODAY}. Report a missing or wrong word on the [contact page](/contact/).""", topic="about-site", purpose="Source, filtering, scoring method, counts and limits of the word list")
    simple("about", "About WordTrove", f"About {SITE_NAME}, an independent free word finder and daily word puzzle.", f"""
## What is {SITE_NAME}?

{SITE_NAME} is an independent, free word finder and daily word puzzle for people who play word games. It is not affiliated with The New York Times, Hasbro or Mattel.

## What can I do here?

- Find 3 to 8 letter words with letters you know, using the [5 letter word finder](/) or another length.
- Unscramble letters with the [word unscrambler](/word-unscrambler/).
- Play the [daily word puzzle](/daily-word-puzzle/) and keep a streak.
- Browse [word lists](/word-lists/) by first and last letter.

## Why is it fast?

Every search runs in your browser. There is nothing to install and no account to create, and results appear while you type. Our list covers {TOTAL:,} words; [how our word list works](/how-our-word-list-works/) explains where they come from.

## Contact

Ideas, bugs and missing words: [contact us](/contact/).""", purpose="What WordTrove is, who it is for and what it offers")
    simple("contact", "Contact Us", f"Contact the {SITE_NAME} team with questions, feedback or word suggestions.", f"""
## How do I contact {SITE_NAME}?

Email **{EMAIL}**. We read every message and usually reply within two working days.

## What should I include?

For a missing or wrong word, include the word and the game you were playing. For a bug, include your device and browser.""", purpose="How to reach the WordTrove team")
    simple("privacy-policy", "Privacy Policy", f"How {SITE_NAME} handles your data, cookies, analytics and advertising.", privacy_md(),
           topic="legal", purpose="What data WordTrove collects and how it is used")
    simple("terms", "Terms of Use", f"Terms for using {SITE_NAME}.", f"""
By using {SITE_NAME} you agree to these terms.

## Use of the site

The site is free for personal use. Don't scrape it at volume, attempt to disrupt it, or reuse its content commercially without permission.

## No warranty

Word lists are provided as is. Game dictionaries differ, so a word listed here may not be accepted by every game.

## Trademarks

Wordle is a trademark of The New York Times Company. Scrabble is a trademark of Hasbro in the US and Canada and Mattel elsewhere. {SITE_NAME} is not affiliated with them.

## Contact

Questions about these terms: {EMAIL}.""", topic="legal", purpose="Terms for using WordTrove")
    page("404", f"Page not found | {SITE_NAME}", "This page doesn't exist.", f"""<section class="hero">{tiles('OOPS', ['','near','','hit'])}<h1>Page not found</h1>
<p class="lede">That page doesn't exist. Try the <a href="{u()}">5 letter word finder</a>, today's <a href="{u('daily-word-puzzle')}">daily puzzle</a> or the <a href="{u('word-lists')}">word lists</a>.</p></section>""", h_index=False)

# ---------- Markdown discovery layer (suite tool) ----------
def run_suite(*args):
    r = subprocess.run([sys.executable, os.path.join(SUITE, "scripts", "manage_markdown_site.py"), *args], capture_output=True, text=True)
    if r.returncode: sys.exit(f"suite tool failed: {r.stderr or r.stdout}")
    return r.stdout.strip()

def markdown_layer():
    shutil.rmtree(PRIV, ignore_errors=True)
    for f in (os.path.join(ROOT, "out", "public-md-manifest.json"),):
        if os.path.exists(f): os.remove(f)
    src = os.path.join(PRIV, "md-source"); os.makedirs(src)
    pages = []
    for p in MDPAGES:
        open(os.path.join(src, p["id"] + ".md"), "w", encoding="utf-8").write(p["body"].strip() + "\n")
        pages.append({"id": p["id"], "url": p["url"], "disposition": "publish", "reviewed_public": True, "title": p["title"],
                      "purpose": p["purpose"], "locale": "en", "topic": p["topic"], "updated_at": TODAY, "source_revision": REV,
                      "body_ref": f"md-source/{p['id']}.md", "md_path": f"llm/pages/{p['id']}.md"})
    pages.append({"id": "not-found", "url": SITE_URL + "/404/", "disposition": "exclude", "reason": "Error page with noindex; no substantive content."})
    inv = {"schema_version": "1.0.0", "site_name": SITE_NAME,
           "summary": f"{SITE_NAME} is a free word finder, word unscrambler, daily 5 letter word puzzle and set of 3 to 8 letter word lists with Scrabble scores.",
           "origin": SITE_URL, "inventory_scope": "complete",
           "inventory_evidence": f"Generated by build.py from the same source revision as every HTML page ({len(MDPAGES)} indexable pages plus one excluded 404).",
           "owner": OWNER, "refresh_trigger": "Regenerate on every build; build.py writes HTML and Markdown from one source revision.",
           "index_policy": "canonical-to-html", "pages": pages}
    json.dump(inv, open(os.path.join(PRIV, "inventory.json"), "w"), indent=1)
    pub = os.path.join(ROOT, "out", "public-md")
    shutil.rmtree(pub, ignore_errors=True)
    print(run_suite("build", "--inventory", os.path.join(PRIV, "inventory.json"), "--output", pub))
    man = pub + "-manifest.json"
    print(run_suite("validate", "--manifest", man, "--root", pub))
    hints = os.path.join(PRIV, "native-discovery.md")
    run_suite("hints", "--manifest", man, "--root", pub, "--output", hints)
    blocks = re.findall(r"```(?:text|xml)\n(.*?)```", open(hints).read(), re.S)
    shutil.copytree(pub, OUT, dirs_exist_ok=True)
    return blocks[0], blocks[1]

# ---------- build ----------
def main():
    shutil.rmtree(OUT, ignore_errors=True)
    os.makedirs(os.path.join(OUT, "data"))
    for n in LENGTHS:
        open(os.path.join(OUT, "data", f"{n}.txt"), "w").write(" ".join(WORDS[n]))
    open(os.path.join(OUT, "data", "daily.txt"), "w").write(" ".join(ANSWERS))
    for f in ("style.css", "app.js", "favicon.ico", "favicon-16x16.png", "favicon-32x32.png", "apple-touch-icon.png",
              "icon-192.png", "icon-512.png", "logo.png", "logo-mark.png", "site.webmanifest",
              "google2daa8c1ff52bce85.html"):   # Search Console ownership file, must stay at the site root
        shutil.copy(os.path.join(ROOT, "src", f), OUT)
    for n in LENGTHS:
        finder_page(n)
        for c in ABC:
            if has_start(n, c): list_page(n, c, "start")
            if has_end(n, c): list_page(n, c, "end")
    unscramble_page(); daily_page(); lists_page(); info_pages()
    if not PREVIEW:
        # SUITE must be an explicit absolute path: an empty or relative SEO_SUITE would let
        # build.py execute a scripts/manage_markdown_site.py picked up from the current directory.
        if SUITE and os.path.isabs(SUITE) and os.path.exists(os.path.join(SUITE, "scripts", "manage_markdown_site.py")):
            robots_hint, xml_hint = markdown_layer()
        else:   # suite not installed: keep the previously generated llms.txt/llm/ files from the zip, skip regeneration
            print("SEO suite not found (set SEO_SUITE); Markdown layer not regenerated")
            robots_hint, xml_hint = "", ""
        open(os.path.join(OUT, "sitemap.xml"), "w").write('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' +
            xml_hint + "".join(f"<url><loc>{x}</loc><lastmod>{TODAY}</lastmod></url>\n" for x in SITEMAP) + "</urlset>\n")
        open(os.path.join(OUT, "robots.txt"), "w").write(f"User-agent: *\nAllow: /\nSitemap: {SITE_URL}/sitemap.xml\n" + robots_hint)
        open(os.path.join(OUT, "ads.txt"), "w").write("# Paste the lines your ad network gives you here (required for AdSense, Ezoic, Publift).\n" +
            (f"google.com, {ADSENSE_ID.removeprefix('ca-')}, DIRECT, f08c47fec0942fa0\n" if ADSENSE_ID else ""))
        hdr = open(os.path.join(ROOT, "src", "_headers"), encoding="utf-8").read()
        hdr += f"""
/*
  Content-Security-Policy: {csp()}
  X-Content-Type-Options: nosniff
  Referrer-Policy: strict-origin-when-cross-origin
  Permissions-Policy: geolocation=(), camera=(), microphone=(), payment=(), usb=(), interest-cohort=()
  Cross-Origin-Opener-Policy: same-origin
  Cross-Origin-Resource-Policy: same-origin
  X-Frame-Options: DENY
  Strict-Transport-Security: max-age=63072000; includeSubDomains; preload
"""
        hdr += "\n/llms.txt\n  Content-Type: text/plain; charset=utf-8\n/*.md\n  Content-Type: text/markdown; charset=utf-8\n"
        hdr += "".join(f"/llm/pages/{p['id']}.md\n  Link: <{p['url']}>; rel=\"canonical\"\n" for p in MDPAGES)
        open(os.path.join(OUT, "_headers"), "w").write(hdr)
    print(f"{OUT}: {len(SITEMAP)} indexed pages, {len(MDPAGES)} Markdown mirrors, daily answers {len(ANSWERS)}, words:", {n: len(WORDS[n]) for n in LENGTHS})

if __name__ == "__main__":
    main()
