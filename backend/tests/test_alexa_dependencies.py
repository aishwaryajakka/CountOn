"""Native import compatibility and pinned upstream OpenSSL parser regressions."""

import ast
import re
import subprocess
import sys
from importlib.metadata import distribution
from pathlib import Path

import pytest


@pytest.mark.parametrize("backend", ["default", "ctypes"])
def test_alexa_adapter_crypto_dependencies_load_in_fresh_process(backend):
    script = Path(__file__).resolve().parents[1] / "db/scripts/alexa_import_smoke.py"
    result = subprocess.run(
        [sys.executable, str(script), "--backend", backend],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert (
        "PASS Alexa adapter, certificate dependencies and native crypto"
        in result.stdout
    )


@pytest.mark.parametrize("filename", ["_libcrypto_cffi.py", "_libcrypto_ctypes.py"])
@pytest.mark.parametrize(
    "version", ["1.1.1w", "3.0.9", "3.0.10", "3.0.13", "3.0.20", "3.0.100", "3.5.7"]
)
def test_installed_libcrypto_parser_accepts_multidigit_patch(filename, version):
    # Inspect the actual installed parser without executing source or monkeypatching
    # re.search. This tests both code paths even on hosts using macOS Security.
    source = distribution("oscrypto").locate_file(f"oscrypto/_openssl/{filename}")
    tree = ast.parse(Path(source).read_text())
    patterns = [
        statement.value.args[0].value
        for statement in tree.body
        if isinstance(statement, ast.Assign)
        and any(
            isinstance(t, ast.Name) and t.id == "version_match"
            for t in statement.targets
        )
        and isinstance(statement.value, ast.Call)
        and isinstance(statement.value.args[0], ast.Constant)
    ]
    assert len(patterns) == 1
    match = re.search(patterns[0], f"OpenSSL {version} 30 Jan 2024")
    assert match is not None and match.group(1) == version
