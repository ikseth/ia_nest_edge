# 0001: tarea de fondo con cabecera vacia

Estado: implementada
Tipo: correccion de comportamiento (ejecuta edge ADR 0002, punto 1)
Impacto de version: patch (el contrato no cambia; el borde pasa a cumplirlo)
Version objetivo: v0.1.1

## Problema

edge ADR 0002 (punto 1): "Las tareas de fondo del consumidor (Open WebUI:
`X-OpenWebUI-Task`) no entran como turnos". El borde lo aplica en
`service.py` con `_header_present`: si la cabecera configurada como
`headers.background_task` APARECE en la peticion, la peticion es tarea de fondo
y lleva `write_back=false`.

Open WebUI no manda esa cabecera solo en las tareas. Desde 0.10.0 se declara en
la conexion como cabecera propia, `X-OpenWebUI-Task: {{TASK}}`, y Open WebUI la
envia en TODAS las peticiones: con el nombre de la tarea
(`title_generation`, `tags_generation`, `follow_up_generation`...) en las de
fondo y VACIA en un turno normal de chat (`utils/headers.py`,
`'{{TASK}}': metadata.get('task', '') or ''`, v0.12.4).

Resultado, medido en la visita de laboratorio del 2026-10-26
(`ia_nest_lab/medidas/edge/2026-10-26_visita_laboratorio.md`): con Open WebUI
TODAS las peticiones quedan auditadas con `background_task=true`, ningun turno
se escribe en la memoria de extended y un mismo chat no recuerda lo dicho en el
turno anterior. El criterio "una tarea de fondo no deja turno" pasa, pero por
la razon equivocada: tampoco lo deja la conversacion.

Los tests no lo detectaron porque el doble de prueba solo manda la cabecera en
la tarea (`{"X-Task": "anything"}`) y nunca vacia en un turno normal.

## Cambio

Una peticion es tarea de fondo si y solo si la cabecera configurada en
`headers.background_task` esta presente Y su valor, sin espacios al principio ni
al final, no es vacio. Presente y vacia (o solo espacios) = turno normal.
Ausente = turno normal, como hoy.

El campo `background_task` de la auditoria sigue la misma regla, porque ya sale
del mismo estado.

No cambia nada mas: ni los nombres de cabecera (son configuracion), ni el
esquema de `edge.yaml`, ni `write_memory`, ni la resolucion de sesiones.

## Criterios de aceptacion

- Con `headers.background_task` configurada:
  - cabecera con valor no vacio (`"title_generation"`) -> `write_back=false` y
    auditoria `background_task=true` (como hoy);
  - cabecera presente con valor `""` -> la peticion NO lleva `write_back=false`
    y la auditoria dice `background_task=false`;
  - cabecera presente con valor `"   "` -> igual que vacia;
  - cabecera ausente -> igual que hoy (turno normal).
- Lo anterior vale en `prompt.run`, `reasoning.run` y `task.run`, con y sin
  streaming.
- El nombre de la cabecera sigue sin distinguir mayusculas.
- Un consumidor con `write_memory: false` sigue mandando `write_back=false`
  siempre, haya o no cabecera.
- `python3 -m pytest -q` en verde.

## Archivos previstos

- `src/ianest_edge/service.py`
- `tests/test_service.py` (y `tests/conftest.py` si hace falta)
- `CHANGELOG.md` (`[No publicado]`, seccion Corregido)

## Resultado

Implementada por el codificador desde `docs/handoff/brief_fix_v0.1_0001.md`, en
una ronda. `_header_present` pasa a leer el valor con `_header_value` (que ya no
distingue mayusculas) y exige que no sea vacio tras quitar espacios. Un test
parametrizado cubre valor, vacia, solo espacios y ausente, en los tres modos y
con y sin streaming, incluida la auditoria; el de `write_memory: false` se
amplia a streaming.

Verificacion independiente: 99 tests en verde con las dependencias del servicio
(REST incluido). La comprobacion en vivo con Open WebUI es parte de la visita de
laboratorio tras instalar `v0.1.1`.
