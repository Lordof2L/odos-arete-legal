#!/usr/bin/env python3
"""Stdlib check for the public Odos Areté legal site. Run: python3 check.py

Fails (exit 1) when a page is missing in a language, a footer version or date
(machine-readable or visible) differs from VERSIONS, the page source holds a
placeholder, the operator line or contact is missing, a banned name, a mention of
terms Part B, bank or tax data appears, a file that is not part of the site sits in
the tree, or a crawl of the site served by `python -m http.server`, following
every href on every page from the root (absolute links to the published site
included; other sites, mailto: and tel: are not fetched), meets a status other
than 200, a missing #anchor or an HTML page outside VERSIONS, or never reaches a
page in VERSIONS.
"""
import functools
import hashlib
import html
import http.server
import re
import sys
import threading
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin

ROOT = Path(__file__).resolve().parent
LANGS = {"en": "", "sk": "sk/", "de": "de/"}
# Version id and date per page, the same in all three languages. When the published
# text of a page changes, give it a new id and date here and in its three footers.
VERSIONS = {
    "index": ("index-1", "2026-09-24"),
    "terms": ("terms-1-a", "2026-09-24"),
    "privacy": ("privacy-1", "2026-09-24"),
    "ai": ("ai-1", "2026-09-24"),
    "delete-account": ("delete-account-1", "2026-09-24"),
    "support": ("support-1", "2026-09-24"),
}
OPERATOR = {"en": "Lukáš Litvák, an individual", "sk": "Lukáš Litvák, fyzická osoba", "de": "Lukáš Litvák, Einzelperson"}
SITE = re.compile(r"^https?://lordof2l\.github\.io/odos-arete-legal/")
EXTERNAL = re.compile(r"^(https?:|mailto:|tel:)")
CONTACT = ["Manzigenstrasse 1", "6067 Melchtal", "+41 76 672 95 90", "lukasllitvak@gmail.com"]
# SHA-256 of the banned name's first four letters, lower case, in both spellings, so that
# this public file does not hold the name. A word starting with them fails; a word that
# merely contains them passes.
BANNED = {
    "d569bfdc5432ae8cf5dfa5903b0c0cd97c678ed6040f08091f0f462d751aa647",
    "f45996824c88cebd82247cdb3751ff3b717dbdba50c6e8153d3e1aa641495a4f",
}
# Terms Part B (money commitments) is not published while stakes do not exist (F168).
PART_B = re.compile(r"\bPart B\b|\bčasť B\b|\bTeil B\b", re.I)
# GitHub Pages publishes every committed file, so nothing else may sit in the tree.
OTHER_FILES = {".nojekyll", "README.md", "check.py", "style.css"}
MONTHS = {
    "en": "January February March April May June July August September October November December".split(),
    "sk": "januára februára marca apríla mája júna júla augusta septembra októbra novembra decembra".split(),
    "de": "Januar Februar März April Mai Juni Juli August September Oktober November Dezember".split(),
}
DATE_TEXT = {"en": "{d} {m} {y}", "sk": "{d}. {m} {y}", "de": "{d}. {m} {y}"}
PLACEHOLDER = re.compile(r"[\[\]]|\{\{|\}\}|\bTODO\b|\bTBD\b|\bXXX\b|lorem ipsum|placeholder", re.I)
BANK_OR_TAX = re.compile(
    r"\b[A-Z]{2}\d{2}(?:\s?[A-Z0-9]{4}){3,7}\b"  # IBAN
    r"|\bCHE-?\d{3}\.?\d{3}\.?\d{3}\b"  # Swiss UID / VAT number
    r"|\b(?:IBAN|BIC|SWIFT)\b"
)


class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.lang = None
        self.text = []
        self.links = []
        self.ids = set()
        self.versions = []
        self.dates = []
        self.date_texts = []
        self._footer = 0
        self._time = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "html":
            self.lang = a.get("lang")
        if "id" in a:
            self.ids.add(a["id"])
        if tag == "footer":
            self._footer += 1
            if "data-version" in a:
                self.versions.append(a["data-version"])
        if tag == "time" and self._footer:
            self.dates.append(a.get("datetime"))
            self.date_texts.append("")
            self._time = True
        if a.get("href"):
            self.links.append(a["href"])

    def handle_endtag(self, tag):
        if tag == "footer":
            self._footer -= 1
        if tag == "time":
            self._time = False

    def handle_data(self, data):
        self.text.append(data)
        if self._time:
            self.date_texts[-1] += data


def page_url(prefix, page):
    return prefix if page == "index" else f"{prefix}{page}/"


def visible_date(lang, iso):
    y, m, d = (int(x) for x in iso.split("-"))
    return DATE_TEXT[lang].format(d=d, m=MONTHS[lang][m - 1], y=y)


