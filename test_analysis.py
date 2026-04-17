from analysis.engine import analyze_universe

results = analyze_universe(limit=1000)

print(f"\nGefilterte Treffer: {len(results)}\n")

for r in results[:20]:
    print(f"{r['score']:>3} | {r['category']:>10} | {r['name']}")
