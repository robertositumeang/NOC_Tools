import requests
from requests.auth import HTTPDigestAuth
from bs4 import BeautifulSoup
import re
import json

auth = HTTPDigestAuth("comtech", "comtech")
base = "http://10.70.1.225/"

categories = {
    "Home": ["home.htm", "main.htm"],
    "Admin": ["admin_access.htm"],
    "Configuration": ["femgt.htm"],
    "Status": ["ether_stats.htm"],
    "Utility": ["save.htm"],
    "Contact": ["contact.htm"]
}

discovered = {}
to_check = set(["home.htm", "main.htm", "admin_access.htm", "femgt.htm", "ether_stats.htm", "save.htm", "contact.htm", "errstr.htm"])
checked = set()

while to_check:
    page = to_check.pop()
    if page in checked:
        continue
    checked.add(page)
    
    url = base + page
    try:
        r = requests.get(url, auth=auth, timeout=8)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, "html.parser")
            title = soup.title.string.strip() if soup.title and soup.title.string else ""
            
            # find all sublinks and frames
            links = []
            for a in soup.find_all(["a", "frame", "iframe"]):
                h = a.get("href") or a.get("src")
                if h and not h.startswith(("#", "javascript:")):
                    links.append(h)
                    if h.endswith((".htm", ".html")) and h not in checked:
                        to_check.add(h)
                        
            # find js references
            js_refs = set(re.findall(r'([a-zA-Z0-9_\-]+\.htm[l]?)', r.text))
            for j in js_refs:
                if j not in checked:
                    to_check.add(j)
                    
            discovered[page] = {
                "title": title,
                "status": r.status_code,
                "links": list(set(links)),
                "js_refs": list(js_refs)
            }
            print(f"[OK] {page}: '{title}' | links: {len(links)} | js: {len(js_refs)}", flush=True)
        else:
            print(f"[{r.status_code}] {page}", flush=True)
    except Exception as e:
        print(f"[ERR] {page}: {e}", flush=True)

with open("mapped_structure.json", "w") as f:
    json.dump(discovered, f, indent=2)

print(f"\nTotal pages mapped: {len(discovered)}", flush=True)
