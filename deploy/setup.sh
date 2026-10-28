#!/usr/bin/env bash
#
# Proposito:
#   Desplegar ia_nest_edge de forma declarativa: configuracion, venv, comando,
#   servicio systemd y verificacion de que el borde autentica antes de actuar.
#
# Entradas:
#   --config PATH, --print-config y overrides de las claves documentadas en
#   deploy/ejemplo.setup.conf.
#
# Salidas:
#   /opt/ia_nest/config/edge/<instancia>/edge.yaml,
#   /opt/ia_nest/state/edge/<instancia>, el comando ianest-edge y, si se
#   solicita, una unit systemd por instancia.
#
# Requisitos:
#   Bash, curl, Python >= 3.13,<3.14 y PyYAML en ese Python. Instalar PyYAML
#   con `zypper install python313-PyYAML` (openSUSE) o `apt install python3-yaml`
#   (Debian). Extended debe existir aparte: valida los dominios cuando el borde
#   arranca, no este instalador.

set -Eeuo pipefail

readonly REPO_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly INSTALL_ROOT="${IANEST_INSTALL_ROOT:-/opt/ia_nest}"
readonly BIN_DIR="${IANEST_BIN_DIR:-/usr/local/bin}"
readonly SYSTEMD_DIR="${IANEST_SYSTEMD_DIR:-/etc/systemd/system}"
readonly -a CONFIG_KEYS=(
  INSTANCE_NAME EDGE_CONFIG SERVICE_INSTALL SERVICE_ENABLE VERIFY OPERATOR_USER
  REPLACE_CONFIG
)

declare -A VALUES=(
  [INSTANCE_NAME]=edge
  [EDGE_CONFIG]=''
  [SERVICE_INSTALL]=true
  [SERVICE_ENABLE]=true
  [VERIFY]=strict
  [OPERATOR_USER]="${SUDO_USER:-$(id -un)}"
  [REPLACE_CONFIG]=false
)
declare -A SOURCES=()
declare -A ARGUMENTS=()
for key in "${CONFIG_KEYS[@]}"; do SOURCES["${key}"]=default; done

CONFIG_FILE=''
PRINT_CONFIG=false
DEPLOY_PYTHON=''
CONFIG_DIR=''
STATE_DIR=''
VENV_DIR=''
INSTALLED_CONFIG=''
EFFECTIVE_CONFIG=''
EDGE_HOST=''
EDGE_PORT=''
EDGE_TLS_CERT=''
EDGE_TLS_KEY=''
DIRECTORY_CA_FILE=''
DIRECTORY_PASSWORD_FILE=''

usage() {
  sed -n '2,22p' "$0" | sed 's/^# \{0,1\}//'
  cat <<'EOF'

Overrides:
  --instance-name NAME       --edge-config PATH
  --service-install BOOL     --service-enable BOOL
  --verify strict|warn|skip  --operator-user USER
  --replace-config BOOL
EOF
}

log() { printf '[setup] %s\n' "$*"; }
warning() { printf '[setup] WARNING: %s\n' "$*" >&2; }
error() { printf '[setup] ERROR: %s\n' "$*" >&2; exit 1; }

set_argument() { ARGUMENTS["$1"]="$2"; }

