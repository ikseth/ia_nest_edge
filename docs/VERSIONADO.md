# Versionado de ia_nest_edge

Estado: activo
Version: 1.0 - 2026-10-22

La POLITICA de versionado es comun al ente y vive en
`ia_nest_meta/docs/POLITICA_SEMVER.md`: esquema `MAJOR.MINOR.PATCH`, el tag como
fuente de verdad, que numero subir y el proceso de publicacion.

Este documento fija lo que solo esta capa puede fijar: QUE cuenta como su
contrato publico. Cierra lo que edge ADR 0001 dejaba pendiente ("sin SemVer ni
tag hasta que exista contrato publico").

## Que es "contrato publico" (lo que gobierna la version)

Cuenta como contrato:

1. **La piel OpenAI**: `GET /v1/models` y `POST /v1/chat/completions`, con y sin
   streaming; que campos de la peticion se aceptan, se ignoran o se rechazan
   (mensajes `system`/`developer`, `tools`, contenido en partes) y la forma de la
   respuesta y de sus eventos.
2. **La autenticacion**: clave `Bearer` por consumidor y el rechazo antes de
   cualquier otra cosa.
3. **Lo que el borde afirma hacia dentro**: los campos de identidad que envia a
   extended (`user_id`, `service`, `session_id` e `interlocutor_profile`) y la
   regla de que una persona o perfil desconocido es `child`.
4. **La traduccion a sesiones**: como una conversacion se convierte en una
   sesion de extended (edge ADR 0002, puntos 1 y 6).
5. **El esquema de `edge.yaml`**: claves, valores admitidos y lo que impide
   arrancar.
6. **Los errores propios** (`origin=ia_nest_edge`); su FORMA es la del ente
   (`meta docs/FORMA_DE_ERRORES_Y_TRAZA.md`).
7. **El esquema de la auditoria** (campos de cada linea JSONL) y las claves del
   instalador (`deploy/ejemplo.setup.conf`).

## Que NO cuenta como contrato

- La estructura de modulos, el `IdentityResolver` y el cliente de extended.
- Los nombres de cabecera de cada consumidor: son configuracion, no contrato.
- El texto de los mensajes de error y de log.
