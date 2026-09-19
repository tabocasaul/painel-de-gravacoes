"""Remember the next source in each task's ordered video list."""
import hashlib
import json
import os
import uuid

from automation import task_key


class InterleavedVideoRotation:
    def __init__(self, path=None):
        # Resolve configured Windows Junction chains before creating a new
        # sibling file: the logical C: alias can report false name collisions.
        self.path = os.path.realpath(os.path.abspath(path)) if path is not None else None
        self.positions = {}
        self.pending_round = None
        if self.path is not None:
            try:
                with open(self.path, encoding='utf-8') as stream:
                    saved = json.load(stream)
            except FileNotFoundError:
                return
            except (OSError, ValueError) as exc:
                raise RuntimeError('Não foi possível ler a sequência de vídeos salva.') from exc
            if (not isinstance(saved, dict) or saved.get('version') != 1
                    or not isinstance(saved.get('positions'), dict)
                    or any(not isinstance(key, str) or type(value) is not int or value < 0
                           for key, value in saved['positions'].items())):
                raise RuntimeError('A sequência de vídeos salva está inválida.')
            self.positions = saved['positions']
            pending = saved.get('pendingRound')
            if pending is not None:
                if (not isinstance(pending, dict) or not isinstance(pending.get('id'), str)
                        or not pending['id'] or not isinstance(pending.get('key'), str)
                        or type(pending.get('index')) is not int or type(pending.get('count')) is not int
                        or not 0 <= pending['index'] < pending['count']
                        or not isinstance(pending.get('serials'), list) or not pending['serials']
                        or any(not isinstance(serial, str) or not serial for serial in pending['serials'])
                        or len(set(pending['serials'])) != len(pending['serials'])):
                    raise RuntimeError('A rodada pendente da sequência de vídeos está inválida.')
                if 'allowPartial' in pending and type(pending['allowPartial']) is not bool:
                    raise RuntimeError('A regra da rodada pendente está inválida.')
                self.pending_round = pending

    @staticmethod
    def _key(task, videos):
        content = json.dumps([task_key(task), videos], ensure_ascii=False, separators=(',', ':'))
        return hashlib.sha256(content.encode('utf-8')).hexdigest()

    def position(self, task, videos):
        index = self.positions.get(self._key(task, videos), 0)
        if not videos or not 0 <= index < len(videos):
            raise RuntimeError('A posição salva da sequência de vídeos está inválida.')
        return index

    def advance(self, task, videos, index):
        if self.position(task, videos) != index:
            raise RuntimeError('A sequência de vídeos mudou durante a rodada.')
        updated = dict(self.positions)
        updated[self._key(task, videos)] = (index + 1) % len(videos)
        pending = self.pending_round
        if pending and pending['key'] == self._key(task, videos) and pending['index'] == index:
            pending = None
        self._save(updated, pending)

    def begin_round(self, task, videos, index, targets, allow_partial=False):
        if self.position(task, videos) != index:
            raise RuntimeError('A sequência de vídeos mudou durante a rodada.')
        pending = dict(id=uuid.uuid4().hex, key=self._key(task, videos), index=index,
                       count=len(videos), serials=[serial for serial, _ in targets.values()],allowPartial=bool(allow_partial))
        self._save(self.positions, pending)

    def reconcile(self, ledger):
        """Advance a recovered round only from receipts for its exact capture group."""
        pending = self.pending_round
        if pending is None:
            return False
        confirmed = {entry.get('serial') for entry in ledger.values()
                     if isinstance(entry, dict) and entry.get('interleavedRound') == pending['id']}
        if not (bool(set(pending['serials']) & confirmed) if pending.get('allowPartial')
                else set(pending['serials']) <= confirmed):
            return False
        if self.positions.get(pending['key'], 0) != pending['index']:
            raise RuntimeError('A posição da rodada recuperada precisa ser conferida.')
        updated = dict(self.positions)
        updated[pending['key']] = (pending['index'] + 1) % pending['count']
        self._save(updated, None)
        return True

    def require_all(self):
        """A manual cancellation retains the original all-saved recovery rule."""
        if self.pending_round and self.pending_round.get('allowPartial'):
            self._save(self.positions,dict(self.pending_round,allowPartial=False))

    def _save(self, updated, pending):
        if self.path is not None:
            temporary = None
            try:
                directory = os.path.dirname(self.path)
                os.makedirs(directory, exist_ok=True)
                # Windows tempfile treats some permission failures as name
                # collisions and can retry hundreds of thousands of times.
                # Retry only a real collision, with an explicit small bound.
                for _ in range(3):
                    candidate = os.path.join(directory, '.interleaved-videos-'+uuid.uuid4().hex+'.tmp')
                    try:
                        stream = open(candidate, 'x', encoding='utf-8')
                    except FileExistsError:
                        continue
                    temporary = candidate
                    break
                else:
                    raise RuntimeError('Não foi possível criar o controle da sequência após três tentativas. Tente iniciar novamente.')
                with stream:
                    json.dump({'version': 1, 'positions': updated, 'pendingRound': pending}, stream, ensure_ascii=False)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, self.path)
            except PermissionError as exc:
                raise RuntimeError('Sem permissão para guardar a sequência de vídeos na pasta de dados. A sequência não foi atualizada; verifique o acesso à pasta e tente novamente.') from exc
            except OSError as exc:
                raise RuntimeError('Não foi possível guardar a sequência de vídeos. A gravação não continuará sem preservar a posição.') from exc
            finally:
                if temporary and os.path.exists(temporary):
                    try:
                        os.unlink(temporary)
                    except OSError as exc:
                        raise RuntimeError('Não foi possível limpar o arquivo temporário da sequência. O progresso anterior permanece preservado.') from exc
        self.positions = updated
        self.pending_round = pending
