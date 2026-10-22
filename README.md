# ia_nest_edge

El borde del ente IA_NEST: la unica puerta por la que se le habla.

Estado: activo
Version: 0.2 - 2026-10-22

## Que es

Autentica a cada consumidor y afirma su identidad hacia dentro; las capas
interiores la consumen como hasta ahora (meta ADR 0011). Traduce cada
conversacion de un consumidor a una sesion de `ia_nest_extended`
(`extended ADR 0014` y `0015`).

Zona **Exterior** del registro (meta ADR 0013): no infiere, no recuerda, no
delibera ni presenta. Decide quien habla con el ente y en nombre de quien.

Dos caras, ambas dentro del contrato uniforme (meta ADR 0007):

- **Reenvio del contrato de extended** (REST y MCP), con autenticacion. Para
  los agentes (`ia_nest_agents`).
- **Piel en el dialecto OpenAI** (`/v1/chat/completions`, `/v1/models`). Para
  Home Assistant, el recomendador de Kodi y el webchat (Open WebUI).

Todo interno: el borde se publica solo en la red de casa, y es lo unico que se
publica. Nada expuesto a Internet.

## Criterio de salida

Fijado en meta ADR 0013, antes que el mecanismo:

1. Home Assistant, Kodi y Open WebUI responden a traves del borde cambiando solo
   su configuracion (URL y credencial).
2. Desde otra maquina de la red no responde ninguna superficie del core ni de
   extended.
3. **Duro.** Ninguna peticion con perfil infantil sale del borde sin el perfil
   aplicado; perfil desconocido = infantil.
4. Una conversacion = una sesion de extended, estable entre turnos y nunca
   compartida.

## Estado

Primera version con contrato publico: `v0.1.0` (`CHANGELOG.md`). Que cuenta
como contrato, en `docs/VERSIONADO.md`; de que depende, en
`docs/DEPENDENCIAS.md`. Diseno en `docs/decision_records/0002-*`.

## Instalacion

El instalador deja la configuracion efectiva en
`/opt/ia_nest/config/edge/<instancia>/edge.yaml` y el estado, incluido el venv,
en `/opt/ia_nest/state/edge/<instancia>/`. No crea claves, certificados ni el
servicio extended.

Requisitos: Bash, curl, Python >= 3.13,<3.14 y PyYAML en ese Python, porque el
instalador valida `edge.yaml` antes de crear el venv. Instalar PyYAML con
`zypper install python313-PyYAML` en openSUSE o `apt install python3-yaml` en
Debian.

En una maquina limpia, primero crear un entorno temporal para generar cada
clave de consumidor y conservar solo su hash en `edge.yaml`:

```bash
python3 -m venv /tmp/ianest-edge-key
/tmp/ianest-edge-key/bin/pip install .
/tmp/ianest-edge-key/bin/ianest-edge key
```

Copiar `config/edge.example.yaml` fuera del repositorio, completar los hashes y
ajustar `audit.path` dentro del estado de la instancia, por ejemplo
`/opt/ia_nest/state/edge/family/audit/edge.jsonl`. Preparar tambien
`deploy/ejemplo.setup.conf` fuera del repositorio con la ruta de ese `edge.yaml`
y lanzar:

```bash
deploy/setup.sh --config /ruta/privada/edge.setup.conf
```

Los overrides de linea de comandos tienen precedencia sobre el fichero, que la
tiene sobre los valores por defecto. `--print-config` muestra la configuracion
efectiva sin instalar; una configuracion ya desplegada se conserva salvo
`REPLACE_CONFIG=true`.

## Orden de lectura

Ver `AGENTS.md`.
