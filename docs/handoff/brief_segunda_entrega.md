# Brief: segunda entrega del borde (directorio y punto REST/MCP)

Destinatario: codificador (Codex)
Autor: disenador (Claude)
Verifica: disenador (Claude), con revision de codigo y tests; despues, montaje
en el laboratorio con el operador. Nunca quien implementa.
Fecha: 2026-10-28

## Base

Repo y punto de partida: `ia_nest_edge`, rama `plan/H05-borde` (desde `main`
en `5904907`). En el working tree, sin commitear y VINCULANTES:
`docs/decision_records/0003-identidades-del-directorio-y-punto-rest-mcp.md` y
la nota anadida al final de `0002`.

Estado de contrato: meta ADR 0007, 0009, 0011 y 0015; edge ADR 0002 (lo que
0003 no sustituye) y 0003 (reconciliado con el usuario en meta `H05`).

## Lectura obligatoria

1. `AGENTS.md`, `README.md`, `docs/PLAN.md` y los tres ADR de este repo.
2. El codigo actual entero (`src/`, `tests/`, `deploy/setup.sh`): la entrega
   lo transforma, no empieza de cero.
3. `ia_nest_extended/docs/EXTENDED_CONTRACT.md`: "Interfaces publicas" y "El
   contrato uniforme". `ia_nest_extended/src/ianest_extended/mcp_server.py` y
   `rest.py`: como deriva extended sus herramientas MCP y sus rutas REST del
   catalogo (proyecciones `mcp`, `rest`, `streaming`). Se lee para seguir la
   misma regla; NO se importa extended (el borde no depende de su codigo).
4. `ia_nest_meta/docs/FORMA_DE_ERRORES_Y_TRAZA.md`.

Si el codigo de extended contradice su contrato, manda el contrato y lo anotas
en la entrega; no lo resuelves tu.

## Objetivo

El borde resuelve toda identidad en el directorio (LDAPS) y ofrece, junto a la
piel OpenAI, un reenvio REST y un servidor MCP hacia extended, con la
identidad puesta por el borde y una lista de capacidades permitidas. Su
configuracion no contiene ninguna identidad.

## Alcance

Entra:

1. **Adaptador de directorio** que sustituye a `FileIdentityResolver` detras
   del mismo `IdentityResolver` (o su evolucion minima). Se elimina la fuente
   de fichero.
   - Cliente LDAP: `ldap3` (Python puro). LDAPS con verificacion obligatoria
     contra `directory.ca_file`; nunca sin verificar, nunca LDAP en claro.
   - Bind con `directory.bind_dn` y la contrasena leida de
     `directory.bind_password_file` (fichero; se lee al arrancar).
   - Se permite reutilizar la conexion; NO se guarda ningun dato de identidad
     entre peticiones. Toda peticion autenticada hace sus busquedas.
   - Tiempo de espera `directory.timeout_seconds` (por defecto 3). Error de
     red, TLS, bind o tiempo: `DirectoryUnavailableError`, 503, tipo propio y
     `origin=ia_nest_edge`.
   - El borde arranca aunque el directorio no responda (no lo exige en
     `validate_startup`) y se recupera solo al volver.
2. **Autenticacion por clave** (edge ADR 0003, punto 2).
   - `Bearer <uid>.<secreto>`: se parte por el PRIMER punto. `uid` con la
     forma `^[a-z][a-z0-9_]{1,31}$`; secreto no vacio. Si no, 401 sin tocar el
     directorio.
   - Busqueda en `ou=people` (configurable: `directory.people_dn`) por
     `uid`, filtro con escape, pidiendo `uid`, `mail`, `memberOf` y el atributo
     de clave (`directory.key_attribute`, por defecto `edge-key-sha256`).
   - 401 si la cuenta no existe, no esta en el grupo de servicios, no tiene
     atributo de clave o el sha256 hex del secreto no coincide
     (`hmac.compare_digest`).
   - Los grupos se leen de `memberOf` por su `cn`. Nombres en
     `directory.groups` con estos defectos: `users: ia_nest_users`,
     `services: ia_nest_services`, `adult: profile_adult`,
     `child: profile_child`, `asserts_people: edge_asserts_people`,
     `prototypes: edge_prototypes`, `class_prefix: edge_class_`.
