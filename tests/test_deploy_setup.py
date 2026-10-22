from __future__ import annotations

import os
import pwd
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SETUP = ROOT / "deploy" / "setup.sh"
EXAMPLE = ROOT / "deploy" / "ejemplo.setup.conf"


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="ascii")
    path.chmod(0o755)


def _edge_config(path: Path, *, port: int = 8080) -> None:
    path.write_text(
        "server:\n"
        '  host: "127.0.0.1"\n'
        f"  port: {port}\n"
        "extended:\n"
        '  base_url: "http://127.0.0.1:8001"\n'
        "audit:\n"
        f'  path: "{path.parent / "edge.jsonl"}"\n'
        "guest:\n"
        '  user_id: "guest"\n'
        "  menu:\n"
        '    - id: "conversation"\n'
        '      mode: "directo"\n'
        '      domain: "auto"\n'
        "      default: true\n"
        "consumers:\n"
        "  chat:\n"
        '    key_sha256: "0000000000000000000000000000000000000000000000000000000000000000"\n'
        "    can_assert_people: false\n"
        "    default_identity:\n"
        '      user_id: "shared"\n'
        '      profile: "adult"\n'
        "      menu:\n"
        '        - id: "conversation"\n'
        '          mode: "directo"\n'
        '          domain: "auto"\n'
        "          default: true\n",
        encoding="ascii",
    )


def _deployment(tmp_path: Path):
    install_root = tmp_path / "opt" / "ia_nest"
    bin_dir = tmp_path / "bin"
    systemd_dir = tmp_path / "systemd"
    fake_path = tmp_path / "fake-path"
    edge_config = tmp_path / "edge.yaml"
    setup_config = tmp_path / "setup.conf"
    log_path = tmp_path / "calls.log"
    operator_user = pwd.getpwuid(os.getuid()).pw_name
    _edge_config(edge_config)
    bin_dir.mkdir()
    systemd_dir.mkdir()
    fake_path.mkdir()
    setup_config.write_text(
        "\n".join(
            (
                "INSTANCE_NAME=test",
                f"EDGE_CONFIG={edge_config}",
                "SERVICE_INSTALL=false",
                "SERVICE_ENABLE=false",
                "VERIFY=skip",
                f"OPERATOR_USER={operator_user}",
                "REPLACE_CONFIG=false",
            )
        )
        + "\n",
        encoding="ascii",
    )
    _write_executable(
        fake_path / "curl",
        "#!/usr/bin/env bash\nprintf 'curl:%s\\n' \"$*\" >> \"$FAKE_CALL_LOG\"\nexit 0\n",
    )
    _write_executable(
        fake_path / "systemctl",
        "#!/usr/bin/env bash\nprintf 'systemctl:%s\\n' \"$*\" >> \"$FAKE_CALL_LOG\"\nexit 0\n",
    )
    env = {
        **os.environ,
        "PATH": f"{fake_path}:{os.environ['PATH']}",
        "IANEST_INSTALL_ROOT": str(install_root),
        "IANEST_BIN_DIR": str(bin_dir),
        "IANEST_SYSTEMD_DIR": str(systemd_dir),
        "FAKE_CALL_LOG": str(log_path),
    }
    return setup_config, edge_config, env, install_root, bin_dir, systemd_dir, log_path


def _prepare_venv(install_root: Path) -> None:
    venv_bin = install_root / "state" / "edge" / "test" / "venv" / "bin"
    venv_bin.mkdir(parents=True)
    _write_executable(
        venv_bin / "python",
        "#!/usr/bin/env bash\n"
        "if [[ ${1:-} == -m && ${2:-} == pip ]]; then exit 0; fi\n"
        f'exec "{sys.executable}" "$@"\n',
    )
    _write_executable(venv_bin / "ianest-edge", "#!/usr/bin/env bash\nexit 0\n")


def _run_setup(config: Path, env: dict[str, str], *arguments: str):
    return subprocess.run(
        [str(SETUP), "--config", str(config), *arguments],
        env=env,
        capture_output=True,
        text=True,
    )


