#!/usr/bin/env python3
"""
painel - janelinha para trocar o que passa na camera do emulador.

Escolhe um video, prepara e instala como camera. Nao precisa de terminal:
de dois cliques neste arquivo (a extensao .pyw abre sem janela de console).

O emulador le sempre o mesmo arquivo:
    %LOCALAPPDATA%\\emulation-cam\\atual.mp4
Trocar esse arquivo troca o que a camera mostra. E o que este painel faz.
"""

import os
import re
import json
import shutil
import subprocess
import sys
import threading
import time
import tkinter as tk
from concurrent.futures import ThreadPoolExecutor, as_completed
from tkinter import filedialog, messagebox, simpledialog, ttk

AQUI = os.path.dirname(os.path.abspath(__file__))
EMPACOTADO = bool(getattr(sys, "frozen", False))
# No executavel de arquivo unico, os scripts auxiliares ficam em _MEIPASS,
# mas a pasta de videos deve continuar ao lado do .exe e sobreviver ao fechar.
RECURSOS = getattr(sys, "_MEIPASS", AQUI)
PASTA_APP = os.path.dirname(sys.executable) if EMPACOTADO else AQUI
VIDEOS = os.path.join(PASTA_APP, "videos")
MONTAR = os.path.join(RECURSOS, "montar.py")
INSTALADOR = os.path.join(RECURSOS, "instalar-videocam.ps1")
CONTROLADOR = os.path.join(RECURSOS, "controlar-videocam.ps1")
AREA = os.path.expandvars(r"%LOCALAPPDATA%\emulation-cam")
ATUAL = os.path.join(AREA, "atual.mp4")
AVD_HOME = os.path.expandvars(r"%USERPROFILE%\.android\avd")
TEMPLATE_AVD = os.path.expandvars(
    r"%LOCALAPPDATA%\EmulationCamera\MinuteTemplate.avd")
EXTS = (".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v")
ADB = os.path.expandvars(
    r"%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe")
CONTROLE_ANDROID = (
    "/data/adb/modules/videocam/system/vendor/etc/config/"
    "emu_camera_control.txt")
VIDEO_ANDROID = "/vendor/etc/config/emu_camera_video.i420"
GRAVACOES_ANDROID = "/data/user/0/com.bakerdata.minute/files/recordings"
HISTORICO_TAREFAS = os.path.join(AREA, "controle-tarefas.json")
LIMITE_TAREFA_SEGUNDOS = 2 * 60 * 60

LARGURA, ALTURA = 1280, 720


def achar(nome):
    achado = shutil.which(nome)
    if achado:
        return achado
    raiz = os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Packages")
    if os.path.isdir(raiz):
        alvo = nome + ".exe"
        for pasta, _, arqs in os.walk(raiz):
            if alvo in arqs and os.path.basename(pasta) == "bin":
                return os.path.join(pasta, alvo)
    return None


def sem_console():
    """No Windows, nao pisca janela preta ao chamar o ffmpeg."""
    if os.name != "nt":
        return {}
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    return {"startupinfo": si, "creationflags": subprocess.CREATE_NO_WINDOW}


def indice_minuteplay(nome):
    if nome == "MinutePlay":
        return 1
    achado = re.fullmatch(r"MinutePlay(\d+)", nome)
    return int(achado.group(1)) if achado else None


def descobrir_celulares():
    nomes = []
    try:
        with open(os.path.join(AREA,"retired-emulators.json"),encoding="utf-8") as f:
            retired=set(json.load(f))
    except (OSError,ValueError,TypeError):retired=set()
    if os.path.isdir(AVD_HOME):
        for arquivo in os.listdir(AVD_HOME):
            if not arquivo.lower().endswith(".ini"):
                continue
            nome = os.path.splitext(arquivo)[0]
            if nome in retired:continue
            indice = indice_minuteplay(nome)
            if indice is not None and os.path.isdir(os.path.join(AVD_HOME, nome + ".avd")):
                nomes.append((indice, nome))
    nomes.sort()
    return {
        nome: (f"emulator-{5554 + (indice - 1) * 2}",
               str(5554 + (indice - 1) * 2))
        for indice, nome in nomes
    }