load_config_file() {
  local path="$1" line key value line_number=0
  [[ -r "$path" ]] || error "no se puede leer la configuracion: $path"
  while IFS= read -r line || [[ -n "$line" ]]; do
    line_number=$((line_number + 1))
    line="${line%$'\r'}"
    [[ -z "$line" || "$line" == \#* ]] && continue
    [[ "$line" == *=* ]] || error "$path:$line_number: se esperaba CLAVE=VALOR"
    key="${line%%=*}"
    value="${line#*=}"
    [[ -n "${VALUES[$key]+present}" ]] ||
      error "$path:$line_number: clave desconocida '$key'"
    VALUES["$key"]="$value"
    SOURCES["$key"]=file
  done < "$path"
}

apply_arguments() {
  local key
  for key in "${CONFIG_KEYS[@]}"; do
    if [[ -n "${ARGUMENTS[$key]+present}" ]]; then
      VALUES["$key"]="${ARGUMENTS[$key]}"
      SOURCES["$key"]=argument
    fi
  done
}

require_bool() {
  [[ "$2" == true || "$2" == false ]] || error "$1 debe ser true o false"
}

resolve_implicit_values() {
  if [[ -z "${VALUES[OPERATOR_USER]}" ]]; then
    VALUES[OPERATOR_USER]="${SUDO_USER:-$(id -un)}"
  fi
}

validate_config() {
  local key
  for key in SERVICE_INSTALL SERVICE_ENABLE REPLACE_CONFIG; do
    require_bool "$key" "${VALUES[$key]}"
  done
  [[ "${VALUES[VERIFY]}" == strict || "${VALUES[VERIFY]}" == warn || "${VALUES[VERIFY]}" == skip ]] ||
    error "VERIFY debe ser strict, warn o skip"
  [[ "${VALUES[INSTANCE_NAME]}" =~ ^[A-Za-z0-9_-]+$ ]] ||
    error "INSTANCE_NAME solo admite letras, numeros, guion y guion bajo"
  [[ -n "${VALUES[EDGE_CONFIG]}" ]] || error "EDGE_CONFIG es obligatoria"
  [[ -n "${VALUES[OPERATOR_USER]}" ]] || error "OPERATOR_USER no puede estar vacio"
  id "${VALUES[OPERATOR_USER]}" >/dev/null 2>&1 ||
    error "OPERATOR_USER no existe: ${VALUES[OPERATOR_USER]}"
  if [[ "${VALUES[SERVICE_ENABLE]}" == true && "${VALUES[SERVICE_INSTALL]}" == false ]]; then
    error "SERVICE_ENABLE=true requiere SERVICE_INSTALL=true"
  fi
  if [[ "${VALUES[VERIFY]}" == strict && "${VALUES[SERVICE_ENABLE]}" == false ]]; then
    error "VERIFY=strict requiere SERVICE_ENABLE=true para verificar el servicio"
  fi
}

print_config() {
  local key
  for key in "${CONFIG_KEYS[@]}"; do
    printf '%s=%s (%s)\n' "$key" "${VALUES[$key]}" "${SOURCES[$key]}"
  done
}

check_dependencies() {
  command -v curl >/dev/null 2>&1 || error "curl no encontrado; instalalo y repite"
  local candidate
  for candidate in python3.13 python3; do
    if command -v "$candidate" >/dev/null 2>&1 &&
      "$candidate" -c 'import sys; raise SystemExit(sys.version_info < (3, 13) or sys.version_info >= (3, 14))'; then
      DEPLOY_PYTHON="$(command -v "$candidate")"
      "$DEPLOY_PYTHON" -c 'import yaml' >/dev/null 2>&1 ||
        error "falta PyYAML en $DEPLOY_PYTHON; instalalo con 'zypper install python313-PyYAML' (openSUSE) o 'apt install python3-yaml' (Debian)"
      return
    fi
  done
  error "se requiere Python >=3.13,<3.14; instalalo y repite"
}

read_edge_config() {
  local path="$1" output status
  [[ -f "$path" && -r "$path" ]] || error "EDGE_CONFIG no es un fichero legible: $path"
  set +e
  output="$(PYTHONPATH="${REPO_DIR}/src${PYTHONPATH:+:${PYTHONPATH}}" "$DEPLOY_PYTHON" - "$path" <<'PY'
import sys

from ianest_edge.config import EdgeConfig
from ianest_edge.errors import ConfigurationError

try:
    config = EdgeConfig.from_path(sys.argv[1])
except ConfigurationError as exc:
    raise SystemExit(str(exc))

print(config.host)
print(config.port)
print("-" if config.tls is None else config.tls.certfile)
print("-" if config.tls is None else config.tls.keyfile)
print(config.directory.ca_file)
print(config.directory.bind_password_file)
PY
)"
  status=$?
  set -e
  ((status == 0)) || error "EDGE_CONFIG no es valida: $path"
  local -a details=()
  mapfile -t details <<< "$output"
  ((${#details[@]} == 6)) || error "EDGE_CONFIG no produjo sus datos de despliegue: $path"
  EDGE_HOST="${details[0]}"
  EDGE_PORT="${details[1]}"
  EDGE_TLS_CERT="${details[2]}"
  EDGE_TLS_KEY="${details[3]}"
  DIRECTORY_CA_FILE="${details[4]}"
  DIRECTORY_PASSWORD_FILE="${details[5]}"
  if [[ "$EDGE_TLS_CERT" == - ]]; then EDGE_TLS_CERT=''; fi
  if [[ "$EDGE_TLS_KEY" == - ]]; then EDGE_TLS_KEY=''; fi
}

check_directory_files() {
  if ! "$DEPLOY_PYTHON" - "${VALUES[OPERATOR_USER]}" "$DIRECTORY_CA_FILE" "$DIRECTORY_PASSWORD_FILE" <<'PY'
import os
import pwd
import sys

account = pwd.getpwnam(sys.argv[1])
if os.geteuid() != account.pw_uid:
    if os.geteuid() != 0:
        raise SystemExit(1)
    os.initgroups(account.pw_name, account.pw_gid)
    os.setgid(account.pw_gid)
    os.setuid(account.pw_uid)
for path in sys.argv[2:]:
    with open(path, "rb"):
        pass
PY
  then
    error "el usuario del servicio no puede leer directory.ca_file o directory.bind_password_file"
  fi
}

resolve_paths() {
  CONFIG_DIR="${INSTALL_ROOT}/config/edge/${VALUES[INSTANCE_NAME]}"
  STATE_DIR="${INSTALL_ROOT}/state/edge/${VALUES[INSTANCE_NAME]}"
  VENV_DIR="${STATE_DIR}/venv"
  INSTALLED_CONFIG="${CONFIG_DIR}/edge.yaml"
}

select_effective_config() {
  read_edge_config "${VALUES[EDGE_CONFIG]}"
  if [[ -f "$INSTALLED_CONFIG" && "${VALUES[REPLACE_CONFIG]}" == false ]]; then
    EFFECTIVE_CONFIG="$INSTALLED_CONFIG"
    read_edge_config "$EFFECTIVE_CONFIG"
  else
    EFFECTIVE_CONFIG="${VALUES[EDGE_CONFIG]}"
  fi
}

prepare_directories() {
  mkdir -p "$CONFIG_DIR" "$STATE_DIR" "$BIN_DIR"
  chown "${VALUES[OPERATOR_USER]}" "$CONFIG_DIR" "$STATE_DIR"
  chmod 700 "$CONFIG_DIR" "$STATE_DIR"
}

write_atomic() {
  local target="$1" mode="$2" temporary
  temporary="$(mktemp "${target}.tmp.XXXXXX")"
  cat > "$temporary"
  chmod "$mode" "$temporary"
  mv -f -- "$temporary" "$target"
}

install_config() {
  if [[ -f "$INSTALLED_CONFIG" && "${VALUES[REPLACE_CONFIG]}" == false ]]; then
    log "Configuracion existente detectada en $INSTALLED_CONFIG; se preserva (usa REPLACE_CONFIG=true para sustituirla)."
    return
  fi
  local temporary
  temporary="$(mktemp "${INSTALLED_CONFIG}.tmp.XXXXXX")"
  cp -- "${VALUES[EDGE_CONFIG]}" "$temporary"
  chmod 640 "$temporary"
  mv -f -- "$temporary" "$INSTALLED_CONFIG"
  chown "${VALUES[OPERATOR_USER]}" "$INSTALLED_CONFIG"
}

prepare_venv() {
  if [[ ! -x "$VENV_DIR/bin/python" ]]; then
    log "Creando entorno Python de despliegue en $VENV_DIR."
    "$DEPLOY_PYTHON" -m venv "$VENV_DIR"
  else
    log "Reutilizando entorno Python de despliegue."
  fi
  "$VENV_DIR/bin/python" -c 'import sys; raise SystemExit(sys.version_info < (3, 13) or sys.version_info >= (3, 14))' ||
    error "el entorno existente no usa Python >=3.13,<3.14"
  log "Instalando o actualizando ia_nest_edge desde el repositorio."
  "$VENV_DIR/bin/python" -m pip install --upgrade "$REPO_DIR"
}

write_wrapper() {
  {
    printf '#!/usr/bin/env bash\nset -Eeuo pipefail\n'
    printf 'export IANEST_EDGE_CONFIG=%q\n' "$INSTALLED_CONFIG"
    printf 'exec %q "$@"\n' "$VENV_DIR/bin/ianest-edge"
  } | write_atomic "${BIN_DIR}/ianest-edge" 755
}

install_commands() {
  write_wrapper
  log "Comando instalado en $BIN_DIR; no requiere activar el venv."
}

unit_name() { printf 'ianest-edge-%s.service\n' "${VALUES[INSTANCE_NAME]}"; }

install_services() {
  [[ "${VALUES[SERVICE_INSTALL]}" == true ]] || return 0
  local unit
  mkdir -p "$SYSTEMD_DIR"
  unit="$(unit_name)"
  {
    cat <<EOF
[Unit]
Description=IA_NEST Edge (${VALUES[INSTANCE_NAME]})
Wants=network-online.target
After=network-online.target
StartLimitIntervalSec=0

[Service]
Type=simple
User=${VALUES[OPERATOR_USER]}
WorkingDirectory=${STATE_DIR}
Environment=IANEST_EDGE_CONFIG=${INSTALLED_CONFIG}
ExecStart=${VENV_DIR}/bin/ianest-edge serve
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
  } | write_atomic "${SYSTEMD_DIR}/${unit}" 644
  systemctl daemon-reload
  if [[ "${VALUES[SERVICE_ENABLE]}" == true ]]; then
    systemctl enable "$unit"
    systemctl restart "$unit"
  fi
}

probe_host() {
  case "$1" in
    0.0.0.0) printf '127.0.0.1\n' ;;
    ::|'[::]') printf '::1\n' ;;
    *) printf '%s\n' "$1" ;;
  esac
}

wait_for_port() {
  local host="$1" port="$2" attempt target
  target="$(probe_host "$host")"
  for ((attempt = 1; attempt <= 30; attempt++)); do
    if "$VENV_DIR/bin/python" - "$target" "$port" <<'PY' >/dev/null 2>&1
import socket
import sys

with socket.create_connection((sys.argv[1], int(sys.argv[2])), timeout=1):
    pass
PY
    then
      log "El borde escucha en $host:$port."
      return 0
    fi
    sleep 1
  done
  printf '[setup] ERROR: el borde no escucha en %s:%s tras 30 segundos\n' "$host" "$port" >&2
  return 1
}

verify_unauthenticated_models() {
  local host url protocol status
  host="$(probe_host "$EDGE_HOST")"
  [[ "$host" == *:* ]] && host="[$host]"
  protocol=http
  local -a curl_options=(--silent --show-error --output /dev/null --write-out '%{http_code}' --max-time 10)
  if [[ -n "$EDGE_TLS_CERT" ]]; then
    protocol=https
    # Solo esta sonda local omite verificar el certificado de TLS.
    curl_options+=(--insecure)
  fi
  url="${protocol}://${host}:${EDGE_PORT}/v1/models"
  status="$(curl "${curl_options[@]}" "$url")" || return 1
  [[ "$status" == 401 ]]
}

verify_runtime() {
  [[ "${VALUES[VERIFY]}" == skip ]] && { log "Verificacion final omitida por VERIFY=skip."; return; }
  local unit status=0
  unit="$(unit_name)"
  systemctl is-active --quiet "$unit" || status=1
  wait_for_port "$EDGE_HOST" "$EDGE_PORT" || status=1
  verify_unauthenticated_models || status=1
  if ((status == 0)); then
    log "Verificacion ejecutada con exito: servicio activo, puerto y /v1/models sin clave devuelve 401."
    return
  fi
  if [[ "${VALUES[VERIFY]}" == strict ]]; then
    error "verificacion estricta fallida: revisa servicio, puerto y autenticacion del borde"
  fi
  warning "verificacion no completada (VERIFY=warn)"
}

while (($# > 0)); do
  case "$1" in
    --config) (($# >= 2)) || error "--config requiere una ruta"; CONFIG_FILE="$2"; shift 2 ;;
    --print-config) PRINT_CONFIG=true; shift ;;
    --instance-name|--edge-config|--service-install|--service-enable|--verify|--operator-user|--replace-config)
      (($# >= 2)) || error "$1 requiere un valor"
      key="${1#--}"; key="${key//-/_}"; set_argument "${key^^}" "$2"; shift 2 ;;
    --help|-h) usage; exit 0 ;;
    *) error "argumento no reconocido: $1" ;;
  esac
done

if [[ -n "$CONFIG_FILE" ]]; then load_config_file "$CONFIG_FILE"; fi
apply_arguments
resolve_implicit_values
validate_config
if [[ "$PRINT_CONFIG" == true ]]; then print_config; exit 0; fi

check_dependencies
resolve_paths
select_effective_config
check_directory_files
prepare_directories
install_config
prepare_venv
chown -R "${VALUES[OPERATOR_USER]}" "$STATE_DIR"
install_commands
install_services
verify_runtime
log "setup completado: instancia ${VALUES[INSTANCE_NAME]}"
