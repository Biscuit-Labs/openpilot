#!/usr/bin/env bash
# Run pytest for this checkout inside the larch64 builder container, against the committed device artifacts.
# usage: tools/night_star_port/docker_pytest.sh -q <tests...>
#
# One-time setup, from this checkout (builds .venv-linux-arm64 from 7.0's uv.lock; both dirs are gitignored):
#   mkdir -p .venv-linux-arm64 .cache/uv
#   docker run --rm --platform linux/arm64 --user "$(id -u):$(id -g)" -v "$PWD:/work" -w /work starpilot-larch64-builder:latest \
#     bash -c 'export HOME=/tmp UV_CACHE_DIR=/work/.cache/uv UV_PYTHON_INSTALL_DIR=/work/.cache/uv-python;
#              UV_PROJECT_ENVIRONMENT=/work/.venv-linux-arm64 uv sync --frozen --all-extras'
# UV_PYTHON_INSTALL_DIR matters: without it uv puts the interpreter under HOME=/tmp and the venv dies with the container.
# --init: pytest must not be PID 1 (the FLM analysis worker refuses a parent PID <= 1).
W="$(cd "$(dirname "$0")/../.." && pwd)"
M="${PORT_MAIN_REPO:-$HOME/nrdr/openpilot}"  # supplies the larch64 sysroot (.comma_sysroot)
docker run --rm --init --platform linux/arm64 --user "$(id -u):$(id -g)" -v "$W:/work" \
  -v "$M/.comma_sysroot:/opt/tici-sysroot:ro" -v "$M/.comma_sysroot/system/vendor/lib64:/system/vendor/lib64:ro" \
  -w /work "${COMMA_BUILD_IMAGE:-starpilot-larch64-builder:latest}" bash -c '
export SP_FORCE_TICI=1 SP_FORCE_ARCH=larch64 HOME=/tmp PARAMS_ROOT=/tmp/params
export LD_LIBRARY_PATH=/usr/local/lib:/usr/lib/aarch64-linux-gnu:/opt/tici-sysroot/usr/local/lib:/opt/tici-sysroot/usr/lib/aarch64-linux-gnu:/system/vendor/lib64
mkdir -p /tmp/params; source /work/.venv-linux-arm64/bin/activate
python -m pytest -p no:cacheprovider -o addopts="" -n0 "$@"' _ "$@"
