# Changelog

Formato basado en Keep a Changelog; SemVer (ver `docs/VERSIONADO.md`).
Sin acentos por convencion.

## [No publicado]

## [0.2.0] - 2026-10-28

### Anadido
- Resolucion de cuentas y personas por LDAPS verificado, sin cache ni respaldo;
  clave `Bearer <uid>.<secreto>` y fallo cerrado 503 si el directorio no esta
  disponible (edge ADR 0003).
- Clases, perfiles y menus desde grupos del directorio, con entradas prototipo
  gobernadas por `edge_prototypes`.
- Reenvio generico `/rest/{ruta}` con identidad sustituida, query y flujos SSE.
- Servidor MCP Streamable HTTP con herramientas derivadas de
  `capability.list` y llamadas por la proyeccion REST del catalogo.
- Lista de capacidades permitidas para REST y MCP y auditoria por cara.

### Cambiado
- Configuracion incompatible: elimina identidades, invitado y hashes del YAML;
  anade `directory`, `classes` y `api.allowed_capabilities`.
- `deploy/setup.sh` comprueba la lectura de la CA y la contrasena de bind por el
  usuario del servicio.

### Dependencias
- `ldap3 >=2.9 <3` y `mcp >=2.3 <3`.

## [0.1.1] - 2026-10-26

### Corregido
- Una cabecera de tarea de fondo vacia o solo con espacios vuelve a contar como
  turno normal; solo un valor no vacio desactiva `write_back` (edge ficha
  v0.1/0001).

## [0.1.0] - 2026-10-22

Primera version con contrato publico (`docs/VERSIONADO.md`).

### Anadido
- **Piel OpenAI** (`/v1/models`, `/v1/chat/completions`, con y sin streaming)
  delante de la REST de extended (edge ADR 0002).
- **Autenticacion** por clave `Bearer` por consumidor (SHA-256, tiempo
  constante) y un unico punto de resolucion de identidades, con fuente fichero.
- **Identidad afirmada**: persona solo desde consumidores declarados; persona o
  perfil desconocido -> `child`; `interlocutor_profile` en cada peticion
  (efectivo cuando se entreguen edge CR-0001 y CR-0002).
- **Menu por consumidor e identidad**: modos directo, razonado e iterativo
  (prototipo); dominio fijo o automatico.
- **Sesiones** sin estado propio: una conversacion es una sesion de extended.
- **Consumidores sin memoria** (`write_memory: false`) y **TLS opcional**.
- **Auditoria** JSONL sin contenido ni claves.
- **Instalador** declarativo (`deploy/setup.sh`): venv, configuracion, comando,
  unit systemd y verificacion de que `/v1/models` sin clave da 401.

### Dependencias
- `ia_nest_extended >=0.5 <0.6` (`docs/DEPENDENCIAS.md`).
