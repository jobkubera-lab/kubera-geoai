# KUBERA GeoAI — EPC by UPRN (run in Google Colab; your key never leaves your browser session)
# 1) Add a Colab Secret named EPC_API_KEY (key icon, left) or paste the key when asked. 2) Run.
# 3) A file kubera_epc_raw.json downloads. 4) Attach that file in the chat with Claude.
import json, getpass, time, urllib.request, urllib.parse, urllib.error

LISTINGS = "https://kubera-geoai.pages.dev/data/mitcham_active_listings.geojson"
API = "https://api.get-energy-performance-data.communities.gov.uk"
TOKEN = ""
try:  # preferred: Colab Secrets (key icon on the left), name EPC_API_KEY
    from google.colab import userdata
    TOKEN = (userdata.get("EPC_API_KEY") or "").strip()
except Exception:
    pass
if not TOKEN:
    TOKEN = getpass.getpass("EPC API key (hidden): ").strip()
print("key length:", len(TOKEN))

def get(url):
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {TOKEN}", "Accept": "application/json", "User-Agent": "KUBERA GeoAI EPC helper"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            print("EPC API refused the key (HTTP", e.code, ") - check the key on the EPC website")
        return {"__error__": e.code}

def uprn12(v):
    t = str(v or "").strip()
    return t.zfill(12) if t.isdigit() and 0 < len(t) <= 12 and int(t) else None

def no_address(d):
    # EPC address/postcode fields have separate OS/Royal Mail terms: never keep them
    if isinstance(d, dict):
        return {k: no_address(v) for k, v in d.items() if "address" not in k.lower() and "postcode" not in k.lower()}
    if isinstance(d, list):
        return [no_address(x) for x in d]
    return d

UA = {"User-Agent": "Mozilla/5.0 (KUBERA GeoAI EPC helper; Colab)", "Accept": "application/json"}
feats = json.loads(urllib.request.urlopen(urllib.request.Request(LISTINGS, headers=UA), timeout=30).read())["features"]
print("listings:", len(feats))
searches, out, counts = {}, [], {"matched": 0, "no_match": 0, "no_uprn": 0, "error": 0}
for f in feats:
    p = f["properties"]
    u, pc = uprn12(p.get("uprn")), p.get("postcode")
    if not u or not pc:
        counts["no_uprn"] += 1
        continue
    if pc not in searches:
        r = get(f"{API}/api/domestic/search?" + urllib.parse.urlencode({"postcode": pc}))
        searches[pc] = None if (isinstance(r, dict) and r.get("__error__") not in (None, 404)) else (r.get("data") or [] if isinstance(r, dict) else [])
        time.sleep(0.2)
    rows = searches[pc]
    if rows is None:
        counts["error"] += 1
        out.append({"id": p.get("id"), "uprn": u, "status": "source_error"})
        continue
    hits = [r for r in rows if uprn12(r.get("uprn")) == u]
    if not hits:
        counts["no_match"] += 1
        out.append({"id": p.get("id"), "uprn": u, "status": "no_match"})
        continue
    row = max(hits, key=lambda r: r.get("registrationDate") or "")
    cert = get(f"{API}/api/certificate?" + urllib.parse.urlencode({"certificate_number": row["certificateNumber"]}))
    time.sleep(0.2)
    if not isinstance(cert, dict) or "__error__" in cert or not cert.get("data"):
        counts["error"] += 1
        out.append({"id": p.get("id"), "uprn": u, "status": "source_error"})
        continue
    counts["matched"] += 1
    out.append({"id": p.get("id"), "uprn": u, "status": "matched",
                "search_row": no_address(row), "certificate": no_address(cert["data"])})

result = {"retrieved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "counts": counts, "listings": out}
text = json.dumps(result, ensure_ascii=False)
assert TOKEN not in text, "key leaked"
open("kubera_epc_raw.json", "w").write(text)
print("DONE", counts)
try:
    from google.colab import files
    files.download("kubera_epc_raw.json")
except Exception:
    print("Download kubera_epc_raw.json from the Files panel on the left")
