# Brief: tarea de fondo con cabecera vacia (edge ficha v0.1/0001)

Destinatario: codificador
Autor: disenador
Verifica: disenador (no el codificador)
Fecha: 2026-10-26

## Base

Repo y punto de partida: `ia_nest_edge`, rama local `fix/tarea-de-fondo-vacia`
sobre el tag `v0.1.0` (`597b8f2`).
Estado de contrato: edge ADR 0002 (punto 1) y la ficha
`docs/fixes/v0.1/0001-tarea-de-fondo-con-cabecera-vacia.md`, que esta en el
working tree SIN commitear.

## Lectura obligatoria

- `docs/fixes/v0.1/0001-tarea-de-fondo-con-cabecera-vacia.md` (manda)
- `docs/decision_records/0002-diseno-de-la-primera-entrega.md`, punto 1
- `src/ianest_edge/service.py` (`_header_present` y su uso)
- `tests/test_service.py` y `tests/conftest.py`

## Objetivo

Que una cabecera de tarea de fondo presente pero vacia (o solo espacios) cuente
como turno normal, y solo una con valor no vacio como tarea de fondo.

## Alcance

Entra:
- La regla de la ficha en `service.py`.
- Tests de los criterios de la ficha, en los tres modos y con y sin streaming.
- Entrada en `CHANGELOG.md` bajo `[No publicado]`, seccion `### Corregido`,
  citando `edge ficha v0.1/0001`.

NO entra:
- Cambiar version en `pyproject.toml` ni en `src/ianest_edge/__init__.py`, ni
  mover `[No publicado]` a una version: eso es de la publicacion.
- Tocar `config.py`, el esquema de `edge.yaml`, `identity.py`, `rest.py`,
  `deploy/`, `docs/decision_records/`, `docs/fixes/` ni `README.md`.
- Cambiar la resolucion de sesiones, `write_memory` o la auditoria mas alla de
  que `background_task` siga la nueva regla.
- Refactors o mejoras no pedidas.

## Criterios de aceptacion

Los de la ficha, seccion "Criterios de aceptacion". Ademas:
- `git diff --stat` solo toca `src/ianest_edge/service.py`, `tests/` y
  `CHANGELOG.md`.

## Entrega

Cambios STAGED por ruta explicita; sin commit ni push. Listar: ficheros
tocados, tests anadidos (nombre y que criterio cubren) y la salida de
`python3 -m pytest -q`.

## Regla que manda sobre las demas

Ante ambiguedad, PARA y pregunta. No rellenes huecos por inferencia: eso
introduce diseno no reconciliado.
