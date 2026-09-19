"""Durable run intent and capture journal; recovery never discards a video."""
import json
import math
import os
import re
import subprocess
import threading
import time
import xml.etree.ElementTree as ET
from automation import task_key, confirmed_recording_seconds


def read_json(path, fallback):
    try:
        with open(path,encoding='utf-8') as stream: return json.load(stream)
    except (OSError,ValueError): return fallback


def write_json(path, value):
    with open(path+'.tmp','w',encoding='utf-8') as stream:
        json.dump(value,stream,ensure_ascii=False)
        stream.flush();os.fsync(stream.fileno())
    os.replace(path+'.tmp',path)


def accepted_upload_pending(raw, session):
    """An already accepted session may need its app reopened to send uploads."""
    session=re.sub(r'_\d+$','',session)
    decoder=json.JSONDecoder()
    text=raw.decode('utf-8','replace')
    accepted=False
    uploads={}
    for match in re.finditer(r'\{',text):
        try:record,_=decoder.raw_decode(text,match.start())
        except ValueError:continue
        if not isinstance(record,dict) or record.get('sessionId')!=session:continue
        if 'accepted' in record:
            accepted=record.get('accepted') is True and record.get('status')=='ended'
        if 'durationMs' in record and record.get('id'):
            uploads[record['id']]=record
    if not accepted or not uploads:return False
    if any(record.get('status') not in {'done','pending','uploading'} for record in uploads.values()):return False
    if not any(record.get('status') in {'pending','uploading'} for record in uploads.values()):return False
    try:
        durations=[float(record['durationMs'])/1000 for record in uploads.values()]
    except (ValueError,TypeError):return False
    return all(math.isfinite(value) and value>0 for value in durations) and sum(durations)<=1799


def credit_history(history, entry, seconds):
    """Credit + session marker are committed in the same history document."""
    seconds=float(seconds)
    if not math.isfinite(seconds) or not 0<seconds<=1799: raise ValueError('Duração inválida')
    session=entry['session']
    ledger=history.setdefault('supervisorSessions',{})
    if session in ledger:return False
    task=entry['task'];key=' '.join(task_key(task))
    tasks=history.setdefault('dias',{}).setdefault(entry['day'],{}).setdefault(entry['phone'],{})
    keys=[k for k,v in tasks.items() if task_key(v.get('nome') or k)==task_key(task)]
    total=sum(float(tasks[k].get('segundos',0)) for k in keys)
    for old in keys:del tasks[old]
    tasks[key]={'nome':task,'segundos':min(7200,total+seconds)}
    ledger[session]={'day':entry['day'],'phone':entry['phone'],'seconds':seconds}
    if entry.get('interleavedRound'):
        ledger[session].update(interleavedRound=entry['interleavedRound'],serial=entry['serial'])
    return True


