"""Bounded audio prefetch queue: OpenAI writes, local OmniVoice synthesizes."""
from collections import deque
import atexit
import threading
import time
import random
import re
from voice_manager import read_json


class LiveVoice:
    def __init__(self, voice, writer):
        self.voice, self.writer = voice, writer
        self.lock = threading.RLock()
        self.cancel = threading.Event()
        self.thread = None
        self.sales = deque()
        self.sale_orders = set()
        self.sale_min, self.sale_max = 30, 90
        self.sale_due = float('inf')
        self.sale_announced = 0
        self.last_pseudonym = None
        self.stock = dict(product='', remaining=None, revision=0)
        self.state = dict(active=False, message='Informe o produto e prepare uma amostra.',
                          queued=0, generated=0, played=0, requests=0, tokens=0)
        atexit.register(self.stop)

    def snapshot(self):
        with self.lock:
            return dict(self.state, apiKeyConfigured=self.writer.configured(), product=self.writer.product(), stock=dict(self.stock),
                        sales=dict(queued=len(self.sales), announced=self.sale_announced,
                                   minimum=self.sale_min, maximum=self.sale_max))

    def update_stock(self, product, remaining):
        if not isinstance(product, str) or not 1 <= len(product.strip()) <= 120:
            raise ValueError('Preencha o nome do produto antes de salvar o estoque promocional.')
        if remaining is not None and (type(remaining) is not int or not 0 <= remaining <= 1000000):
            raise ValueError('Informe uma quantidade inteira entre 0 e 1000000.')
        with self.lock:
            self.stock = dict(product=product.strip(), remaining=remaining, revision=self.stock['revision'] + 1)
            if self.state.get('active'):
                if remaining == 0:
                    self.stop()
                    self.state['message'] = 'Estoque promocional esgotado. Parando as falas; atualize antes de reiniciar.'
                else:
                    self.voice.stop('playback')
                    self.state['message'] = 'Estoque atualizado. Renovando as falas com a informação atual.'

    def configure_sales(self, minimum, maximum):
        if type(minimum) is not int or type(maximum) is not int or not 10 <= minimum <= maximum <= 3600:
            raise ValueError('Use intervalos de 10 a 3600 segundos; o máximo deve ser maior ou igual ao mínimo.')
        with self.lock:
            self.sale_min, self.sale_max = minimum, maximum

    def add_sale(self, order, confirmed):
        return dict(pseudonym=self.add_sales([dict(order=order)], confirmed)['pseudonyms'][0])

    def add_sales(self, entries, confirmed):
        if confirmed is not True:
            raise ValueError('Confirme que todas as vendas foram concluídas.')
        if not isinstance(entries, list) or not 1 <= len(entries) <= 50:
            raise ValueError('Adicione de 1 a 50 pedidos por envio. Você pode enviar mais lotes depois.')
        validated, orders = [], set()
        for entry in entries:
            if not isinstance(entry, dict):
                raise ValueError('Pedido inválido.')
            order = entry.get('order')
            real_name = 'name' in entry
            alias = entry.get('name') if real_name else entry.get('alias', '')
            if not isinstance(order, str) or not re.fullmatch(r'[\w-]{1,80}', order):
                raise ValueError('Cada linha precisa do código do pedido: até 80 letras, números ou hífens.')
            if order in orders:
                raise ValueError('Há códigos de pedido repetidos neste lote. Nenhum pedido foi adicionado.')
            if not isinstance(alias, str) or (real_name and not alias.strip()) or len(alias) > 60 or any(not (c.isalpha() or c in " '-") for c in alias):
                raise ValueError('Use nomes de até 60 caracteres, somente letras, espaços, hífens ou apóstrofos.')
            orders.add(order)
            validated.append((order, alias.strip(), real_name))
        with self.lock:
            if not self.state.get('active') or not self.state.get('continuous') or self.cancel.is_set():
                raise ValueError('Inicie as falas contínuas antes de registrar os avisos de venda.')
            if orders & self.sale_orders:
                raise ValueError('Um pedido deste lote já foi registrado. Nenhum pedido foi adicionado.')
            if len(self.sales) + len(entries) > 1000 or len(self.sale_orders) + len(entries) > 10000:
                raise ValueError('Limite de pedidos atingido (1000 pendentes ou 10000 por execução).')
            names = ('Ana Gabriela', 'Mariana', 'Juliana', 'Camila', 'Beatriz',
                     'Rafael', 'Lucas', 'Gabriel', 'Bruno', 'Daniel', 'Clara', 'Helena')
            pseudonyms = []
            for order, alias, real_name in validated:
                pseudonym = alias or random.choice([name for name in names if name != self.last_pseudonym])
                self.last_pseudonym = pseudonym
                speech = (f'{pseudonym}, obrigada pela sua compra e pela confiança!' if real_name else
                          'Compra confirmada! Para preservar a privacidade, '
                          f'vou usar o nome fictício {pseudonym}. Obrigada pela compra e pela confiança, {pseudonym}!')
                self.sales.append(speech)
                self.sale_orders.add(order)
                pseudonyms.append(pseudonym)
            if self.sale_due == float('inf'):
                self.sale_due = time.monotonic() + random.uniform(self.sale_min, self.sale_max)
            return dict(added=len(pseudonyms), names=pseudonyms, pseudonyms=pseudonyms)

    def start(self, product, output='', volume=.8, minutes=60, steps=32, continuous=True):
        with self.lock:
            if self.thread and self.thread.is_alive():
                raise ValueError('Aguarde a sessão anterior parar.')
            if any(self.voice.jobs.values()):
                raise ValueError('Aguarde ou pare a fala atual primeiro.')
            if not self.voice.installed():
                raise ValueError('Instale o OmniVoice primeiro.')
            if not self.writer.configured():
                raise ValueError('Salve sua chave da OpenAI primeiro.')
            if steps not in (16, 32) or minutes not in (0, 15, 30, 60, 120):
                raise ValueError('Configuração da sessão inválida.')
            if not isinstance(volume, (float, int)) or not 0 <= volume <= 1:
                raise ValueError('Volume inválido.')
            if continuous and not any(row['key'] == output for row in self.voice.output_devices):
                raise ValueError('Selecione a saída de áudio da live.')
            product = self.writer.save_product(product)
            if self.stock['product'] == product['name'] and self.stock['remaining'] == 0:
                raise ValueError('Estoque promocional zerado. Atualize a quantidade ou desative a menção antes de iniciar.')
            self.cancel = threading.Event()
            self.state = dict(active=True, message='Preparando roteiro com a OpenAI...', queued=0,
                              generated=0, played=0, requests=0, tokens=0, script='', error=False,
                              continuous=continuous, minutes=minutes, started=time.time())
            self.thread = threading.Thread(target=self._run,
                args=(product, output, volume, minutes, steps, continuous), daemon=True)
            self.thread.start()

    def stop(self):
        with self.lock:
            self.cancel.set()
            if self.state['active']:
                self.voice.stop('generation')
                self.voice.stop('playback')
                self.state['message'] = 'Parando. Uma solicitação à OpenAI já enviada pode terminar.'

    def update(self, **values):
        with self.lock:
            self.state.update(values)

    def _run(self, product, output, volume, minutes, steps, continuous):
        queue, history = deque(), []
        pending = None
        pending_sale = False
        revision = self.stock['revision']
        pending_revision = revision
        sale_clips = set()
        playback = None
        started_playing = False
        deadline = time.monotonic() + minutes * 60 if minutes else float('inf')
        try:
            while not self.cancel.is_set() and time.monotonic() < deadline:
                with self.lock:
                    if revision != self.stock['revision']:
                        revision = self.stock['revision']
                        queue = deque(ident for ident in queue if ident in sale_clips)
                        history.clear()
                        self.update(queued=len(queue))
                with self.voice.lock:
                    generating = self.voice.jobs['generation'] is not None
                    playing = self.voice.jobs['playback'] is not None
                    generation_state = dict(self.voice.states['generation'])
                    playback_state = dict(self.voice.states['playback'])
                if pending and not generating:
                    if not pending_sale and pending_revision != revision:
                        pending = None
                        continue
                    clip = read_json(self.voice.clip_path(pending).with_suffix('.json'), {})
                    if not clip:
                        raise ValueError(generation_state.get('message', 'A voz não foi gerada.'))
                    if pending_sale:
                        queue.appendleft(pending)
                        sale_clips.add(pending)
                        pending_sale = False
                    else:
                        queue.append(pending)
                    pending = None
                    self.update(generated=self.state['generated'] + 1, queued=len(queue))
                    if not continuous:
                        self.update(message='Amostra pronta na biblioteca. Ouça antes de iniciar.', lastClip=queue[0])
                        return
                if playback and not playing:
                    if playback_state.get('error'):
                        raise ValueError(playback_state['message'])
                    self.update(played=self.state['played'] + 1)
                    if playback in sale_clips:
                        sale_clips.remove(playback)
                        with self.lock:
                            self.sale_announced += 1
                            self.sale_due = time.monotonic() + random.uniform(self.sale_min, self.sale_max) if self.sales else float('inf')
                    playback = None
                # Start with two complete files, then synthesize ahead of playback.
                if not playing and queue and (started_playing or len(queue) >= 2):
                    with self.lock:
                        if revision != self.stock['revision'] or self.cancel.is_set():
                            continue
                        playback = queue.popleft()
                        self.voice.play(playback, output, volume)
                    started_playing = True
                    self.update(queued=len(queue), message='Falando sobre o produto e preparando as próximas falas.')
                sale_name = None
                with self.lock:
                    if continuous and not pending and not sale_clips and self.sales and time.monotonic() >= self.sale_due:
                        sale_name = self.sales.popleft()
                        self.sale_due = float('inf')
                if sale_name:
                    pending = self.voice.generate(sale_name, sale_demo=True)
                    pending_sale = True
                    self.update(message='Preparando o agradecimento de uma venda confirmada.')
                elif not pending and len(queue) < 2:
                    with self.lock:
                        pending_revision = self.stock['revision']
                        stock = dict(self.stock) if self.stock['product'] == product['name'] else None
                    self.update(message='Criando a próxima fala com a OpenAI...', requests=self.state['requests'] + 1)
                    text, usage = self.writer.write(product, history, stock=stock)
                    if self.cancel.is_set() or time.monotonic() >= deadline:
                        break
                    if pending_revision != self.stock['revision']:
                        continue
                    history.append(text)
                    history = history[-3:]
                    self.update(script=text, tokens=self.state['tokens'] + usage.get('total_tokens', 0))
                    pending = self.voice.generate(text, steps=steps, target_duration=60,
                        seed=42 + self.state['generated'])
                    self.update(message='Gerando áudio local; a primeira preparação precisa de duas falas.')
                self.cancel.wait(.1)
        except Exception as error:
            self.update(error=True, message=str(error))
        finally:
            if continuous or self.cancel.is_set() or self.state.get('error'):
                self.voice.stop('generation')
                self.voice.stop('playback')
            with self.lock:
                self.state['active'] = False
                self.sales.clear()
                self.sale_due = float('inf')
                if not self.state.get('error') and (continuous or self.cancel.is_set()):
                    self.state['message'] = 'Sessão encerrada. As falas geradas ficaram salvas.'
