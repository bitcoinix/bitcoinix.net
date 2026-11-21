"""Checks the built site: references, Content Security Policy, JSON-LD, XML
and security.txt.

Usage: check-site.py SITE_DIR

The page is served with the Content Security Policy from its <meta> tag. A
resource that the policy doesn't allow fails silently in the browser, so this
checks every resource the page loads against the policy.
"""

import json
import posixpath
import re
import sys
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit

# Files that are published without being referenced from the page
ROOT_FILES = {"index.html", "robots.txt", "sitemap.xml", ".well-known/security.txt"}

# The CSP directive that governs each kind of load, and its fallbacks
# (CSP Level 3, "effective directive")
FALLBACKS = {
    "script-src-elem": ["script-src", "default-src"],
    "script-src-attr": ["script-src", "default-src"],
    "style-src-elem": ["style-src", "default-src"],
    "style-src-attr": ["style-src", "default-src"],
    "img-src": ["default-src"],
    "font-src": ["default-src"],
    "media-src": ["default-src"],
    "connect-src": ["default-src"],
    "manifest-src": ["default-src"],
    "object-src": ["default-src"],
    "frame-src": ["child-src", "default-src"],
}

# <link rel> values that make the browser fetch the link, and the directive
LINK_RELS = {
    "stylesheet": "style-src-elem",
    "icon": "img-src",
    "apple-touch-icon": "img-src",
    "manifest": "manifest-src",
}

# Elements whose `src` the browser fetches, and the directive
SRC_ELEMENTS = {
    "img": "img-src",
    "audio": "media-src",
    "video": "media-src",
    "track": "media-src",
    "iframe": "frame-src",
    "embed": "object-src",
}

URL_ATTRIBUTES = {"href", "src", "action", "poster", "cite", "data"}

FONT_EXTENSIONS = {".woff", ".woff2", ".ttf", ".otf", ".eot"}

errors = []


def error(message):
    errors.append(message)


class Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.elements = []  # (tag, attrs) in document order
        self.ids = set()
        self.in_script = None
        self.inline_scripts = []  # (type, text)
        self.inline_styles = []

    def handle_starttag(self, tag, attrs):
        attrs = {name: (value or "") for name, value in attrs}
        self.elements.append((tag, attrs))
        if "id" in attrs:
            self.ids.add(attrs["id"])
        if tag == "script" and "src" not in attrs:
            self.in_script = attrs.get("type", "")
            self.inline_scripts.append([self.in_script, ""])
        if tag == "style":
            self.inline_styles.append("")

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        if tag == "script":
            self.in_script = None

    def handle_data(self, data):
        if self.in_script is not None:
            self.inline_scripts[-1][1] += data


class Site:
    def __init__(self, root):
        self.root = root
        self.page = Page()
        self.page.feed((root / "index.html").read_text())
        self.page.close()
        self.referenced = set()

        canonical = [
            a.get("href", "")
            for t, a in self.page.elements
            if t == "link" and a.get("rel") == "canonical"
        ]
        if len(canonical) != 1:
            sys.exit("index.html: expected exactly one <link rel=canonical>")
        parts = urlsplit(canonical[0])
        if parts.scheme != "https" or parts.path != "/":
            sys.exit(f"index.html: canonical URL {canonical[0]} is not https://<host>/")
        self.origin = f"https://{parts.netloc}"
        self.base = self.origin + "/"

    def local_path(self, url, base=None):
        """The site path of a URL on this site, or None for other origins."""
        url = urljoin(base or self.base, url)
        parts = urlsplit(url)
        if f"{parts.scheme}://{parts.netloc}" != self.origin:
            return None
        path = posixpath.normpath(parts.path)
        if path in ("/", "/."):
            return "index.html"
        return path.lstrip("/") + ("/index.html" if parts.path.endswith("/") else "")

    def check_reference(self, where, url, base=None, fragment=True):
        """Checks that a URL on this site points to a published file."""
        if url.startswith("http://"):
            error(f"{where}: insecure URL {url}")
            return None
        path = self.local_path(url, base)
        if path is None:
            return None
        self.referenced.add(path)
        if not (self.root / path).is_file():
            error(f"{where}: {url} is not a published file ({path})")
            return path
        frag = urlsplit(url).fragment
        if fragment and frag and path == "index.html" and frag not in self.page.ids:
            error(f"{where}: {url} links to a missing id #{frag}")
        return path


