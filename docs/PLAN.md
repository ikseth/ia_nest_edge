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
3. **Mecanismo de autenticacion. DECIDIDA el 2026-10-22: clave Bearer por
   consumidor.** Es lo unico que saben mandar los tres clientes sin codigo
   propio (criterio 1).
   - Una clave por consumidor; en HA, una por dispositivo.
   - La clave lleva asociada la identidad del consumidor (que es, si puede
     afirmar personas, perfil por defecto). Configuracion fuera del repo; se
     guarda el hash, no la clave.
   - Rotar o revocar es editar esa configuracion. Sin panel: eso es de
     `ia_nest_web`.
   - Sin clave o con clave desconocida: rechazo, antes de tocar nada.
   - Los agentes usaran el mismo mecanismo (MCP por HTTP admite Bearer).
   - **Un unico punto de resolucion de identidades** (clave -> consumidor,
     persona -> `user_id` y perfil). Primera fuente: fichero. LDAP u OIDC
     serian otra fuente detras del mismo punto (los grupos LDAP darian el
     perfil). Criterio: cambiar la fuente solo edita su adaptador; ni la
     autenticacion, ni la traduccion a sesiones, ni el perfil.
   - TLS aparcado. Riesgo declarado: en HTTP, quien escuche la red ve las
     claves. Disparador: publicar el borde en una red que no sea de confianza
     (por ejemplo, la wifi de invitados).
4. **Perfil. DECIDIDA el 2026-10-22: el borde afirma un hecho, el ente decide.**
   - El borde no manda instrucciones: afirma que clase de interlocutor es, como
     un campo mas de la identidad (`edge CR-0001`, al core). Decirle al ente
     como comportarse seria dirigir su pensar (`core ADR 0033`).
   - Mientras conscience no exista, extended lo compone como contexto del
     interlocutor, siempre y sin memorizarlo (`edge CR-0002`). El juicio sigue
     destinado a conscience, sin cambiar la costura.
   - Mapa identidad -> perfil en la configuracion del borde (decision 3);
     dispositivo compartido o perfil desconocido: infantil.
   - Para identidades infantiles el borde usa solo `prompt.*` y nunca desactiva
     el enriquecimiento.
   - Criterio duro, comprobable en dos puntos: la auditoria del borde (ninguna
     identidad infantil sale sin el atributo) y la telemetria de extended
     (ninguna peticion con el atributo sin el contexto compuesto).
   - La familia no entra hasta que los dos CR esten desplegados: hoy un campo
     de identidad desconocido se descarta en silencio en el core y en
     extended. Antes, prueba de laboratorio de que el modelo atiende el
     contexto. Alternativa si los CR se atascan: variante de modelo con
     `SYSTEM` propio, comprobada antes en el laboratorio.
5. **Que capacidad de extended** atiende `/v1/chat/completions`, y con streaming.

## Aparcado

- Reenvio del contrato de extended (MCP y REST) para los agentes: segunda
  entrega.
- Valoraciones de usuario de Open WebUI como dato para extended y conscience:
  se mira cuando haya familia usandolo.
