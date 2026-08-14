"""Licencia offline para la app de escritorio.

- Prueba gratuita de TRIAL_DAYS dias desde la primera ejecucion.
- Despues exige una clave de licencia firmada (HMAC) generada con licencias.py.
- El estado se guarda en data/licencia.json junto a la app; el archivo lleva
  un MAC para detectar manipulacion (borrarlo reinicia la prueba).
"""

import base64
import hashlib
import hmac
import json
import os
import sys
import time
from pathlib import Path

TRIAL_DAYS = 30

# Secreto maestros: solo para generar/validar claves. No compartir.
_SECRET = b"LPML-2f7a-9c41-marmol-2026-xz91"


def _project_base():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def _state_path():
    override = os.getenv("CORTE_LICENCIA_PATH")
    if override:
        return Path(override)
    return _project_base() / "data" / "licencia.json"


def _mac(payload: str) -> str:
    return hmac.new(_SECRET, payload.encode("utf-8"),
                    hashlib.sha256).hexdigest()[:8].upper()


def generate_key(name: str, days: int = 3650) -> str:
    """Genera una clave: nombre del cliente + vencimiento (por defecto 10 anios)."""
    payload = f"{name}|{int(time.time()) + days * 86400}"
    data = base64.b32encode(payload.encode("utf-8")).decode("ascii").rstrip("=")
    raw = f"{len(data):02x}{data}{_mac(data)}"
    return "-".join(raw[i:i + 4] for i in range(0, len(raw), 4)).upper()


def validate_key(key: str):
    """Devuelve {"name", "expires"} si la clave es valida, o None."""
    clean = "".join(key.split("-")).strip().upper()
    if len(clean) < 14:
        return None
    try:
        size = int(clean[:2], 16)
        data = clean[2:2 + size]
        signature = clean[2 + size:2 + size + 8]
    except ValueError:
        return None
    if _mac(data) != signature:
        return None
    try:
        payload = base64.b32decode(
            data + "=" * (-len(data) % 8)).decode("utf-8")
        name, expires = payload.rsplit("|", 1)
        return {"name": name, "expires": int(expires)}
    except Exception:
        return None


def _read_state():
    path = _state_path()
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _write_state(state):
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False),
                    encoding="utf-8")


def _state_valid(state) -> bool:
    if not isinstance(state, dict):
        return False
    mac = state.get("mac")
    if not mac:
        return False
    body = {"first_run": state.get("first_run"),
            "key": state.get("key")}
    return _mac(json.dumps(body, ensure_ascii=False)) == mac


def _seal(state):
    body = {"first_run": state.get("first_run"), "key": state.get("key")}
    state["mac"] = _mac(json.dumps(body, ensure_ascii=False))
    return state


def status():
    """Estado de la licencia: trial / licensed / expired."""
    now = int(time.time())
    state = _read_state()
    if state is None:
        state = _seal({"first_run": now, "key": None})
        _write_state(state)
    if not _state_valid(state):
        return {"status": "expired",
                "reason": "archivo de licencia invalido o manipulado"}

    key = state.get("key")
    if key:
        info = validate_key(key)
        if info and info["expires"] > now:
            return {
                "status": "licensed",
                "licensed_to": info["name"],
                "days_left": int((info["expires"] - now) / 86400),
            }
        return {"status": "expired", "reason": "licencia vencida o invalida"}

    days_left = TRIAL_DAYS - int((now - state["first_run"]) / 86400)
    if days_left > 0:
        return {"status": "trial", "days_left": days_left}
    return {"status": "expired", "reason": "periodo de prueba vencido"}


def activate(key: str):
    """Valida y guarda una clave. Devuelve (ok, mensaje)."""
    info = validate_key(key)
    if info is None:
        return False, "La clave no es valida. Verifica que este bien copiada."
    if info["expires"] <= int(time.time()):
        return False, "La clave esta vencida."
    state = _read_state() or {"first_run": int(time.time()), "key": None}
    if not _state_valid(state):
        state = {"first_run": int(time.time()), "key": None}
    state["key"] = "".join(key.split("-")).upper()
    _write_state(_seal(state))
    return True, f"Licencia activada para {info['name']}."


def reset_trial():
    """Solo para desarrollo: borra el estado y reinicia la prueba."""
    path = _state_path()
    if path.exists():
        path.unlink()
