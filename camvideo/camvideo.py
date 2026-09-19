#!/usr/bin/env python3
"""
camvideo - monta a imagem da camera do emulador no OBS.

Cadeia:
    camera do celular (Iriun)  ─┐
                                ├─ OBS compoe ─→ DroidCam Virtual Output
    video do PC (arquivo)      ─┘                ─→ driver "DroidCam Video"
                                                 ─→ emulador (webcam0)

O emulador NAO aponta pro Iriun: quem le o Iriun e o OBS. Assim da pra ter a
camera ao vivo e o video por cima ao mesmo tempo.

Uso:
    python camvideo.py video.mp4                     so o video, tela cheia
    python camvideo.py --live                        so a camera do celular
    python camvideo.py video.mp4 --live              camera + video no canto
    python camvideo.py video.mp4 --live --sobre cheio  video cobrindo a camera
    python camvideo.py --live --cam "Iriun"          escolhe outra webcam
    python camvideo.py --listar-cams                 mostra as webcams do OBS
    python camvideo.py --status

Ajustes de giro (o emulador gira o quadro pelo sensor.orientation = 90):

    video       --rot 270  --flip     (padrao: espelhado ja vem ligado)
                --rot 90   --flip     idem na frontal (ela espelha, inverte 180)
                --no-flip             desliga o espelho do video
    camera      --rot-cam 0           (padrao)
                --flip-cam            liga o espelho da camera ao vivo
                --no-flip-cam         desliga (padrao)

`--flip` existe so para deixar a intencao explicita na linha de comando: o
espelho do video ja vem ligado, entao passar ou nao passar da no mesmo. Quem
muda alguma coisa e o `--no-flip`.
"""

import asyncio
import base64
import hashlib
import json
import os
import sys

import websockets

HOST = "127.0.0.1"
PORT = 4455
CONFIG = os.path.expandvars(
    r"%APPDATA%\obs-studio\plugin_config\obs-websocket\config.json"
)

SCENE = "CamVideo"
VIDEO = "Video do PC"
CAMERA = "Camera ao vivo"


def senha():
    with open(CONFIG, encoding="utf-8") as f:
        return json.load(f)["server_password"]


class Obs:
    """Cliente minimo do obs-websocket 5.x."""

    def __init__(self, ws):
        self.ws = ws
        self._n = 0

    @classmethod
    async def conectar(cls):
        try:
            ws = await websockets.connect(f"ws://{HOST}:{PORT}", max_size=None)
        except OSError:
            sys.exit("nao conectou no OBS. Ele esta aberto? "
                     "(Ferramentas > Configuracoes do WebSocket > servidor ligado)")
        hello = json.loads(await ws.recv())
        ident = {"op": 1, "d": {"rpcVersion": 1}}

        auth = hello["d"].get("authentication")
        if auth:
            p = senha()
            segredo = base64.b64encode(
                hashlib.sha256((p + auth["salt"]).encode()).digest()
            ).decode()
            ident["d"]["authentication"] = base64.b64encode(
                hashlib.sha256((segredo + auth["challenge"]).encode()).digest()
            ).decode()

        await ws.send(json.dumps(ident))
        resp = json.loads(await ws.recv())
        if resp["op"] != 2:
            raise RuntimeError(f"falha ao identificar: {resp}")
        return cls(ws)

    async def pedir(self, tipo, dados=None):
        self._n += 1
        rid = str(self._n)
        await self.ws.send(json.dumps({
            "op": 6,
            "d": {"requestType": tipo, "requestId": rid,
                  "requestData": dados or {}},
        }))
        while True:
            msg = json.loads(await self.ws.recv())
            if msg["op"] == 7 and msg["d"]["requestId"] == rid:
                return msg["d"]

    async def fechar(self):
        await self.ws.close()


# ----------------------------------------------------------------- utilidades

async def canvas_do_obs(obs):
    v = await obs.pedir("GetVideoSettings")
    return v["responseData"]["baseWidth"], v["responseData"]["baseHeight"]


async def trocar_canvas(obs, largura, altura):
    """O OBS recusa a troca com qualquer saida ativa; avisa em vez de falhar calado."""
    r = await obs.pedir("SetVideoSettings", {
        "baseWidth": largura, "baseHeight": altura,
        "outputWidth": largura, "outputHeight": altura,
    })
    if r["requestStatus"]["result"]:
        print(f"canvas alterado para {largura}x{altura}")
        return True
    print(f"nao deu pra mudar o canvas: "
          f"{r['requestStatus'].get('comment', r['requestStatus'])}")
    print("pare a saida antes: Ferramentas > DroidCam Virtual Output > Stop")
    return False


