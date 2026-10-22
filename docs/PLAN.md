# Plan de ia_nest_edge

Estado: propuesta
Version: 0.1 - 2026-10-22

## Primera entrega: la piel OpenAI para la familia

Objetivo: los criterios 1 a 4 del `README.md` (meta ADR 0013). El reenvio del
contrato de extended para los agentes va en una entrega posterior, cuando
`ia_nest_agents` lo necesite.

La familia no entra hasta que extended cierre L5r y L4b; el borde se construye y
se prueba antes, con el operador.

## Decisiones antes del primer brief

Un brief se escribe sobre diseno reconciliado (`meta docs/PLANTILLA_BRIEF.md`).
Se deciden con el usuario, una a una y en este orden:

1. **Conversacion -> sesion. DECIDIDA el 2026-10-22.** El dialecto OpenAI no
   tiene estado: el cliente reenvia toda la historia en cada peticion, y
   extended ya guarda el hilo de cada sesion.
   - **Extended lleva el hilo.** El borde le pasa solo el turno nuevo del
     usuario y la sesion; la historia del cliente sirve para localizar la
     sesion, no se reenvia.
   - **Localizar la sesion.** Si el consumidor manda identificador de chat
     (Open WebUI: cabecera `X-OpenWebUI-Chat-Id`), un chat es una sesion. Si
     no, la historia decide: un solo turno de usuario abre sesion nueva
     (`session.new`); mas de uno sigue la ultima sesion activa de esa
     identidad.
   - Las tareas de fondo del consumidor (Open WebUI: `X-OpenWebUI-Task`) no
     entran como turnos.
   - Limites declarados: una misma identidad sin identificador de chat con dos
     conversaciones a la vez mezcla sesiones (una credencial por dispositivo lo
     evita); editar o regenerar en Open WebUI no reescribe el hilo de extended
     (aparcado).
2. **Identidad de la persona. DECIDIDA el 2026-10-22: confianza encadenada.**
   El borde autentica al consumidor y acepta la persona que este afirma, con
   tres condiciones:
   - Solo afirman personas los consumidores declarados para ello (hoy, Open
     WebUI). En los demas, la identidad es el propio consumidor o dispositivo.
   - Solo vale una persona declarada en el borde (configuracion fuera del
     repo: persona del consumidor -> `user_id` y perfil).
   - Persona no declarada: perfil infantil y `user_id` de invitado.
   - Riesgo declarado: quien administra el consumidor puede afirmar a
     cualquier persona de la lista.
   - Camino declarado: un proveedor de identidad (OIDC) comun en el que confien
     el consumidor y el borde. Disparador: el segundo consumidor que lleve
     personas (`ia_nest_web`, o un agente que actue en nombre de alguien).
     Open WebUI no es proveedor de identidad: no emite identidad para otros
     consumidores, y es provisional.
3. **Mecanismo de autenticacion** de los consumidores (meta ADR 0011 lo dejo
   abierto).
4. **Perfil.** Mapa de identidad a perfil, perfil de los dispositivos
   compartidos, y como se aplica el infantil mientras conscience no exista.
5. **Que capacidad de extended** atiende `/v1/chat/completions`, y con streaming.

## Aparcado

- Reenvio del contrato de extended (MCP y REST) para los agentes: segunda
  entrega.
- Valoraciones de usuario de Open WebUI como dato para extended y conscience:
  se mira cuando haya familia usandolo.
