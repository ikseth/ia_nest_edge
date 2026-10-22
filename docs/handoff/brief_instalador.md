# Brief: instalador del borde

Destinatario: codificador (Codex)
Autor: disenador (Claude)
Verifica: disenador (Claude); despues, instalacion real en el laboratorio con el
operador. Nunca quien implementa.
Fecha: 2026-10-22

## Base

Repo `ia_nest_edge`, rama `feat/instalador` (sale de `main` con la primera
entrega mergeada). Linea base: `python3 -m pytest -q` en verde.

Motivo: la maquina del laboratorio activo debe ser EXACTAMENTE lo que dejan los
instaladores a partir de un tag; un paso a mano es un fallo de codigo, no un
parche en la maquina. El borde no tiene instalador, asi que no se puede
desplegar sin romper esa regla.

## Lectura obligatoria

1. `README.md`, `AGENTS.md` y `docs/decision_records/0002-*` de este repo.
2. `config/edge.example.yaml` y `src/ianest_edge/cli.py` y `config.py`.
3. **El patron a seguir**: `ia_nest_extended/deploy/setup.sh`,
   `ia_nest_extended/deploy/ejemplo.setup.conf` y
   `ia_nest_extended/tests/test_deploy_setup.py`. El instalador del borde es la
   version reducida de ese: mismas convenciones, mismas rutas, mismo estilo de
   tests. Lo que no aparezca abajo no se copia (no hay almacen, ni esquema, ni
   corpus, ni MCP).

## Objetivo

`deploy/setup.sh` despliega el borde de forma declarativa e idempotente: venv,
configuracion, comando, servicio systemd y verificacion. Una maquina instalada
con el y un fichero de parametros es reproducible.

## Alcance

Entra:

1. **`deploy/setup.sh`**, con la cabecera de proposito/entradas/salidas/
   requisitos y la precedencia argumento > fichero > defecto de extended
   (`--config`, `--print-config`, overrides por clave, `usage`). Variables de
   entorno `IANEST_INSTALL_ROOT`, `IANEST_BIN_DIR`, `IANEST_SYSTEMD_DIR` como en
   extended.
2. **Claves** (y nada mas):
   - `INSTANCE_NAME` (defecto `edge`);
   - `EDGE_CONFIG`: ruta al `edge.yaml` efectivo del operador, OBLIGATORIA, sin
     defecto;
   - `SERVICE_INSTALL`, `SERVICE_ENABLE` (defecto `true`);
   - `VERIFY` `strict|warn|skip` (defecto `strict`);
   - `OPERATOR_USER` (vacio: `SUDO_USER` o quien lanza);
   - `REPLACE_CONFIG` (defecto `false`).
   Host, puerto, TLS y auditoria NO son claves del instalador: viven solo en
   `edge.yaml` (hogar unico). El instalador los LEE de el cuando los necesita.
3. **Rutas**: configuracion en `<root>/config/edge/<instancia>/edge.yaml`
   (modo 640, propietario el operador; contiene hashes de claves); estado en
   `<root>/state/edge/<instancia>/` (venv y, por convencion, la auditoria).
   Una configuracion ya instalada se conserva salvo `REPLACE_CONFIG=true`, como
   en extended.
4. **Validacion antes de tocar nada**: se carga `EDGE_CONFIG` con el propio
   paquete (la validacion estructural de `EdgeConfig`, no una segunda en bash).
   Error claro si no existe o no es valido. La validacion contra extended
   (dominios) la hace el servicio al arrancar; el instalador no la duplica.
5. **venv** en el estado, con el paquete instalado desde el repo.
6. **Comando** `ianest-edge` en `IANEST_BIN_DIR` (envoltorio como los de
   extended), con `IANEST_EDGE_CONFIG` apuntando a la configuracion instalada.
7. **Unit** `ianest-edge-<instancia>.service`: `User=` el operador,
   `Environment=IANEST_EDGE_CONFIG=...`, `ExecStart=<venv>/bin/ianest-edge
   serve`, `Restart=on-failure` con `RestartSec` de unos segundos (si extended
   no esta listo, el borde no arranca y reintenta). Instalar y habilitar son
   decisiones distintas, como en extended.
8. **Verificacion** (`VERIFY`): servicio activo, puerto de `edge.yaml`
   escuchando y `GET /v1/models` SIN clave devuelve 401. Esa prueba no usa
   ningun secreto y demuestra que el borde autentica antes de hacer nada. Con
   TLS declarado en `edge.yaml`, la prueba va por HTTPS (sin verificar el
   certificado SOLO en esta sonda local, declarado en un comentario).
9. **`deploy/ejemplo.setup.conf`** comentado, y un apartado "Instalacion" en el
   `README.md`: generar claves con `ianest-edge key`, preparar `edge.yaml` a
   partir del ejemplo (con `audit.path` dentro del estado de la instancia),
   lanzar el instalador.
10. **Tests** (`tests/test_deploy_setup.py`) con el estilo de extended:
    ejecutables simulados, raiz temporal, sin root, sin red. Cubren: precedencia
    de valores; `EDGE_CONFIG` ausente o invalido falla sin escribir nada;
    configuracion existente preservada y sustituida con `REPLACE_CONFIG`; modo
    640 de la configuracion; unit generada con usuario, entorno y `ExecStart`;
    `SERVICE_INSTALL=false` no genera unit; `VERIFY=skip` no sondea.

NO entra:

- Instalar Open WebUI, extended, el core u ollama.
- Tocar el cortafuegos, generar certificados, crear la CA.
- Crear el `edge.yaml` real o claves reales.
- Cualquier cambio en el codigo del servicio, salvo lo minimo para que el
  instalador lea host, puerto y TLS de la configuracion (si hiciera falta,
  dilo en la entrega).
- Cambios en otros repos.

## Criterios de aceptacion

1. Ejecutar dos veces seguidas con los mismos parametros deja el mismo
   resultado (idempotente) y la segunda no sustituye la configuracion.
2. Sin `EDGE_CONFIG`, o con uno invalido, falla ANTES de escribir nada.
3. La configuracion instalada tiene modo 640 y propietario el operador.
4. Ninguna clave del instalador duplica host, puerto, TLS ni auditoria.
5. La unit arranca `ianest-edge serve` como el operador, con la configuracion
   instalada, y reintenta si falla.
6. La verificacion `strict` falla si el puerto no escucha o si `/v1/models` sin
   clave no da 401.
7. Tests en verde sin root ni red; los existentes siguen en verde.

## Entrega

En la rama `feat/instalador`, STAGED por ruta explicita, sin commit ni push.
Lista: ficheros, resultado de `python3 -m pytest -q`, y como lo lanzarias en una
maquina limpia.

## Regla que manda sobre las demas

Ante ambiguedad, PARA y pregunta. No rellenes huecos por inferencia.
