#!/usr/bin/env python3
"""
montar - compoe uma cena e entrega pronta para a camera do emulador.

Substitui, para a via nativa, o que o OBS fazia: juntar um fundo com coisas por
cima. A diferenca e que aqui a composicao vira um ARQUIVO, e o emulador toca
esse arquivo como camera (`-camera-back videofile:...`). Nao e ao vivo -- a
ponte ao vivo do OBS para o emulador deixou de existir (ver secao 4 do README).

Saida sempre 1280x720, que e o teto do buffer de camera do emulador, num
caminho SEM espaco -- o `videofile:` falha calado com espaco no caminho.

Uso:
    python montar.py --fundo videos/base.mp4
    python montar.py --fundo videos/base.mp4 --sobre logo.png
    python montar.py --fundo foto.jpg --dur 60
    python montar.py --fundo base.mp4 --sobre pip.mp4 --canto cima-esquerda --escala 0.4
    python montar.py --fundo base.mp4 --texto "AO VIVO" --texto-pos cima
    python montar.py --cor black --texto "teste" --dur 30

Opcoes:
    --fundo ARQ      video ou imagem de fundo
    --cor COR        fundo de cor solida em vez de arquivo (ex: black, red)
    --dur N          duracao em segundos (obrigatorio se o fundo e imagem/cor)
    --sobre ARQ      imagem ou video por cima
    --escala F       tamanho do sobreposto, fracao da largura (padrao 0.3)
    --canto POS      cima-esquerda | cima-direita | baixo-esquerda |
                     baixo-direita (padrao) | centro
    --texto TXT      escreve um texto por cima
    --texto-pos POS  cima | centro | baixo (padrao cima)
    --ajuste MODO    caber (padrao, nao corta nada) | cheio (corta pra preencher)
    -o ARQ           saida (padrao: <fundo>.montado.mp4)
    --instalar       ja copia a saida para a area que o CAMERA.bat usa
"""

import os
import shutil
import subprocess
import sys

LARGURA = 1280
ALTURA = 720
AREA = os.path.expandvars(r"%LOCALAPPDATA%\emulation-cam")
IMAGENS = {".png", ".jpg", ".jpeg", ".bmp", ".webp", ".gif"}

CANTOS = {
    "cima-esquerda":  ("{m}", "{m}"),
    "cima-direita":   ("W-w-{m}", "{m}"),
    "baixo-esquerda": ("{m}", "H-h-{m}"),
    "baixo-direita":  ("W-w-{m}", "H-h-{m}"),
    "centro":         ("(W-w)/2", "(H-h)/2"),
}

TEXTO_Y = {"cima": "h*0.06", "centro": "(h-text_h)/2", "baixo": "h*0.88"}


def achar(nome):
    """ffmpeg/ffprobe pelo PATH; se nao, onde o winget deixa."""
    achado = shutil.which(nome)
    if achado:
        return achado
    raiz = os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Packages")
    if os.path.isdir(raiz):
        alvo = nome + ".exe"
        for pasta, _, arquivos in os.walk(raiz):
            if alvo in arquivos and os.path.basename(pasta) == "bin":
                return os.path.join(pasta, alvo)
    return None


def eh_imagem(caminho):
    return os.path.splitext(caminho)[1].lower() in IMAGENS


def ler_args(argv):
    cfg = {"fundo": None, "cor": None, "dur": None, "sobre": None,
           "escala": 0.3, "canto": "baixo-direita", "texto": None,
           "texto_pos": "cima", "ajuste": "caber", "saida": None,
           "instalar": False, "progresso": False}
    pares = {"--fundo": "fundo", "--cor": "cor", "--sobre": "sobre",
             "--canto": "canto", "--texto": "texto", "--texto-pos": "texto_pos",
             "--ajuste": "ajuste", "-o": "saida"}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in pares:
            i += 1
            if i >= len(argv):
                sys.exit(f"{a} precisa de um valor")
            cfg[pares[a]] = argv[i]
        elif a == "--dur":
            i += 1
            try:
                cfg["dur"] = float(argv[i])
            except (IndexError, ValueError):
                sys.exit("--dur precisa de um numero de segundos")
        elif a == "--escala":
            i += 1
            try:
                cfg["escala"] = float(argv[i])
            except (IndexError, ValueError):
                sys.exit("--escala precisa de um numero (ex: 0.3)")
            if not 0.05 <= cfg["escala"] <= 1.0:
                sys.exit("--escala tem que ficar entre 0.05 e 1.0")
        elif a == "--instalar":
            cfg["instalar"] = True
        elif a == "--progresso":
            cfg["progresso"] = True
        else:
            sys.exit(f"opcao desconhecida: {a}")
        i += 1

    if cfg["canto"] not in CANTOS:
        sys.exit("--canto aceita: " + ", ".join(CANTOS))
    if cfg["texto_pos"] not in TEXTO_Y:
        sys.exit("--texto-pos aceita: cima, centro, baixo")
    if cfg["ajuste"] not in ("caber", "cheio"):
        sys.exit("--ajuste aceita 'caber' ou 'cheio'")
    if not cfg["fundo"] and not cfg["cor"]:
        sys.exit("preciso de --fundo ARQUIVO ou --cor COR")
    if cfg["fundo"] and cfg["cor"]:
        sys.exit("use --fundo ou --cor, nao os dois")
    return cfg


