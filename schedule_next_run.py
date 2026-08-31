#!/usr/bin/env python3
"""
Reprograma el cron de update-champion.yml a partir del próximo partido conocido.

GitHub no tiene temporizadores dinámicos: el cron vive en el YAML. Como sí
sabemos cuándo juega el campeón (docs/data/next_match.json), reescribimos el
bloque de `schedule` para despertar solo alrededor del final de ese partido, en
vez de estar sondeando cada hora sin que haya fútbol.

Deja siempre una red de seguridad diaria fuera del bloque gestionado, por si el
campeón se queda sin próximo partido (parón, fin de temporada) o algo falla.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WORKFLOW = ROOT / ".github" / "workflows" / "update-champion.yml"
NEXT_MATCH = ROOT / "docs" / "data" / "next_match.json"

BEGIN = "    # >>> AUTO-SCHEDULE"
END = "    # <<< AUTO-SCHEDULE"

# Minutos tras el saque inicial. 110 cubre el partido normal con margen; 150 y
# 240, prórroga, penaltis y retrasos de la fuente de datos.
OFFSETS_MIN = (110, 150, 240)


def wake_up_crons(kickoff: datetime) -> list[str]:
    """Líneas de cron para los despertares posteriores a un saque inicial."""
    now = datetime.now(timezone.utc)
    lines: list[str] = []
    for offset in OFFSETS_MIN:
        moment = kickoff + timedelta(minutes=offset)
        if moment <= now:
            continue  # ya pasó: ese despertar no aporta nada
        line = f'    - cron: "{moment.minute} {moment.hour} {moment.day} {moment.month} *"'
        if line not in lines:
            lines.append(line)
    return lines


def read_kickoff() -> datetime | None:
    if not NEXT_MATCH.exists():
        return None
    try:
        data = json.loads(NEXT_MATCH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not data or not data.get("kickoff_utc"):
        return None
    try:
        return datetime.fromisoformat(data["kickoff_utc"].replace("Z", "+00:00"))
    except ValueError:
        return None


def main() -> int:
    text = WORKFLOW.read_text(encoding="utf-8")
    lines = text.splitlines()
    try:
        start = next(i for i, l in enumerate(lines) if l.startswith(BEGIN))
        end = next(i for i, l in enumerate(lines) if l.startswith(END))
    except StopIteration:
        print(f"ERROR: faltan los marcadores {BEGIN!r}/{END!r} en {WORKFLOW.name}")
        return 1

    kickoff = read_kickoff()
    if kickoff is None:
        body = ["    # Sin próximo partido conocido: solo queda la red diaria."]
        resumen = "sin próximo partido"
    else:
        body = wake_up_crons(kickoff)
        if not body:
            body = ["    # Los despertares de este partido ya pasaron."]
            resumen = f"despertares ya pasados (kickoff {kickoff.isoformat()})"
        else:
            resumen = f"kickoff {kickoff.isoformat()} → {len(body)} despertares"

    nuevo = lines[: start + 1] + body + lines[end:]
    salida = "\n".join(nuevo) + "\n"

    if salida == text:
        print(f"Cron ya al día ({resumen}).")
        return 0

    WORKFLOW.write_text(salida, encoding="utf-8")
    print(f"Cron reprogramado: {resumen}")
    for line in body:
        print(" ", line.strip())
    return 0


if __name__ == "__main__":
    sys.exit(main())