3. **Clase y persona** (puntos 3 y 5).
   - Clase de la cuenta: el unico grupo `edge_class_<nombre>` con `<nombre>`
     declarado en `classes`. Ninguno, dos o uno no declarado: 403
     (`AuthorizationError`, nuevo, 403) y auditoria.
   - Si la cuenta esta en `asserts_people`: la cabecera de persona de su clase
     es obligatoria; busqueda por `mail` (con escape) en `people_dn`; debe
     haber exactamente una entrada y estar en `users`. Si no: 403. `user_id`
     = `uid` de la persona; su perfil y sus grupos de prototipos, los de la
     persona.
   - Si no afirma personas: `user_id` = `uid` de la cuenta; perfil y
     prototipos, los de la cuenta.
   - Perfil: `adult` solo si esta en `adult` y no en `child`; si no, `child`.
   - `service` = nombre de la clase.
   - Menu: el de la clase para ese perfil; las entradas con `prototype: true`
     solo si la identidad esta en `prototypes`. Debe quedar exactamente una
     entrada `default` tras filtrar (validarlo al cargar: el menu de cada
     perfil, sin sus prototipos, tiene una sola `default`).
4. **Configuracion** (punto 5). Nueva forma, documentada en
   `config/edge.example.yaml`: `server`, `extended`, `audit` (como hoy),
   `directory` (url, base_dn, people_dn, ca_file, bind_dn,
   bind_password_file, timeout_seconds, key_attribute, groups), `classes`
   (por nombre: `headers` como hoy, `write_memory`, `menus` con `adult` y
   `child`, cada entrada como hoy mas `prototype` opcional) y `api`
   (`allowed_capabilities`: lista de nombres exactos de capacidad).
   - El ejemplo declara las clases `open_webui` (cabeceras de Open WebUI de la
     configuracion actual del laboratorio) y `api`, y esta lista de
     permitidas: `capability.list`, `prompt.run`, `prompt.stream`,
     `reasoning.run`, `reasoning.stream`, `task.run`, `session.list`,
     `session.show`, `session.new`, `memory.recall`, `knowledge.status`,
     `runtime.health`.
   - Las claves de la primera entrega (`consumers`, `people`, `key_sha256`,
     `guest`) en cualquier sitio impiden arrancar con un error que lo dice.
   - Se mantiene la validacion de dominios de los menus contra `domain.list`.
5. **Piel OpenAI** con la identidad nueva; su comportamiento no cambia salvo
   lo que fija 0003 (sin invitado). Sus llamadas internas a extended no pasan
   por la lista de permitidas.
6. **`/rest/{ruta}`**: metodo, ruta, query y cuerpo reenviados a
   `extended.base_url/{ruta}`. Capacidad = ruta con `/` cambiado por `.`; si
   no esta en la lista: 403 antes de llamar a extended. En cuerpos JSON objeto
   se fija `identity` = la del borde (`user_id`, `service`,
   `interlocutor_profile`), sustituyendo lo que trajera; si traia otra, se
   cuenta en la auditoria (`identity_overridden: true`). Respuestas
   `text/event-stream` se retransmiten evento a evento; las JSON, opacas;
   errores ajenos con su codigo y campos (meta ADR 0009).
7. **`/mcp`**: SDK oficial `mcp` de Python, transporte Streamable HTTP, sin
   estado de sesion propio mas alla del que exija el SDK. Autenticacion: la
   misma, por peticion HTTP, antes de entrar en MCP (401 con
   `WWW-Authenticate: Bearer`; 503 si no hay directorio).
   - `tools/list`: pide `capability.list` a extended y deriva las herramientas
     con la regla de `mcp_server.py` de extended (proyeccion `mcp`, sin
     `streaming`), filtradas por la lista de permitidas.
   - `tools/call`: herramienta permitida -> llamada por la proyeccion `rest`
     del catalogo (metodo y ruta) con los argumentos como cuerpo y `identity`
     del borde; resultado JSON como contenido de texto; error tipado como
     resultado de error MCP.
8. **Auditoria**: los registros de `/rest` y `/mcp` con la cara (`face`:
   `openai`, `rest`, `mcp`), cuenta (`consumer` = `uid` de la cuenta),
   `user_id`, perfil, capacidad, resultado y latencia. Resultados nuevos al
   menos: `directory_unavailable`, `forbidden`, `capability_not_allowed`. Sin
   contenido ni credenciales, como hoy.