def test_setup_is_valid_bash_and_example_prints_effective_values():
    syntax = subprocess.run(["bash", "-n", str(SETUP)], capture_output=True, text=True)
    assert syntax.returncode == 0, syntax.stderr

    printed = subprocess.run(
        [str(SETUP), "--config", str(EXAMPLE), "--print-config"],
        capture_output=True,
        text=True,
    )

    assert printed.returncode == 0, printed.stderr
    assert "INSTANCE_NAME=edge (file)" in printed.stdout
    assert "EDGE_CONFIG=/ruta/a/edge.yaml (file)" in printed.stdout
    assert "VERIFY=strict (file)" in printed.stdout


def test_arguments_take_precedence_over_setup_file(tmp_path):
    config, _, env, _, _, _, _ = _deployment(tmp_path)

    result = _run_setup(
        config,
        env,
        "--instance-name",
        "from-argument",
        "--print-config",
    )

    assert result.returncode == 0, result.stderr
    assert "INSTANCE_NAME=from-argument (argument)" in result.stdout


def test_missing_or_invalid_edge_config_fails_before_writing(tmp_path):
    config, edge_config, env, install_root, _, _, _ = _deployment(tmp_path)
    config.write_text(
        config.read_text(encoding="ascii").replace(f"EDGE_CONFIG={edge_config}\n", ""),
        encoding="ascii",
    )

    missing = _run_setup(config, env)

    assert missing.returncode != 0
    assert "EDGE_CONFIG es obligatoria" in missing.stderr
    assert not install_root.exists()

    config.write_text(
        config.read_text(encoding="ascii") + f"EDGE_CONFIG={edge_config}\n",
        encoding="ascii",
    )
    edge_config.write_text("server: [\n", encoding="ascii")
    invalid = _run_setup(config, env)

    assert invalid.returncode != 0
    assert "EDGE_CONFIG no es valida" in invalid.stderr
    assert not install_root.exists()


def test_missing_system_pyyaml_fails_before_writing(tmp_path):
    config, _, env, install_root, _, _, _ = _deployment(tmp_path)
    fake_path = Path(env["PATH"].split(":", 1)[0])
    _write_executable(
        fake_path / "python3.13",
        "#!/usr/bin/env bash\n"
        "if [[ ${1:-} == -c && ${2:-} == 'import yaml' ]]; then exit 1; fi\n"
        "exit 0\n",
    )

    result = _run_setup(config, env)

    assert result.returncode != 0
    assert "falta PyYAML" in result.stderr
    assert "python313-PyYAML" in result.stderr
    assert "python3-yaml" in result.stderr
    assert not install_root.exists()


def test_existing_configuration_is_preserved_and_replace_substitutes_it(tmp_path):
    config, edge_config, env, install_root, _, _, _ = _deployment(tmp_path)
    _prepare_venv(install_root)

    first = _run_setup(config, env)
    _edge_config(edge_config, port=8099)
    second = _run_setup(config, env)
    installed = install_root / "config" / "edge" / "test" / "edge.yaml"
    preserved = installed.read_text(encoding="ascii")
    replaced = _run_setup(config, env, "--replace-config", "true")

    assert first.returncode == second.returncode == replaced.returncode == 0
    assert "se preserva" in second.stdout
    assert "port: 8080" in preserved
    assert "port: 8099" in installed.read_text(encoding="ascii")


def test_installed_configuration_has_mode_640(tmp_path):
    config, _, env, install_root, _, _, _ = _deployment(tmp_path)
    _prepare_venv(install_root)

    result = _run_setup(config, env)

    installed = install_root / "config" / "edge" / "test" / "edge.yaml"
    assert result.returncode == 0, result.stderr
    assert installed.stat().st_mode & 0o777 == 0o640
    assert installed.stat().st_uid == os.getuid()


