# ia_nest_edge

El borde del ente IA_NEST: la unica puerta por la que se le habla.

Estado: activo
Version: 0.2 - 2026-10-28

## Que es

Autentica una vez contra el directorio y afirma la identidad hacia dentro
(meta ADR 0011, edge ADR 0003). Las capas interiores no reautentican. El borde
no infiere, no recuerda, no delibera ni presenta (`core ADR 0033`).

Ofrece tres caras sobre una sola REST de extended en loopback:

- `/v1/models` y `/v1/chat/completions`: piel OpenAI para clientes de chat.
- `/rest/{ruta}`: reenvio generico del contrato uniforme de extended.
- `/mcp`: MCP Streamable HTTP; herramientas derivadas de `capability.list`.

REST y MCP pasan solo las capacidades de `api.allowed_capabilities`. La lista
autoriza; no replica el catalogo. Una capacidad nueva con proyecciones REST y
MCP se expone anadiendo su nombre a la lista, sin editar codigo (meta ADR 0007).

## Identidad y fallo cerrado

La credencial es `Authorization: Bearer <uid>.<secreto>`. El directorio guarda
el hash SHA-256 del secreto en `edge-key-sha256` (atributo configurable), los
grupos de servicio, perfil, clase y prototipos. La configuracion no contiene
cuentas, personas, claves ni hashes.

Cada peticion consulta el directorio por LDAPS, con verificacion contra
`directory.ca_file`. No hay cache ni fuente alternativa. Si el directorio no
responde, las tres caras devuelven 503; el proceso sigue vivo y la siguiente
peticion vuelve a intentarlo.

Una cuenta de `edge_asserts_people` debe aportar la cabecera de persona de su
clase. La persona se busca por `mail` y debe estar en `ia_nest_users`. No hay
invitado. El perfil es `adult` solo si el sujeto esta en `profile_adult` y no
esta en `profile_child`; cualquier otro caso es `child`.

## Configuracion

La forma completa esta en `config/edge.example.yaml`:

- `server`, `extended` y `audit`: escucha, REST interior y auditoria.
- `directory`: LDAPS, DN de lectura, CA, fichero de contrasena y nombres de
  grupos.
- `classes`: cabeceras, `write_memory` y menus `adult`/`child`.
- `api.allowed_capabilities`: autorizacion exacta para REST y MCP.

El menu se elige por clase y perfil. Las entradas `prototype: true` solo se
publican a sujetos de `edge_prototypes`. Los dominios fijos se validan contra
`domain.list` al arrancar. El arranque no consulta el directorio.

`ianest-edge-key --help` explica la credencial y `ianest-edge-key` genera el
secreto y su hash. La contrasena de bind se lee de
`directory.bind_password_file` al arrancar y nunca se versiona.

## Instalacion

El instalador deja la configuracion efectiva en
`/opt/ia_nest/config/edge/<instancia>/edge.yaml` y el estado, incluido el venv,
en `/opt/ia_nest/state/edge/<instancia>/`. Comprueba que el usuario del servicio
puede leer la CA y el fichero de contrasena del directorio.

Requisitos: Bash, curl, Python >=3.13,<3.14 y PyYAML en ese Python, porque el
instalador valida `edge.yaml` antes de crear el venv. Copiar el ejemplo fuera
del repo, ajustar rutas y lanzar:

```bash
deploy/setup.sh --config /ruta/privada/edge.setup.conf
```

Los overrides de linea de comandos tienen precedencia sobre el fichero, y el
fichero sobre los valores por defecto. `VERIFY=strict` comprueba que
`/v1/models` sin credencial devuelve 401; esa sonda no necesita directorio.

## Criterio de salida

El criterio de `H05` no se redefine aqui: vive en
`ia_nest_meta/docs/plan/hitos/H05_borde_contra_el_directorio.md`, desde meta
ADR 0015 (C1, C2, C4 y C5). El detalle implementado se decide en edge ADR 0003
y se registra en `docs/PLAN.md`.

## Orden de lectura

Ver `AGENTS.md`.