def check_files(errors):
    for page, (version, date) in VERSIONS.items():
        for lang, prefix in LANGS.items():
            rel = page_url(prefix, page) + "index.html"
            path = ROOT / rel
            if not path.exists():
                errors.append(f"{rel}: missing ({lang} version of {page})")
                continue
            raw = path.read_text(encoding="utf-8")
            p = Page()
            p.feed(raw)
            text = " ".join(" ".join(p.text).split())
            if p.lang != lang:
                errors.append(f"{rel}: html lang={p.lang!r}, expected {lang!r}")
            if p.versions != [version]:
                errors.append(f"{rel}: footer version {p.versions}, VERSIONS says {version!r}")
            if p.dates != [date]:
                errors.append(f"{rel}: footer date {p.dates}, VERSIONS says {date!r}")
            if p.date_texts != [visible_date(lang, date)]:
                errors.append(f"{rel}: visible footer date {p.date_texts}, expected {visible_date(lang, date)!r}")
            if version not in text:
                errors.append(f"{rel}: version id {version!r} is not visible in the page text")
            # The whole source, entities decoded: attributes such as mailto:[SUPPORT_EMAIL] count too.
            source = html.unescape(raw)
            for m in PLACEHOLDER.finditer(source):
                errors.append(f"{rel}: placeholder-like text {m.group(0)!r} near {source[max(0, m.start() - 40):m.end() + 40]!r}")
            for needle in CONTACT + [OPERATOR[lang]]:
                if needle not in text:
                    errors.append(f"{rel}: operator line or contact {needle!r} missing")


def check_repo_text(errors):
    for path in sorted(ROOT.rglob("*")):
        if ".git" in path.parts or not path.is_file() or path.name == "check.py":
            continue
        if path.suffix not in (".html", ".css", ".json", ".md"):
            continue
        raw = path.read_text(encoding="utf-8")
        rel = path.relative_to(ROOT)
        for word in re.findall(r"\w+", html.unescape(raw)):
            if hashlib.sha256(word[:4].lower().encode()).hexdigest() in BANNED:
                errors.append(f"{rel}: banned name {word!r}")
        for m in PART_B.finditer(raw):
            errors.append(f"{rel}: mentions {m.group(0)!r}")
        for m in BANK_OR_TAX.finditer(raw):
            errors.append(f"{rel}: bank or tax data {m.group(0)!r}")


def check_tree(errors):
    pages = {page_url(prefix, page) + "index.html" for page in VERSIONS for prefix in LANGS.values()}
    files = {p.relative_to(ROOT).as_posix() for p in ROOT.rglob("*") if p.is_file() and ".git" not in p.parts}
    for rel in sorted(files - pages - OTHER_FILES):
        errors.append(f"{rel}: not an expected file of the site (GitHub Pages would publish it)")


def crawl(errors):
    """Serve ROOT as `python -m http.server` does and follow every href from the root."""
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT))
    http.server.SimpleHTTPRequestHandler.log_message = lambda *args: None
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}/"
    queue, seen, ids, pages, anchors = [base], set(), {}, set(), []
    try:
        while queue:
            url = queue.pop()
            if url in seen:
                continue
            seen.add(url)
            try:
                with urllib.request.urlopen(url, timeout=5) as r:
                    status, final, kind, body = r.status, r.url, r.headers.get_content_type(), r.read()
            except Exception as exc:  # every failure is reported, none is swallowed
                errors.append(f"GET /{url[len(base):]}: {exc}")
                continue
            if status != 200:
                errors.append(f"GET /{url[len(base):]}: status {status}, expected 200")
                continue
            if kind != "text/html":  # style.css
                continue
            p = Page()
            p.feed(body.decode("utf-8"))
            ids[url] = ids[final] = p.ids
            pages.add(final[len(base):])
            for href in p.links:
                # Absolute links to the published site are checked here like relative ones.
                target, _, anchor = urljoin(final, SITE.sub(base, href)).partition("#")
                if not target.startswith(base):
                    if not EXTERNAL.match(href):  # other sites, mailto: and tel: are not fetched
                        errors.append(f"/{final[len(base):]}: link {href!r} leaves the site")
                    continue
                queue.append(target)
                if anchor:
                    anchors.append((final[len(base):], href, target, anchor))
    finally:
        server.shutdown()
        server.server_close()
    for page, href, target, anchor in anchors:
        if target in ids and anchor not in ids[target]:
            errors.append(f"/{page}: link {href!r} points to a missing anchor")
    # A directory without index.html answers 200 with a listing; it shows up here as a page outside VERSIONS.
    expected = {page_url(prefix, page) for page in VERSIONS for prefix in LANGS.values()}
    for url in sorted(pages - expected):
        errors.append(f"GET /{url}: an HTML page that is not in VERSIONS")
    for url in sorted(expected - pages):
        errors.append(f"/{url}: no link from the root reaches this page")
    return len(seen)


def main():
    errors = []
    check_files(errors)
    check_repo_text(errors)
    check_tree(errors)
    crawled = crawl(errors)
    for e in errors:
        print("FAIL", e)
    print(f"{len(VERSIONS)} pages x {len(LANGS)} languages, {crawled} URLs crawled, {len(errors)} failures")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