def test_unit_has_operator_config_and_serve_command(tmp_path):
    config, _, env, install_root, _, systemd_dir, _ = _deployment(tmp_path)
    _prepare_venv(install_root)
    config.write_text(
        config.read_text(encoding="ascii")
        .replace("SERVICE_INSTALL=false", "SERVICE_INSTALL=true"),
        encoding="ascii",
    )

    result = _run_setup(config, env)

    unit = (systemd_dir / "ianest-edge-test.service").read_text(encoding="ascii")
    operator_user = pwd.getpwuid(os.getuid()).pw_name
    installed = install_root / "config" / "edge" / "test" / "edge.yaml"
    venv = install_root / "state" / "edge" / "test" / "venv"
    assert result.returncode == 0, result.stderr
    assert f"User={operator_user}" in unit
    assert f"Environment=IANEST_EDGE_CONFIG={installed}" in unit
    assert f"ExecStart={venv}/bin/ianest-edge serve" in unit
    assert "StartLimitIntervalSec=0" in unit
    assert "Restart=on-failure" in unit
    assert "RestartSec=5" in unit


def test_service_install_false_does_not_generate_unit(tmp_path):
    config, _, env, install_root, _, systemd_dir, _ = _deployment(tmp_path)
    _prepare_venv(install_root)

    result = _run_setup(config, env)

    assert result.returncode == 0, result.stderr
    assert not (systemd_dir / "ianest-edge-test.service").exists()


def test_verify_skip_does_not_probe(tmp_path):
    config, _, env, install_root, _, _, log_path = _deployment(tmp_path)
    _prepare_venv(install_root)

    result = _run_setup(config, env)

    assert result.returncode == 0, result.stderr
    assert not log_path.exists() or "curl:" not in log_path.read_text(encoding="ascii")


def test_strict_verification_fails_when_the_port_does_not_listen(tmp_path):
    config, _, env, install_root, _, _, _ = _deployment(tmp_path)
    _prepare_venv(install_root)
    config.write_text(
        config.read_text(encoding="ascii")
        .replace("SERVICE_INSTALL=false", "SERVICE_INSTALL=true")
        .replace("SERVICE_ENABLE=false", "SERVICE_ENABLE=true")
        .replace("VERIFY=skip", "VERIFY=strict"),
        encoding="ascii",
    )
    fake_path = Path(env["PATH"].split(":", 1)[0])
    _write_executable(fake_path / "sleep", "#!/usr/bin/env bash\nexit 0\n")

    result = _run_setup(config, env)

    assert result.returncode != 0
    assert "verificacion estricta fallida" in result.stderr


def test_strict_tls_probe_uses_https_and_expects_401(tmp_path):
    config, edge_config, env, install_root, _, _, log_path = _deployment(tmp_path)
    certificate = tmp_path / "edge-cert.pem"
    key = tmp_path / "edge-key.pem"
    certificate.touch()
    key.touch()
    edge_config.write_text(
        edge_config.read_text(encoding="ascii").replace(
            "  port: 8080\n",
            "  port: 8080\n"
            "  tls:\n"
            f'    certfile: "{certificate}"\n'
            f'    keyfile: "{key}"\n',
        ),
        encoding="ascii",
    )
    _prepare_venv(install_root)
    venv_python = install_root / "state" / "edge" / "test" / "venv" / "bin" / "python"
    _write_executable(
        venv_python,
        "#!/usr/bin/env bash\n"
        "if [[ ${1:-} == -m && ${2:-} == pip ]]; then exit 0; fi\n"
        "if [[ ${1:-} == - ]]; then exit 0; fi\n"
        f'exec "{sys.executable}" "$@"\n',
    )
    config.write_text(
        config.read_text(encoding="ascii")
        .replace("SERVICE_INSTALL=false", "SERVICE_INSTALL=true")
        .replace("SERVICE_ENABLE=false", "SERVICE_ENABLE=true")
        .replace("VERIFY=skip", "VERIFY=strict"),
        encoding="ascii",
    )
    fake_path = Path(env["PATH"].split(":", 1)[0])
    _write_executable(
        fake_path / "curl",
        "#!/usr/bin/env bash\nprintf 'curl:%s\\n' \"$*\" >> \"$FAKE_CALL_LOG\"\nprintf '401'\n",
    )

    result = _run_setup(config, env)

    calls = log_path.read_text(encoding="ascii")
    assert result.returncode == 0, result.stderr
    assert "--insecure" in calls
    assert "https://127.0.0.1:8080/v1/models" in calls
