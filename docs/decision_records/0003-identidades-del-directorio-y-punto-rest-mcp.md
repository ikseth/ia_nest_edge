# Decision 0003: identidades del directorio y punto REST/MCP (segunda entrega)

Fecha: 2026-10-28

Reconciliado con el usuario, decision a decision, en el hito `H05` de meta
(`ia_nest_meta/docs/plan/hitos/H05_borde_contra_el_directorio.md`, pasos
H05P1-P6). Gobierna el brief de la segunda entrega. El criterio de salida es
el de ese hito, desde meta ADR 0015 (C1, C2, C4, C5).

## 1. Fuente de identidades: el directorio, y solo el

- El adaptador de fichero del punto unico de resolucion (edge ADR 0002, punto
  3) se sustituye por uno de directorio: LDAPS verificado contra una raiz
  declarada, leyendo con la cuenta de solo lectura del borde. No hay fuente
  alternativa: ni fichero ni cache de identidades.
- Cada peticion pregunta al directorio. Una baja vale desde la siguiente
  peticion.
- **Fallo cerrado.** Directorio inalcanzable o que no responde a tiempo: 503
  a toda peticion autenticable, y queda en la auditoria. El borde arranca aunque
  el directorio no responda, y se recupera solo cuando vuelve.

## 2. Autenticacion: clave de API por cuenta

- El consumidor manda `Authorization: Bearer <uid>.<secreto>`. El borde lee la
  cuenta `<uid>` y compara el hash del secreto con el atributo de la cuenta
  (`edge-key-sha256`). Una busqueda por peticion.
- Una clave por cuenta; un dispositivo con clave propia es una cuenta propia.
- La contrasena de la cuenta (login, bind) y su clave del borde son
  credenciales distintas: la contrasena nunca llega al borde.
- Solo entran por clave las cuentas de `ia_nest_services`. Sin clave, clave
  mal formada, cuenta inexistente o fuera de ese grupo, o hash distinto: 401.
- Motivo: es la practica habitual de claves de API (identificador, secreto
  aleatorio, solo el hash, revocable sola). OAuth 2.1/OIDC queda como camino:
  otro adaptador en el mismo punto, sin tocar a los clientes con clave.

## 3. Personas y perfil

- Sustituye al punto 2 de edge ADR 0002 en lo que toca a la fuente: la
  confianza encadenada sigue (el consumidor afirma la persona), pero quien
  puede afirmar personas lo dice el grupo `edge_asserts_people`, y la persona
  debe estar en el directorio.
- La persona afirmada se busca por `mail`; su `uid` es el `user_id`.
- Persona no encontrada, fuera de `ia_nest_users`, o cabecera de persona
  ausente en una cuenta que afirma personas: 403 y auditoria. **No hay
  invitado**: con invitado, una persona dada de baja seguiria entrando.
- Una cuenta que no afirma personas se atiende como ella misma: `user_id` = su
  `uid`.
- Perfil, para personas y cuentas: `child` salvo que este solo en
  `profile_adult` (meta H04P3). El punto 4 de edge ADR 0002 sigue igual.
- `service` hacia extended es el nombre de la clase de la cuenta (punto 5).

## 4. Punto REST/MCP

- Tres caras, una sola via hacia extended (su REST en loopback):
  - `/v1/...`: la piel OpenAI, como hasta ahora.
  - `/rest/<ruta de extended>`: reenvio generico de metodo, ruta y cuerpo;
    flujos evento a evento; errores ajenos tal cual (meta ADR 0009).
  - `/mcp`: MCP por Streamable HTTP. Herramientas derivadas del
    `capability.list` de extended con la misma regla que su servidor MCP; cada
    llamada, por la ruta REST que declara el catalogo. Las capacidades de flujo
    quedan fuera de MCP, como en extended.
- En las tres el borde pone el campo `identity`; lo que mande el cliente se
  ignora y queda en la auditoria.
- **Lista de permitidas.** Por `/rest` y `/mcp` solo pasan las capacidades de
  una lista de la configuracion; MCP lista solo esas. Lo que cambia estado
  compartido queda para el operador por loopback. Una capacidad nueva del core
  se expone anadiendo una linea a la lista, sin codigo: el reenvio sigue siendo
  generico y la lista es autorizacion, no catalogo (meta ADR 0007).
- Descartado reenviar al servidor MCP propio de extended: otro proceso, otra
  puerta, y la identidad dentro de los mensajes MCP.

## 5. Que queda en la configuracion

El directorio dice quien; el fichero dice como.

- Directorio: cuentas, hash de su clave, alta y baja, perfil, clase de cada
  cuenta (`edge_class_<nombre>`), quien afirma personas
  (`edge_asserts_people`) y quien ve las entradas prototipo del menu
  (`edge_prototypes`; mantiene el punto 5 de edge ADR 0002 sin nombrar a nadie
  en el fichero).
- Fichero: conexion al directorio (con la ruta de la clave de la cuenta del
  borde), clases de consumidor (cabeceras, menu por perfil, si escribe
  memoria), lista de permitidas, servidor, TLS, extended y auditoria.
- Una cuenta pertenece a exactamente una clase; ninguna o dos: 403 y
  auditoria.
- La configuracion no contiene ninguna identidad (C2): ni personas, ni claves,
  ni hashes. Una configuracion con las claves de la primera entrega
  (`consumers`, `people`, `key_sha256`, `guest`) impide arrancar.

## Lo que esta decision NO hace

- No conecta Home Assistant, Kodi ni el agente Linux: son `H07`, cada uno con
  su clase.
- No aplica `write_memory` a `/rest` ni a `/mcp`: hoy solo lo usa la piel
  OpenAI; el agente Linux lo resuelve en su hito.
- No toca el login de Open WebUI (`H07`).

## Impacto de version

Cambia la configuracion de forma incompatible y anade dos caras: `v0.2.0`.
El tag lo corta el operador.