def parse_csp(elements):
    policies = [
        a.get("content", "")
        for t, a in elements
        if t == "meta" and a.get("http-equiv", "").lower() == "content-security-policy"
    ]
    if len(policies) != 1:
        error(f"index.html: expected one Content-Security-Policy <meta>, found {len(policies)}")
        return None

    # The policy covers only resources after it
    for tag, attrs in elements:
        if tag == "meta" and attrs.get("http-equiv", "").lower() == "content-security-policy":
            break
        if tag in ("link", "script", "style", "img", "body"):
            error(f"index.html: <{tag}> before the Content-Security-Policy <meta> is not covered by it")
            break

    directives = {}
    for directive in policies[0].split(";"):
        tokens = directive.split()
        if tokens:
            directives.setdefault(tokens[0].lower(), tokens[1:])
    for name in ("frame-ancestors", "report-uri", "sandbox"):
        if name in directives:
            error(f"index.html: CSP directive {name} has no effect in a <meta> tag")
    return directives


class Policy:
    def __init__(self, directives, origin):
        self.directives = directives
        self.origin = origin

    def sources(self, directive):
        for name in [directive] + FALLBACKS.get(directive, []):
            if name in self.directives:
                return name, self.directives[name]
        return None, None  # No directive: allowed

    def allows_url(self, directive, url):
        name, sources = self.sources(directive)
        if sources is None:
            return True
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        for source in sources:
            s = source.lower()
            if s == "'self'" and origin == self.origin:
                return True
            if s == "*" and parts.scheme in ("http", "https"):
                return True
            if s.endswith(":") and "/" not in s and parts.scheme == s[:-1]:
                return True
            if re.fullmatch(r"[a-z][a-z0-9+.-]*://[^/]+/?", s) and origin == s.rstrip("/"):
                return True
        return False

    def allows_inline(self, directive):
        _, sources = self.sources(directive)
        return sources is None or "'unsafe-inline'" in (s.lower() for s in sources)


def check_page(site):
    elements = site.page.elements
    directives = parse_csp(elements)
    policy = Policy(directives or {}, site.origin)

    def load(where, directive, url):
        if site.check_reference(where, url) is None and url.startswith("http://"):
            return
        absolute = urljoin(site.base, url)
        if directives is not None and not policy.allows_url(directive, absolute):
            error(f"{where}: {url} is blocked by the CSP ({policy.sources(directive)[0]})")

    for tag, attrs in elements:
        where = f"index.html <{tag}>"

        for name, value in attrs.items():
            if name.startswith("on"):
                if not policy.allows_inline("script-src-attr"):
                    error(f"{where}: event handler attribute {name} is blocked by the CSP")
            if name == "style" and not policy.allows_inline("style-src-attr"):
                error(f"{where}: style attribute is blocked by the CSP")
            if name in URL_ATTRIBUTES and value.strip().lower().startswith("javascript:"):
                error(f"{where}: javascript: URL in {name}")

        if tag == "script" and "src" in attrs:
            load(where, "script-src-elem", attrs["src"])
        elif tag == "link":
            rels = attrs.get("rel", "").lower().split()
            fetched = [LINK_RELS[r] for r in rels if r in LINK_RELS]
            for directive in fetched:
                load(where, directive, attrs.get("href", ""))
            if not fetched:
                site.check_reference(where, attrs.get("href", ""))
        elif tag in SRC_ELEMENTS and "src" in attrs:
            load(where, SRC_ELEMENTS[tag], attrs["src"])
        elif tag == "object" and "data" in attrs:
            load(where, "object-src", attrs["data"])
        elif tag == "meta":
            content = attrs.get("content", "")
            if re.match(r"https?://|/", content):
                site.check_reference(where, content, fragment=False)
        else:
            for name in ("href", "src", "poster"):
                if name in attrs:
                    site.check_reference(where, attrs[name])
        if tag in ("img", "source") and "srcset" in attrs:
            for candidate in attrs["srcset"].split(","):
                if candidate.strip():
                    load(where, "img-src", candidate.split()[0])

    if site.page.inline_styles and not policy.allows_inline("style-src-elem"):
        error("index.html: inline <style> is blocked by the CSP")

    for script_type, text in site.page.inline_scripts:
        if script_type.lower() == "application/ld+json":
            # A data block, not run as script and not subject to the CSP
            try:
                data = json.loads(text)
            except json.JSONDecodeError as e:
                error(f"index.html: JSON-LD is not valid JSON: {e}")
                continue
            for url in json_strings(data):
                if re.match(r"https?://", url):
                    site.check_reference("index.html JSON-LD", url, fragment=False)
        elif not policy.allows_inline("script-src-elem"):
            error("index.html: inline <script> is blocked by the CSP")

    return policy


def json_strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from json_strings(item)
    elif isinstance(value, dict):
        for item in value.values():
            yield from json_strings(item)


