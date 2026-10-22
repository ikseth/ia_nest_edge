# Plan de ia_nest_edge

Estado: propuesta
Version: 0.2 - 2026-10-22 (diseno de la primera entrega cerrado, edge ADR 0002)

## Primera entrega: la piel OpenAI para la familia

Objetivo: los criterios 1 a 4 del `README.md` (meta ADR 0013). El reenvio del
contrato de extended para los agentes va en una entrega posterior, cuando
`ia_nest_agents` lo necesite.

Diseno reconciliado: `docs/decision_records/0002-diseno-de-la-primera-entrega.md`
(sesiones, identidad de la persona, autenticacion, perfil y menu por
consumidor). No se repite aqui.

Siguiente paso: el brief para el codificador (`meta docs/PLANTILLA_BRIEF.md`).

## Lo que espera fuera de este repo

| que | donde | bloquea |
|---|---|---|
| `edge CR-0001`: perfil del interlocutor en la identidad | core | la entrada de la familia |
| `edge CR-0002`: extended lo transporta y lo compone | extended | la entrada de la familia |
| `edge CR-0003`: modo iterativo de uso normal | extended (y el core, por su CR) | que el iterativo deje de ser prototipo |
| L5r y L4b de la puerta de extended | extended | la entrada de la familia |

Ninguno bloquea la primera entrega: se construye y se prueba con el operador.

## Aparcado

- Reenvio del contrato de extended (MCP y REST) para los agentes: segunda
  entrega.
- Editar o regenerar en Open WebUI reescribiendo el hilo de extended.
- TLS (disparador en edge ADR 0002, punto 3).
- Proveedor de identidad comun (disparador en edge ADR 0002, punto 2).
- `reasoning_effort` para el modo razonado.
- Valoraciones de usuario de Open WebUI como dato para extended y conscience:
  se mira cuando haya familia usandolo.