def encaixe(ajuste):
    if ajuste == "cheio":
        return (f"scale={LARGURA}:{ALTURA}:force_original_aspect_ratio=increase,"
                f"crop={LARGURA}:{ALTURA}")
    return (f"scale={LARGURA}:{ALTURA}:force_original_aspect_ratio=decrease,"
            f"pad={LARGURA}:{ALTURA}:(ow-iw)/2:(oh-ih)/2:black")


def duracao(caminho):
    """Segundos do arquivo, via ffprobe. None se nao der para saber."""
    ffprobe = achar("ffprobe")
    if not ffprobe:
        return None
    try:
        r = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", caminho],
            capture_output=True, text=True, timeout=30)
        return float(r.stdout.strip())
    except (ValueError, OSError, subprocess.SubprocessError):
        return None


def rodar_com_progresso(cmd, total):
    """
    Roda o ffmpeg imprimindo "PROGRESSO:<0-100>" a cada avanco, para quem
    chamou (o painel) poder mostrar uma barra de verdade.

    `-progress pipe:1` faz o ffmpeg cuspir pares chave=valor legiveis; o que
    interessa e out_time_us (ou out_time_ms nas versoes antigas), que e quanto
    do video ja foi codificado.
    """
    cmd = cmd[:1] + ["-progress", "pipe:1", "-nostats"] + cmd[1:]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         text=True, bufsize=1)
    ultimo = -1
    for linha in p.stdout:
        linha = linha.strip()
        us = None
        if linha.startswith("out_time_us="):
            us = linha.split("=", 1)[1]
        elif linha.startswith("out_time_ms="):      # ffmpeg antigo: ja e us
            us = linha.split("=", 1)[1]
        if us and total:
            try:
                pct = min(100, int(float(us) / 1_000_000 / total * 100))
            except ValueError:
                continue
            if pct != ultimo:
                ultimo = pct
                print(f"PROGRESSO:{pct}", flush=True)
    p.wait()
    return p.returncode


def escapar(texto):
    """drawtext trata : ' \\ % como sintaxe."""
    for de, para in (("\\", r"\\"), (":", r"\:"), ("'", r"\'"), ("%", r"\%")):
        texto = texto.replace(de, para)
    return texto


def fonte():
    """
    ARMADILHA: no Windows o drawtext SEM fontfile nao acha fonte e o ffmpeg
    morre com violacao de acesso (0xC0000005) -- sem mensagem, so o codigo de
    saida 3221225477. Por isso apontamos o arquivo na mao.
    O caminho vai no filtro com os dois-pontos escapados: C\\:/Windows/...
    """
    candidatas = ["arial.ttf", "segoeui.ttf", "tahoma.ttf", "verdana.ttf"]
    raiz = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
    for nome in candidatas:
        caminho = os.path.join(raiz, nome)
        if os.path.isfile(caminho):
            return caminho.replace("\\", "/").replace(":", r"\:")
    return None