async def garantir_cena(obs):
    cenas = await obs.pedir("GetSceneList")
    nomes = [s["sceneName"] for s in cenas["responseData"]["scenes"]]
    if SCENE not in nomes:
        await obs.pedir("CreateScene", {"sceneName": SCENE})
        print(f"cena '{SCENE}' criada")


async def id_do_item(obs, fonte):
    r = await obs.pedir("GetSceneItemId",
                        {"sceneName": SCENE, "sourceName": fonte})
    return r["responseData"]["sceneItemId"] if r["requestStatus"]["result"] else None


async def dimensoes(obs, item):
    t = await obs.pedir("GetSceneItemTransform",
                        {"sceneName": SCENE, "sceneItemId": item})
    tr = t["responseData"]["sceneItemTransform"]
    return tr["sourceWidth"], tr["sourceHeight"]


async def esperar_dimensoes(obs, item, antes=None, tentativas=25):
    """O OBS demora a atualizar o tamanho depois de trocar a fonte."""
    sw = sh = 0
    for _ in range(tentativas):
        w, h = await dimensoes(obs, item)
        if w and h:
            sw, sh = w, h
            if antes is None or (w, h) != antes:
                break
        await asyncio.sleep(0.2)
    return sw, sh


def recorte_para(sw, sh, alvo):
    """
    Quanto cortar de cada lado pra fonte virar o aspecto `alvo` (larg/alt).

    Serve pra transformar a camera 16:9 deitada num 9:16 em pe: sem isso o app
    do celular corta sozinho a faixa central e voce perde as bordas.
    """
    atual = sw / sh
    if abs(atual - alvo) < 0.01:
        return 0, 0, 0, 0
    if atual > alvo:                       # larga demais: corta as laterais
        nova = sh * alvo
        lado = int((sw - nova) / 2)
        return lado, lado, 0, 0
    nova = sw / alvo                       # alta demais: corta topo e base
    lado = int((sh - nova) / 2)
    return 0, 0, lado, lado


async def posicionar(obs, item, cw, ch, rot=0, espelhar=False,
                     cobrir=True, fracao=1.0, canto=None, antes=None,
                     obrigatorio=True, aspecto=None):
    """
    Escala e posiciona um item na cena.

    cobrir=True preenche a area cortando o excesso; False deixa caber inteiro.
    fracao encolhe o item (0.35 = 35% da tela). canto posiciona o item reduzido.

    Devolve None se a fonte ainda nao tem tamanho — e o caso da webcam quando
    o celular nao esta conectado: ela existe mas nao entrega quadro nenhum.
    """
    sw, sh = await esperar_dimensoes(obs, item, antes)
    if not sw or not sh:
        if obrigatorio:
            sys.exit("o OBS nao reportou o tamanho da fonte "
                     "(ela carregou? o arquivo abre?)")
        return None

    # recorte opcional: a escala passa a valer sobre o que sobrou
    cl = cr = ct = cb = 0
    if aspecto:
        cl, cr, ct, cb = recorte_para(sw, sh, aspecto)
    vw, vh = sw - cl - cr, sh - ct - cb

    alvo_w, alvo_h = cw * fracao, ch * fracao
    if rot % 180 == 90:                       # girado: os eixos trocam
        a, b = alvo_w / vh, alvo_h / vw
    else:
        a, b = alvo_w / vw, alvo_h / vh
    escala = max(a, b) if cobrir else min(a, b)

    if canto is None:
        px, py = cw / 2, ch / 2
    else:
        larg = (vh if rot % 180 == 90 else vw) * escala
        alt = (vw if rot % 180 == 90 else vh) * escala
        margem = min(cw, ch) * 0.03
        px = cw - larg / 2 - margem if "direita" in canto else larg / 2 + margem
        py = ch - alt / 2 - margem if "baixo" in canto else alt / 2 + margem

    await obs.pedir("SetSceneItemTransform", {
        "sceneName": SCENE,
        "sceneItemId": item,
        "sceneItemTransform": {
            "boundsType": "OBS_BOUNDS_NONE",
            "alignment": 0,                   # ancora no centro do item
            "positionX": px,
            "positionY": py,
            "rotation": float(rot),
            "scaleX": -escala if espelhar else escala,
            "scaleY": escala,
            "cropLeft": cl, "cropRight": cr,
            "cropTop": ct, "cropBottom": cb,
        },
    })
    larg = int((vh if rot % 180 == 90 else vw) * escala)
    alt = int((vw if rot % 180 == 90 else vh) * escala)
    return sw, sh, larg, alt, (vw, vh)