class LoopSupervisor:
    def __init__(self, area, history_path, engine, automation, update):
        self.path=os.path.join(area,'loop-supervisor.json')
        self.history_path=history_path
        self.e,self.a,self.update=engine,automation,update
        self.lock=threading.RLock()
        self.ensure_online=lambda serial:None
        self.recover_on_open=None
        self._upload_resume_at={}
        self.interleaved_round=None

    def state(self):return read_json(self.path,{'enabled':False,'pending':{}})

    def change(self, **fields):
        with self.lock:
            state=self.state();state.update(fields);write_json(self.path,state)

    def begin(self, options, url):
        self.change(enabled=True,options=options,url=url,ownerPid=os.getpid(),lastError='',restarts=0)

    def stop(self):self.change(enabled=False)

    def checkpoint(self, serial, **fields):
        with self.lock:
            state=self.state();pending=state.setdefault('pending',{})
            if 'phone' in fields and serial in pending:
                raise RuntimeError('Há uma gravação pendente em '+serial+'; recupere antes de iniciar outra.')
            entry=pending.setdefault(serial,{})
            entry.update(fields);entry['serial']=serial
            if 'phone' in fields:
                if self.interleaved_round and serial in self.interleaved_round['serials']:
                    entry['interleavedRound']=self.interleaved_round['id']
                else:
                    entry.pop('interleavedRound',None)
            write_json(self.path,state)

    def clear(self,serial):
        with self.lock:
            state=self.state();state.setdefault('pending',{}).pop(serial,None);write_json(self.path,state)

    def credit(self,serial,seconds):
        entry=self.state()['pending'][serial]
        with self.e.lock_historico:
            history=self.e._ler_historico()
            if credit_history(history,entry,seconds):write_json(self.history_path,history)
        self.clear(serial)

    def recover_quick(self, serial, budget=8):
        """One bounded recovery pass; keep unresolved captures in the journal."""
        entry=self.state().get('pending',{}).get(serial)
        if entry is None:return True
        deadline=time.monotonic()+max(0,float(budget))

        def timeout():
            self.a.check_cancel()
            remaining=deadline-time.monotonic()
            if remaining<=0:raise TimeoutError('Tempo de recuperação esgotado')
            return min(3,remaining)

        def adb(*args):
            return self.e._adb(serial,*args,timeout=timeout(),check=True).stdout

        def root(command):
            return self.e._shell_root_bytes(serial,command,timeout=timeout())

        def same_task(raw, session):
            session_id=re.sub(r'_\d+$','',session).encode('ascii')
            # Never borrow task metadata from a neighbouring session in MMKV.
            pattern=(rb'"sessionId"\s*:\s*"'+re.escape(session_id)+
                     rb'"(?:(?!"sessionId"\s*:).){0,6000}?"taskId"\s*:\s*"[^"]+"\s*,\s*'
                     rb'"taskName"\s*:\s*"((?:\\.|[^"\\])*)"')
            matches=list(re.finditer(pattern,raw,re.DOTALL))
            if not matches:return False
            actual=json.loads('"'+matches[-1].group(1).decode('utf-8')+'"')
            return task_key(actual)==task_key(entry['task'])

        def confirmed(raw, session):
            seconds=confirmed_recording_seconds(raw,session)
            if seconds is None or not same_task(raw,session):return False
            timeout()
            self.credit(serial,seconds)
            self.a.mark(serial,stage='Salvo',percent=100,error='')
            return True

        try:
            if adb('get-state').strip()!='device':return False
            session=entry.get('session')
            if not session:
                output=root('find /data/user/0/com.bakerdata.minute/files/recordings '
                            '-mindepth 1 -maxdepth 1 -type d').decode('utf-8')
                folders={line.strip().rstrip('/').rsplit('/',1)[-1]
                         for line in output.splitlines() if line.strip()}
                new=folders-set(entry.get('before',[]))
                if not new:
                    self.clear(serial);return True
                if len(new)!=1:return False
                session=next(iter(new))
                if not re.fullmatch(r'[A-Za-z0-9_-]+',session):return False
                self.checkpoint(serial,session=session)
            if not re.fullmatch(r'[A-Za-z0-9_-]+',session):return False
            command='cat /data/user/0/com.bakerdata.minute/files/mmkv/recording-store'
            raw=root(command)
            if confirmed(raw,session):return True
            if accepted_upload_pending(raw,session):
                self.a.mark(serial,stage='Vídeo salvo — aguardando envio',error='')
                # Saving and uploading are distinct. Reopen only the already
                # accepted session's app; never credit, tap, replace its source,
                # or start another recording while these uploads remain pending.
                if same_task(raw,session) and self.recover_on_open is not None:
                    key=(serial,session)
                    now=time.monotonic()
                    with self.lock:
                        previous=self._upload_resume_at.get(key)
                        resume=previous is None or now-previous>=30
                        if resume:self._upload_resume_at[key]=now
                    if resume:self.recover_on_open(serial,timeout())
                return False

            xml=adb('shell','uiautomator','dump','--compressed','/dev/tty')
            start,end=xml.find('<hierarchy'),xml.rfind('</hierarchy>')
            if start<0 or end<start:return False
            nodes=list(ET.fromstring(xml[start:end+len('</hierarchy>')]).iter('node'))
            nodes=[node for node in nodes if node.get('package')=='com.bakerdata.minute'
                   and node.get('enabled','true')=='true' and node.get('visible-to-user','true')=='true']
            dialog=any(node.get('text')=='Salvar este Minute?' for node in nodes)
            button=next((node for node in nodes if node.get('clickable')=='true' and
                         ((dialog and (node.get('text')=='Salvar' or node.get('content-desc')=='Salvar'))
                          or (not dialog and node.get('resource-id') in {'record-accept','minute-save'}))),None)
            if button is not None:
                bounds=re.fullmatch(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]',button.get('bounds',''))
                if not bounds:return False
                left,top,right,bottom=map(int,bounds.groups())
                if right<=left or bottom<=top:return False
                adb('shell','input','tap',str((left+right)//2),str((top+bottom)//2))
            else:
                # Stop only this journaled file while it demonstrably grows,
                # and only inside a currently resumed Minute camera activity.
                if entry.get('quickStopRequested'):return False
                activity=adb('shell','dumpsys','activity','top')
                blocks=re.split(r'(?m)(?=\s*ACTIVITY )',activity)
                if not any('com.bakerdata.minute/' in block and 'EgoCameraPreview' in block
                           and re.search(r'\bmResumed=true\b',block) for block in blocks):return False
                path='/data/user/0/com.bakerdata.minute/files/recordings/'+session+'/video.mp4'
                first=int(root('stat -c %s '+path).strip())
                if deadline-time.monotonic()<=.2:return False
                time.sleep(.2)
                if int(root('stat -c %s '+path).strip())<=first:return False
                sizes=re.findall(r'(\d+)x(\d+)',adb('shell','wm','size'))
                if not sizes:return False
                width,height=map(int,sizes[-1])
                if width<=0 or height<=0:return False
                timeout()
                self.checkpoint(serial,quickStopRequested=True)
                try:tap_timeout=timeout()
                except TimeoutError:
                    self.checkpoint(serial,quickStopRequested=False)
                    return False
                self.e._adb(serial,'shell','input','tap',str(width//2),str(round(height*.922)),timeout=tap_timeout,check=True)
            return confirmed(root(command),session)
        except InterruptedError:
            raise
        except (OSError,RuntimeError,subprocess.TimeoutExpired,ET.ParseError,ValueError,KeyError):
            return False

    def recover(self):
        for serial,entry in self.state().get('pending',{}).items():
            self.a.check_cancel()
            self.ensure_online(serial)
            connection=self.e._adb(serial,'get-state',timeout=8,check=True)
            if connection.stdout.strip()!='device':raise RuntimeError('Celular pendente desconectado: '+serial)
            session=entry.get('session')
            if not session:
                new=self.e._pastas_gravacao(serial)-set(entry.get('before',[]))
                if not new:
                    self.clear(serial);continue
                if len(new)!=1:raise RuntimeError('Mais de uma captura pendente em '+serial+'; vídeos preservados.')
                session=next(iter(new));self.checkpoint(serial,session=session)
            if not re.fullmatch(r'[\w-]+',session):raise RuntimeError('Identificador de captura inválido')
            self.update(supervisorStage='Recuperando gravação',message='Conferindo gravação pendente em '+serial)
            raw=self.e._shell_root_bytes(serial,'cat /data/user/0/com.bakerdata.minute/files/mmkv/recording-store',timeout=15)
            seconds=confirmed_recording_seconds(raw,session)
            if seconds is None:
                # Stop only a known journaled capture whose file is still growing.
                path='/data/user/0/com.bakerdata.minute/files/recordings/'+session+'/video.mp4'
                def size():return int(self.e._shell_root(serial,'stat -c %s '+path,timeout=12,check=True).stdout.strip())
                first=size()
                if self.e.cancelar_sync.wait(2):self.a.check_cancel()
                if size()>first and self.a.minute_foreground(serial) and self.e._camera_pronta(serial) is not None:
                    self.e._tocar_botao_gravacao(serial)
                self.a.launch_minute(serial)
                self.a.save(serial)
                raw=self.e._shell_root_bytes(serial,'cat /data/user/0/com.bakerdata.minute/files/mmkv/recording-store',timeout=15)
                seconds=confirmed_recording_seconds(raw,session)
            if seconds is None:raise RuntimeError('Vídeo preservado; aguardando confirmação do salvamento/envio em '+serial)
            _,actual=self.e._detectar_tarefa_sessao(serial,session)
            if task_key(actual)!=task_key(entry['task']):raise RuntimeError('A tarefa da gravação pendente precisa ser conferida.')
            self.credit(serial,seconds)
            self.a.mark(serial,stage='Salvo',percent=100,error='')

    def run(self, operation, reset_idle):
        failures=0
        while self.state().get('enabled'):
            self.a.check_cancel()
            if self.a.stop_after_round.is_set():self.stop();return
            try:
                self.recover()
                self.update(supervisorStage='Acompanhando',supervisorAttempts=failures)
                operation()
                self.stop();return
            except InterruptedError:
                self.stop();raise
            except Exception as exc:
                failures+=1
                if self.e.cancelar_sync.is_set() or self.a.stop_after_round.is_set():self.stop();return
                delay=min(120,30*failures)
                self.change(lastError=str(exc))
                self.update(busy=True,planActive=True,supervisorStage='Recuperando',supervisorAttempts=failures,
                            level='warn',message=f'Supervisor: {exc}. Nova tentativa em {delay}s; vídeos pendentes preservados.')
                # Only reset idle apps when no capture needs saving.
                if not self.state().get('pending'):
                    try:reset_idle()
                    except Exception:pass
                for _ in range(delay):
                    if not self.state().get('enabled') or self.a.stop_after_round.is_set():self.stop();return
                    if self.e.cancelar_sync.wait(1):self.stop();return