def main(argv):
    if not argv:
        sys.exit(__doc__)
    cfg = ler_args(argv)

    ffmpeg = achar("ffmpeg")
    if not ffmpeg:
        sys.exit("nao achei o ffmpeg. Rode setup/01-ferramentas.ps1, "
                 "ou: winget install Gyan.FFmpeg")

    entradas = []
    estatico = cfg["cor"] is not None or (cfg["fundo"] and eh_imagem(cfg["fundo"]))
    if estatico and not cfg["dur"]:
        sys.exit("fundo parado (imagem ou cor) precisa de --dur SEGUNDOS")

    if cfg["cor"]:
        entradas += ["-f", "lavfi", "-t", str(cfg["dur"]),
                     "-i", f"color=c={cfg['cor']}:s={LARGURA}x{ALTURA}:r=30"]
    else:
        fundo = os.path.abspath(cfg["fundo"])
        if not os.path.isfile(fundo):
            sys.exit(f"fundo nao encontrado: {fundo}")
        if eh_imagem(fundo):
            entradas += ["-loop", "1", "-t", str(cfg["dur"]), "-i", fundo]
        else:
            entradas += ["-i", fundo]
            if cfg["dur"]:
                entradas = ["-t", str(cfg["dur"])] + entradas

    tem_sobre = bool(cfg["sobre"])
    if tem_sobre:
        sobre = os.path.abspath(cfg["sobre"])
        if not os.path.isfile(sobre):
            sys.exit(f"sobreposto nao encontrado: {sobre}")
        if eh_imagem(sobre):
            entradas += ["-loop", "1", "-i", sobre]
        else:
            entradas += ["-stream_loop", "-1", "-i", sobre]

    # --- filtro ---
    partes = [f"[0:v]{encaixe(cfg['ajuste'])},setsar=1[base]"]
    ultimo = "base"

    if tem_sobre:
        larg = max(2, int(LARGURA * cfg["escala"]) // 2 * 2)
        partes.append(f"[1:v]scale={larg}:-2[pip]")
        margem = int(LARGURA * 0.03)
        x, y = CANTOS[cfg["canto"]]
        # shortest=1 e OBRIGATORIO: o sobreposto entra em loop infinito
        # (-stream_loop -1 para video, -loop 1 para imagem). Com shortest=0 a
        # saida nunca termina e o ffmpeg fica gravando para sempre.
        partes.append(f"[{ultimo}][pip]overlay={x.format(m=margem)}:"
                      f"{y.format(m=margem)}:shortest=1[comp]")
        ultimo = "comp"

    if cfg["texto"]:
        f = fonte()
        if not f:
            sys.exit("nao achei nenhuma fonte em %WINDIR%\\Fonts para o --texto")
        partes.append(
            f"[{ultimo}]drawtext=fontfile='{f}':text='{escapar(cfg['texto'])}'"
            f":fontcolor=white:fontsize=48:borderw=3:bordercolor=black@0.8"
            f":x=(w-text_w)/2:y={TEXTO_Y[cfg['texto_pos']]}[txt]")
        ultimo = "txt"

    saida = cfg["saida"]
    if not saida:
        base = os.path.splitext(os.path.abspath(cfg["fundo"]))[0] if cfg["fundo"] \
               else os.path.join(os.getcwd(), "cena")
        saida = base + ".montado.mp4"
    saida = os.path.abspath(saida)

    cmd = [ffmpeg, "-y", "-loglevel", "error"] + entradas + [
        "-filter_complex", ";".join(partes), "-map", f"[{ultimo}]",
        "-r", "30", "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-preset", "veryfast", "-an", saida]

    print("ffmpeg :", ffmpeg)
    print("filtro :", ";".join(partes))

    if cfg["progresso"]:
        total = cfg["dur"]
        if total is None and cfg["fundo"]:
            total = duracao(os.path.abspath(cfg["fundo"]))
        print(f"TOTAL:{total or 0}", flush=True)
        codigo = rodar_com_progresso(cmd, total)
    else:
        codigo = subprocess.run(cmd).returncode

    if codigo != 0 or not os.path.isfile(saida):
        sys.exit(f"ffmpeg falhou (codigo {codigo})")

    mb = os.path.getsize(saida) / (1024 * 1024)
    print(f"\npronto: {saida}  ({mb:.1f} MB, {LARGURA}x{ALTURA})")

    if cfg["instalar"]:
        os.makedirs(AREA, exist_ok=True)
        destino = os.path.join(AREA, "atual.mp4")
        shutil.copyfile(saida, destino)
        print(f"instalado em: {destino}")
        print("\nsuba o emulador:")
        print(f'    emulator -avd MinutePlay -no-snapshot '
              f'-camera-back "videofile:{destino}" -camera-front emulated -gpu auto')
    elif " " in saida:
        print("\n  ATENCAO: esse caminho tem ESPACO e o `videofile:` do emulador")
        print("  nao aceita -- falha calado, sem imagem nenhuma. Use --instalar,")
        print("  que copia para uma area sem espaco.")


if __name__ == "__main__":
    main(sys.argv[1:])
