import glob
import os
import subprocess
import sys

seen_gir: set[str] = set()
gir_paths: list[str] = []

python_tag = f"python{sys.version_info.major}.{sys.version_info.minor}"
output_dir = f"/home/{os.environ.get('USER')}/.local/lib/{python_tag}/site-packages/gi"


def collect_gir_files(gir_dir: str) -> None:
    if not os.path.isdir(gir_dir):
        return
    for f in os.listdir(gir_dir):
        if f.endswith(".gir") and f not in seen_gir:
            seen_gir.add(f)
            gir_paths.append(f"{gir_dir}/{f}")


# Source 1: nativeBuildInputs (direct devshell packages)
for build_input in os.environ.get("nativeBuildInputs", "").split():
    collect_gir_files(f"{build_input}/share/gir-1.0")

# Source 2: GI_TYPELIB_PATH — every runtime library has a matching -dev package in
# the Nix store with GIR files. The runtime path is /nix/store/<hash>-<pkg>-<ver>
# and the dev package is /nix/store/<hash2>-<pkg>-<ver>-dev.
for typelib_dir in os.environ.get("GI_TYPELIB_PATH", "").split(":"):
    # Extract <pkg>-<ver> from /nix/store/<hash>-<pkg>-<ver>/lib/girepository-1.0
    parts = typelib_dir.split("/")
    if len(parts) >= 4 and parts[1] == "nix" and parts[2] == "store":
        pkg_with_hash = parts[3]  # <hash>-<pkg>-<ver>
        name_part = pkg_with_hash.split("-", 1)[1] if "-" in pkg_with_hash else ""
        if name_part:
            for dev_gir_dir in glob.glob(f"/nix/store/*-{name_part}-dev/share/gir-1.0"):
                collect_gir_files(dev_gir_dir)

if gir_paths and os.environ.get("USER"):
    subprocess.run(["gengir", "-o", output_dir] + gir_paths)