def check_css(site, policy):
    for css in sorted(site.root.rglob("*.css")):
        rel = css.relative_to(site.root).as_posix()
        text = re.sub(r"/\*.*?\*/", "", css.read_text(), flags=re.S)
        if "@import" in text:
            error(f"{rel}: @import is not allowed, link the stylesheet from the page")
        base = urljoin(site.base, rel)
        for match in re.finditer(r"url\(\s*(['\"]?)(.*?)\1\s*\)", text):
            url = match.group(2)
            if url.startswith("data:"):
                directive = "img-src"
                absolute = url
            else:
                site.check_reference(rel, url, base=base, fragment=False)
                absolute = urljoin(base, url)
                ext = posixpath.splitext(urlsplit(absolute).path)[1].lower()
                directive = "font-src" if ext in FONT_EXTENSIONS else "img-src"
            if not policy.allows_url(directive, absolute):
                error(f"{rel}: {url} is blocked by the CSP ({policy.sources(directive)[0]})")


def check_scripts(site, policy):
    for js in sorted(site.root.rglob("*.js")):
        rel = js.relative_to(site.root).as_posix()
        text = js.read_text()
        for match in re.finditer(r"\bfetch\(\s*(?:(['\"])(.*?)\1)?", text):
            url = match.group(2)
            if url is None:
                error(f"{rel}: fetch() without a string literal URL; the CSP check needs a literal")
                continue
            absolute = urljoin(urljoin(site.base, rel), url)
            if not policy.allows_url("connect-src", absolute):
                error(f"{rel}: fetch({url}) is blocked by the CSP ({policy.sources('connect-src')[0]})")
        if re.search(r"\b(XMLHttpRequest|WebSocket|EventSource|sendBeacon)\b", text):
            error(f"{rel}: only fetch() with a literal URL is supported by the CSP check")


def check_xml(site):
    path = site.root / "sitemap.xml"
    try:
        tree = ET.parse(path)
    except ET.ParseError as e:
        error(f"sitemap.xml: not well-formed XML: {e}")
        return
    ns = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
    if tree.getroot().tag != f"{ns}urlset":
        error("sitemap.xml: root element is not a sitemaps.org <urlset>")
    locs = [loc.text or "" for loc in tree.iter(f"{ns}loc")]
    if not locs:
        error("sitemap.xml: no <loc>")
    for loc in locs:
        if site.check_reference("sitemap.xml", loc.strip()) is None:
            error(f"sitemap.xml: {loc} is not on {site.origin}")


def check_robots(site):
    sitemaps = []
    for line in (site.root / "robots.txt").read_text().splitlines():
        key, _, value = line.partition(":")
        if key.strip().lower() == "sitemap":
            sitemaps.append(value.strip())
    if not sitemaps:
        error("robots.txt: no Sitemap")
    for url in sitemaps:
        site.check_reference("robots.txt", url)


def check_security_txt(site):
    # RFC 9116
    rel = ".well-known/security.txt"
    fields = {}
    for number, line in enumerate((site.root / rel).read_text().splitlines(), 1):
        if not line.strip() or line.startswith("#"):
            continue
        name, sep, value = line.partition(":")
        if not sep or not re.fullmatch(r"[A-Za-z0-9-]+", name):
            error(f"{rel}:{number}: not a `Field: value` line")
            continue
        fields.setdefault(name.lower(), []).append(value.strip())

    if not fields.get("contact"):
        error(f"{rel}: Contact is required")
    if len(fields.get("expires", [])) != 1:
        error(f"{rel}: exactly one Expires is required")
    elif not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})", fields["expires"][0]
    ):
        error(f"{rel}: Expires is not an RFC 3339 date-time")
    for name in ("preferred-languages",):
        if len(fields.get(name, [])) > 1:
            error(f"{rel}: {name} must appear at most once")
    for name in ("contact", "policy", "acknowledgments", "canonical", "encryption", "hiring"):
        for url in fields.get(name, []):
            if not re.match(r"(https://|mailto:|tel:)", url):
                error(f"{rel}: {name} {url} is not https, mailto or tel")
    canonical = urljoin(site.base, rel)
    if canonical not in fields.get("canonical", []):
        error(f"{rel}: Canonical must include {canonical}")
    site.referenced.add(rel)


def check_unreferenced(site):
    published = {
        p.relative_to(site.root).as_posix() for p in site.root.rglob("*") if p.is_file()
    }
    for path in sorted(published - site.referenced - ROOT_FILES):
        error(f"{path}: published but not referenced; reference it or remove it from the site")


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    site = Site(Path(sys.argv[1]))
    policy = check_page(site)
    check_css(site, policy)
    check_scripts(site, policy)
    check_xml(site)
    check_robots(site)
    check_security_txt(site)
    check_unreferenced(site)

    for message in errors:
        print(f"error: {message}", file=sys.stderr)
    if errors:
        sys.exit(1)
    print("Site checks passed")


if __name__ == "__main__":
    main()
