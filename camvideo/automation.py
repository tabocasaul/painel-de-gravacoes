"""Minute navigation and per-device recording deadlines."""
import concurrent.futures
import json
import math
import re
import subprocess
import threading
import time
import unicodedata
import xml.etree.ElementTree as ET
from unicode_search import write_query, exact_text
from synchronized_recording_start import RecordingStartGroup

MAX_SECONDS = 29 * 60 + 59


def confirmed_recording_seconds(raw, session):
    session = re.sub(r'_\d+$', '', session)
    decoder = json.JSONDecoder()
    text = raw.decode('utf-8', 'replace')
    accepted = False
    uploads = {}
    for match in re.finditer(r'\{', text):
        try:
            obj, _ = decoder.raw_decode(text, match.start())
        except ValueError:
            continue
        if not isinstance(obj, dict) or obj.get('sessionId') != session:
            continue
        if 'accepted' in obj:
            accepted = obj.get('accepted') is True and obj.get('status') == 'ended'
        if 'durationMs' in obj and obj.get('id'):
            uploads[obj['id']] = obj
    if not accepted or not uploads or any(o.get('status') != 'done' for o in uploads.values()):
        return None
    try:
        seconds = sum(float(o['durationMs']) / 1000 for o in uploads.values())
    except (ValueError, TypeError):
        return None
    return seconds if math.isfinite(seconds) and 0 < seconds <= MAX_SECONDS else None


def normalize(value):
    return ' '.join(''.join(c for c in unicodedata.normalize('NFD', value.casefold())
                            if not unicodedata.combining(c)).split())


def task_key(value):
    # Preserve every word and its order; accept only a simple final plural s.
    return tuple(w[:-1] if len(w) > 4 and w.endswith('s') else w
                 for w in normalize(value).split())


def search_text(node):
    text = node.get('text', '')
    # Android's accessibility dump exposes this placeholder as EditText.text.
    return '' if normalize(text) == 'buscar tarefas' else text


def recording_duration(seconds):
    seconds = float(seconds)
    if not math.isfinite(seconds) or seconds < 61.5:
        raise ValueError('O vídeo precisa ter pelo menos 61,5 segundos para salvar no Minute.')
    return min(seconds, MAX_SECONDS)


def stop_deadline(play_started, record_triggered, duration):
    # Includes countdown/setup in the recording cap; reserve time for the ADB tap.
    return min(play_started + duration, record_triggered + MAX_SECONDS - 1)


