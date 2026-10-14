#!/usr/bin/env bash
# Rebuild every tinygrad artifact the car runs for the tinygrad pin in tinygrad_repo/TINYGRAD_COMMIT (d3f09c9b, comma's pin
# since d05c2d971b). A model only runs correctly on the pin it was compiled for, so this runs on the comma, offroad, after
# a tinygrad bump: QCOM artifacts always, Chestnut artifacts when it is attached. Recipes are comma master's
# (selfdrive/modeld/SConscript at a47d1c56f6): QCOM via compile_onnx/compile_warp with comma's QCOM flags; Chestnut with the
# upstream recipe (compile_onnx.py's own OPENPILOT_HACKS/TC context, GMMU=0, --out-of-band --retargetable).
#
# usage: scripts/rebuild_tg_artifacts.sh [qcom] [chestnut] [big ID ONNX GEOM ...]
#   qcom      DM model + DM warps, default small model + small warps        -> selfdrive/modeld/models/
#   chestnut  default big warps (512x256)                                   -> selfdrive/modeld/models/
#   big ID ONNX GEOM   a local Chestnut model -> /data/models/ID_driving_tinygrad.pkl + its warps (GEOM: stock | g1b)
# Inputs default to ONNX already on the device: DM_ONNX, SMALL_ONNX. Logs to /data/tmp/rebuild_tg_artifacts.log.
set -uo pipefail
OP=/data/openpilot; MODELS=$OP/selfdrive/modeld/models; LOCAL=/data/models; TG=$OP/tinygrad_repo
DM_ONNX=${DM_ONNX:-$MODELS/dmonitoring_model.onnx}
SMALL_ONNX=${SMALL_ONNX:-$MODELS/driving_supercombo.onnx}
LOG=/data/tmp/rebuild_tg_artifacts.log; mkdir -p /data/tmp
QCOM_FLAGS='DEV=QCOM IMAGE=1 FLOAT16=1 NOLOCALS=1 JIT_BATCH_SIZE=0 OPENPILOT_HACKS=1'
CHESTNUT_FLAGS='GMMU=0 DEV=USB+AMD:LLVM'
cd $OP && set +u && source ./launch_env.sh >/dev/null 2>&1; set -u   # launch_env.sh reads unset vars
unset IMAGE NOLOCALS OPENPILOT_HACKS FLOAT16 TC_OPT TC_MIN_GLOBALS JIT_BATCH_SIZE BEAM CACHEDB DEV GMMU
export PYTHONPATH=$OP:$TG
log() { echo "== $* $(date +%H:%M:%S)" | tee -a $LOG; }
run() { log "$1"; shift; (cd $TG && env "$@") >> $LOG 2>&1 || { log "FAILED"; exit 1; }; }
frame() { python3 -c "from openpilot.system.camerad.cameras.nv12_info import get_nv12_info as g; w,h=$1,$2; s,y,u,_=g(w,h); print(f'{w},{h},{s},{y},{u},{s*(y+u)}')"; }
dmframe() { python3 -c "from openpilot.system.camerad.cameras.nv12_info import get_nv12_info as g; w,h=$1,$2; s,y,u,n=g(w,h); print(f'{w},{h},{s},{y},{u},{n}')"; }
CAMS="1344,760 1928,1208"
log "tinygrad $(cat $TG/TINYGRAD_COMMIT)"

while [ $# -gt 0 ]; do
  case $1 in
  qcom)
    shift
    run "DM model" $QCOM_FLAGS python3 examples/openpilot/compile_onnx.py $DM_ONNX $MODELS/dmonitoring_model_tinygrad.pkl --out-of-band --benchmark-runs 1
    run "small model" $QCOM_FLAGS python3 examples/openpilot/compile_onnx.py $SMALL_ONNX $MODELS/driving_tinygrad.pkl --out-of-band --benchmark-runs 1
    for c in $CAMS; do w=${c%,*}; h=${c#*,}
      run "small warp ${w}x$h" $QCOM_FLAGS python3 examples/openpilot/compile_warp.py --frame $(frame $w $h) --warp-to 512x256 \
        --layout yuv420 --frames 2 --output $MODELS/small_driving_warp_${w}x${h}_tinygrad.pkl
      run "DM warp ${w}x$h" $QCOM_FLAGS python3 examples/openpilot/compile_warp.py --frame $(dmframe $w $h) --warp-to 1440x960 \
        --layout luma --border-fill 16 --transform-device NPY --output $MODELS/dm_warp_${w}x${h}_tinygrad.pkl
    done
    # the single-file artifacts win over the old chunked ones; move those aside so nothing loads a stale pin
    for f in $MODELS/driving_tinygrad.pkl.chunk* $MODELS/driving_tinygrad.pkl.sha256; do [ -e "$f" ] && mv "$f" "$f.pre-d3f0"; done
    ;;
  chestnut)
    shift
    for c in $CAMS; do w=${c%,*}; h=${c#*,}
      run "big warp ${w}x$h" $CHESTNUT_FLAGS python3 examples/openpilot/compile_warp.py --frame $(frame $w $h) --warp-to 512x256 \
        --layout yuv420 --frames 2 --output $MODELS/big_driving_warp_${w}x${h}_tinygrad.pkl
    done
    ;;
  big)
    id=$2; onnx=$3; geom=$4; shift 4
    case $geom in stock) wt=512x256;; g1b) wt=768x448;; *) log "unknown geometry $geom"; exit 1;; esac
    run "$id model" $CHESTNUT_FLAGS python3 examples/openpilot/compile_onnx.py $onnx $LOCAL/${id}_driving_tinygrad.pkl.tmp --out-of-band --retargetable
    mv $LOCAL/${id}_driving_tinygrad.pkl.tmp $LOCAL/${id}_driving_tinygrad.pkl
    for c in $CAMS; do w=${c%,*}; h=${c#*,}
      run "$id warp ${w}x$h" $CHESTNUT_FLAGS python3 examples/openpilot/compile_warp.py --frame $(frame $w $h) --warp-to $wt \
        --layout yuv420 --frames 2 --output $LOCAL/${id}_warp_${w}x${h}_tinygrad.pkl
    done
    log "$id sha $(sha256sum $LOCAL/${id}_driving_tinygrad.pkl | cut -c1-16)"
    ;;
  *) log "unknown step $1"; exit 1;;
  esac
done
log "ALL DONE"
