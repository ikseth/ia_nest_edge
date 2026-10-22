# Brief: primera entrega del borde (la piel OpenAI)

Destinatario: codificador (Codex)
Autor: disenador (Claude)
Verifica: disenador (Claude), con revision de codigo y tests; despues, visita de
laboratorio con el operador. Nunca quien implementa.
Fecha: 2026-10-22

## Base

Repo y punto de partida: `ia_nest_edge`, rama `main` con
`docs/decision_records/0002-diseno-de-la-primera-entrega.md` en su version con
el punto 6. Repo sin codigo: esta entrega crea el paquete.

Estado de contrato: meta ADR 0011 y 0013; edge ADR 0001 y 0002 (reconciliados).
`edge CR-0001` y `CR-0002` estan PROPUESTOS, no entregados: el campo de
identidad del interlocutor se envia ya, aunque hoy el core y extended lo
descarten en silencio.

## Lectura obligatoria

1. `README.md`, `AGENTS.md`, `docs/PLAN.md` y los dos ADR de este repo.
2. `ia_nest_extended/docs/EXTENDED_CONTRACT.md`: "Interfaces publicas",
   "Garantia de transparencia", "Parametros de extension del enriquecimiento" y
   "Sesiones".
3. `ia_nest_extended` ADR 0014 y 0015 (identidad obligatoria; la sesion como
   entidad, archivado y ids).
4. `ia_nest_core/docs/CORE_CONTRACT.md`: "Contexto de identidad del request",
   `domain.list`, `prompt.run`, `reasoning.run`, `task.run` y la forma de sus
   eventos de flujo.
5. `ia_nest_meta/docs/FORMA_DE_ERRORES_Y_TRAZA.md` y
   `ia_nest_meta/docs/ARQUITECTURA_DE_CAPAS.md`.

Si lo que ves en el codigo de extended contradice su contrato, manda el
contrato y lo anotas en la entrega; no lo resuelves tu.

## Objetivo

Un servicio HTTP que habla el dialecto OpenAI (`GET /v1/models`,
`POST /v1/chat/completions`, con y sin streaming), autentica a cada consumidor,
resuelve su identidad y su menu, traduce cada conversacion a una sesion de
extended y reenvia a la REST de extended. Sin estado propio salvo la
configuracion.

## Alcance

Entra:

1. **Paquete y servicio.** Python 3.13 y el mismo estilo de empaquetado y de
   servidor que `ia_nest_extended` (`pyproject.toml`, uvicorn). Host y puerto
   configurables. Cliente HTTP hacia la REST de extended, con su URL base
   configurable.
2. **Configuracion.** Un fichero YAML cuya ruta llega por variable de entorno;
   se versiona solo `config/edge.example.yaml`, comentado. Contiene:
   - consumidores: nombre, hash de su clave, si puede afirmar personas, nombres
     de cabecera (chat, persona, tarea de fondo; cada una opcional), identidad
     por defecto (`user_id`, perfil) y menu;
   - personas, por consumidor: valor de la cabecera de persona -> `user_id`,
     perfil y menu;
   - entradas de menu: nombre visible (es el `id` de `/v1/models`), modo
     (`directo` | `razonado` | `iterativo`), dominio (`auto` o un nombre), y cual
     es la entrada por defecto (la que responde al nombre `ia_nest`);
   - `user_id` y menu del invitado.
3. **Autenticacion.** `Authorization: Bearer <clave>`. Se compara el SHA-256 de
   la clave con los hashes configurados, en tiempo constante (las claves son
   aleatorias y largas; no hace falta un hash lento). Sin clave o con clave
   desconocida: 401, antes de cualquier otra cosa. Un subcomando de consola que
   genera una clave nueva e imprime clave y hash.
4. **Un unico punto de resolucion de identidades** (edge ADR 0002, punto 3): una
   interfaz con UNA implementacion, la de fichero. Devuelve consumidor, `user_id`,
   `service` (nombre del consumidor), perfil del interlocutor y menu.
   - La cabecera de persona solo cuenta si el consumidor puede afirmar personas.
     En otro caso se ignora.
   - Persona no declarada, o cabecera ausente en un consumidor que si afirma
     personas: invitado, con perfil `child`.
   - Perfil ausente o desconocido en la configuracion: `child`.
5. **Menu.** `/v1/models` devuelve exactamente las entradas del menu de la
   identidad resuelta, mas `ia_nest`. Un `model` que no esta en el menu: error.
6. **Validacion al arrancar.** El servicio NO arranca si: una entrada nombra un
   dominio que no esta en `domain.list` (consultado a extended, que lo reenvia
   al core); una identidad con perfil `child` tiene en su menu una entrada que no
   es `directo`; extended no responde. Error claro en cada caso.
7. **Sesiones** (edge ADR 0002, puntos 1 y 6):
   - Con cabecera de chat: id de sesion `<consumidor>-<chat>-<n>`. Se busca con
     `session.list` (estado `activa`) la de ese prefijo; si no hay, `session.new`
     con `n` igual a uno mas que el mayor `n` de ese prefijo en `session.list`
     con `todas` (1 si no hay ninguna).
   - Sin cabecera de chat: si `messages` trae un solo mensaje de usuario,
     `session.new` con id del servidor; si trae mas, la sesion activa mas
     reciente de esa identidad por ultima actividad, y si no hay ninguna,
     `session.new`.
   - El `prompt` enviado a extended es SOLO el ultimo mensaje de usuario.
