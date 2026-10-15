import os
import re
from urllib.parse import urljoin, urlparse
import requests
from requests.auth import HTTPDigestAuth
from bs4 import BeautifulSoup

BASE_URL = "http://10.70.1.225/"
AUTH = HTTPDigestAuth("comtech", "comtech")

visited = set()
to_visit = set(["", "index.html", "vfpHeights.htm", "home.htm"])
discovered_pages = {}
all_assets = set()

session = requests.Session()
session.auth = AUTH

print(f"[*] Starting crawl on {BASE_URL} ...")

while to_visit:
    current = to_visit.pop()
    if current in visited:
        continue
    visited.add(current)

    url = urljoin(BASE_URL, current)
    try:
        res = session.get(url, timeout=5)
        status = res.status_code
        content_type = res.headers.get("Content-Type", "")
        print(f"[{status}] {current} -> {len(res.content)} bytes ({content_type})")

        if status == 200 and ("html" in content_type or "text" in content_type or current.endswith((".htm", ".html"))):
            discovered_pages[current] = {
                "url": url,
                "status": status,
                "title": "",
                "links": []
            }
            soup = BeautifulSoup(res.text, "html.parser")
            if soup.title and soup.title.string:
                discovered_pages[current]["title"] = soup.title.string.strip()

            # Find HTML tags with links/sources
            for tag, attr in [("a", "href"), ("frame", "src"), ("iframe", "src"), ("link", "href"), ("script", "src"), ("img", "src"), ("form", "action")]:
                for el in soup.find_all(tag):
                    val = el.get(attr)
                    if not val or val.startswith(("#", "javascript:", "mailto:")):
                        continue
                    full = urljoin(url, val)
                    parsed = urlparse(full)
                    if parsed.netloc == "10.70.1.225":
                        rel = parsed.path.lstrip("/")
                        if parsed.query:
                            rel += f"?{parsed.query}"
                        
                        if any(rel.endswith(ext) for ext in [".css", ".js", ".png", ".jpg", ".gif", ".ico", ".svg"]):
                            all_assets.add(rel)
                        else:
                            discovered_pages[current]["links"].append(rel)
                            if rel not in visited:
                                to_visit.add(rel)

            # Find patterns in JavaScript (e.g. location.href = "...", window.open("..."), .location="...")
            js_matches = re.findall(r'["\']([a-zA-Z0-9_\-\/]+\.(?:htm|html|cgi|php|asp)(?:\?[^"\']*)?)["\']', res.text)
            for jm in js_matches:
                full = urljoin(url, jm)
                parsed = urlparse(full)
                if parsed.netloc == "10.70.1.225":
                    rel = parsed.path.lstrip("/")
                    if parsed.query:
                        rel += f"?{parsed.query}"
                    discovered_pages[current]["links"].append(rel)
                    if rel not in visited:
                        to_visit.add(rel)

    except Exception as e:
        print(f"[!] Error fetching {url}: {e}")

print("\n" + "="*50)
print(f"CRAWL COMPLETED: {len(discovered_pages)} pages discovered, {len(all_assets)} assets discovered.")
print("="*50)

for path, info in sorted(discovered_pages.items()):
    title = f" - '{info['title']}'" if info['title'] else ""
    print(f"- /{path}{title}")
    if info["links"]:
        for l in sorted(set(info["links"])):
            print(f"    --> {l}")
