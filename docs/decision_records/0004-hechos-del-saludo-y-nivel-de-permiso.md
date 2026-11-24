# Decision 0004: hechos del saludo, persona opcional por clase y nivel de permiso

Fecha: 2026-11-24
Estado: propuesta

Tanda B del hito `H12` de meta ("sabe con quien habla", meta H12P8). Dispone en
el borde lo decidido en meta ADR 0017 (el borde afirma hechos observables), meta
H12P5 (D1-D3: forma del saludo por superficie), meta H12P3 (D3: el espacio de
nombres del dispositivo es la cuenta) y meta ADR 0019 (nivel de permiso y tono,
separados). Lo que el borde pide a extended esta en `edge CR-0004`.

## Contexto

Hacia dentro el borde afirma `user_id`, `service` (la clase) e
`interlocutor_profile` (`adult` o `child`). La cuenta autenticada no sale del
borde y no hay dispositivo. Una cuenta de `edge_asserts_people` sin cabecera de
persona recibe 403, asi que la voz de la casa (satelite, usuario sin persona en
el directorio) no puede afirmar personas sin romperse. Y `child` mezcla tres
cosas: permiso, tono y respaldo de quien no se sabe quien es (meta ADR 0019).

## Decision

### 1. Cabecera de dispositivo por clase (H12P5 D1)

- `headers` de cada clase gana la clave `device`, junto a `chat`, `person` y
  `background_task`. Sin la clave, la clase no lee dispositivo.
- Las tres caras (`/v1`, `/rest`, `/mcp`) leen las cabeceras igual: no hay forma
  propia por cara.
- Nada del cuerpo cuenta: ni `user` ni `metadata` de OpenAI, ni `_meta` de MCP,
  ni lo que el cliente ponga en `identity` (salvo `session_id`, edge ADR 0003).

### 2. Tres hechos hacia dentro, con su origen (H12P5 D2)

La identidad que el borde pone hacia extended gana `frame_facts`, siempre con
las tres claves:

| Hecho | `value` | `origin` | Que comprueba el borde | Si falla |
|---|---|---|---|---|
| `account` | uid de la cuenta autenticada | `authenticated` | la clave, como hoy | 401 / 403, como hoy |
| `person` | uid del directorio, o `null` | `validated`, o `absent` | existe, es unica y esta en `ia_nest_users`, como hoy | 403 y auditoria |
| `device` | lo que manda el consumidor, o `null` | `asserted`, o `absent` | solo la forma: 1 a 128 caracteres de `[A-Za-z0-9._:-]` | 400 y auditoria |

- Un hecho sin cabecera va con `value: null` y `origin: "absent"`, nunca
  omitido.
- Cualquier cuenta puede afirmar un dispositivo: el espacio de nombres lo pone
  la cuenta (`account:<uid>`, meta H12P3 D3), y extended lo forma con
  `account.value`. Afirmar personas sigue exigiendo `edge_asserts_people`.
- Una cuenta que habla como ella misma (sin afirmar personas) lleva `person`
  ausente: no es una persona.
- El borde no consulta entities ni sabe si un dispositivo esta sembrado (core
  ADR 0033: el borde no recuerda).
- Ninguno de los tres concede nada.

### 3. Persona obligatoria u opcional por clase (H12P5 D3)

- Opcion de clase `person_required`, `true` por defecto (como hoy).
- Cuenta de `edge_asserts_people` sin cabecera de persona:
  - con `person_required: true`, 403 como hoy;
  - con `person_required: false`, habla la cuenta: `user_id` = uid de la cuenta,
    `person` ausente, nivel `restricted` y tono `general` (punto 4), tenga la
    cuenta los grupos que tenga.
- Opcional es poder faltar, no poder ser falsa: una persona que viene y no esta
  en el directorio da 403 en las dos.
- Las cuentas que no afirman personas no cambian.

### 4. Nivel de permiso y tono, separados (meta ADR 0019)

- `interlocutor_profile` es el **nivel de permiso**: `adult` si el sujeto esta en
  el grupo adulto y no en el infantil; `restricted` en cualquier otro caso. El
  respaldo del punto 3 es siempre `restricted`.
- Nuevo campo `audience`, el **tono**, aparte del permiso:

  | Quien habla | `audience` |
  |---|---|
  | Persona afirmada y validada del grupo infantil (`directory.groups.child`) | `child` |
  | Persona afirmada y validada del grupo adulto (y no del infantil) | `adult` |
  | Cualquier otro caso: habla la cuenta (respaldo o cuenta que no afirma personas), persona sin grupo de perfil | `general` |

- Los menus por perfil de cada clase pasan de `adult` y `child` a `adult` y
  `restricted`. Durante una version se acepta `child` como nombre antiguo de la
  clave del menu; las dos a la vez impiden arrancar.
- La regla del borde "si no se puede determinar el perfil, el infantil" (meta
  ADR 0013, criterio duro 3) queda como "si no se puede determinar, `restricted`
  y tono `general`". Las herramientas y los menus de `restricted` son los que
  tenia `child`.

### 5. Auditoria

Cada registro gana `person` (uid o vacio), `device` (valor o vacio) y
`audience`. `consumer` sigue siendo la cuenta. Un dispositivo mal formado y una
persona rechazada dejan registro con su resultado.

## Orden de despliegue

El borde se programa antes que extended y el core (ellos usan lo que afirma),
pero **se despliega despues** de que extended y el core acepten `restricted` y
`audience`: hoy los dos rechazan cualquier perfil que no sea `adult` o `child`.
`frame_facts` y `audience` son aditivos y una capa que no los conoce los
ignora (meta ADR 0007).

## Practica habitual

La forma (cabeceras por clase, origen de cada hecho, persona opcional con
respaldo de menos permisos) esta contrastada en meta H12P5 y meta ADR 0019:
cabeceras de usuario de Open WebUI, proxies de autenticacion con cabecera de
confianza, `ConversationInput` de Home Assistant, invitado de los asistentes de
voz y rol por defecto minimo del control por roles.

## Lo que esta decision NO hace

- No compone ni guarda el marco: es de extended (`edge CR-0004`).
- No valida el dispositivo contra entities ni crea nada.
- No cambia Open WebUI ni su clase, salvo el nombre de la clave del menu.
- No cambia que herramientas tiene nadie.

## Impacto de version

Extension aditiva de la identidad hacia extended (`frame_facts`, `audience`),
clave nueva de configuracion (`device`, `person_required`) y cambio de valor del
perfil (`child` a `restricted`) con una version de transicion en los menus:
MINOR, `v0.3.0`. El tag lo corta el operador.
