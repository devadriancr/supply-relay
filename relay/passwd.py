"""Generates the admin password hash for the .env file.

    .venv\\Scripts\\python.exe -m relay.passwd
"""

import getpass
import sys

from relay.auth import hash_password

MIN_LENGTH = 12


def main() -> int:
    password = getpass.getpass("Nueva contraseña del administrador: ")
    if len(password) < MIN_LENGTH:
        print(f"Debe tener al menos {MIN_LENGTH} caracteres.", file=sys.stderr)
        return 1
    if getpass.getpass("Repítela: ") != password:
        print("Las contraseñas no coinciden.", file=sys.stderr)
        return 1
    print("\nCopia esta línea en el archivo .env:\n")
    print(f"ADMIN_PASSWORD_HASH={hash_password(password)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