class Automation:
    def __init__(self, engine, update):
        self.e, self.update = engine, update
        self.lock = threading.Lock()
        self.rows = {}
        self.stop_after_round = threading.Event()
        self.usage_since = None
        self.recovery = None

    def task_usage(self, phone, task):
        if not self.usage_since:
            return self.e._uso_tarefa(phone, task)
        from task_history import task_usage
        with self.e.lock_historico:
            history = self.e._ler_historico()
        return sum(task_usage(history, phone, task, day) for day in history.get('dias', {}) if day >= self.usage_since)

    def request_stop_after_round(self):
        self.stop_after_round.set()
        self.update(loopStopping=True, message='O loop vai parar depois de salvar esta rodada.')

    def snapshot(self):
        with self.lock:
            return {s: dict(row) for s, row in self.rows.items()}

    def mark(self, serial, **data):
        with self.lock:
            self.rows.setdefault(serial, {}).update(data)

    def check_cancel(self):
        if self.e.cancelar_sync.is_set():
            raise InterruptedError('Automação interrompida')

    def wait_preparation_connection(self, serial, timeout=60):
        deadline = time.monotonic() + timeout
        stable = 0
        while time.monotonic() < deadline:
            self.check_cancel()
            try:
                result = self.e._adb(serial, 'shell', 'getprop', 'sys.boot_completed', timeout=5)
                stable = stable + 1 if result.returncode == 0 and result.stdout.strip() == '1' else 0
                if stable >= 3:
                    return
            except (RuntimeError, subprocess.TimeoutExpired):
                stable = 0
            if self.e.cancelar_sync.wait(2):
                self.check_cancel()
        raise RuntimeError('O celular não estabilizou a conexão durante a preparação: ' + serial)

    def xml(self, serial):
        path = f'/data/local/tmp/minute-automation-{threading.get_ident()}.xml'
        for attempt in range(2):
            try:
                self.e._adb(serial, 'shell', 'rm', '-f', path, timeout=5, check=True)
                self.e._adb(serial, 'shell', 'uiautomator', 'dump', '--compressed', path, timeout=20, check=True)
                raw = self.e._adb(serial, 'shell', 'cat', path, timeout=5, check=True).stdout
                root = ET.fromstring(raw)
                if any(n.get('resource-id') == 'com.android.systemui:id/notification_panel' for n in root.iter('node')):
                    self.e._adb(serial, 'shell', 'cmd', 'statusbar', 'collapse', timeout=8, check=True)
                    if not attempt:
                        time.sleep(.5)
                        continue
                    raise RuntimeError('A cortina de notificações está cobrindo o Minute')
                return root
            except (RuntimeError, subprocess.TimeoutExpired, ET.ParseError):
                if attempt:
                    raise
                time.sleep(.5)

    def tap(self, serial, node):
        bounds = re.fullmatch(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]', node.get('bounds', ''))
        if not bounds:
            raise RuntimeError('Botão sem posição válida')
        x1, y1, x2, y2 = map(int, bounds.groups())
        if x2 <= x1 or y2 <= y1 or node.get('enabled') == 'false':
            raise RuntimeError('Botão fora da tela ou desabilitado')
        self.e._adb(serial, 'shell', 'input', 'tap', str((x1+x2)//2), str((y1+y2)//2), timeout=5, check=True)

    def rotate_left(self, serial):
        for attempt in range(4):
            self.check_cancel()
            raw = self.e._adb(serial, 'emu', 'sensor', 'get', 'acceleration', timeout=5, check=True).stdout
            match = re.search(r'acceleration\s*=\s*([-\d.e+]+):([-\d.e+]+):', raw)
            if not match:
                raise RuntimeError('Não foi possível confirmar a orientação do emulador')
            x, y = map(float, match.groups())
            if x > 7 and abs(y) < 3:
                return
            # Console rotates the window and sensors, just like its toolbar button.
            if attempt == 3:
                break
            self.e._adb(serial, 'emu', 'rotate', timeout=5, check=True)
            time.sleep(.25)
        raise RuntimeError('Não foi possível girar para a esquerda')

    def launch_minute(self, serial):
        # Start the launcher activity directly instead of using the monkey event
        # runner, which can hang during a cold boot even after opening the app.
        for attempt in range(3):
            try:
                if self.minute_foreground(serial):
                    return
            except (RuntimeError, subprocess.TimeoutExpired):
                pass
            try:
                result = self.e._adb(serial, 'shell', 'am', 'start', '-n',
                    'com.bakerdata.minute/.MainActivity', timeout=30)
                diagnostics = result.stdout + '\n' + (result.stderr if isinstance(result.stderr, str) else '')
                if result.returncode == 0 and not re.search(r'^\s*Error', diagnostics, re.MULTILINE):
                    return
            except subprocess.TimeoutExpired:
                # A lost/late ADB acknowledgement does not mean launch failed.
                try:
                    if self.minute_foreground(serial):
                        return
                except (RuntimeError, subprocess.TimeoutExpired):
                    pass
            if attempt < 2:
                time.sleep(1)
        raise RuntimeError('O Minute não abriu em ' + serial + ' após 3 tentativas. Confira a resposta do celular.')

    def hide_keyboard(self, serial):
        # Stop the dump after the service visibility flag, before the IME's huge
        # client diagnostics. Some keyboards fail while dumping those clients.
        command = 'dumpsys input_method | grep -m 1 -E "mInputShown=|isInputViewShown="'
        for attempt in range(3):
            self.check_cancel()
            try:
                result = self.e._adb(serial, 'shell', command, timeout=8, check=False)
                visible = re.search(r'(?:mInputShown|isInputViewShown)=(true|false)\b', result.stdout)
                if result.returncode == 0 and visible:
                    if visible[1] == 'true':
                        # ENTER does not dismiss Gboard's clipboard panel. BACK
                        # closes the visible IME; verify it before tapping cards.
                        self.e._adb(serial, 'shell', 'input', 'keyevent', '4', timeout=8, check=True)
                    else:
                        return
            except subprocess.TimeoutExpired:
                pass
            if attempt < 2:
                if self.e.cancelar_sync.wait(.5):
                    self.check_cancel()
        raise RuntimeError('Não foi possível verificar o teclado em ' + serial + ' após 3 tentativas. Confira a conexão do celular.')

    def minute_foreground(self, serial):
        raw = self.e._adb(serial, 'shell', 'dumpsys', 'activity', 'activities', timeout=8, check=True).stdout
        return any('com.bakerdata.minute' in line for line in raw.splitlines()
                   if 'mResumedActivity' in line or 'topResumedActivity' in line)

    @staticmethod
    def visible(node):
        bound = re.fullmatch(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]', node.get('bounds', ''))
        return bool(bound and int(bound[3]) > int(bound[1]) and int(bound[4]) > int(bound[2]))

    def scroll_tasks(self, serial, down=True):
        nodes = list(self.xml(serial).iter('node'))
        container = next((n for n in nodes if n.get('resource-id') == 'home-tasks' and self.visible(n)), None)
        if container is None:
            raise RuntimeError('A lista do Minute não está visível; rolagem interrompida')
        x1, y1, x2, y2 = map(int, re.findall(r'\d+', container.get('bounds')))
        start, end = (.70, .30) if down else (.30, .70)
        self.e._adb(serial, 'shell', 'input', 'swipe', str((x1+x2)//2), str(int(y1+(y2-y1)*start)),
                    str((x1+x2)//2), str(int(y1+(y2-y1)*end)), '300', timeout=8, check=True)

    def task_list(self, serial):
        left_camera = False
        reopened = False
        system_waits = 0
        anr_restarted = False
        tips_dismissed = False
        for _ in range(10):
            self.check_cancel()
            if not self.minute_foreground(serial):
                if reopened:
                    raise RuntimeError('O Minute não ficou em primeiro plano; confira login ou permissões')
                self.mark(serial, stage='Reabrindo o Minute')
                self.launch_minute(serial)
                reopened = True
                time.sleep(1)
                continue
            # Native capture sometimes has no accessibility tree. Leave it once,
            # only after confirming both the foreground app and native camera.
            try:
                nodes = list(self.xml(serial).iter('node'))
            except (RuntimeError, subprocess.TimeoutExpired, ET.ParseError):
                if not left_camera and self.minute_foreground(serial) and self.e._camera_pronta(serial) is not None:
                    self.e._adb(serial, 'shell', 'input', 'keyevent', '4', timeout=8, check=True)
                    left_camera = True
                    time.sleep(1)
                    continue
                raise RuntimeError('Não consegui reconhecer a tela do Minute; navegação interrompida')
            if any(n.get('resource-id') in {'record-accept', 'minute-save'} for n in nodes):
                raise RuntimeError('Há uma gravação na tela de revisão; salve ou descarte antes de iniciar outra')
            system_wait = next((n for n in nodes if n.get('resource-id') == 'android:id/aerr_wait' and self.visible(n)), None)
            if system_wait is not None:
                if anr_restarted:
                    raise RuntimeError('O Minute continua sem responder após aguardar e reabrir o app; confira o celular')
                if system_waits:
                    # Only restart a confirmed task-list ANR during preparation.
                    # Unknown screens and pending capture/review must survive.
                    safe_list = any(n.get('resource-id') in {'nav-index', 'home-search-input', 'home-tasks'}
                                    and self.visible(n) for n in nodes)
                    if not safe_list or self.e._camera_pronta(serial) is not None:
                        raise RuntimeError('Minute sem responder em tela não segura para reabrir; captura preservada')
                    self.mark(serial, stage='Reabrindo o Minute após travamento')
                    self.e._adb(serial, 'shell', 'am', 'force-stop', 'com.bakerdata.minute', timeout=15, check=True)
                    self.check_cancel()
                    self.launch_minute(serial)
                    anr_restarted = True
                    self.wait_minute_ready(serial)
                    continue
                self.mark(serial, stage='Android sem responder — aguardando recuperação')
                self.tap(serial, system_wait)
                system_waits += 1
                if self.e.cancelar_sync.wait(5):
                    self.check_cancel()
                continue
            tips = next((n for n in nodes if n.get('resource-id') == 'recording-tips-got-it' and self.visible(n)), None)
            if tips is not None:
                if not tips_dismissed:
                    self.mark(serial, stage='Fechando dicas do Minute')
                    self.tap(serial, tips)
                    tips_dismissed = True
                time.sleep(1)
                continue
            nav = next((n for n in nodes if n.get('resource-id') == 'nav-index' and self.visible(n)), None)
            if nav is not None:
                self.tap(serial, nav)
                self.hide_keyboard(serial)
                return
            close = next((n for n in nodes if n.get('resource-id') in {'record-close', 'record-new-task'} and self.visible(n)), None)
            if close is not None:
                self.tap(serial, close)
            elif not left_camera and self.minute_foreground(serial) and self.e._camera_pronta(serial) is not None:
                # Native preview may return a valid but buttonless XML tree.
                # This is preparation only; review/save controls were checked above.
                self.e._adb(serial, 'shell', 'input', 'keyevent', '4', timeout=8, check=True)
                left_camera = True
                time.sleep(1)
            else:
                time.sleep(.5)
        raise RuntimeError('Não consegui abrir a lista de tarefas; confira a tela do Minute')

    def wait_minute_ready(self, serial, timeout=90):
        """ADB online does not mean the cold-started React Native screen is ready."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.check_cancel()
            try:
                if self.minute_foreground(serial):
                    if self.e._camera_pronta(serial) is not None:
                        return
                    nodes = list(self.xml(serial).iter('node'))
                    # Navigation handles Android's ANR dialog with a bounded
                    # Wait action; do not wait forever for the obscured app.
                    if any(n.get('resource-id') == 'android:id/aerr_wait' for n in nodes):
                        return
                    if any(n.get('package') == 'com.bakerdata.minute' and
                           (n.get('resource-id') in {'nav-index', 'home-search-input', 'record-close',
                                                    'record-new-task', 'record-accept', 'minute-save'} or
                            len(n.get('text', '').strip()) > 3) for n in nodes):
                        return
            except (RuntimeError, subprocess.TimeoutExpired, ET.ParseError):
                pass
            if self.e.cancelar_sync.wait(1):
                self.check_cancel()
        raise RuntimeError('O Minute não terminou de abrir em 90 segundos; confira o celular')

    def search_field(self, serial):
        for _ in range(10):
            self.check_cancel()
            nodes = list(self.xml(serial).iter('node'))
            field = next((n for n in nodes if n.get('resource-id') == 'home-search-input' and self.visible(n)), None)
            if field is not None:
                return field
            self.scroll_tasks(serial, down=False)
        raise RuntimeError('Campo de busca não encontrado na lista de tarefas')

    def set_query(self, serial, query):
        for _ in range(2):
            self.search_field(serial)
            write_query(serial, query)
            time.sleep(.8)
            nodes = list(self.xml(serial).iter('node'))
            actual = next((n for n in nodes if n.get('resource-id') == 'home-search-input'), None)
            if actual is not None and exact_text(search_text(actual)) == exact_text(query):
                self.hide_keyboard(serial)
                return
        raise RuntimeError('O campo de busca não confirmou o texto digitado; nenhuma tarefa foi iniciada')

    def navigate(self, serial, task):
        self.task_list(serial)
        queries = [task.strip()]
        deadline = time.monotonic() + 60
        for query in queries:
            self.check_cancel()
            if time.monotonic() >= deadline:
                break
            self.mark(serial, stage='Buscando: '+(query or 'lista completa'))
            self.set_query(serial, query)
            previous = None
            unchanged = 0
            for _ in range(4):
                self.check_cancel()
                if time.monotonic() >= deadline:
                    break
                nodes = list(self.xml(serial).iter('node'))
                cards = [n for n in nodes if n.get('resource-id', '').startswith(('task-card-', 'featured-card-')) and self.visible(n)]
                matches = [n for n in cards if normalize(n.get('content-desc', '').split(',')[0]) == normalize(task)]
                if not matches:
                    matches = [n for n in cards if task_key(n.get('content-desc', '').split(',')[0]) == task_key(task)]
                    titles = {normalize(n.get('content-desc', '').split(',')[0]) for n in matches}
                    if len(titles) > 1:
                        raise RuntimeError('Mais de uma tarefa parecida encontrada. Informe o título exato: '+ '; '.join(sorted(titles)))
                if matches:
                    card = matches[0]
                    x1,y1,x2,y2 = map(int,re.findall(r'\d+',card.get('bounds')))
                    footers = [int(re.findall(r'\d+',n.get('bounds'))[1]) for n in nodes
                               if n.get('resource-id') in {'nav-index','nav-minutes','nav-settings'} and self.visible(n)]
                    if footers: y2=min(y2,min(footers)-8)
                    if y2-y1 >= 40:
                        card.set('bounds',f'[{x1},{y1}][{x2},{y2}]')
                        self.mark(serial, stage='Tarefa encontrada: '+card.get('content-desc', '').split(',')[0])
                        self.tap(serial, card)
                        self.finish_camera(serial, card.get('resource-id'))
                        return
                signature = tuple((n.get('resource-id'), n.get('bounds')) for n in cards)
                unchanged = unchanged+1 if signature == previous else 0
                previous = signature
                if unchanged >= 2:
                    break
                self.scroll_tasks(serial)
        raise RuntimeError('Tarefa não encontrada: '+task+'. Confira o nome completo e se ela está disponível nesta conta.')

    def finish_camera(self, serial, card_id=None):
        for attempt in range(8):
            self.check_cancel()
            try:
                root = self.xml(serial)
            except (subprocess.TimeoutExpired, RuntimeError, ET.ParseError):
                # Native camera preview may not expose an idle accessibility tree.
                if self.e._camera_pronta(serial) is not None:
                    return
                continue
            # Only known task workflow buttons, never arbitrary dialogs.
            button = next((n for n in root.iter('node') if n.get('resource-id') in
                           {'record-start-task', 'recording-tips-got-it'}), None)
            if button is None:
                if self.e._camera_pronta(serial) is not None:
                    return
                # A tap can merely dismiss the keyboard and move the result card.
                # Retry only the same identified card using its new visible bounds.
                if card_id and attempt in {1, 3}:
                    card = next((n for n in root.iter('node') if n.get('resource-id') == card_id and self.visible(n)), None)
                    if card is not None:
                        x1,y1,x2,y2 = map(int,re.findall(r'\d+',card.get('bounds')))
                        footer = [int(re.findall(r'\d+',n.get('bounds'))[1]) for n in root.iter('node')
                                  if n.get('resource-id') == 'nav-index' and self.visible(n)]
                        if footer: y2 = min(y2, min(footer)-8)
                        if y2-y1 >= 40:
                            card.set('bounds',f'[{x1},{y1}][{x2},{y2}]')
                            self.tap(serial, card)
                # A task tap can return an accessibility snapshot of the old
                # list while the detail screen is still mounting.
                time.sleep(.5)
                continue
            self.tap(serial, button)
            if button.get('resource-id') == 'recording-tips-got-it':
                for _ in range(10):
                    self.check_cancel()
                    time.sleep(.5)
                    if self.e._camera_pronta(serial) is not None:
                        return
            time.sleep(.4)
        raise RuntimeError('A câmera da tarefa não abriu')

    def wait_recording(self, serial, before, triggered_at):
        # A session directory can exist before the ten-second countdown finishes.
        if self.e.cancelar_sync.wait(max(0, triggered_at + 10 - time.monotonic())):
            self.check_cancel()
        end = time.monotonic() + 60
        session = self.e._esperar_gravacao(serial, before, end)
        if not re.fullmatch(r'[A-Za-z0-9_-]+', session):
            raise RuntimeError('Identificador de gravação inválido')
        previous = None
        path = '/data/user/0/com.bakerdata.minute/files/recordings/' + session + '/video.mp4'
        while time.monotonic() < end:
            self.check_cancel()
            raw = self.e._shell_root(serial, 'if [ -f ' + path + ' ]; then stat -c %s ' + path + '; else echo 0; fi', timeout=12, check=True).stdout.strip()
            size = int(raw)
            if previous is not None and size > previous and previous > 0:
                return session
            previous = size
            if self.e.cancelar_sync.wait(1):
                self.check_cancel()
        raise RuntimeError('A contagem terminou, mas o arquivo de vídeo não está crescendo; confira o celular')

    def run(self, targets, prepare, installed, task='', auto=True, repeat=False):
        self.e.cancelar_sync.clear()
        self.stop_after_round.clear()
        if repeat and (not auto or not task.strip()):
            raise ValueError('Para repetir, use a busca automática e informe o nome completo da tarefa.')
        cycle = 0
        completed = 0
        self.update(loopActive=repeat, loopStopping=False, loopCycle=0, loopCompleted=0)
        try:
            while True:
                self.check_cancel()
                if cycle and self.stop_after_round.is_set():
                    break
                cycle += 1
                self.update(loopCycle=cycle, message=f'Preparando rodada {cycle}...')
                self._run_cycle(targets, prepare, installed, task, auto, keep_busy=repeat)
                saved = all(r.get('stage') == 'Salvo' for r in self.snapshot().values())
                saved = saved and len(self.snapshot()) == len(targets) and bool(targets)
                if saved:
                    completed += 1
                self.update(loopCompleted=completed)
                if not repeat or not saved or self.e.cancelar_sync.is_set() or self.stop_after_round.is_set():
                    break
                self.update(message=f'Rodada {cycle} salva. Reiniciando o vídeo e a tarefa...')
            if repeat and saved:
                self.update(message=f'Loop encerrado. {completed} rodada(s) salva(s).')
        finally:
            self.update(busy=False, loopActive=False, loopStopping=False)

    def _run_cycle(self, targets, prepare, installed, task='', auto=True, keep_busy=False, tolerate_failures=False, require_all_ready=False):
        with self.lock:
            self.rows = {s: {'name': n, 'stage': 'Aguardando', 'elapsed': 0, 'total': 0, 'percent': 0}
                         for n, (s, _) in targets.items()}
        if not targets:
            raise ValueError('Nenhum celular selecionado')
        records = [installed.get(s, {}) for s, _ in targets.values()]
        if any(not (r.get('confirmed') or (r.get('staged') and r.get('mode') == 'shared')) or not r.get('assetId') for r in records):
            raise ValueError('Instale e confirme o vídeo na aba Vídeos em todos os celulares participantes.')
        if len({r['assetId'] for r in records}) != 1:
            raise ValueError('Os celulares têm vídeos diferentes. Use “Usar em todos” na aba Vídeos.')
        if auto and not task.strip():
            raise ValueError('Informe o nome completo da tarefa para a busca automática.')
        self.update(task=task, elapsed=0, total=0, progress=0, message='Preparando os celulares...')
        durations = {}
        def ready(item, attempt=0):
            name, (s, port) = item
            try:
                self.check_cancel()
                self.mark(s, stage='Ligando e girando à esquerda', video=installed[s].get('name', ''))
                prepare(name, s, port)
                self.e._escrever_controle(s, 'pause', self.e._ler_geracao(s)+1)
                self.rotate_left(s)
                if auto:
                    self.mark(s, stage='Procurando a tarefa')
                    self.navigate(s, task)
                else:
                    self.finish_camera(s)
                self.check_cancel()
                value = self.e._camera_pronta(s)
                if value is None:
                    raise RuntimeError('A câmera da tarefa não está pronta')
                durations[s] = recording_duration(value)
                if auto:
                    remaining = 7200 - self.task_usage(name, task)
                    if remaining < 90:
                        raise RuntimeError('Limite diário de 2 horas insuficiente para esta gravação')
                    durations[s] = min(durations[s], remaining)
                self.mark(s, stage='Pronto', total=durations[s], error='')
            except Exception as exc:
                transient = re.search(r"device\s+['\"]?[^\n]*not found|device offline|device still authorizing|no devices/emulators found|ADB n[aã]o respondeu|timed out", str(exc), re.I)
                # Only retry preparation: no recording button has been pressed.
                # Never replay commands during capture or saving.
                if not tolerate_failures and transient and 'unauthorized' not in str(exc).lower() and attempt < 2:
                    self.mark(s, stage='Reconectando antes de gravar', error=str(exc))
                    try:
                        self.wait_preparation_connection(s)
                    except Exception as reconnect_error:
                        self.mark(s, stage='Erro na preparação', error=str(reconnect_error))
                        raise
                    return ready(item, attempt + 1)
                self.mark(s, stage='Erro na preparação', error=str(exc))
                raise
        # Retry only task navigation, before any recording worker is created.
        # Join every preparation worker before revisiting the entire group.
        attempts = 3 if auto and require_all_ready else 1
        recoverable = (
            'A lista do Minute não está visível',
            'Não consegui abrir a lista de tarefas',
            'Não consegui reconhecer a tela do Minute',
            'O Minute não ficou em primeiro plano',
            'O Minute não abriu em ',
            'A câmera da tarefa não está pronta',
        )
        for preparation_attempt in range(attempts):
            durations.clear()
            errors = []
            with concurrent.futures.ThreadPoolExecutor(max_workers=min(2, len(targets))) as pool:
                for future in [pool.submit(ready, item) for item in targets.items()]:
                    try:
                        future.result()
                    except Exception as exc:
                        errors.append(exc)
            self.check_cancel()
            if not errors:
                break
            retry = (preparation_attempt + 1 < attempts and
                     all(isinstance(exc, RuntimeError) and str(exc).startswith(recoverable) for exc in errors))
            if retry:
                for serial, _ in targets.values():
                    self.mark(serial, stage='Aguardando nova busca em grupo')
                self.update(stage='Recuperando busca da tarefa', level='warn',
                    message=f'Um celular não ficou pronto. Nova busca nos {len(targets)} aparelhos em 5 segundos (tentativa {preparation_attempt+2}/{attempts}).')
                if self.e.cancelar_sync.wait(5):
                    self.check_cancel()
                self.check_cancel()
                continue
            if require_all_ready or not tolerate_failures:
                raise RuntimeError('Gravação não iniciada: '+'; '.join(map(str, errors)))
            break
        self.check_cancel()
        if tolerate_failures and not require_all_ready:
            ready_rows=self.snapshot()
            targets = {name: pair for name, pair in targets.items() if ready_rows.get(pair[0],{}).get('stage')=='Pronto'}
            if not targets:
                return
        coordinated = tolerate_failures or require_all_ready
        start_timeout = 360 if require_all_ready else 90
        barrier = (RecordingStartGroup([s for s,_ in targets.values()],self.check_cancel,allow_partial=not require_all_ready)
                   if coordinated else threading.Barrier(len(targets)))
        task_ids = {}
        def record(name, s):
            triggered = False
            capture_confirmed = False
            started = None
            generation = None
            try:
                generation = self.e._ler_geracao(s)+1
                self.e._escrever_controle(s, 'pause', generation)
                before = self.e._pastas_gravacao(s)
                if self.recovery:
                    self.recovery.checkpoint(s,phone=name,task=task,day=self.e._hoje(),before=sorted(before),startedAt=time.time())
                if coordinated:barrier.wait(s,0,timeout=start_timeout)
                else:barrier.wait(timeout=90)
                self.check_cancel()
                self.mark(s, stage='Contagem do Minute')
                trigger_time = time.monotonic()
                triggered = True
                self.e._tocar_botao_gravacao(s)
                session = self.wait_recording(s, before, trigger_time)
                if self.recovery:self.recovery.checkpoint(s,session=session)
                capture_confirmed = True
                task_id, actual = self.e._detectar_tarefa_sessao(s, session)
                task_ids[s] = task_id
                if auto and task_key(actual) != task_key(task):
                    raise RuntimeError('Tarefa aberta diferente da escolhida: '+actual)
                if self.recovery and not auto:self.recovery.checkpoint(s,task=actual)
                if self.task_usage(name, actual)+durations[s] > 7200:
                    raise RuntimeError('Limite diário insuficiente')
                self.mark(s, task=actual, stage='Sincronizando o início')
                if coordinated:barrier.wait(s,1,timeout=start_timeout)
                else:barrier.wait(timeout=90)
                active=barrier.active() if coordinated else None
                active_ids={value for serial,value in dict(task_ids).items() if active is None or serial in active}
                if len(active_ids) != 1:
                    raise RuntimeError('Os celulares estão em tarefas diferentes')
                self.check_cancel()
                self.update(task=actual)
                self.e._escrever_controle(s, 'play', generation)
                started = time.monotonic()
                remaining_daily = 7200-self.task_usage(name, actual)
                deadline = min(stop_deadline(started, trigger_time, durations[s]), trigger_time+remaining_daily-1)
                target = deadline-started
                if target < 60:
                    raise RuntimeError('Preparação demorou demais para gravar com segurança')
                next_health_check = started
                last_growth = started
                last_size = 0
                recording_path = '/data/user/0/com.bakerdata.minute/files/recordings/' + session + '/video.mp4'
                while True:
                    now = time.monotonic()
                    if now >= next_health_check:
                        next_health_check = now + 10
                        if not self.minute_foreground(s) or self.e._camera_pronta(s) is None:
                            # The camera may already be closed. Never tap blindly:
                            # a stop tap could start a new recording instead.
                            triggered = False
                            raise RuntimeError('Minute saiu da câmera durante a gravação. Confira o trecho pendente; tempo não contabilizado.')
                        raw = self.e._shell_root(s, 'stat -c %s ' + recording_path,
                                                 timeout=12, check=True).stdout.strip()
                        current_size = int(raw.splitlines()[-1])
                        if current_size > last_size:
                            last_size, last_growth = current_size, now
                        elif now - last_growth >= 30:
                            raise RuntimeError('O arquivo de vídeo parou de crescer por 30 segundos. Confira a gravação antes de retomar.')
                    elapsed = min(time.monotonic()-started, target)
                    self.mark(s, stage='Gravando', elapsed=elapsed, total=target, percent=min(99, int(elapsed/target*100)))
                    if self.e.cancelar_sync.wait(min(.1, max(0, deadline-time.monotonic()))) or time.monotonic() >= deadline:
                        break
                elapsed = min(time.monotonic()-started, target)
                self.mark(s, stage='Encerrando', elapsed=elapsed)
                self.e._tocar_botao_gravacao(s)
                triggered = False
                recorded_seconds = min(MAX_SECONDS, time.monotonic()-trigger_time)
                # Once stopped, save even if the user requested early stop.
                self.mark(s, stage='Salvando')
                if elapsed < 60:
                    self.mark(s, stage='Interrompido: gravação curta; confira o Minute')
                    return
                try:
                    self.save(s)
                except RuntimeError:
                    raw = self.e._shell_root_bytes(s, 'cat /data/user/0/com.bakerdata.minute/files/mmkv/recording-store', timeout=12)
                    confirmed = confirmed_recording_seconds(raw, session)
                    if confirmed is None:
                        raise
                    recorded_seconds = min(recorded_seconds, confirmed)
                if self.recovery:self.recovery.credit(s,recorded_seconds)
                else:self.e._somar_uso_tarefa(name, actual, recorded_seconds)
                self.mark(s, stage='Salvo', percent=100, elapsed=elapsed)
            except Exception as exc:
                if coordinated:barrier.drop(s)
                else:barrier.abort()
                if isinstance(exc, threading.BrokenBarrierError):
                    exc = RuntimeError('Outro celular falhou ou demorou para confirmar a gravação; início em grupo cancelado')
                if triggered:
                    try:
                        # Back cancels countdown or leaves capture; a second record
                        # tap could START capture after an unconfirmed first tap.
                        if capture_confirmed and self.minute_foreground(s) and self.e._camera_pronta(s) is not None:
                            self.e._tocar_botao_gravacao(s)
                        elif self.minute_foreground(s) and self.e._camera_pronta(s) is not None:
                            self.e._adb(s, 'shell', 'input', 'keyevent', '4', timeout=12, check=True)
                    except Exception as stop_error:
                        exc = RuntimeError(str(exc)+'; falha ao parar: '+str(stop_error))
                self.mark(s, stage='Erro — confira o celular', error=str(exc))
            finally:
                try:
                    if generation is not None:
                        self.e._escrever_controle(s, 'pause', generation)
                except Exception:
                    pass
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(targets)) as pool:
            futures = [pool.submit(record, n, s) for n, (s, _) in targets.items()]
            while any(not f.done() for f in futures):
                rows = list(self.snapshot().values())
                self.update(elapsed=min(r['elapsed'] for r in rows), total=max(r['total'] for r in rows),
                            progress=int(sum(r['percent'] for r in rows)/len(rows)), message='Automação em andamento; acompanhe cada celular abaixo.')
                time.sleep(.2)
            for future in futures:
                future.result()
        rows = list(self.snapshot().values())
        saved = sum(r['stage'] == 'Salvo' for r in rows)
        self.update(busy=keep_busy, progress=100 if saved == len(rows) else 0,
                    level='ok' if saved == len(rows) else 'warn',
                    message=f'{saved} de {len(rows)} celulares salvos. '+('Concluído.' if saved == len(rows) else 'Confira os resultados por celular.'))

    def save(self, serial, pause_preview=True):
        # Independent of the stop event: stopping must not skip the Save button.
        if pause_preview:
            # Minute autoplays the just-recorded preview. Its moving seek bar
            # prevents UIAutomator reaching idle; pause via the preview surface.
            end_transition = time.monotonic()+180
            while time.monotonic()<end_transition:
                if self.e._camera_pronta(serial) is None:
                    break
                # Android can retain EgoCameraPreview in the activity tree
                # after capture ends. A visible review is stronger evidence.
                try:
                    review = self.xml(serial)
                    if any(n.get('resource-id') in {'record-accept', 'minute-save'}
                           or n.get('text') in {'Minute salvo.', 'Salvar este Minute?'}
                           for n in review.iter('node')):
                        break
                except (subprocess.TimeoutExpired, RuntimeError, ET.ParseError):
                    pass
                time.sleep(.2)
            else:
                # XML reads can outlast the deadline while the moving review
                # prevents accessibility from becoming idle. Check native state
                # again: it may have closed during that last blocking read.
                if self.e._camera_pronta(serial) is not None:
                    raise RuntimeError('A tela de gravação não encerrou; confira o celular imediatamente')
            time.sleep(.5)
        end = time.monotonic()+45
        clicked = False
        confirmed_clicked = False
        preview_recovery = False
        while time.monotonic() < end:
            try:
                root = self.xml(serial)
            except (subprocess.TimeoutExpired, RuntimeError, ET.ParseError):
                # A moving preview can prevent UIAutomator from ever reaching
                # idle. Recover once, only before any save click and after the
                # native camera has closed; never toggle a readable preview.
                if pause_preview and not clicked and not preview_recovery:
                    preview_recovery = True
                    if self.minute_foreground(serial) and self.e._camera_pronta(serial) is None:
                        raw = self.e._adb(serial, 'shell', 'wm', 'size', timeout=5, check=True).stdout
                        sizes = re.findall(r'(\d+)x(\d+)', raw)
                        if sizes:
                            width, height = map(int, sizes[-1])
                            self.e._adb(serial, 'shell', 'input', 'tap', str(width//2), str(height//2), timeout=5, check=True)
                            end = time.monotonic()+45
                time.sleep(.5)
                continue
            nodes = list(root.iter('node'))
            if any(n.get('text') == 'Minute salvo.' for n in nodes):
                return
            confirm = any(n.get('text') == 'Salvar este Minute?' for n in nodes)
            if confirm:
                accept = next((n for n in nodes if n.get('clickable') == 'true' and
                               (n.get('content-desc') == 'Salvar' or n.get('text') == 'Salvar')), None)
                if accept is not None and not confirmed_clicked:
                    self.tap(serial, accept)
                    clicked = True
                    confirmed_clicked = True
                    time.sleep(.5)
                    continue
            button = next((n for n in nodes if n.get('resource-id') in {'minute-save', 'record-accept'}), None)
            if button is not None and not clicked:
                self.tap(serial, button)
                clicked = True
            elif clicked and any(n.get('resource-id') in {'nav-index', 'nav-minutes'} for n in nodes):
                return
            time.sleep(.5)
        raise RuntimeError('O Minute não confirmou o retorno após salvar; confira o celular')
