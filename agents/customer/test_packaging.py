"""
Regression test for a real bug found in review: a non-editable pip install
(`pip install .`, what the Dockerfile actually does) copies personas.py
into site-packages, separate from personas.yaml which only lives in /app.
personas.py's default path resolution (Path(__file__).parent) then points
at the wrong place, and get_persona() raises FileNotFoundError -- but only
when run this way. An editable install (`pip install -e .`) or running
the script directly from this folder both mask the bug, since personas.py
and personas.yaml stay adjacent by accident in those cases.

This test simulates the real conditions that exposed the bug:
  1. A genuine, non-editable install into a throwaway virtualenv
  2. Run from a completely different working directory
  3. WITHOUT the PERSONAS_CONFIG_PATH env var set by default, first
     confirming the failure still reproduces if the fix were ever removed,
     then confirming it works correctly with the env var set (as the
     Dockerfile does)

Run directly:  python test_packaging.py
Requires: python3 -m venv + pip available on PATH. Takes ~10-20s (installs
a fresh virtualenv) -- this is a packaging smoke test, not a fast unit test,
so it's kept separate from test_workflow.py rather than run on every change.

Installs with --no-deps: only personas.py's own path-resolution logic is
under test here (stdlib + pyyaml), so there's no need to also pull in the
full nvidia-nat/nemoguardrails/langchain dependency tree declared in
pyproject.toml -- that would turn a ~10s check into several minutes for
no added coverage.
"""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

APP_DIR = Path(__file__).parent


def venv_bin_dir(venv_dir: Path) -> Path:
    return venv_dir / ("Scripts" if os.name == "nt" else "bin")


def venv_python(venv_dir: Path) -> Path:
    return venv_bin_dir(venv_dir) / ("python.exe" if os.name == "nt" else "python3")


def venv_pip(venv_dir: Path) -> Path:
    return venv_bin_dir(venv_dir) / ("pip.exe" if os.name == "nt" else "pip")


def run(cmd, **kwargs):
    return subprocess.run(cmd, capture_output=True, text=True, **kwargs)


def main():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        venv_dir = tmp / "venv"
        install_src = tmp / "src"

        # Copy source so we're not affected by any local __pycache__/egg-info
        shutil.copytree(APP_DIR, install_src, ignore=shutil.ignore_patterns(
            "__pycache__", "*.egg-info", "build", "*.db", "test_*.py"
        ))

        print("Creating throwaway virtualenv...")
        r = run([sys.executable, "-m", "venv", str(venv_dir)])
        assert r.returncode == 0, r.stderr

        pip = venv_pip(venv_dir)
        python = venv_python(venv_dir)

        print("Installing package (non-editable, matching the Dockerfile)...")
        r = run([str(pip), "install", "--quiet", "--no-deps", "."], cwd=install_src)
        assert r.returncode == 0, f"Install failed:\n{r.stderr}"
        # personas.py's own runtime need (not nvidia-nat/nemoguardrails/langchain,
        # which --no-deps above skips as irrelevant to this path-resolution bug).
        r = run([str(pip), "install", "--quiet", "pyyaml"])
        assert r.returncode == 0, f"Install of pyyaml failed:\n{r.stderr}"

        # --- Case 1: confirm the bug WOULD reproduce without the env var ---
        # (i.e. prove this test is actually testing something real, not a no-op)
        print("\n=== Case 1: no PERSONAS_CONFIG_PATH set (expect FileNotFoundError) ===")
        r = run(
            [str(python), "-c", "from personas import get_persona; get_persona('loyal_customer')"],
            cwd=tmp,  # deliberately NOT install_src, to avoid any accidental adjacency
        )
        if r.returncode == 0:
            print("UNEXPECTED: succeeded without the env var. Either the bug was "
                  "already fixed some other way, or this test isn't reproducing "
                  "real conditions anymore -- worth investigating either way.")
        else:
            assert "FileNotFoundError" in r.stderr, f"Expected FileNotFoundError, got:\n{r.stderr}"
            print("Confirmed: fails as expected without the fix in place.")

        # --- Case 2: confirm the fix (env var, as set in the Dockerfile) works ---
        print("\n=== Case 2: PERSONAS_CONFIG_PATH set, matching the Dockerfile ===")
        env = {"PERSONAS_CONFIG_PATH": str(install_src / "personas.yaml")}
        r = run(
            [str(python), "-c",
             "from personas import get_persona, all_persona_ids; "
             "print(all_persona_ids()); "
             "print(get_persona('loyal_customer')['display_name'])"],
            cwd=tmp,
            env={**os.environ, **env},
        )
        assert r.returncode == 0, f"Expected success with env var set, got:\n{r.stderr}"
        assert "loyal_customer" in r.stdout
        print(r.stdout.strip())
        print("Confirmed: works correctly with the fix in place.")

    print("\nAll packaging checks passed.")


if __name__ == "__main__":
    main()
