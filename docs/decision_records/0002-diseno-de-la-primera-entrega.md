# Decision 0002: diseno de la primera entrega (la piel OpenAI)

Fecha: 2026-10-22

Reconciliado con el usuario, decision a decision, sobre el plan de
`docs/PLAN.md`. Gobierna el primer brief.

## 1. Conversacion -> sesion: extended lleva el hilo

- El borde pasa a extended solo el turno nuevo del usuario y la sesion. La
  historia que reenvia el cliente sirve para localizar la sesion, no se reenvia.
- Si el consumidor manda identificador de chat (Open WebUI:
  `X-OpenWebUI-Chat-Id`), un chat es una sesion. Si no, la historia decide: un
  solo turno de usuario abre sesion (`session.new`); mas de uno sigue la ultima
  sesion activa de esa identidad.
- Las tareas de fondo del consumidor (Open WebUI: `X-OpenWebUI-Task`) no entran
  como turnos.
- Limites declarados: una misma identidad sin identificador de chat con dos
  conversaciones a la vez mezcla sesiones (una credencial por dispositivo lo
  evita); editar o regenerar en Open WebUI no reescribe el hilo (aparcado).

## 2. Identidad de la persona: confianza encadenada

- El borde autentica al consumidor y acepta la persona que este afirma, solo si
  el consumidor esta declarado para afirmar personas (hoy, Open WebUI) y solo si
  la persona esta declarada en el borde (persona -> `user_id` y perfil).
- En los demas consumidores, la identidad es el propio consumidor o dispositivo.
- Persona no declarada: perfil infantil y `user_id` de invitado.
- Riesgo declarado: quien administra el consumidor puede afirmar a cualquier
  persona de la lista.
- Camino declarado: un proveedor de identidad (OIDC o LDAP) comun al consumidor y
  al borde. Disparador: el segundo consumidor que lleve personas. Open WebUI no
  es proveedor de identidad: no emite identidad para otros, y es provisional.

## 3. Autenticacion: clave Bearer por consumidor

- Una clave por consumidor; en HA, una por dispositivo. Es lo unico que los tres
  clientes mandan sin codigo propio.
- Configuracion fuera del repo; se guarda el hash. Rotar o revocar es editarla.
- Sin clave o con clave desconocida: rechazo antes de tocar nada.
- **Un unico punto de resolucion de identidades.** Primera fuente: fichero.
  Criterio: cambiar la fuente (fichero -> LDAP u OIDC) solo edita su adaptador.
- TLS aparcado; riesgo declarado (en HTTP, quien escuche la red ve las claves).
  Disparador: publicar el borde en una red que no sea de confianza.

## 4. Perfil: el borde afirma un hecho, el ente decide

- El borde afirma que clase de interlocutor es, como campo de la identidad
  (`edge CR-0001`). No manda instrucciones: seria dirigir el pensar del ente
  (`core ADR 0033`).
- Mientras conscience no exista, extended lo compone siempre como contexto del
  interlocutor y no lo memoriza (`edge CR-0002`). Destino del juicio:
  conscience, sin cambiar la costura.
- Dispositivo compartido o perfil desconocido: infantil.
- Criterio duro comprobable en dos puntos: auditoria del borde y telemetria de
  extended.
- La familia no entra hasta que los dos CR esten desplegados (hoy un campo de
  identidad desconocido se descarta en silencio) y el laboratorio pruebe que el
  modelo atiende el contexto. Alternativa si los CR se atascan: variante de
  modelo con `SYSTEM` propio, comprobada antes en el laboratorio.

## 5. Personalizacion: un menu por consumidor e identidad

- La configuracion define, por consumidor o identidad, un menu de entradas:
  nombre visible, modo y dominio (fijo, o automatico por `domain.route`).
  `/v1/models` publica ese menu y solo ese; pedir una entrada que no esta en el
  menu se rechaza.
- Modos: **directo** (`prompt.*`), **razonado** (`reasoning.*`) e
  **iterativo** (`task.run`).
- Servicios especializados (HA, Kodi): una entrada con dominio fijo. Abiertos
  (webchat): varias, o pocas, a voluntad del operador.
- Identidades infantiles: modo directo, entrada automatica y, si se quiere, un
  menu corto con nombres comprensibles, cada uno con su dominio. Otros modos,
  cuando se compruebe que el contexto del interlocutor llega tambien por ellos.
- **El iterativo es prototipo**: solo en el menu del operador, marcado como tal,
  por `task.run` con la respuesta entera al final. Pasa a uso normal cuando se
  resuelva `edge CR-0003` (`task.stream` enriquecido y re-planificacion con
  enriquecimiento), sin tocar a ningun cliente.
- Criterio: una entrada con un dominio que no existe en `domain.list` impide
  arrancar al borde.
- Asi la pregunta 1 de "quien decide" (`meta docs/CAPAS_FUTURAS.md`) la
  contesta quien debe, el operador o el usuario, por configuracion o eleccion.
  El borde no decide como piensa el ente.
- Aparcado: `reasoning_effort` para afinar el modo razonado.

## 6. Anadido el 2026-10-22: sesion archivada y consecuencias derivadas

Reconciliado con el usuario al preparar el brief.

- **Volver a un chat cuya sesion se archivo** (extended archiva tras 4 h sin
  actividad y no resucita un id, `extended ADR 0015`): sesion nueva para el
  mismo chat. El ente conserva su memoria larga, no el hilo anterior; el borde
  NO le reenvia la historia del cliente. Limite declarado: la pantalla muestra
  una historia que el ente ya no tiene presente.
- **El borde no guarda estado** salvo su configuracion. El id de sesion se
  deriva del chat (`<chat>-<n>`) y la sesion activa se localiza con
  `session.list`; sin activa, se crea la siguiente.

Consecuencias de los puntos 1 y 4, que el brief aplica:

- **Los mensajes de sistema del cliente no se reenvian**, y quedan contados en
  la auditoria. Son instrucciones del exterior sobre como pensar, igual que las
  que el borde renuncia a mandar.
- **Una peticion con herramientas (`tools`) se rechaza** con error explicito.
  La primera entrega es conversacion; actuar es de la capa agentica. HA se
  configura sin control de la casa.
- **Los nombres de las cabeceras** (chat, persona, tarea de fondo) son
  configuracion por consumidor, no codigo. Asi sustituir Open WebUI no edita el
  borde.

## Impacto de version

Ninguno todavia: no hay contrato publico. La piel OpenAI sera el primero.