8. **Peticion a extended.** `identity` con `user_id`, `session_id`, `service` e
   `interlocutor_profile` (`adult` | `child`). El nombre de ese campo es una
   constante en un unico sitio del codigo (`edge CR-0001` no esta dispuesto).
   Segun el modo:
   - `directo`: `prompt.run` o `prompt.stream`;
   - `razonado`: `reasoning.run` o `reasoning.stream`;
   - `iterativo`: SIEMPRE `task.run`, tambien si el cliente pidio streaming
     (ver 9).
   Dominio fijo: `domain=<nombre>`; `auto`: `auto_domain=true`. El borde nunca
   envia `enrich=false`, ni `use_memory` ni `use_rag`.
   Tarea de fondo (cabecera de tarea presente): misma peticion con
   `write_back=false`.
9. **Respuesta en dialecto OpenAI.** Sin streaming: objeto `chat.completion`.
   Con streaming: SSE de `chat.completion.chunk` que traduce los eventos de
   flujo de extended, y termina en `data: [DONE]`. En el modo iterativo con
   streaming pedido: se espera a `task.run` y se emite la respuesta entera en un
   solo chunk. `finish_reason`: `stop` y `length` pasan tal cual; `incomplete`
   se traduce a `length`; cualquier otro, a `stop`, y queda en la auditoria.
   `usage` si extended lo da.
10. **Lo que no se reenvia.** Mensajes `system` del cliente: no se reenvian y se
    cuentan en la auditoria. Peticion con `tools` o `functions`: error explicito,
    no se ignora.
11. **Errores.** Sobre de error de OpenAI (`{"error": {...}}`). Dentro, la forma
    de `meta docs/FORMA_DE_ERRORES_Y_TRAZA.md`: errores propios con
    `origin=ia_nest_edge`; los de extended o del core se propagan con sus campos
    intactos, sin re-tipar (seccion 2 de ese documento).
12. **Auditoria.** Una linea JSONL por peticion: instante, consumidor,
    `user_id`, `interlocutor_profile`, entrada de menu, modo, capacidad llamada,
    `session_id`, si era tarea de fondo, mensajes `system` descartados,
    resultado, `finish_reason` y latencia. NUNCA el texto de los mensajes ni la
    clave. Ruta configurable.
13. **Tests** (pytest), contra un extended simulado; ninguno necesita red ni
    modelos.

NO entra:

- Reenvio del contrato de extended (REST o MCP) para los agentes.
- LDAP, OIDC, TLS, panel de administracion, limites de uso.
- Despliegue: unidad de servicio, cortafuegos, instalador. El criterio 2 del
  `README.md` se comprueba en la visita de laboratorio, no aqui.
- Editar o regenerar mensajes en Open WebUI; `reasoning_effort`.
- La variante de modelo con `SYSTEM` propio (alternativa de edge ADR 0002,
  punto 4).
- Cualquier cambio en `ia_nest_core`, `ia_nest_extended`, `ia_nest_meta` u otro
  repo.
- Cualquier cadena "OpenWebUI" en el codigo: los nombres de cabecera son
  configuracion.

## Criterios de aceptacion

Los comprueba quien verifica, con los tests y leyendo el codigo:

1. Sin clave o con clave desconocida: 401, y el extended simulado no recibe
   NINGUNA llamada.
2. **Criterio duro.** En toda la matriz de tests -persona declarada infantil,
   persona no declarada, cabecera de persona ausente, dispositivo con perfil
   `child`, perfil sin declarar- cada peticion que llega al extended simulado
   lleva `interlocutor_profile=child`, y su linea de auditoria tambien.
3. Una identidad `child` nunca llega a `reasoning.*` ni a `task.*`: la
   configuracion que lo permitiria impide arrancar.
4. La cabecera de persona en un consumidor que no puede afirmar personas no
   cambia la identidad.
5. Dos chats distintos nunca comparten sesion; el mismo chat conserva su sesion
   entre turnos; con la sesion archivada se crea `-<n+1>`; las reglas sin
   cabecera de chat se cumplen como en el punto 7.
6. A extended llega solo el ultimo mensaje de usuario como `prompt`.
7. `/v1/models` devuelve exactamente el menu de la identidad mas `ia_nest`, y un
   `model` fuera del menu da error.
8. Un dominio inexistente en la configuracion, o extended caido, impide arrancar.
9. Una tarea de fondo llega con `write_back=false`.
10. Una peticion con `tools` da error; los mensajes `system` no llegan a extended
    y constan en la auditoria.
11. El flujo traducido es SSE valido de OpenAI y acaba en `[DONE]`; en el modo
    iterativo, un solo chunk con la respuesta.
12. Ningun modulo, salvo la implementacion de fichero, sabe que las identidades
    salen de un fichero.
13. `grep -ri openwebui` en el codigo fuente no da resultados (si en el ejemplo
    de configuracion y en tests).
14. Ninguna linea de auditoria contiene el texto de un mensaje ni una clave.
15. Un error de extended llega al cliente con su `type` y su `origin` intactos.

## Entrega

En una rama local `feat/primera-entrega`, sin push. Al terminar, lista: ficheros
creados, resultado de los tests, comandos para arrancar el servicio con el
ejemplo de configuracion, y cualquier punto donde el contrato de extended y su
codigo no coincidieran.

## Regla que manda sobre las demas

Ante ambiguedad, PARA y pregunta. No rellenes huecos por inferencia: eso
introduce diseno no reconciliado.
