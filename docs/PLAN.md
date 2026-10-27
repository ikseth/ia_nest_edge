# Plan de ia_nest_edge

Estado: propuesta
Version: 0.3 - 2026-10-27 (primera entrega hecha; orden entre capas en meta, H01)

El orden de este repo respecto a otras capas no se fija aqui: vive en la hoja
de ruta del ente (`ia_nest_meta/docs/plan/HOJA_DE_RUTA.md`, meta ADR 0014).
Este plan lleva solo el detalle interno del borde.

## Primera entrega: la piel OpenAI (hecha)

Objetivo: los criterios 1 a 4 del `README.md` (meta ADR 0013). Diseno
reconciliado en `docs/decision_records/0002-diseno-de-la-primera-entrega.md`.

Publicada en `v0.1.0` y corregida en `v0.1.1` (ficha v0.1/0001). Verificada en
la visita de laboratorio del 2026-10-26/27: criterios 2, 3 y 4 pasan; el 1,
parcial (Open WebUI si; Kodi y HA, fuera). Evidencia en el laboratorio del
operador, fuera de este repo.

## Lo que sigue, por hito de meta

| Que | Hito |
|---|---|
| Fuente de identidades en el directorio (edge ADR 0002, punto 2) | H05 |
| Reenvio del contrato de extended (REST y MCP): el punto comun para servicios y agentes | H05 |
| TLS en los tramos que cruzan el perimetro (edge ADR 0002, punto 8) | H06 |
| Diseno por consumidor: Kodi (su `system`, sin memoria), HA (estado de la casa), `write_back=false` por consumidor para el agente | H07 |

Lo que el borde espera de otras capas (`edge CR-0001`, `CR-0002`, `CR-0003`,
L5r y L4b de extended) figura en la hoja de ruta como trabajo de capa vigilado.

## Aparcado

- Editar o regenerar en Open WebUI reescribiendo el hilo de extended.
- `reasoning_effort` para el modo razonado.
- Valoraciones de usuario de Open WebUI como dato para extended y conscience:
  se mira cuando haya familia usandolo.
