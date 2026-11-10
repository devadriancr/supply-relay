"""Loads the vendors the portal works with, like a Laravel seeder.
Running it again only adds the ones that are missing.

    .venv\\Scripts\\python.exe -m relay.seed
"""

import sys

from relay import store as st
from relay.config import get_settings

# Vendor number in Infor (AVM) and its name; the name is replaced by Infor's on the first sync
VENDORS = {
    101402: "MATSUJU MEXICANA SA DE CV",
    400050: "NIFAST MEXICANA SA DE CV",
    400070: "NITTO DENKO DE MEXICO S DE RL DE CV",
    400110: "SK TEC MEXICANA SA DE CV",
    400190: "NORTON GALVANOPLASTIA SA DE CV",
    400192: "ALPHAMETAL MEXICO SA DE CV",
    400193: "MINAMIDA MEXICANA SA DE CV",
    400194: "TECHNO ASSOCIE DE MEXICO SA DE CV",
    400195: "NIPPON STEEL PIPE MEXICO SA DE CV",
    410010: "HIRUTA MEXICO SA DE CV MXN",
    410020: "F E G DE QUERETARO SA DE CV MXN",
    410030: "TYRSA TROQUELADOS SA DE CV MXN",
    410191: "YOROZU AUTOMOTIVE GUANAJUATO DE MEXICO SA DE CV MX",
}


def seed(store: st.Store) -> list[int]:
    """Adds the missing vendors and returns their numbers."""
    added = [number for number, name in VENDORS.items() if store.add_vendor(number, name)]
    for number in added:
        store.log_event(st.ADDED, number, actor="seed")
    return added


def main() -> int:
    store = st.Store(get_settings().database_path)
    added = seed(store)
    print(f"{len(added)} proveedor(es) agregados, {len(VENDORS) - len(added)} ya estaban en la lista.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
