#!/usr/bin/env bash
# Rebuild do app Lentes (sem Gradle: aapt2 -> javac -> d8 -> zipalign -> apksigner)
set -e
export MSYS_NO_PATHCONV=1
export MSYS2_ARG_CONV_EXCL='*'

# caminho do SDK sem nome de usuario fixo
SDK="$(cygpath -m "$LOCALAPPDATA")/Android/Sdk"
BT="$SDK/build-tools/37.0.0"
AJ="$SDK/platforms/android-34/android.jar"
cd "$(dirname "$0")"

rm -rf build/classes build/dex
mkdir -p build/classes build/dex

"$BT/aapt2.exe" link -o build/res.apk --manifest AndroidManifest.xml -I "$AJ" \
    --min-sdk-version 28 --target-sdk-version 33
javac --release 17 -nowarn -classpath "$AJ" -d build/classes $(find src -name '*.java')
"$BT/d8.bat" --min-api 28 --lib "$AJ" --output build/dex $(find build/classes -name '*.class')

python -c "
import zipfile, shutil
shutil.copy('build/res.apk','build/unsigned.apk')
with zipfile.ZipFile('build/unsigned.apk','a',zipfile.ZIP_DEFLATED) as z:
    z.write('build/dex/classes.dex','classes.dex')
"

[ -f build/debug.keystore ] || keytool -genkeypair -keystore build/debug.keystore \
    -storepass android -keypass android -alias lentes -keyalg RSA -keysize 2048 \
    -validity 10000 -dname "CN=Lentes, OU=local, O=local, L=SP, S=SP, C=BR"

"$BT/zipalign.exe" -f -p 4 build/unsigned.apk build/aligned.apk
rm -f lentes.apk
"$BT/apksigner.bat" sign --ks build/debug.keystore --ks-pass pass:android \
    --key-pass pass:android --out lentes.apk build/aligned.apk 2>/dev/null

echo "OK -> lentes.apk"
echo "instalar: adb install -r lentes.apk"
