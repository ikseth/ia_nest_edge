# ia_nest_edge

El borde del ente IA_NEST: la unica puerta por la que se le habla.

Estado: semilla
Version: 0.1 - 2026-10-22

## Que es

Autentica a cada consumidor y afirma su identidad hacia dentro; las capas
interiores la consumen como hasta ahora (meta ADR 0011). Traduce cada
conversacion de un consumidor a una sesion de `ia_nest_extended`
(`extended ADR 0014` y `0015`).

Zona **Exterior** del registro (meta ADR 0013): no infiere, no recuerda, no
delibera ni presenta. Decide quien habla con el ente y en nombre de quien.

Dos caras, ambas dentro del contrato uniforme (meta ADR 0007):

- **Reenvio del contrato de extended** (REST y MCP), con autenticacion. Para
  los agentes (`ia_nest_agents`).
- **Piel en el dialecto OpenAI** (`/v1/chat/completions`, `/v1/models`). Para
  Home Assistant, el recomendador de Kodi y el webchat (Open WebUI).

Todo interno: el borde se publica solo en la red de casa, y es lo unico que se
publica. Nada expuesto a Internet.

## Criterio de salida

Fijado en meta ADR 0013, antes que el mecanismo:

1. Home Assistant, Kodi y Open WebUI responden a traves del borde cambiando solo
   su configuracion (URL y credencial).
2. Desde otra maquina de la red no responde ninguna superficie del core ni de
   extended.
3. **Duro.** Ninguna peticion con perfil infantil sale del borde sin el perfil
   aplicado; perfil desconocido = infantil.
4. Una conversacion = una sesion de extended, estable entre turnos y nunca
   compartida.

## Estado

Semilla documental, sin codigo. Lo que falta decidir antes del primer brief esta
en `docs/PLAN.md`.

## Orden de lectura

Ver `AGENTS.md`.
