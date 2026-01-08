import json

# Yokosuka
data = json.load(open('data/mini-tokyo-3d/train-timetables/jreast-yokosuka.json', encoding='utf-8'))
matches = [t for t in data if t.get('n') == '4824Y']
print(f"Yokosuka: {len(matches)} matches")
for t in matches[:3]:
    print(f"  id={t.get('id')[:60]}, d={t.get('d')}, r={t.get('r')}")
    tt = t.get('tt', [])
    print(f"    stations: {len(tt)}, first={tt[0].get('s') if tt else None}, last={tt[-1].get('s') if tt else None}")

print()

# ShonanShinjuku
data = json.load(open('data/mini-tokyo-3d/train-timetables/jreast-shonanshinjuku.json', encoding='utf-8'))
matches = [t for t in data if t.get('n') == '4824Y']
print(f"ShonanShinjuku: {len(matches)} matches")
for t in matches[:3]:
    print(f"  id={t.get('id')[:60]}, d={t.get('d')}, r={t.get('r')}")
    tt = t.get('tt', [])
    print(f"    stations: {len(tt)}, first={tt[0].get('s') if tt else None}, last={tt[-1].get('s') if tt else None}")
