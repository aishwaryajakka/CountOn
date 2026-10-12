"""Read-only Gitleaks scans; report filenames/rules only, never secret values.

Requires Docker. Copies only git history and non-ignored source into a temporary
container; no host bind mounts, .env files, credentials, or Docker socket mounts.
"""

import argparse
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

IMAGE = "ghcr.io/gitleaks/gitleaks:v8.30.1@sha256:c00b6bd0aeb3071cbcb79009cb16a60dd9e0a7c60e2be9ab65d25e6bc8abbb7f"
ROOT = Path(__file__).resolve().parents[1]


def run(*args):
    result = subprocess.run(
        args, cwd=ROOT, capture_output=True, timeout=180, check=False
    )
    if result.returncode:
        raise RuntimeError("Scanner infrastructure unavailable")
    return result.stdout.decode().strip()


def scan(kind):
    container = None
    with tempfile.TemporaryDirectory(prefix="counton-secrets-") as directory:
        root = Path(directory)
        source = root / "repo"
        source.mkdir()
        if kind == "git":
            # Git config may contain a runner's checkout credential. Hooks and
            # configuration are not history and must never enter the container.
            def ignored(directory, names):
                return {
                    name
                    for name in names
                    if Path(directory) == ROOT / ".git" and name in ("config", "hooks")
                }

            shutil.copytree(ROOT / ".git", source / ".git", ignore=ignored)
            (source / ".git" / "config").write_text(
                "[core]\nrepositoryformatversion = 0\nbare = false\n"
            )
            shutil.copyfile(ROOT / ".gitleaks.toml", source / ".gitleaks.toml")
        else:
            paths = run(
                "git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"
            ).split("\x00")
            for path in paths:
                original = ROOT / path
                if not path or not original.is_file() or original.is_symlink():
                    continue
                # Even if accidentally tracked, env files must never enter this scan container.
                # History catches tracked env secrets. Scan source env templates only.
                if original.name.startswith(".env") and not original.name.endswith(
                    (".example", ".sample")
                ):
                    print("FAIL tracked environment file:", path)
                    return 1
                target = source / path
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(original, target)
        try:
            options = ["--log-opts=--all"] if kind == "git" else []
            container = run(
                "docker",
                "create",
                "--network",
                "none",
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges",
                IMAGE,
                kind,
                "/repo",
                "--config",
                "/repo/.gitleaks.toml",
                "--redact",
                "--log-level",
                "error",
                "--report-format",
                "json",
                "--report-path",
                "/tmp/report.json",
                *options,
            )
            run("docker", "cp", str(source) + "/.", container + ":/repo")
            # All scanner output stays captured; only redacted structured findings are examined.
            subprocess.run(
                ["docker", "start", "--attach", container],
                capture_output=True,
                timeout=180,
                check=False,
            )
            code = int(
                run("docker", "inspect", "--format", "{{.State.ExitCode}}", container)
            )
            if code not in (0, 1):
                raise RuntimeError("Scanner infrastructure unavailable")
            run(
                "docker",
                "cp",
                container + ":/tmp/report.json",
                str(root / "report.json"),
            )
            findings = json.loads((root / "report.json").read_text()) or []
            if code != 0 and not findings:
                raise RuntimeError("Scanner did not complete successfully")
            for item in findings:
                print(
                    "FAIL",
                    kind,
                    item["File"],
                    "line",
                    item["StartLine"],
                    item["RuleID"],
                )
            print(
                ("PASS" if not findings else "FAIL"),
                kind,
                "secret scan:",
                len(findings),
                "findings",
            )
            return int(bool(findings))
        finally:
            if container:
                subprocess.run(
                    ["docker", "rm", "-f", container],
                    capture_output=True,
                    timeout=30,
                    check=False,
                )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history-only", action="store_true")
    args = parser.parse_args()
    try:
        codes = [scan("git")]
        if not args.history_only:
            codes.append(scan("dir"))
        return max(codes)
    except (
        OSError,
        RuntimeError,
        ValueError,
        TypeError,
        KeyError,
        subprocess.TimeoutExpired,
    ):
        print("BLOCKED secret scanner infrastructure unavailable; no secrets printed")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
