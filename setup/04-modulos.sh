#!/usr/bin/env bash
# 04 - Instala os modulos Magisk no emulador.
#
# Rode no GIT BASH com o emulador ligado e `adb shell "su -c id"` respondendo uid=0:
#   bash 04-modulos.sh
#
#   s22spoof  -> Build.MODEL = SM-S901B, passa a trava de modelo do Minute
#   uwcam     -> traseira vira multi-camera logica com fisica ultra-wide,
#                passa o "No ultra-wide physical camera available"
#   videocam  -> habilita o arquivo I420 lido pela Camera HAL customizada

set -e
export MSYS_NO_PATHCONV=1
export MSYS2_ARG_CONV_EXCL='*'

# cygpath -m: caminho estilo Windows com barras normais. MESMA armadilha do
# 03-rootear.sh -- o `pwd` do Git Bash devolve "/c/PROJETO EMULATION", e o
# adb.exe e binario Windows, que nao entende esse formato. Sem a conversao o
# push falha com "cannot stat '/c/...': No such file or directory".
BASE="$(cygpath -m "$(cd "$(dirname "$0")/.." && pwd)")"
TMP=/data/local/tmp/modulos

echo "=== conferindo root ==="
if ! adb shell "su -c id" 2>/dev/null | grep -q "uid=0"; then
    echo "ERRO: sem root."
    echo "Abra o Magisk > Superuser e ligue o botao de [SharedUID] Shell."
    exit 1
fi

echo "=== enviando arquivos ==="
adb shell "rm -rf $TMP; mkdir -p $TMP"
adb push "$BASE/magisk/s22spoof" "$TMP/" >/dev/null
adb push "$BASE/magisk/uwcam" "$TMP/" >/dev/null
adb push "$BASE/magisk/videocam" "$TMP/" >/dev/null

echo "=== instalando ==="
adb shell "su -c '
    rm -rf /data/adb/modules/s22spoof /data/adb/modules/uwcam /data/adb/modules/videocam
    cp -r $TMP/s22spoof /data/adb/modules/
    cp -r $TMP/uwcam /data/adb/modules/
    cp -r $TMP/videocam /data/adb/modules/
    chown -R 0:0 /data/adb/modules/s22spoof /data/adb/modules/uwcam
    chown -R 0:0 /data/adb/modules/videocam
    chmod -R 644 /data/adb/modules/uwcam/system/vendor/etc/config/*.json
    ls /data/adb/modules/
'"

adb shell "rm -rf $TMP"

echo
echo "Instalado. Reiniciando o emulador para os modulos valerem..."
adb reboot
adb wait-for-device

echo "aguardando o boot..."
until [ "$(adb shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" = "1" ]; do
    sleep 5
done
sleep 5

echo
echo "=== conferindo ==="
echo -n "modelo:   "; adb shell getprop ro.product.model
echo "cameras:"
adb shell "dumpsys media.camera 2>/dev/null | grep -E 'Facing|physicalIds'"
cat <<'EOF'

Esperado:
    modelo:  SM-S901B
    Facing: Back
      android.logicalMultiCamera.physicalIds ...   <- a ultra-wide

Se a traseira aparecer SEM physicalIds, confira que o emulador subiu com
-camera-back emulated. Fonte webcam ou videofile usa outro HAL e nao tem fisicas.
EOF