9. **CLI**: `ianest-edge-key` genera un secreto y su sha256 hex (sin cambios
   si ya lo hace); su ayuda explica que el Bearer es `<uid>.<secreto>` y que el
   hash va al atributo de la cuenta.
10. **Instalador** (`deploy/setup.sh`): sigue funcionando con la configuracion
    nueva; comprueba que el usuario del servicio puede leer `ca_file` y
    `bind_password_file`; `VERIFY=strict` sigue comprobando 401 sin
    credencial (eso no necesita directorio).
11. **Tests** sin red: directorio falso (por ejemplo la estrategia `MOCK_SYNC`
    de `ldap3`, o un doble del adaptador detras de la interfaz) y el extended
    falso de `conftest.py`.
12. **Docs**: `README.md` (caras, configuracion, criterio de `H05` por
    referencia), `docs/PLAN.md` (segunda entrega), `CHANGELOG.md` y
    `pyproject.toml` a `0.2.0`, `docs/DEPENDENCIAS.md` si aplica.

NO entra:

- Clases de Home Assistant, Kodi o el agente Linux; `write_memory` en `/rest`
  y `/mcp` (edge ADR 0003, "NO hace").
- Ninguna cache de identidades ni fuente de respaldo.
- OAuth/OIDC.
- Tocar `ia_nest_extended`, `ia_nest_core` ni ningun repo que no sea este.
- Configuracion de laboratorio, direcciones o secretos reales.
- Commits, tags o ramas: el trabajo se deja STAGED.

## Criterios de aceptacion

Cada uno con al menos un test:

1. La configuracion de ejemplo y el codigo no contienen ninguna identidad; una
   configuracion con `consumers`, `people`, `key_sha256` o `guest` no arranca.
2. Bearer valido de una cuenta de servicios con clase -> 200 por la piel
   OpenAI, por `/rest/prompt/run` y por `tools/call` de MCP; a extended llega
   `identity.user_id` = `uid` de la cuenta y `service` = clase.
3. 401 en: sin cabecera, sin punto, `uid` invalido, cuenta inexistente, fuera
   de `ia_nest_services`, sin atributo de clave, secreto erroneo. En los tres
   casos de forma (sin cabecera, sin punto, `uid` invalido) no se consulta el
   directorio.
4. Cuenta que afirma personas: persona adulta -> `adult`; en los dos grupos o
   en ninguno -> `child`; fuera de `ia_nest_users`, inexistente o sin
   cabecera -> 403. Tras dar de baja a la persona en el directorio falso, la
   siguiente peticion da 403 sin reiniciar nada.
5. Cuenta sin clase, con dos o con una no declarada -> 403.
6. Entradas `prototype` solo para quien esta en `edge_prototypes`.
7. `identity` enviada por el cliente en `/rest` y en `tools/call` se sustituye
   y queda `identity_overridden` en la auditoria.
8. Capacidad fuera de la lista: 403 por `/rest` sin llamar a extended, y no
   aparece en `tools/list`. Una capacidad que el borde no nombra en su codigo,
   anadida al extended falso y a la lista, es alcanzable por `/rest` y aparece
   en MCP sin tocar el codigo.
9. Un flujo de `/rest/prompt/stream` llega evento a evento.
10. Directorio caido (conexion rechazada y tiempo agotado): 503 por las tres
    caras y registro `directory_unavailable`; el servicio arranca con el
    directorio caido y, al volver el directorio falso, la siguiente peticion
    entra.
11. Suite completa en verde; `deploy/setup.sh` y sus tests al dia.

## Entrega

Trabajo STAGED en `plan/H05-borde`, sin commit. Al terminar lista: ficheros
cambiados, dependencias nuevas con su version, decisiones tomadas dentro del
alcance, lo que haya quedado fuera y cualquier contradiccion encontrada.

## Regla que manda sobre las demas

Ante ambiguedad, PARA y pregunta. No rellenes huecos por inferencia: eso
introduce diseno no reconciliado. En particular: si extended rechaza el campo
`identity` en alguna capacidad permitida, o si el SDK de MCP obliga a una
forma distinta de la descrita, para y anotalo.
