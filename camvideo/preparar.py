#!/usr/bin/env python3
"""
preparar - deixa um video pronto para entrar como camera do emulador.

Serve para a via NATIVA (`-camera-back videofile:...`), onde o emulador faz o
encaixe sozinho e sem controle nenhum. E o equivalente, para essa via, do que o
`recorte_para` do camvideo.py fazia dentro do OBS.

Por que precisa: o buffer de camera do emulador e 1280x720 DEITADO, e o
sensor.orientation e 90, entao o app ainda gira o quadro na hora de exibir. Um
video vertical 1080x1920 jogado ai perde ~68% da altura antes de chegar no app
(1080 / (16/9) = 607 px sobrevivem de 1920). Girando e completando com tarja
ANTES, nada se perde.

Uso:
    python preparar.py meu.mp4                      -> meu.pronto.mp4
    python preparar.py meu.mp4 saida.mp4

    --modo caber (padrao)  cabe inteiro, sobra tarja preta. NAO PERDE NADA.
    --modo cheio           preenche os 1280x720 cortando o excesso.
    --rot 90|180|270       gira. O padrao e NAO girar.
    --espelhar             espelha na horizontal.

O padrao (sem girar, modo caber) e o que resolve o caso comum: video maior que
o quadro da camera, que sem isso entra cortado. Video 16:9 encaixa exato e
enche a tela; outros formatos aparecem inteiros, com tarja preta em volta.

Use --rot 270 se quiser um video vertical em pe numa tela em pe.

Depois:
    emulator -avd MinutePlay -no-snapshot -camera-back "videofile:C:\\...\\saida.mp4" ...

ATENCAO ao caminho: passe o arquivo entre aspas como um token so. Caminho com
espaco quebra se o argumento for montado por partes.
"""

import os
import shutil
import subprocess
import sys

LARGURA = 1280   # teto do buffer de camera do emulador
ALTURA = 720


def achar_ffmpeg():
    """ffmpeg pelo PATH; se nao, onde o winget costuma deixar."""
    achado = shutil.which("ffmpeg")
    if achado:
        return achado

    raiz = os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Packages")
    if os.path.isdir(raiz):
        for pasta, _, arquivos in os.walk(raiz):
            if "ffmpeg.exe" in arquivos and os.path.basename(pasta) == "bin":
                return os.path.join(pasta, "ffmpeg.exe")
    return None


def filtro_giro(rot):
    """
    transpose do ffmpeg: 1 = 90 horario, 2 = 90 anti-horario.
    O 270 (padrao) e o que deixa video vertical em pe na traseira, porque o
    app ainda vai girar 90 pelo sensor.orientation.
    """
    return {0: [], 90: ["transpose=1"], 180: ["transpose=1", "transpose=1"],
            270: ["transpose=2"]}[rot]


def montar_filtro(rot, espelhar, modo):
    partes = filtro_giro(rot)
    if espelhar:
        partes.append("hflip")
    if modo == "cheio":
        partes += [f"scale={LARGURA}:{ALTURA}:force_original_aspect_ratio=increase",
                   f"crop={LARGURA}:{ALTURA}"]
    else:
        partes += [f"scale={LARGURA}:{ALTURA}:force_original_aspect_ratio=decrease",
                   f"pad={LARGURA}:{ALTURA}:(ow-iw)/2:(oh-ih)/2:black"]
    partes.append("setsar=1")
    return ",".join(partes)


def ler_args(argv):
    cfg = {"entrada": None, "saida": None, "rot": 0,
           "espelhar": False, "modo": "caber"}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--rot":
            i += 1
            try:
                cfg["rot"] = int(argv[i]) % 360
            except (IndexError, ValueError):
                sys.exit("--rot precisa de 0, 90, 180 ou 270")
            if cfg["rot"] not in (0, 90, 180, 270):
                sys.exit("--rot so aceita 0, 90, 180 ou 270")
        elif a == "--no-rot":
            cfg["rot"] = 0
        elif a == "--espelhar":
            cfg["espelhar"] = True
        elif a == "--modo":
            i += 1
            if i >= len(argv) or argv[i] not in ("caber", "cheio"):
                sys.exit("--modo aceita 'caber' ou 'cheio'")
            cfg["modo"] = argv[i]
        elif a.startswith("-"):
            sys.exit(f"opcao desconhecida: {a}")
        elif cfg["entrada"] is None:
            cfg["entrada"] = a
        elif cfg["saida"] is None:
            cfg["saida"] = a
        else:
            sys.exit(f"argumento sobrando: {a}")
        i += 1
    return cfg


def main(argv):
    if not argv:
        sys.exit(__doc__)
    cfg = ler_args(argv)
    if not cfg["entrada"]:
        sys.exit(__doc__)

    entrada = os.path.abspath(cfg["entrada"])
    if not os.path.isfile(entrada):
        sys.exit(f"arquivo nao encontrado: {entrada}")

    saida = cfg["saida"]
    if saida is None:
        base, ext = os.path.splitext(entrada)
        saida = f"{base}.pronto{ext or '.mp4'}"
    saida = os.path.abspath(saida)
    if os.path.normcase(saida) == os.path.normcase(entrada):
        sys.exit("a saida nao pode ser o mesmo arquivo da entrada")

    ffmpeg = achar_ffmpeg()
    if not ffmpeg:
        sys.exit("nao achei o ffmpeg. Rode o setup/01-ferramentas.ps1, "
                 "ou instale com: winget install Gyan.FFmpeg")

    vf = montar_filtro(cfg["rot"], cfg["espelhar"], cfg["modo"])
    print(f"ffmpeg : {ffmpeg}")
    print(f"entrada: {entrada}")
    print(f"filtro : {vf}")

    cmd = [ffmpeg, "-y", "-loglevel", "error", "-i", entrada,
           "-vf", vf, "-r", "30",
           "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast",
           "-an",                       # o emulador ignora audio da camera
           saida]
    r = subprocess.run(cmd)
    if r.returncode != 0 or not os.path.isfile(saida):
        sys.exit(f"ffmpeg falhou (codigo {r.returncode})")

    mb = os.path.getsize(saida) / (1024 * 1024)
    print(f"\npronto: {saida}  ({mb:.1f} MB, {LARGURA}x{ALTURA})")

    if " " in saida:
        print(f"""
  ATENCAO: esse caminho tem ESPACO, e o `videofile:` do emulador nao aceita.

  A falha e silenciosa e engana: o emulador sobe, o CameraService abre o
  dispositivo, e simplesmente nao chega frame nenhum -- o app fica travado
  esperando. Nao adianta por entre aspas; testado com o mesmo arquivo nos dois
  caminhos, so o sem espaco entrega imagem.

  Isso morde este projeto porque a pasta se chama "PROJETO EMULATION". Copie
  para um caminho sem espaco antes de usar, por exemplo:

      copy "{saida}" "%LOCALAPPDATA%\\Temp\\cam.mp4"

  (o camera/CAMERA.bat ja faz isso sozinho)""")
        return

    print("\nsubir o emulador com ele:")
    print(f'    emulator -avd MinutePlay -no-snapshot -camera-back '
          f'"videofile:{saida}" -camera-front emulated -gpu auto')


if __name__ == "__main__":
    main(sys.argv[1:])
