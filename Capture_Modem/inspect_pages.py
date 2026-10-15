import requests
from requests.auth import HTTPDigestAuth
from bs4 import BeautifulSoup
import re

auth = HTTPDigestAuth("comtech", "comtech")

for page in ["vfpHeights.htm", "home.htm"]:
    url = f"http://10.70.1.225/{page}"
    try:
        r = requests.get(url, auth=auth, timeout=10)
        print(f"=== {page} (Length: {len(r.text)}) ===", flush=True)
        soup = BeautifulSoup(r.text, "html.parser")
        
        # print text and links
        links = []
        for a in soup.find_all(["a", "button", "input", "frame", "iframe"]):
            href = a.get("href") or a.get("src") or a.get("onclick") or a.get("value")
            text = a.get_text(strip=True)
            if href or text:
                links.append((a.name, text, href))
        print("Elements found:", links[:25], flush=True)

        # find mentions of .htm
        htm_refs = set(re.findall(r'([a-zA-Z0-9_\-]+\.htm[l]?)', r.text))
        print("HTM references in code:", htm_refs, flush=True)

    except Exception as e:
        print(f"Error {page}: {e}", flush=True)
