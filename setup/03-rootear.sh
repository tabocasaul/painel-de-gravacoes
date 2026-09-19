#!/usr/bin/env bash
# 03 - Rooteia o AVD com Magisk (via rootAVD).
#
# Rode no GIT BASH, com o emulador JA LIGADO e o Minute instalado/logado:
#   bash 03-rootear.sh
#
# Ele baixa o rootAVD, injeta o Magisk no ramdisk da imagem e reinicia o emulador.

set -e
export MSYS_NO_PATHCONV=1
export MSYS2_ARG_CONV_EXCL='*'

# Caminho estilo Windows com barras normais. ISSO IMPORTA:
# o rootAVD monta o caminho do ramdisk e passa pro adb.exe, que e binario
# Windows e nao entende "/c/Users/...". Com o formato MSYS o push falha em
# silencio e o patch aborta com "Ramdisk.img uses UNKNOWN compression".
export ANDROID_SDK_ROOT="$(cygpath -m "$LOCALAPPDATA")/Android/Sdk"
export ANDROID_HOME="$ANDROID_SDK_ROOT"
export PATH="$ANDROID_SDK_ROOT/platform-tools:$ANDROID_SDK_ROOT/emulator:$PATH"

IMG="system-images/android-33/google_apis_playstore/x86_64"
DEST="$ANDROID_SDK_ROOT/_root"

echo "=== conferindo o emulador ==="
adb wait-for-device
adb shell getprop ro.build.version.sdk

if [ ! -d "$DEST/rootAVD" ]; then
    echo "=== baixando rootAVD ==="
    mkdir -p "$DEST"
    git clone --depth 1 https://github.com/newbit1/rootAVD.git "$DEST/rootAVD"
fi

echo "=== rodando o rootAVD (escolhe o Magisk local com ENTER) ==="
cd "$DEST/rootAVD"
yes "" | bash rootAVD.sh "$IMG/ramdisk.img"

cat <<'EOF'

=================================================================
O emulador vai desligar. Suba ele de novo:

    emulator -avd MinutePlay -no-snapshot -timezone America/Sao_Paulo -gpu auto

Depois, DENTRO do emulador:

  1. Abra o app Magisk. Ele pede "Requires Additional Setup" -> OK (reinicia).

  2. Reabra o Magisk -> aba Superuser.
     Vai aparecer "[SharedUID] Shell / com.android.shell" com o botao DESLIGADO.
     LIGUE ESSE BOTAO. Sem isso o `adb shell su` e recusado, mesmo com
     "Superuser Access = Apps and ADB" e "Automatic Response = Grant".
     (foi o que travou por bastante tempo aqui)

  3. Confira no Git Bash:
        adb shell "su -c id"
     Tem que responder: uid=0(root)

  4. Rode: bash 04-modulos.sh
=================================================================
EOF