class Painel:
    def __init__(self, raiz):
        self.raiz = raiz
        self.escolhido = None
        self.ocupado = False
        self.cancelar_sync = threading.Event()
        self.sync_em_gravacao = False
        self.lock_historico = threading.Lock()
        self.tarefa_sync = ""
        raiz.title("Camera do emulador")
        raiz.geometry("720x1010")
        raiz.minsize(620, 830)

        pad = {"padx": 12, "pady": 6}

        tk.Label(raiz, text="O que passa na camera",
                 font=("Segoe UI", 14, "bold")).pack(anchor="w", **pad)

        self.celulares = descobrir_celulares()
        if not self.celulares:
            self.celulares = {"MinutePlay": ("emulator-5554", "5554")}
        primeiro = next(iter(self.celulares))
        self.alvo = tk.StringVar(value=primeiro)

        gerente = tk.LabelFrame(raiz, text="Gerenciador de celulares",
                                font=("Segoe UI", 10, "bold"))
        gerente.pack(fill="x", padx=12, pady=(0, 8))
        self.arvore = ttk.Treeview(gerente, columns=("nome", "estado"),
                                   show="headings", height=2, selectmode="browse")
        self.arvore.heading("nome", text="Nome")
        self.arvore.heading("estado", text="Estado")
        self.arvore.column("nome", width=260, anchor="w")
        self.arvore.column("estado", width=180, anchor="center")
        for nome in self.celulares:
            self.arvore.insert("", "end", iid=nome, values=(nome, "verificando..."))
        self.arvore.selection_set(primeiro)
        self.arvore.bind("<<TreeviewSelect>>", self.selecionar_celular)
        self.arvore.pack(fill="x", padx=8, pady=6)

        botoes_gerente = tk.Frame(gerente)
        botoes_gerente.pack(fill="x", padx=8, pady=(0, 7))
        tk.Button(botoes_gerente, text="LIGAR",
                  command=self.abrir_emulador).pack(side="left", expand=True, fill="x")
        tk.Button(botoes_gerente, text="DESLIGAR",
                  command=self.desligar_emulador).pack(side="left", expand=True, fill="x", padx=4)
        tk.Button(botoes_gerente, text="ABRIR MINUTE",
                  command=self.abrir_minute).pack(side="left", expand=True, fill="x")
        tk.Button(botoes_gerente, text="LIGAR OS DOIS",
                  command=self.ligar_todos).pack(side="left", expand=True, fill="x", padx=(4, 0))

        self.btn_adicionar = tk.Button(
            gerente, text="+ ADICIONAR CELULAR", font=("Segoe UI", 10, "bold"),
            command=self.adicionar_celular)
        self.btn_adicionar.pack(fill="x", padx=8, pady=(0, 7))

        self.lbl_alvo = tk.Label(
            gerente, text=f"Selecionado: {primeiro}", anchor="w", fg="#075985")
        self.lbl_alvo.pack(fill="x", padx=8, pady=(0, 6))

        self.lbl_atual = tk.Label(raiz, text="", fg="#0a7", justify="left",
                                  anchor="w", font=("Segoe UI", 9))
        self.lbl_atual.pack(fill="x", **pad)

        tk.Label(raiz, text="Videos em camvideo/videos/",
                 font=("Segoe UI", 9)).pack(anchor="w", padx=12)

        quadro = tk.Frame(raiz)
        quadro.pack(fill="both", expand=True, padx=12, pady=4)
        barra = tk.Scrollbar(quadro)
        barra.pack(side="right", fill="y")
        self.lista = tk.Listbox(quadro, yscrollcommand=barra.set,
                                font=("Segoe UI", 10), activestyle="none")
        self.lista.pack(side="left", fill="both", expand=True)
        barra.config(command=self.lista.yview)
        self.lista.bind("<<ListboxSelect>>", self.ao_selecionar)
        self.lista.bind("<Double-Button-1>", lambda e: self.aplicar())

        linha = tk.Frame(raiz)
        linha.pack(fill="x", **pad)
        tk.Button(linha, text="Escolher outro arquivo...",
                  command=self.escolher_arquivo).pack(side="left")
        tk.Button(linha, text="Abrir a pasta",
                  command=lambda: os.startfile(VIDEOS)).pack(side="left", padx=6)
        tk.Button(linha, text="Atualizar lista",
                  command=self.carregar).pack(side="left")

        opc = tk.Frame(raiz)
        opc.pack(fill="x", **pad)
        self.cortar = tk.BooleanVar(value=False)
        tk.Checkbutton(opc, text="preencher a tela (corta as bordas)",
                       variable=self.cortar).pack(anchor="w")

        txt = tk.Frame(raiz)
        txt.pack(fill="x", **pad)
        tk.Label(txt, text="Texto por cima:").pack(side="left")
        self.texto = tk.Entry(txt)
        self.texto.pack(side="left", fill="x", expand=True, padx=6)

        self.btn = tk.Button(raiz, text="USAR ESTE VIDEO NA CAMERA",
                             font=("Segoe UI", 11, "bold"), height=2,
                             command=self.aplicar, state="disabled")
        self.btn.pack(fill="x", padx=12, pady=(10, 4))

        controles = tk.Frame(raiz)
        controles.pack(fill="x", padx=12, pady=4)
        tk.Button(controles, text="REINICIAR DO ZERO",
                  command=lambda: self.controlar("reiniciar")).pack(side="left", expand=True, fill="x")
        tk.Button(controles, text="PAUSAR",
                  command=lambda: self.controlar("pausar")).pack(side="left", expand=True, fill="x", padx=6)
        tk.Button(controles, text="CONTINUAR",
                  command=lambda: self.controlar("iniciar")).pack(side="left", expand=True, fill="x")

        sync = tk.LabelFrame(
            raiz, text="Gravacao automatica em todos os celulares",
            font=("Segoe UI", 10, "bold"))
        sync.pack(fill="x", padx=12, pady=6)
        tk.Label(
            sync,
            text=("Abra a camera da tarefa em cada Minute. O gerenciador "
                  "inicia, sincroniza o video, encerra e salva sozinho."),
            justify="left", anchor="w", wraplength=660,
        ).pack(fill="x", padx=8, pady=(6, 3))
        linha_tarefa = tk.Frame(sync)
        linha_tarefa.pack(fill="x", padx=8, pady=(3, 2))
        tk.Label(linha_tarefa, text="Tarefa detectada:").pack(side="left")
        self.tarefa = ttk.Combobox(linha_tarefa, state="readonly")
        self.tarefa.pack(side="left", fill="x", expand=True, padx=6)
        self.tarefa.bind("<KeyRelease>", lambda _e: self.atualizar_uso_tarefa())
        self.tarefa.bind("<<ComboboxSelected>>",
                          lambda _e: self.atualizar_uso_tarefa())
        tk.Button(linha_tarefa, text="AJUSTAR TEMPO",
                  command=self.ajustar_tempo_tarefa).pack(side="left")
        self.lbl_uso_tarefa = tk.Label(
            sync, text="A tarefa sera identificada automaticamente pelo Minute.",
            anchor="w", justify="left", fg="#555")
        self.lbl_uso_tarefa.pack(fill="x", padx=8, pady=(0, 2))
        self.lbl_cronometro = tk.Label(
            sync, text="00:00.0 / 00:00.0",
            font=("Consolas", 18, "bold"), fg="#075985")
        self.lbl_cronometro.pack(pady=3)
        linha_sync = tk.Frame(sync)
        linha_sync.pack(fill="x", padx=8, pady=(2, 8))
        self.btn_sync = tk.Button(
            linha_sync, text="INICIAR E SALVAR EM TODOS",
            font=("Segoe UI", 10, "bold"), command=self.sincronizar_gravacao)
        self.btn_sync.pack(side="left", expand=True, fill="x")
        self.btn_cancelar_sync = tk.Button(
            linha_sync, text="CANCELAR", state="disabled",
            command=self.cancelar_sincronizacao)
        self.btn_cancelar_sync.pack(side="left", padx=(6, 0))

        tk.Button(raiz, text="VERIFICAR AMBIENTE DO SELECIONADO",
                  command=self.verificar).pack(fill="x", padx=12, pady=4)

        self.prog = ttk.Progressbar(raiz, mode="indeterminate")

        self.status = tk.Label(raiz, text="", anchor="w", justify="left",
                               fg="#555", font=("Segoe UI", 9), wraplength=520)
        self.status.pack(fill="x", padx=12, pady=(0, 10))

        self.carregar()
        self.mostrar_atual()
        self.carregar_tarefas_conhecidas()
        self.atualizar_status()

    # ---------------------------------------------------------------- dados
    def carregar(self):
        self.lista.delete(0, tk.END)
        self.arquivos = []
        if os.path.isdir(VIDEOS):
            for nome in sorted(os.listdir(VIDEOS)):
                if not nome.lower().endswith(EXTS):
                    continue
                # .pronto/.montado sao gerados por aqui; nao entram na lista
                base = os.path.splitext(nome)[0]
                if base.endswith((".pronto", ".montado")):
                    continue
                self.arquivos.append(os.path.join(VIDEOS, nome))
                self.lista.insert(tk.END, "  " + nome)
        if not self.arquivos:
            self.lista.insert(tk.END, "  (nenhum video aqui ainda)")
            self.dizer("Ponha videos em camvideo/videos/, ou use "
                       "'Escolher outro arquivo...'")

    def mostrar_atual(self):
        if os.path.isfile(ATUAL):
            mb = os.path.getsize(ATUAL) / (1024 * 1024)
            self.lbl_atual.config(
                text=f"Na camera agora: atual.mp4  ({mb:.1f} MB)\n{ATUAL}")
        else:
            self.lbl_atual.config(text="Na camera agora: (nada instalado ainda)",
                                  fg="#a60")

    def dizer(self, msg, cor="#555"):
        self.status.config(text=msg, fg=cor)
        self.raiz.update_idletasks()

    # --------------------------------------------------------------- acoes
    def ao_selecionar(self, _=None):
        sel = self.lista.curselection()
        if sel and self.arquivos and sel[0] < len(self.arquivos):
            self.escolhido = self.arquivos[sel[0]]
            self.btn.config(state="normal")
            self.dizer("Escolhido: " + os.path.basename(self.escolhido))

    def escolher_arquivo(self):
        caminho = filedialog.askopenfilename(
            title="Escolha um video",
            filetypes=[("Videos", "*.mp4 *.mov *.mkv *.webm *.avi *.m4v"),
                       ("Todos", "*.*")])
        if caminho:
            self.escolhido = caminho
            self.lista.selection_clear(0, tk.END)
            self.btn.config(state="normal")
            self.dizer("Escolhido: " + caminho)

    def aplicar(self):
        if self.ocupado or not self.escolhido:
            return
        self.ocupado = True
        self.comeco = time.time()
        self.btn.config(state="disabled", text="processando...")
        self.prog.config(mode="indeterminate", value=0)
        self.prog.pack(fill="x", padx=12, pady=(0, 6))
        self.prog.start(12)
        self.dizer("preparando...")
        threading.Thread(target=self._trabalho, daemon=True).start()

    def controlar(self, acao):
        serial = self.serial_alvo()
        def trabalho():
            try:
                subprocess.run([
                    "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                    "-File", CONTROLADOR,
                    "-Acao", acao,
                    "-Serial", serial,
                ], check=True, **sem_console())
                mensagens = {
                    "reiniciar": "Video reiniciado do zero.",
                    "pausar": "Video pausado.",
                    "iniciar": "Video continuando.",
                }
                self.raiz.after(0, self.dizer, mensagens[acao], "#0a7")
            except Exception as e:                              # noqa: BLE001
                self.raiz.after(0, self.dizer, "Nao deu: " + str(e), "#c00")
        threading.Thread(target=trabalho, daemon=True).start()

    def selecionar_celular(self, _=None):
        selecao = self.arvore.selection()
        if selecao:
            self.alvo.set(selecao[0])
            self.lbl_alvo.config(text=f"Selecionado: {selecao[0]}")
            self.atualizar_uso_tarefa()

    def atualizar_status(self):
        """Atualiza a lista sem travar a interface."""
        def trabalho():
            sdk = os.path.expandvars(r"%LOCALAPPDATA%\Android\Sdk")
            adb = os.path.join(sdk, "platform-tools", "adb.exe")
            estados = {}
            for nome, (serial, _) in list(self.celulares.items()):
                estado = "desligado"
                if os.path.isfile(adb):
                    try:
                        r = subprocess.run([adb, "-s", serial, "get-state"],
                                           capture_output=True, text=True,
                                           timeout=3, **sem_console())
                        if r.returncode == 0 and "device" in r.stdout:
                            boot = subprocess.run(
                                [adb, "-s", serial, "shell", "getprop", "sys.boot_completed"],
                                capture_output=True, text=True, timeout=3,
                                **sem_console())
                            estado = "ligado" if boot.stdout.strip() == "1" else "iniciando..."
                    except (OSError, subprocess.SubprocessError):
                        pass
                estados[nome] = estado

            def aplicar():
                for nome, estado in estados.items():
                    if self.arvore.exists(nome):
                        self.arvore.item(nome, values=(nome, estado))
                self.raiz.after(5000, self.atualizar_status)
            self.raiz.after(0, aplicar)

        threading.Thread(target=trabalho, daemon=True).start()

    def config_alvo(self):
        nome = self.alvo.get()
        serial, porta = self.celulares.get(nome, self.celulares["MinutePlay"])
        return nome, serial, porta

    def serial_alvo(self):
        return self.config_alvo()[1]

    # --------------------------------------------------------- limite por tarefa
    @staticmethod
    def _chave_tarefa(nome):
        return " ".join(nome.strip().casefold().split())

    def _ler_historico(self):
        try:
            with open(HISTORICO_TAREFAS, "r", encoding="utf-8") as arquivo:
                dados = json.load(arquivo)
            if isinstance(dados, dict):
                return dados
        except (OSError, ValueError, TypeError):
            pass
        return {"versao": 1, "dias": {}}

    @staticmethod
    def _hoje():
        return time.strftime("%Y-%m-%d")

    def _uso_tarefa(self, celular, tarefa):
        from task_history import task_usage
        chave = self._chave_tarefa(tarefa)
        if not chave:
            return 0.0
        with self.lock_historico:
            dados = self._ler_historico()
            return task_usage(dados, celular, tarefa, self._hoje())

    def _definir_uso_tarefa(self, celular, tarefa, segundos):
        from automation import task_key
        chave = self._chave_tarefa(tarefa)
        if not chave:
            raise ValueError("informe a tarefa")
        with self.lock_historico:
            dados = self._ler_historico()
            dias = dados.setdefault("dias", {})
            aparelhos = dias.setdefault(self._hoje(), {})
            tarefas = aparelhos.setdefault(celular, {})
            for existing in list(tarefas):
                if task_key(tarefas[existing].get('nome') or existing) == task_key(tarefa):
                    del tarefas[existing]
            tarefas[chave] = {
                "nome": tarefa.strip(),
                "segundos": max(0.0, min(float(segundos),
                                           LIMITE_TAREFA_SEGUNDOS)),
            }
            os.makedirs(AREA, exist_ok=True)
            temporario = HISTORICO_TAREFAS + ".tmp"
            with open(temporario, "w", encoding="utf-8") as arquivo:
                json.dump(dados, arquivo, ensure_ascii=False, indent=2)
            os.replace(temporario, HISTORICO_TAREFAS)

    def _somar_uso_tarefa(self, celular, tarefa, segundos):
        atual = self._uso_tarefa(celular, tarefa)
        self._definir_uso_tarefa(celular, tarefa, atual + segundos)

    def carregar_tarefas_conhecidas(self):
        nomes = set()
        with self.lock_historico:
            dados = self._ler_historico()
            for dia in dados.get("dias", {}).values():
                for celular in dia.values():
                    for entrada in celular.values():
                        if isinstance(entrada, dict) and entrada.get("nome"):
                            nomes.add(entrada["nome"])
        self.tarefa["values"] = sorted(nomes, key=str.casefold)

    @staticmethod
    def _horas_minutos(segundos):
        minutos = max(0, int(round(float(segundos) / 60)))
        horas, minutos = divmod(minutos, 60)
        return f"{horas}h {minutos:02d}min"

    def atualizar_uso_tarefa(self):
        if not hasattr(self, "tarefa"):
            return
        tarefa = self.tarefa.get().strip()
        if not tarefa:
            self.lbl_uso_tarefa.config(
                text="A tarefa sera identificada automaticamente pelo Minute.",
                fg="#555")
            return
        celular = self.alvo.get()
        usado = self._uso_tarefa(celular, tarefa)
        restante = max(0, LIMITE_TAREFA_SEGUNDOS - usado)
        cor = "#c00" if restante <= 0 else "#075985"
        self.lbl_uso_tarefa.config(
            text=(f"{celular} hoje: {self._horas_minutos(usado)} usados | "
                  f"{self._horas_minutos(restante)} restantes"),
            fg=cor)

    def ajustar_tempo_tarefa(self):
        tarefa = self.tarefa.get().strip()
        if not tarefa:
            messagebox.showwarning(
                "Informe a tarefa",
                "Escreva primeiro o nome da tarefa exatamente como voce quer controlar.")
            return
        celular = self.alvo.get()
        atual = self._uso_tarefa(celular, tarefa) / 60
        minutos = simpledialog.askinteger(
            "Ajustar tempo de hoje",
            f"Quantos minutos de '{tarefa}' ja foram gravados hoje no {celular}?",
            initialvalue=int(round(atual)), minvalue=0, maxvalue=120,
            parent=self.raiz)
        if minutos is None:
            return
        self._definir_uso_tarefa(celular, tarefa, minutos * 60)
        self.carregar_tarefas_conhecidas()
        self.atualizar_uso_tarefa()
        self.dizer(
            f"Limite ajustado: {celular}, {tarefa}, {minutos} minutos hoje.",
            "#0a7")

    # ------------------------------------------------------ gravacao sincronizada
    @staticmethod
    def _adb(serial, *args, timeout=12, check=False):
        r = subprocess.run(
            [ADB, "-s", serial, *args], capture_output=True, text=True,
            stdin=subprocess.DEVNULL, encoding="utf-8", errors="replace", timeout=timeout, **sem_console())
        if check and r.returncode != 0:
            detalhe = (r.stderr or r.stdout or "ADB nao respondeu").strip()
            raise RuntimeError(detalhe)
        return r

    @classmethod
    def _shell_root(cls, serial, comando, timeout=12, check=False):
        r = subprocess.run(
            [ADB, "-s", serial, "shell", "su"],
            input=comando + "\n", capture_output=True, text=True,
            timeout=timeout, **sem_console())
        if check and r.returncode != 0:
            detalhe = (r.stderr or r.stdout or "root nao respondeu").strip()
            raise RuntimeError(detalhe)
        return r

    @staticmethod
    def _paralelo(itens, funcao):
        resultados = {}
        with ThreadPoolExecutor(max_workers=max(1, len(itens))) as pool:
            futuros = {pool.submit(funcao, item): item for item in itens}
            for futuro in as_completed(futuros):
                item = futuros[futuro]
                resultados[item] = futuro.result()
        return resultados

    @staticmethod
    def _formatar_tempo(segundos):
        segundos = max(0.0, float(segundos))
        minutos = int(segundos // 60)
        resto = segundos - minutos * 60
        return f"{minutos:02d}:{resto:04.1f}"

    def _mostrar_cronometro(self, decorrido, total):
        self.lbl_cronometro.config(
            text=(f"{self._formatar_tempo(decorrido)} / "
                  f"{self._formatar_tempo(total)}"))

    def _camera_pronta(self, serial):
        estado = self._adb(serial, "get-state", timeout=4)
        if estado.returncode != 0 or "device" not in estado.stdout:
            return None
        topo = self._adb(serial, "shell", "dumpsys", "activity", "top",
                         timeout=8)
        if (topo.returncode != 0 or "mResumed=true" not in topo.stdout or
                "EgoCameraPreview" not in topo.stdout):
            return None
        tamanho = self._shell_root(
            serial, f"if [ -b {VIDEO_ANDROID} ]; then blockdev --getsize64 {VIDEO_ANDROID}; else stat -c %s {VIDEO_ANDROID}; fi", timeout=6)
        try:
            bytes_video = int(tamanho.stdout.strip().splitlines()[-1])
        except (ValueError, IndexError):
            return None
        if bytes_video <= 0:
            return None
        # I420 640x360, 30 quadros/s: 1,5 byte por pixel.
        return bytes_video / (640 * 360 * 3 / 2 * 30)

    def _ler_geracao(self, serial):
        r = self._shell_root(
            serial, f"cat {CONTROLE_ANDROID} 2>/dev/null", check=True)
        achado = re.search(r"(?:play|pause)\s+(\d+)", r.stdout)
        return int(achado.group(1)) if achado else 0

    def _escrever_controle(self, serial, estado, geracao):
        comando = (
            f"printf '%s\\n' '{estado} {geracao}' > {CONTROLE_ANDROID}; "
            f"chown 0:0 {CONTROLE_ANDROID}; "
            f"chcon u:object_r:system_file:s0 {CONTROLE_ANDROID}; "
            f"chmod 644 {CONTROLE_ANDROID}")
        self._shell_root(serial, comando, check=True)
        return True

    def _pastas_gravacao(self, serial):
        r = self._shell_root(
            serial,
            f"find {GRAVACOES_ANDROID} -mindepth 1 -maxdepth 1 -type d "
            "2>/dev/null",
            timeout=8)
        return {
            linha.strip().rstrip("/").rsplit("/", 1)[-1]
            for linha in r.stdout.splitlines() if linha.strip()
        }

    @staticmethod
    def _shell_root_bytes(serial, comando, timeout=12):
        r = subprocess.run(
            [ADB, "-s", serial, "shell", "su"],
            input=(comando + "\n").encode("utf-8"),
            capture_output=True, timeout=timeout, **sem_console())
        if r.returncode != 0:
            detalhe = r.stderr.decode("utf-8", "replace").strip()
            raise RuntimeError(detalhe or "root nao respondeu")
        return r.stdout

    def _detectar_tarefa_sessao(self, serial, pasta_sessao):
        session_id = re.sub(r"_\d+$", "", pasta_sessao)
        limite = time.monotonic() + 8
        caminho = "/data/user/0/com.bakerdata.minute/files/mmkv/recording-store"
        padrao = re.compile(
            rb'"sessionId":"' + re.escape(session_id.encode("ascii")) +
            rb'".{0,6000}?"taskId":"([^"]+)","taskName":"((?:\\.|[^"])*)"',
            re.DOTALL)
        while time.monotonic() < limite and not self.cancelar_sync.is_set():
            bruto = self._shell_root_bytes(serial, f"cat {caminho}", timeout=8)
            achados = list(padrao.finditer(bruto))
            if achados:
                task_id = achados[-1].group(1).decode("utf-8", "replace")
                nome_json = achados[-1].group(2).decode("utf-8", "replace")
                try:
                    nome = json.loads('"' + nome_json + '"')
                except (ValueError, TypeError):
                    nome = nome_json
                if task_id and nome.strip():
                    return task_id, nome.strip()
            time.sleep(0.20)
        raise RuntimeError("o Minute nao informou qual tarefa foi aberta")

    def _tocar_botao_gravacao(self, serial):
        tamanho = self._adb(serial, "shell", "wm", "size", timeout=5,
                            check=True).stdout
        achado = re.search(r"(?:Physical size|Override size):\s*(\d+)x(\d+)",
                           tamanho)
        if not achado:
            raise RuntimeError("nao consegui ler a resolucao da tela")
        largura, altura = map(int, achado.groups())
        # Botao central do componente RecordPrimaryButton do Minute.
        return self._adb(
            serial, "shell", "input", "tap", str(largura // 2),
            str(round(altura * 0.922)), timeout=5, check=True)

    def _esperar_gravacao(self, serial, antes, limite):
        while time.monotonic() < limite and not self.cancelar_sync.is_set():
            atuais = self._pastas_gravacao(serial)
            novas = atuais - antes
            if novas:
                return next(iter(novas))
            time.sleep(0.20)
        raise RuntimeError("a gravacao nao iniciou depois da contagem")

    @staticmethod
    def _centro_bounds(texto_xml, id_recurso):
        padrao = (r'<node(?=[^>]*resource-id="' + re.escape(id_recurso) +
                  r'")(?=[^>]*clickable="true")[^>]*bounds="'
                  r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]"[^>]*/?>')
        achado = re.search(padrao, texto_xml)
        if not achado:
            # A ordem dos atributos pode variar no dump.
            for node in re.findall(r"<node[^>]*/?>", texto_xml):
                if (f'resource-id="{id_recurso}"' in node and
                        'clickable="true"' in node):
                    b = re.search(
                        r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', node)
                    if b:
                        achado = b
                        break
        if not achado:
            return None
        x1, y1, x2, y2 = map(int, achado.groups())
        return (x1 + x2) // 2, (y1 + y2) // 2

    @staticmethod
    def _centro_texto(texto_xml, texto):
        for node in re.findall(r"<node[^>]*/?>", texto_xml):
            if (f'text="{texto}"' not in node or
                    'clickable="true"' not in node):
                continue
            b = re.search(
                r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', node)
            if b:
                x1, y1, x2, y2 = map(int, b.groups())
                return (x1 + x2) // 2, (y1 + y2) // 2
        return None

    def _confirmar_descarte_curto(self, serial):
        limite = time.monotonic() + 15
        inicio = time.monotonic()
        remoto = "/sdcard/minute-limit-window.xml"
        while time.monotonic() < limite:
            try:
                self._adb(serial, "shell", "uiautomator", "dump", "--compressed",
                          remoto, timeout=5)
                xml = self._adb(
                    serial, "shell", "cat", remoto, timeout=5).stdout
            except (OSError, subprocess.SubprocessError):
                time.sleep(0.4)
                continue
            ponto = (self._centro_texto(xml, "OK") or
                     self._centro_bounds(xml, "minute-discard"))
            if ponto:
                self._adb(serial, "shell", "input", "tap",
                          str(ponto[0]), str(ponto[1]), timeout=5, check=True)
                return True
            if time.monotonic() - inicio > 4:
                # O dialogo curto usa sempre o botao OK neste ponto relativo.
                tamanho = self._adb(
                    serial, "shell", "wm", "size", timeout=5,
                    check=True).stdout
                achado = re.search(
                    r"(?:Physical size|Override size):\s*(\d+)x(\d+)",
                    tamanho)
                if achado:
                    largura, altura = map(int, achado.groups())
                    self._adb(
                        serial, "shell", "input", "tap",
                        str(round(largura * 0.304)),
                        str(round(altura * 0.580)),
                        timeout=5, check=True)
                    return True
            time.sleep(0.4)
        return False

    def _salvar_minute(self, serial):
        limite = time.monotonic() + 30
        remoto = "/sdcard/minute-sync-window.xml"
        while time.monotonic() < limite and not self.cancelar_sync.is_set():
            try:
                self._adb(serial, "shell", "uiautomator", "dump", "--compressed",
                          remoto, timeout=6)
                xml = self._adb(
                    serial, "shell", "cat", remoto, timeout=5).stdout
            except (OSError, subprocess.SubprocessError):
                time.sleep(0.5)
                continue
            ponto = self._centro_bounds(xml, "minute-save")
            if ponto:
                self._adb(serial, "shell", "input", "tap",
                          str(ponto[0]), str(ponto[1]), timeout=5, check=True)
                return True
            time.sleep(0.5)
        raise RuntimeError("o botao Salvar nao apareceu")

    def sincronizar_gravacao(self):
        if self.ocupado:
            self.dizer("Aguarde a operacao atual terminar.", "#a60")
            return
        self.tarefa_sync = ""
        self.ocupado = True
        self.cancelar_sync.clear()
        self.btn_sync.config(state="disabled", text="PREPARANDO...")
        self.btn_cancelar_sync.config(state="normal")
        self.dizer("Procurando celulares com a camera da tarefa aberta...")
        threading.Thread(target=self._sincronizar_trabalho, daemon=True).start()

    def cancelar_sincronizacao(self):
        self.cancelar_sync.set()
        self.dizer("Cancelando a automacao com seguranca...", "#a60")

    def _sincronizar_trabalho(self):
        participantes = []
        nomes = {}
        disparado = False
        try:
            candidatos = list(self.celulares.items())
            def verificar(item):
                nome, (serial, _) = item
                return nome, serial, self._camera_pronta(serial)
            respostas = self._paralelo(candidatos, verificar)
            duracoes = []
            duracao_por_serial = {}
            for nome, serial, duracao in respostas.values():
                if duracao is not None:
                    participantes.append(serial)
                    nomes[serial] = nome
                    duracoes.append(duracao)
                    duracao_por_serial[serial] = duracao
            if not participantes:
                raise RuntimeError(
                    "nenhum celular esta na tela da camera da tarefa; "
                    "abra a tarefa no Minute em cada celular")
            if max(duracoes) - min(duracoes) > 0.15:
                detalhes = ", ".join(
                    f"{nomes[s]}={duracao_por_serial[s]:.1f}s"
                    for s in participantes)
                raise RuntimeError("os celulares estao com videos diferentes: " + detalhes)
            total = min(duracoes)
            if total < 61.5:
                raise RuntimeError(
                    f"o video tem {total:.1f}s; o Minute exige pelo menos "
                    "1 minuto e a automacao encerra 1 segundo antes do fim")
            duracao_contabilizada = max(0.2, total - 1.0)

            lista_nomes = ", ".join(nomes[s] for s in participantes)
            self.raiz.after(
                0, self.dizer,
                f"Prontos: {lista_nomes}. Zerando o video e iniciando a contagem...",
                "#075985")
            geracoes = self._paralelo(participantes, self._ler_geracao)
            geracoes = {s: g + 1 for s, g in geracoes.items()}
            self._paralelo(
                participantes,
                lambda s: self._escrever_controle(s, "pause", geracoes[s]))
            antes = self._paralelo(participantes, self._pastas_gravacao)

            # O clique e disparado em paralelo em todos os emuladores.
            self._paralelo(participantes, self._tocar_botao_gravacao)
            disparado = True
            self.raiz.after(
                0, self.dizer,
                "Contagem do Minute iniciada. Aguardando todos gravarem...",
                "#075985")
            limite = time.monotonic() + 18
            sessoes = self._paralelo(
                participantes,
                lambda s: self._esperar_gravacao(s, antes[s], limite))
            if self.cancelar_sync.is_set():
                raise InterruptedError()

            tarefas = self._paralelo(
                participantes,
                lambda s: self._detectar_tarefa_sessao(s, sessoes[s]))
            ids = {task_id for task_id, _ in tarefas.values()}
            if len(ids) != 1:
                detalhes = ", ".join(
                    f"{nomes[s]}={tarefas[s][1]}" for s in participantes)
                self._paralelo(participantes, self._tocar_botao_gravacao)
                self._paralelo(participantes, self._confirmar_descarte_curto)
                disparado = False
                raise RuntimeError(
                    "os celulares estao em tarefas diferentes: " + detalhes)
            self.tarefa_sync = next(iter(tarefas.values()))[1]
            self.raiz.after(0, self.tarefa.set, self.tarefa_sync)
            self.raiz.after(0, self.atualizar_uso_tarefa)

            bloqueados = []
            for serial in participantes:
                nome_tarefa = tarefas[serial][1]
                usado = self._uso_tarefa(nomes[serial], nome_tarefa)
                novo_total = usado + duracao_contabilizada
                if novo_total > LIMITE_TAREFA_SEGUNDOS + 0.01:
                    restante = max(0, LIMITE_TAREFA_SEGUNDOS - usado)
                    bloqueados.append(
                        f"{nomes[serial]} so tem "
                        f"{self._horas_minutos(restante)} restantes")
            if bloqueados:
                self._paralelo(participantes, self._tocar_botao_gravacao)
                self._paralelo(participantes, self._confirmar_descarte_curto)
                disparado = False
                raise RuntimeError(
                    f"limite diario de 2 horas para '{self.tarefa_sync}': " +
                    "; ".join(bloqueados))

            self._paralelo(
                participantes,
                lambda s: self._escrever_controle(s, "play", geracoes[s]))
            self.sync_em_gravacao = True
            comeco = time.monotonic()
            parar_em = duracao_contabilizada
            self.raiz.after(
                0, self.dizer,
                f"GRAVANDO em {lista_nomes}. Encerramento e salvamento automaticos.",
                "#0a7")
            while not self.cancelar_sync.is_set():
                decorrido = time.monotonic() - comeco
                self.raiz.after(0, self._mostrar_cronometro,
                                min(decorrido, total), total)
                if decorrido >= parar_em:
                    break
                time.sleep(0.10)
            if self.cancelar_sync.is_set():
                raise InterruptedError()

            self.raiz.after(0, self.dizer,
                            "Ultimo segundo: encerrando em todos...", "#075985")
            self._paralelo(participantes, self._tocar_botao_gravacao)
            disparado = False
            self.sync_em_gravacao = False
            self.raiz.after(0, self.dizer,
                            "Gravacoes encerradas. Clicando em Salvar...", "#075985")
            def salvar_seguro(serial):
                try:
                    self._salvar_minute(serial)
                    return True, ""
                except Exception as erro:                       # noqa: BLE001
                    return False, str(erro)
            salvos = self._paralelo(participantes, salvar_seguro)
            for serial, (ok, _) in salvos.items():
                if ok:
                    self._somar_uso_tarefa(
                        nomes[serial], tarefas[serial][1], duracao_contabilizada)
            falhas = [
                f"{nomes[serial]}: {erro}"
                for serial, (ok, erro) in salvos.items() if not ok
            ]
            if falhas:
                raise RuntimeError(
                    "alguns celulares nao confirmaram o salvamento: " +
                    "; ".join(falhas))
            self.raiz.after(0, self._fim_sincronizacao, True,
                            f"Concluido: '{self.tarefa_sync}' encerrada e "
                            f"salva em {lista_nomes}.")
        except InterruptedError:
            if disparado and participantes:
                try:
                    self._paralelo(participantes, self._tocar_botao_gravacao)
                except Exception:
                    pass
            self.raiz.after(0, self._fim_sincronizacao, False,
                            "Automacao cancelada; a gravacao foi encerrada sem salvar.")
        except Exception as e:                                  # noqa: BLE001
            if disparado and participantes:
                try:
                    self._paralelo(participantes, self._tocar_botao_gravacao)
                except Exception:
                    pass
            self.raiz.after(0, self._fim_sincronizacao, False,
                            "Falha na automacao: " + str(e))

    def _fim_sincronizacao(self, ok, mensagem):
        self.ocupado = False
        self.sync_em_gravacao = False
        self.btn_sync.config(state="normal", text="INICIAR E SALVAR EM TODOS")
        self.btn_cancelar_sync.config(state="disabled")
        self.carregar_tarefas_conhecidas()
        self.atualizar_uso_tarefa()
        self.dizer(mensagem, "#0a7" if ok else "#c00")

    def abrir_emulador(self):
        """Abre o AVD no unico modo que preserva a camera logica/ultrawide."""
        sdk = os.path.expandvars(r"%LOCALAPPDATA%\Android\Sdk")
        adb = os.path.join(sdk, "platform-tools", "adb.exe")
        exe = os.path.join(sdk, "emulator", "emulator.exe")
        nome_avd, serial, porta = self.config_alvo()
        avd = os.path.expandvars(
            rf"%USERPROFILE%\.android\avd\{nome_avd}.avd")
        if not os.path.isfile(exe):
            self.dizer("Nao achei o Android Emulator. Rode o setup do projeto.", "#c00")
            return
        if not os.path.isdir(avd):
            self.dizer(f"Nao achei o AVD {nome_avd} neste usuario.", "#c00")
            return
        try:
            if os.path.isfile(adb):
                estado = subprocess.run([adb, "-s", serial, "get-state"], capture_output=True,
                                        text=True, timeout=5, **sem_console())
                if estado.returncode == 0 and "device" in estado.stdout:
                    self.dizer("O emulador ja esta aberto.", "#0a7")
                    return
            subprocess.Popen([
                exe, "-avd", nome_avd, "-port", porta, "-no-snapshot",
                "-timezone", "America/Sao_Paulo", "-camera-back", "emulated",
                "-camera-front", "emulated", "-gpu", "auto",
            ], **sem_console())
            self.dizer(f"Abrindo {nome_avd}. Aguarde o Android iniciar...", "#0a7")
        except Exception as e:                                  # noqa: BLE001
            self.dizer("Nao deu para abrir o emulador: " + str(e), "#c00")

    def desligar_emulador(self):
        nome, serial, _ = self.config_alvo()
        adb = os.path.expandvars(r"%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe")
        try:
            r = subprocess.run([adb, "-s", serial, "emu", "kill"],
                               capture_output=True, text=True, timeout=8,
                               **sem_console())
            if r.returncode != 0:
                raise RuntimeError("o celular ja esta desligado ou nao respondeu")
            self.dizer(f"Desligando {nome}...", "#0a7")
        except Exception as e:                                  # noqa: BLE001
            self.dizer(f"Nao deu para desligar {nome}: {e}", "#c00")

    def abrir_minute(self):
        nome, serial, _ = self.config_alvo()
        adb = os.path.expandvars(r"%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe")
        try:
            r = subprocess.run([
                adb, "-s", serial, "shell", "monkey", "-p",
                "com.bakerdata.minute", "-c",
                "android.intent.category.LAUNCHER", "1",
            ], capture_output=True, text=True, timeout=12, **sem_console())
            if r.returncode != 0:
                raise RuntimeError("ligue o celular primeiro")
            self.dizer(f"Minute aberto no {nome}.", "#0a7")
        except Exception as e:                                  # noqa: BLE001
            self.dizer(f"Nao deu para abrir o Minute no {nome}: {e}", "#c00")

    def ligar_todos(self):
        atual = self.alvo.get()
        for nome in self.celulares:
            self.alvo.set(nome)
            self.abrir_emulador()
            time.sleep(1)
        self.alvo.set(atual)
        self.lbl_alvo.config(text=f"Selecionado: {atual}")
        self.dizer("Comando enviado para ligar todos os celulares.", "#0a7")

    def abrir_tudo(self):
        """Liga todos os AVDs e abre o Minute assim que cada boot terminar."""
        if self.ocupado:
            return
        self.dizer("Abrindo todo o sistema: celulares e Minute...", "#075985")
        self.ligar_todos()

        celulares = list(self.celulares.items())

        def trabalho():
            pendentes = {serial: nome for nome, (serial, _) in celulares}
            limite = time.monotonic() + 420
            while pendentes and time.monotonic() < limite:
                for serial, nome in list(pendentes.items()):
                    try:
                        boot = self._adb(
                            serial, "shell", "getprop", "sys.boot_completed",
                            timeout=5)
                        if boot.returncode != 0 or boot.stdout.strip() != "1":
                            continue
                        abertura = self._adb(
                            serial, "shell", "monkey", "-p",
                            "com.bakerdata.minute", "-c",
                            "android.intent.category.LAUNCHER", "1", timeout=15)
                        if abertura.returncode != 0:
                            continue
                        time.sleep(0.6)
                        foco = self._adb(
                            serial, "shell", "dumpsys", "window", timeout=8)
                        if not re.search(
                                r"mCurrentFocus=[^\r\n]*com\.bakerdata\.minute",
                                foco.stdout):
                            continue
                        del pendentes[serial]
                        abertos = len(celulares) - len(pendentes)
                        self.raiz.after(
                            0, self.dizer,
                            f"Minute aberto em {abertos}/{len(celulares)} celulares...",
                            "#075985")
                    except (OSError, subprocess.SubprocessError):
                        pass
                if pendentes:
                    time.sleep(2)
            if pendentes:
                faltaram = ", ".join(pendentes.values())
                self.raiz.after(
                    0, self.dizer,
                    "Sistema aberto, mas estes celulares nao terminaram o boot: " + faltaram,
                    "#a60")
            else:
                self.raiz.after(
                    0, self.dizer,
                    f"Tudo aberto: administrador e Minute em {len(celulares)} celulares.",
                    "#0a7")

        threading.Thread(target=trabalho, daemon=True).start()

    def adicionar_celular(self):
        if self.ocupado:
            self.dizer("Aguarde a operacao atual terminar.", "#a60")
            return
        if not os.path.isdir(TEMPLATE_AVD):
            self.dizer("Modelo-base nao encontrado. Execute CRIAR-TEMPLATE.ps1 uma vez.", "#c00")
            return

        usados = [indice_minuteplay(nome) for nome in self.celulares]
        indice = max(i for i in usados if i is not None) + 1
        nome = f"MinutePlay{indice}"
        porta = str(5554 + (indice - 1) * 2)
        serial = f"emulator-{porta}"
        destino = os.path.join(AVD_HOME, nome + ".avd")
        if os.path.exists(destino):
            self.dizer(f"O destino {nome} ja existe.", "#c00")
            return

        self.ocupado = True
        self.btn_adicionar.config(state="disabled", text=f"CRIANDO {nome}...")
        self.prog.config(mode="determinate", maximum=100, value=0)
        self.prog.pack(fill="x", padx=12, pady=(0, 6))
        self.dizer(f"Criando {nome}: calculando tamanho...")
        threading.Thread(
            target=self._criar_celular,
            args=(nome, serial, porta, destino), daemon=True).start()

    def _progresso_clone(self, pct, texto):
        self.prog.config(value=pct)
        self.dizer(f"Criando celular... {pct}% — {texto}")

    def _criar_celular(self, nome, serial, porta, destino):
        ignorar = {"hardware-qemu.ini", "emu-launch-params.txt",
                   "multiinstance.lock"}
        try:
            arquivos = []
            total = 0
            for pasta, dirs, nomes in os.walk(TEMPLATE_AVD):
                dirs[:] = [d for d in dirs
                            if not d.endswith(".lock") and d != "tmpAdbCmds"]
                for arq in nomes:
                    if arq in ignorar or arq.endswith(".lock"):
                        continue
                    origem = os.path.join(pasta, arq)
                    relativo = os.path.relpath(origem, TEMPLATE_AVD)
                    tamanho = os.path.getsize(origem)
                    arquivos.append((origem, os.path.join(destino, relativo), tamanho))
                    total += tamanho

            copiado = 0
            ultimo = -1
            for origem, alvo, tamanho in arquivos:
                os.makedirs(os.path.dirname(alvo), exist_ok=True)
                with open(origem, "rb") as entrada, open(alvo, "wb") as saida:
                    while True:
                        bloco = entrada.read(8 * 1024 * 1024)
                        if not bloco:
                            break
                        saida.write(bloco)
                        copiado += len(bloco)
                        pct = min(90, int(copiado / max(1, total) * 90))
                        if pct != ultimo:
                            ultimo = pct
                            self.raiz.after(0, self._progresso_clone, pct,
                                            f"copiando {os.path.basename(origem)}")
                shutil.copystat(origem, alvo)

            ini = os.path.join(AVD_HOME, nome + ".ini")
            with open(ini, "w", encoding="utf-8", newline="\n") as arquivo:
                arquivo.write(
                    "avd.ini.encoding=UTF-8\n"
                    f"path={destino}\n"
                    f"path.rel=avd\\{nome}.avd\n"
                    "target=android-33\n")

            self.raiz.after(0, self._progresso_clone, 92, "iniciando Android")
            sdk = os.path.expandvars(r"%LOCALAPPDATA%\Android\Sdk")
            emulator = os.path.join(sdk, "emulator", "emulator.exe")
            adb = os.path.join(sdk, "platform-tools", "adb.exe")
            subprocess.Popen([
                emulator, "-avd", nome, "-port", porta, "-no-snapshot",
                "-timezone", "America/Sao_Paulo", "-camera-back", "emulated",
                "-camera-front", "emulated", "-gpu", "auto",
            ], **sem_console())

            limite = time.time() + 360
            pronto = False
            while time.time() < limite:
                try:
                    r = subprocess.run(
                        [adb, "-s", serial, "shell", "getprop", "sys.boot_completed"],
                        capture_output=True, text=True, timeout=5, **sem_console())
                    if r.stdout.strip() == "1":
                        pronto = True
                        break
                except subprocess.SubprocessError:
                    pass
                time.sleep(2)
            if not pronto:
                raise RuntimeError("o Android nao concluiu o boot em 6 minutos")

            self.raiz.after(0, self._progresso_clone, 97, "removendo login antigo do Minute")
            limpar = subprocess.run(
                [adb, "-s", serial, "shell", "pm", "clear", "com.bakerdata.minute"],
                capture_output=True, text=True, timeout=30, **sem_console())
            if limpar.returncode != 0 or "Success" not in limpar.stdout:
                raise RuntimeError("nao foi possivel limpar a conta do Minute")
            subprocess.run([
                adb, "-s", serial, "shell", "monkey", "-p",
                "com.bakerdata.minute", "-c", "android.intent.category.LAUNCHER", "1",
            ], capture_output=True, timeout=20, **sem_console())
            self.raiz.after(0, self._fim_criar_celular,
                            True, nome, serial, porta, None)
        except Exception as e:                                  # noqa: BLE001
            self.raiz.after(0, self._fim_criar_celular,
                            False, nome, serial, porta, str(e))

    def _fim_criar_celular(self, ok, nome, serial, porta, erro):
        self.prog.pack_forget()
        self.ocupado = False
        self.btn_adicionar.config(state="normal", text="+ ADICIONAR CELULAR")
        if os.path.isdir(os.path.join(AVD_HOME, nome + ".avd")):
            self.celulares[nome] = (serial, porta)
            if not self.arvore.exists(nome):
                self.arvore.insert("", "end", iid=nome,
                                   values=(nome, "ligado" if ok else "incompleto"))
        if ok:
            self.alvo.set(nome)
            self.arvore.selection_set(nome)
            self.lbl_alvo.config(text=f"Selecionado: {nome}")
            self.dizer(f"{nome} criado. Play Store mantida; Minute aberto sem login.", "#0a7")
        else:
            self.dizer(f"Falha ao criar {nome}: {erro}", "#c00")

    def verificar(self):
        if self.ocupado:
            return
        self.dizer("Verificando ffmpeg, ADB, root e modulo da camera...")

        _, serial, _ = self.config_alvo()

        def trabalho():
            try:
                sdk = os.path.expandvars(r"%LOCALAPPDATA%\Android\Sdk")
                adb = os.path.join(sdk, "platform-tools", "adb.exe")
                faltas = []
                if not achar("ffmpeg"):
                    faltas.append("ffmpeg")
                if not os.path.isfile(adb):
                    faltas.append("ADB")
                if faltas:
                    raise RuntimeError("Faltando: " + ", ".join(faltas))
                estado = subprocess.run([adb, "-s", serial, "get-state"], capture_output=True,
                                        text=True, timeout=8, **sem_console())
                if estado.returncode != 0 or "device" not in estado.stdout:
                    raise RuntimeError("Emulador fechado. Clique em ABRIR EMULADOR.")
                raiz = subprocess.run([adb, "-s", serial, "shell", "su", "-c", "id"],
                                      capture_output=True, text=True, timeout=8,
                                      **sem_console())
                if raiz.returncode != 0 or "uid=0" not in raiz.stdout:
                    raise RuntimeError("O root Magisk nao respondeu.")
                modulo = subprocess.run([
                    adb, "-s", serial, "shell", "su", "-c",
                    "test -f /data/adb/modules/videocam/module.prop",
                ], timeout=8, **sem_console())
                if modulo.returncode != 0:
                    raise RuntimeError("Modulo videocam nao esta instalado.")
                self.raiz.after(0, self.dizer,
                                "Tudo certo: emulador, ADB, root e videocam funcionando.", "#0a7")
            except Exception as e:                              # noqa: BLE001
                self.raiz.after(0, self.dizer, "Verificacao falhou: " + str(e), "#c00")

        threading.Thread(target=trabalho, daemon=True).start()

    def _determinado(self):
        """Sai da barra animada e passa para a de porcentagem."""
        self.prog.stop()
        self.prog.config(mode="determinate", maximum=100, value=0)

    def _avanco(self, pct):
        self.prog.config(value=pct)
        passado = time.time() - self.comeco
        if pct >= 2:
            resta = passado * (100 - pct) / pct
            m, s = divmod(int(resta), 60)
            falta = f" — faltam ~{m}min {s:02d}s" if m else f" — faltam ~{s}s"
        else:
            falta = ""
        self.dizer(f"convertendo... {pct}%{falta}")

    def _trabalho(self):
        try:
            serial = self.serial_alvo()
            os.makedirs(AREA, exist_ok=True)
            if EMPACOTADO:
                args = [sys.executable, "--montar", "--fundo", self.escolhido]
            else:
                args = [sys.executable, MONTAR, "--fundo", self.escolhido]
            args += [
                    "--ajuste", "cheio" if self.cortar.get() else "caber",
                    "--instalar", "--progresso",
                    "-o", os.path.join(AREA, "trabalho.mp4")]
            t = self.texto.get().strip()
            if t:
                args += ["--texto", t]

            p = subprocess.Popen(args, stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT, text=True,
                                 bufsize=1, **sem_console())
            ultimas = []
            for linha in p.stdout:
                linha = linha.strip()
                if linha.startswith("PROGRESSO:"):
                    try:
                        pct = int(linha.split(":", 1)[1])
                    except ValueError:
                        continue
                    self.raiz.after(0, self._avanco, pct)
                elif linha.startswith("TOTAL:"):
                    self.raiz.after(0, self._determinado)
                elif linha:
                    ultimas.append(linha)
                    del ultimas[:-6]
            p.wait()

            if p.returncode != 0 or not os.path.isfile(ATUAL):
                self.raiz.after(0, self._fim, False,
                                ultimas[-1] if ultimas else "falhou sem mensagem")
            else:
                self.raiz.after(0, self.dizer, "Enviando video para a camera; o emulador vai reiniciar...")
                subprocess.run([
                    "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                    "-File", INSTALADOR,
                    "-Video", ATUAL,
                    "-Serial", serial,
                ], check=True, **sem_console())
                self.raiz.after(0, self._fim, True, None)
        except Exception as e:                                  # noqa: BLE001
            self.raiz.after(0, self._fim, False, str(e))

    def _fim(self, ok, erro):
        self.prog.stop()
        self.prog.pack_forget()
        self.ocupado = False
        self.btn.config(state="normal", text="USAR ESTE VIDEO NA CAMERA")
        self.mostrar_atual()
        if ok:
            levou = int(time.time() - self.comeco)
            m, s = divmod(levou, 60)
            quanto = f"{m}min {s:02d}s" if m else f"{s}s"
            self.dizer(f"Pronto em {quanto}. Video enviado; aguarde o Android reiniciar e abra a camera.", "#0a7")
        else:
            self.dizer("Nao deu: " + erro, "#c00")


def main():
    if EMPACOTADO and len(sys.argv) > 1 and sys.argv[1] == "--montar":
        # O proprio .exe funciona como worker de console para manter o painel
        # sem depender de uma instalacao separada do Python.
        import montar
        montar.main(sys.argv[2:])
        return
    if not achar("ffmpeg"):
        raiz = tk.Tk(); raiz.withdraw()
        from tkinter import messagebox
        messagebox.showerror("Falta o ffmpeg",
                             "Nao achei o ffmpeg.\n\n"
                             "Rode setup\\01-ferramentas.ps1, ou:\n"
                             "  winget install Gyan.FFmpeg")
        return
    raiz = tk.Tk()
    os.makedirs(VIDEOS, exist_ok=True)
    painel = Painel(raiz)
    if "--abrir-tudo" in sys.argv:
        raiz.after(600, painel.abrir_tudo)
    raiz.mainloop()


if __name__ == "__main__":
    main()