# -------------------------------------------------------------------- fontes

async def listar_cams(obs):
    """Le a lista de webcams do proprio OBS (precisa de uma fonte dshow viva)."""
    temporaria = False
    if await id_do_item(obs, CAMERA) is None:
        await obs.pedir("CreateInput", {
            "sceneName": SCENE, "inputName": CAMERA,
            "inputKind": "dshow_input", "inputSettings": {},
            "sceneItemEnabled": True})
        temporaria = True

    r = await obs.pedir("GetInputPropertiesListPropertyItems",
                        {"inputName": CAMERA, "propertyName": "video_device_id"})
    itens = r["responseData"]["propertyItems"] if r["requestStatus"]["result"] else []

    if temporaria:
        await obs.pedir("RemoveInput", {"inputName": CAMERA})
    return [(i["itemName"], i["itemValue"]) for i in itens if i.get("itemEnabled", True)]


async def garantir_camera(obs, busca):
    """Cria (ou reaproveita) a fonte da webcam ao vivo e a manda pro fundo."""
    item = await id_do_item(obs, CAMERA)
    if item is None:
        r = await obs.pedir("CreateInput", {
            "sceneName": SCENE, "inputName": CAMERA,
            "inputKind": "dshow_input", "inputSettings": {},
            "sceneItemEnabled": True})
        if not r["requestStatus"]["result"]:
            sys.exit(f"erro ao criar a fonte de camera: {r['requestStatus']}")
        item = r["responseData"]["sceneItemId"]

    cams = await listar_cams(obs)
    if not cams:
        sys.exit("o OBS nao listou nenhuma webcam")

    escolhida = next((c for c in cams if busca.lower() in c[0].lower()), None)
    if escolhida is None:
        print("webcam nao encontrada. Disponiveis:")
        for nome, _ in cams:
            print("   ", nome)
        sys.exit(1)

    await obs.pedir("SetInputSettings", {
        "inputName": CAMERA,
        "inputSettings": {"video_device_id": escolhida[1], "active": True},
    })
    # fundo da cena: indice 0 e o mais atras
    await obs.pedir("SetSceneItemIndex",
                    {"sceneName": SCENE, "sceneItemId": item, "sceneItemIndex": 0})
    print(f"camera ao vivo: {escolhida[0]}")
    return item


async def garantir_video(obs, arquivo):
    """Cria ou atualiza a fonte de video. Devolve (item, dimensoes anteriores)."""
    ajustes = {
        "local_file": arquivo,
        "is_local_file": True,
        "looping": True,
        "restart_on_activate": True,
        "close_when_inactive": False,
        "hw_decode": True,
    }
    item = await id_do_item(obs, VIDEO)
    antes = None

    if item is not None:
        antes = await dimensoes(obs, item)
        # trocar o arquivo em vez de recriar: RemoveInput e assincrono e dava corrida
        r = await obs.pedir("SetInputSettings",
                            {"inputName": VIDEO, "inputSettings": ajustes})
        if not r["requestStatus"]["result"]:
            sys.exit(f"erro ao trocar o video: {r['requestStatus']}")
    else:
        r = await obs.pedir("CreateInput", {
            "sceneName": SCENE, "inputName": VIDEO,
            "inputKind": "ffmpeg_source", "inputSettings": ajustes,
            "sceneItemEnabled": True})
        if not r["requestStatus"]["result"]:
            sys.exit(f"erro ao criar a fonte de video: {r['requestStatus']}")
        item = r["responseData"]["sceneItemId"]

    print(f"video: {os.path.basename(arquivo)}")
    return item, antes


# -------------------------------------------------------------------- acoes

