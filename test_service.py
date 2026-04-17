from core.universe_service import get_all_instruments, search_instruments

print("=== TEST: Alle (5) ===")
print(get_all_instruments(limit=5))

print("\n=== TEST: Suche 'Tesla' ===")
print(search_instruments("Tesla"))
