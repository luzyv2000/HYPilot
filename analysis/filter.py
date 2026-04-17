def is_investable(inst: dict):
    name = inst["name"].lower()

    # Ausschlüsse (harte Filter)
    # if "3x" in name or "lev" in name:
    #     return False

    if "short" in name:
        return False

    if "covered call" in name:
        return False

    if "swap" in name:
        return False

    # Ausschluss sehr generischer Produkte
    # if name.startswith("100"):
    #     return False

    return True
