"""Generador de licencias para La Puntual Marmoleria.

Uso:
    .venv\\Scripts\\python.exe licencias.py generar "Nombre del cliente" [dias]
    .venv\\Scripts\\python.exe licencias.py estado
    .venv\\Scripts\\python.exe licencias.py probar   (reinicia la prueba local)
"""

import sys

from core.licencia import generate_key, reset_trial, status


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return
    if args[0] == "generar":
        if len(args) < 2:
            print("Falta el nombre del cliente. Ej: licencias.py generar \"Taller Perez\"")
            return
        name = args[1]
        days = int(args[2]) if len(args) > 2 else 3650
        print()
        print(f"Cliente : {name}")
        print(f"Vigencia: {days} dias")
        print()
        print("LICENCIA:")
        print(generate_key(name, days))
        print()
    elif args[0] == "estado":
        print(status())
    elif args[0] == "probar":
        reset_trial()
        print("Prueba reiniciada.")
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