async def montar(cfg):
    video = os.path.abspath(cfg["video"]) if cfg["video"] else None
    if video and not os.path.isfile(video):
        sys.exit(f"arquivo nao encontrado: {video}")

    obs = await Obs.conectar()
    print("conectado ao OBS")

    if cfg["canvas"]:
        await trocar_canvas(obs, *cfg["canvas"])
    await garantir_cena(obs)

    if cfg["listar"]:
        for nome, _ in await listar_cams(obs):
            print("  webcam:", nome)
        await obs.fechar()
        return

    item_cam = await garantir_camera(obs, cfg["cam"]) if cfg["live"] else None
    item_vid = antes = None
    if video:
        item_vid, antes = await garantir_video(obs, video)

    # a cena precisa estar no ar antes de medir: o OBS so carrega a midia ativa
    await obs.pedir("SetCurrentProgramScene", {"sceneName": SCENE})
    if item_vid is not None:
        await obs.pedir("TriggerMediaInputAction", {
            "inputName": VIDEO,
            "mediaAction": "OBS_WEBSOCKET_MEDIA_INPUT_ACTION_RESTART"})
    await asyncio.sleep(0.6)

    cw, ch = await canvas_do_obs(obs)

    if item_cam is not None:
        vertical = cfg["cam_vertical"]
        r = await posicionar(
            obs, item_cam, cw, ch,
            rot=cfg["rot"] if vertical else cfg["rot_cam"],
            espelhar=cfg["flip"] if vertical else cfg["flip_cam"],
            cobrir=True, obrigatorio=False,
            aspecto=(9 / 16) if vertical else None)
        if r is None:
            print("   camera sem imagem: conecte o celular no app e rode de novo")
            print("   (a fonte ja esta na cena; ela aparece sozinha ao conectar)")
        else:
            sw, sh, lw, lh, (vw, vh) = r
            corte = f" (recortado p/ {vw}x{vh})" if (vw, vh) != (sw, sh) else ""
            print(f"   camera {sw}x{sh}{corte} -> {lw}x{lh} na tela")

    if item_vid is not None:
        sobrepondo = cfg["live"] and cfg["sobre"] != "cheio"
        fracao = 0.35 if sobrepondo else 1.0
        canto = "baixo-direita" if sobrepondo else None
        sw, sh, lw, lh, _ = await posicionar(
            obs, item_vid, cw, ch, rot=cfg["rot"], espelhar=cfg["flip"],
            cobrir=not sobrepondo, fracao=fracao, canto=canto, antes=antes)
        onde = "canto inferior direito" if sobrepondo else "tela cheia"  # noqa
        giro = f", girado {cfg['rot']}" if cfg["rot"] else ""
        print(f"   video {sw}x{sh} -> {lw}x{lh} ({onde}{giro})")

    print(f"cena ativa: {SCENE}  (canvas {cw}x{ch})")
    print("\nse a camera do emulador mostrar 'Start DroidCam', ligue a saida:")
    print("   OBS > Ferramentas > DroidCam Virtual Output > Start")
    await obs.fechar()


async def status():
    obs = await Obs.conectar()
    v = await obs.pedir("GetVersion")
    print("OBS", v["responseData"]["obsVersion"],
          "| websocket", v["responseData"]["obsWebSocketVersion"])
    cw, ch = await canvas_do_obs(obs)
    print(f"canvas {cw}x{ch}")
    cena = await obs.pedir("GetCurrentProgramScene")
    print("cena ativa:", cena["responseData"]["currentProgramSceneName"])
    for nome, _ in await listar_cams(obs):
        print("  webcam:", nome)
    await obs.fechar()


# ---------------------------------------------------------------- argumentos

def ler_args(argv):
    cfg = {"video": None, "canvas": None, "rot": 270, "flip": True,
           "rot_cam": 0, "flip_cam": False, "live": False, "cam": "Iriun",
           "sobre": "canto", "listar": False, "cam_vertical": True}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--canvas":
            i += 1
            try:
                l, alt = argv[i].lower().split("x")
                cfg["canvas"] = (int(l), int(alt))
            except (IndexError, ValueError):
                sys.exit("--canvas precisa de LARGURAxALTURA, ex: 1920x1080")
        elif a == "--rot":
            i += 1
            cfg["rot"] = int(argv[i]) % 360
        elif a == "--rot-cam":
            i += 1
            cfg["rot_cam"] = int(argv[i]) % 360
        elif a in ("--flip", "-f"):
            cfg["flip"] = True          # ja e o padrao; aceito para ser explicito
        elif a == "--no-flip":
            cfg["flip"] = False
        elif a == "--flip-cam":
            cfg["flip_cam"] = True
        elif a == "--no-flip-cam":
            cfg["flip_cam"] = False
        elif a in ("--live", "-l"):
            cfg["live"] = True
        elif a == "--cam":
            i += 1
            cfg["cam"] = argv[i]
            cfg["live"] = True
        elif a == "--sobre":
            i += 1
            cfg["sobre"] = argv[i]
        elif a == "--cam-deitada":
            cfg["cam_vertical"] = False
        elif a == "--listar-cams":
            cfg["listar"] = True
        elif a.startswith("-"):
            sys.exit(f"opcao desconhecida: {a}")
        else:
            cfg["video"] = a
        i += 1
    return cfg


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        sys.exit(__doc__)
    if args[0] == "--status":
        asyncio.run(status())
    else:
        c = ler_args(args)
        if not (c["video"] or c["live"] or c["canvas"] or c["listar"]):
            sys.exit(__doc__)
        asyncio.run(montar(c))
