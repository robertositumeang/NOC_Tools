import capture_engine

pages = ['alarms.htm', 'stats.htm', 'femgt.htm', 'mod.htm']
for p in pages:
    name = p.replace(".htm", "")
    out = f"captures/{name}.png"
    print(f"Capturing {p} -> {out}...", flush=True)
    res = capture_engine.capture_page("10.70.1.225", p, "comtech", "comtech", out)
    print(f"Result {p}:", res.get("success"), flush=True)
