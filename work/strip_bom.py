from pathlib import Path

p = Path(r"D:\gpt\2026-11-12\codex-handoff-ios26-location-test-md\outputs\run-planner\location_sim.py")
text = p.read_text(encoding="utf-8-sig")
compile(text, str(p), "exec")
p.write_text(text, encoding="utf-8")
print("bom stripped, compile ok, chars", len(text))
print("配速" in text, "路线至少需要两个点" in text)