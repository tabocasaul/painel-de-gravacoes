#!/usr/bin/env python3
"""Interface HTML local para o motor do emulador."""
import concurrent.futures, ctypes, datetime, hashlib, json, mimetypes, os, re, shutil, socket, subprocess, sys, tempfile, threading, time, urllib.parse, webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.machinery import SourceFileLoader
from contextlib import contextmanager
from mirror import TouchMirror
from camera_transfer import Transfers
from background_video import BackgroundVideo
from preparation_job import PreparationJob, PreparationTracker, PreparationCancelled, run_conversion
from automation import Automation
from automation_queue import run_queue, capacity_snapshot, wait_for_shutdown
from task_history import task_usage, daily_task_rows
from daily_plan import DAILY_PLAN, run_daily_plan, continuous_daily_plan
from interleaved_plan import validate_plan, run_interleaved_plan
from interleaved_video_rotation import InterleavedVideoRotation
from interleaved_participants import InterleavedParticipants
from minute_catalog import read_catalog, collect_catalog
from loop_supervisor import LoopSupervisor
from shared_camera import SharedCamera
from storage import clone_offline, finish_resize, DEFAULT_STORAGE_GIB
from voice_manager import VoiceManager
from product_writer import ProductWriter
from live_voice import LiveVoice
from tiktok_live import TikTokLive
from tiktok_video import TikTokVideo
from panel_runtime import runtime_identity, find_running_backend
from participant_selection import recording_options, select_participants
from video_library import rename_video, delete_video, resolve_name, source_path
from video_readiness import video_readiness

HERE=os.path.dirname(os.path.abspath(__file__))
FROZEN=bool(getattr(sys,"frozen",False)); RES=getattr(sys,"_MEIPASS",HERE)
APP=os.path.dirname(sys.executable) if FROZEN else HERE
RUNTIME_ID=runtime_identity(RES,APP,sys.executable if FROZEN else None)
PORT=int(sys.argv[sys.argv.index("--port")+1]) if "--port" in sys.argv else 8768
WEB=os.path.join(RES,"web"); VIDEOS=os.path.join(APP,"videos")
AREA=os.path.expandvars(r"%LOCALAPPDATA%\emulation-cam"); ATUAL=os.path.join(AREA,"atual.mp4")
SELECTED=os.path.join(AREA,"video-selecionado.json"); THUMBS=os.path.join(AREA,"previews"); RAW_READY=os.path.join(AREA,"emu_camera_video.i420")
LIBRARY_CONFIG=os.path.join(AREA,"video-library.json")
try:
    with open(LIBRARY_CONFIG,encoding="utf-8") as f:library_path=json.load(f)["path"]
    if os.path.isdir(library_path):VIDEOS=os.path.abspath(library_path)
except (OSError,ValueError,KeyError,TypeError):pass
os.makedirs(AREA,exist_ok=True)
with open(LIBRARY_CONFIG,"w",encoding="utf-8") as f:json.dump({"path":VIDEOS},f)
P=SourceFileLoader("engine",os.path.join(RES,"painel.pyw")).load_module()
E=object.__new__(P.Painel); E.cancelar_sync=threading.Event(); E.lock_historico=threading.Lock()
LOCK=threading.Lock(); S={"busy":False,"message":"Sistema pronto.","level":"ok","progress":0,"elapsed":0,"total":0,"task":""}
LAST_PROGRESS=time.time()
WATCHDOG=None
PREPARATION_LOCK=threading.Lock(); UPLOAD_LOCK=threading.Lock()
LIBRARY_LOCK=threading.RLock()
LIBRARY_READERS=0
FOREGROUND_PREPARATION=PreparationTracker('foreground')
META_CACHE={}; PROXY_JOBS=set(); PROXY_LOCK=threading.Lock()
PHONE_NAMES=os.path.join(AREA,"phone-names.json")
PHONE_NAMES_LOCK=threading.Lock()

def phone_names():
    try:
        with open(PHONE_NAMES,encoding="utf-8") as f:return json.load(f)
    except (OSError,ValueError):return {}

def rename_phone(serial,name,label):
    if serial not in {v[0] for v in devices().values()}:raise ValueError("Celular desconhecido")
    name=str(name).strip();label=str(label).strip()
    if not name or len(name)>60 or len(label)>60:raise ValueError("Informe um nome de 1 a 60 caracteres; identificacao de ate 60 caracteres")
    if any(ord(c)<32 for c in name+label):raise ValueError("Nome invalido")
    with PHONE_NAMES_LOCK:
        data=phone_names();data[serial]={"name":name,"label":label}
        os.makedirs(AREA,exist_ok=True)
        with open(PHONE_NAMES+".tmp","w",encoding="utf-8") as f:json.dump(data,f,ensure_ascii=False)
        os.replace(PHONE_NAMES+".tmp",PHONE_NAMES)

def hidden(): return P.sem_console()
MIRROR=TouchMirror(P.ADB,hidden)
TRANSFERS=Transfers(P.ADB,AREA,hidden)
SHARED=SharedCamera(AREA,os.path.dirname(os.path.dirname(P.ADB)),P.AVD_HOME,TRANSFERS,RES)
def update(**kw):
    global LAST_PROGRESS
    with LOCK:
        if any(S.get(k)!=v for k,v in kw.items()):LAST_PROGRESS=time.time()
        S.update(kw)
        if S.get('planActive'):S['busy']=True
def snap():
    with LOCK:return dict(S,backendPid=os.getpid(),backendVersion=5,
                         supervisorVersion=1,interleavedPlanVersion=1,interleavedVideoListsVersion=1,interleavedSkipFailedRoundsVersion=1,participantSelectionVersion=1,videoLibraryVersion=1,
                         videoLibraryBusy=bool(S.get('libraryEditing') or PROXY_JOBS or PREPARATION_LOCK.locked() or UPLOAD_LOCK.locked()),
                         preparationCancellationVersion=1,foregroundPreparation=FOREGROUND_PREPARATION.snapshot(),
                         minuteCatalog=read_catalog(os.path.join(AREA,'minute-catalog.json')))
AUTOMATION=Automation(E,update)
SUPERVISOR=LoopSupervisor(AREA,P.HISTORICO_TAREFAS,E,AUTOMATION,update)


def supervised_sync(options):
    global WATCHDOG
    options,targets,_=recording_request(options,check_sources=not bool(SUPERVISOR.state().get('pending')))
    # Persist this run's participants, including an online-only run after its
    # first batch shuts down. Recovery must never widen the user's selection.
    serials={s for s,_ in targets.values()}
    options=dict(options,manageRam=options.get('manageRam',options['scope']!='online'),
                 scope='selected',selectedSerials=[s for s,_ in targets.values()])
    if set(SUPERVISOR.state().get('pending',{})) - serials:
        raise ValueError('Há gravação pendente em um celular fora dos participantes. Inclua esse celular para recuperar e salvar antes de iniciar.')
    E.cancelar_sync.clear();AUTOMATION.stop_after_round.clear()
    SUPERVISOR.begin(options,f'http://127.0.0.1:{PORT}/')
    AUTOMATION.recovery=SUPERVISOR
    def ensure_online(serial):
        if serial not in serials:
            raise RuntimeError('O celular pendente não pertence aos participantes escolhidos.')
        if status(serial)=='online':return
        match=next(((n,p) for n,(s,p) in targets.items() if s==serial),None)
        if match is None:raise RuntimeError('Celular pendente não está cadastrado: '+serial)
        start_phone(match[0],serial,match[1])
        if not wait_open(serial,time.monotonic()+360):raise RuntimeError('Aguardando o celular pendente reiniciar: '+serial)
    SUPERVISOR.ensure_online=ensure_online
    # Resume the Minute uploader only after recovery identifies an accepted,
    # ended capture. Opening its activity never changes the camera source.
    def resume_saved_upload(serial,timeout_seconds):
        if serial not in serials:raise RuntimeError('Celular fora dos participantes escolhidos.')
        return E._adb(serial,'shell','am','start','-n','com.bakerdata.minute/.MainActivity',
                      timeout=timeout_seconds,check=True)
    SUPERVISOR.recover_on_open=resume_saved_upload
    if not FROZEN and (WATCHDOG is None or WATCHDOG.poll() is not None):
        WATCHDOG=subprocess.Popen([sys.executable,os.path.join(RES,'panel_watchdog.py'),SUPERVISOR.path,str(os.getpid()),
                                  os.path.join(RES,'modern_server.pyw')],**hidden())
    def reset_idle():
        for n,(serial,_) in targets.items():
            AUTOMATION.check_cancel()
            if status(serial)!='online' or E._camera_pronta(serial) is not None:continue
            nodes=list(AUTOMATION.xml(serial).iter('node'))
            if any(x.get('resource-id') in {'record-accept','minute-save'} for x in nodes):continue
            if any(x.get('resource-id') in {'nav-index','home-search-input','nav-minutes'} for x in nodes):
                E._adb(serial,'shell','am','force-stop','com.bakerdata.minute',timeout=15,check=True)
                E._adb(serial,'emu','kill',timeout=10,check=True)
                wait_for_shutdown(serial,E._adb,update)
    def resume_operation():
        if options.get('interleavedPlan'):
            for serial in list(SUPERVISOR.state().get('pending',{})):
                AUTOMATION.check_cancel()
                SUPERVISOR.recover_quick(serial)
            rotation=InterleavedVideoRotation(os.path.join(AREA,'interleaved-video-rotation.json'))
            rotation.reconcile(E._ler_historico().get('supervisorSessions',{}))
        return sync(options)
    try:
        if options.get('interleavedPlan'):
            # This plan admits/retries each pending phone separately. A failed
            # phone must never send the saved group into global recovery loops.
            update(supervisorStage='Acompanhando')
            try:resume_operation()
            finally:SUPERVISOR.stop()
        else:SUPERVISOR.run(resume_operation,reset_idle)
    finally:
        AUTOMATION.recovery=None
        update(planActive=False,busy=False,queueActive=False,loopActive=False,supervisorStage='Parado')

def devices(): return P.descobrir_celulares() or {"MinutePlay":("emulator-5554","5554")}
VOICE=VoiceManager(AREA,RES,hidden)
WRITER=ProductWriter(AREA)
LIVE_VOICE=LiveVoice(VOICE,WRITER)
TIKTOK_VIDEO=TikTokVideo(P.ADB,AREA,P.AVD_HOME,VIDEOS,RES,P.achar,hidden)
def tiktok_devices():
    return {p['avd']:(p['serial'],p['serial'].split('-')[1]) for p in TIKTOK_VIDEO.phones()}
TIKTOK=TikTokLive(E._adb,tiktok_devices)

def status(serial):
    try:
        r=E._adb(serial,"get-state",timeout=3)
        if r.returncode:return "off"
        b=E._adb(serial,"shell","getprop","sys.boot_completed",timeout=3)
        return "online" if b.stdout.strip()=="1" else "booting"
    except Exception:return "off"
def analytics(phone_names):
    with E.lock_historico:data=E._ler_historico()
    days=data.get("dias",{}) if isinstance(data,dict) else {}
    today=time.strftime("%Y-%m-%d"); by_task={}; by_phone={}; total_all=0.0; history_rows=[]
    for day,phones in days.items():
        if not isinstance(phones,dict):continue
        for phone,tasks in phones.items():
            if not isinstance(tasks,dict):continue
            for entry in tasks.values():
                if not isinstance(entry,dict):continue
                seconds=max(0.0,float(entry.get("segundos",0) or 0));total_all+=seconds
                history_rows.append(dict(day=day,phone=phone,task=str(entry.get("nome") or "Tarefa sem nome"),seconds=seconds))
                if day==today:
                    name=str(entry.get("nome") or "Tarefa sem nome")
                    by_task[name]=by_task.get(name,0)+seconds;by_phone[phone]=by_phone.get(phone,0)+seconds
    recent=[]
    for offset in range(6,-1,-1):
        day=(datetime.date.today()-datetime.timedelta(days=offset)).isoformat();value=0.0
        for tasks in days.get(day,{}).values():
            if isinstance(tasks,dict):
                value+=sum(max(0.0,float(e.get("segundos",0) or 0)) for e in tasks.values() if isinstance(e,dict))
        recent.append({"date":day,"seconds":value})
    phone_rows=[{"name":name,"seconds":by_phone.get(name,0)} for name in phone_names]
    task_rows=daily_task_rows(data, phone_names, today)
    return {"day":today,"historyRows":history_rows,"todaySeconds":sum(by_task.values()),"totalSeconds":total_all,"activeTasks":sum(row["seconds"]>0 for row in task_rows),"limitSeconds":P.LIMITE_TAREFA_SEGUNDOS,"byTask":task_rows,"byPhone":phone_rows,"last7Days":recent}

def video_meta(path):
    st=os.stat(path);key=(path,st.st_mtime_ns,st.st_size)
    if key in META_CACHE:return META_CACHE[key]
    result={"duration":0,"width":0,"height":0,"codec":""};probe=P.achar("ffprobe")
    if probe:
        try:
            p=subprocess.run([probe,"-v","error","-select_streams","v:0","-show_entries","stream=width,height,codec_name:format=duration","-of","json",path],capture_output=True,text=True,timeout=20,**hidden())
            raw=json.loads(p.stdout or "{}");stream=(raw.get("streams") or [{}])[0];fmt=raw.get("format") or {}
            result={"duration":float(fmt.get("duration") or 0),"width":int(stream.get("width") or 0),"height":int(stream.get("height") or 0),"codec":str(stream.get("codec_name") or "")}
        except Exception:pass
    for old in list(META_CACHE):
        if old[0]==path and old!=key:META_CACHE.pop(old,None)
    META_CACHE[key]=result;return result
def preview_source(path,meta):
    if meta.get("codec") in {"h264","vp8","vp9","av1"}:return {"playback":"/media?name="+urllib.parse.quote(os.path.basename(path)),"previewReady":True}
    os.makedirs(THUMBS,exist_ok=True);st=os.stat(path);ident=hashlib.sha1((path+str(st.st_mtime_ns)).encode()).hexdigest();out=os.path.join(THUMBS,ident+".mp4")
    if os.path.isfile(out):return {"playback":"/preview?id="+ident,"previewReady":True}
    def convert():
        tmp=os.path.join(THUMBS,ident+".building.mp4")
        try:
            ff=P.achar("ffmpeg")
            if ff:
                r=subprocess.run([ff,"-y","-i",path,"-map","0:v:0","-vf","scale='min(1280,iw)':-2","-c:v","libx264","-preset","veryfast","-crf","27","-pix_fmt","yuv420p","-movflags","+faststart","-an",tmp],capture_output=True,timeout=3600,**hidden())
                if r.returncode==0 and os.path.isfile(tmp):os.replace(tmp,out)
        finally:
            try:
                if os.path.isfile(tmp):os.remove(tmp)
            except OSError:pass
            with PROXY_LOCK:PROXY_JOBS.discard(ident)
    with PROXY_LOCK:
        if ident not in PROXY_JOBS:PROXY_JOBS.add(ident);threading.Thread(target=convert,daemon=True).start()
    return {"playback":"","previewReady":False}
def selected_name():
    try:return json.load(open(SELECTED,"r",encoding="utf-8")).get("name","")
    except Exception:return ""
STATUS_CACHE={};STATUS_AT=0;STATUS_LOCK=threading.Lock()
def panel_statuses():
    global STATUS_CACHE,STATUS_AT
    if time.monotonic()-STATUS_AT<5 or not STATUS_LOCK.acquire(blocking=False):return dict(STATUS_CACHE)
    try:
        r=subprocess.run([P.ADB,"devices"],stdin=subprocess.DEVNULL,capture_output=True,text=True,encoding="utf-8",errors="replace",timeout=5,**hidden())
        if r.returncode==0:
            STATUS_CACHE={parts[0]:("online" if parts[1]=="device" else "booting") for line in r.stdout.splitlines()[1:] if len(parts:=line.split())==2}
        STATUS_AT=time.monotonic()
    except (OSError,subprocess.TimeoutExpired):STATUS_AT=time.monotonic()
    finally:STATUS_LOCK.release()
    return dict(STATUS_CACHE)

@contextmanager
def library_read():
    # Register a source reader without holding the mutex during a long browser
    # stream or ffmpeg call. Polling can continue; edits refuse active readers.
    global LIBRARY_READERS
    with LIBRARY_LOCK:LIBRARY_READERS+=1
    try:yield
    finally:
        with LIBRARY_LOCK:LIBRARY_READERS-=1


def preparation_state_for_video(name,background,foreground):
    matching=[row for row in (background,foreground) if row.get('name')==name]
    return max(matching,key=lambda row:(bool(row.get('busy')),row.get('startedAt',0))) if matching else {}


def payload():
    found=devices();states=panel_statuses();ps=[{"name":n,"serial":s,"port":p,"status":states.get(s,"off")} for n,(s,p) in found.items()]
    aliases=phone_names()
    for phone in ps:
        alias=aliases.get(phone["serial"],{})
        phone["avd"]=phone["name"]
        phone["name"]=alias.get("name") or phone["name"]
        phone["label"]=alias.get("label") or phone["serial"]
    with library_read():
        transfer_state=TRANSFERS.snapshot()
        background_state=BACKGROUND_VIDEO.snapshot()
        foreground_state=FOREGROUND_PREPARATION.snapshot()
        os.makedirs(VIDEOS,exist_ok=True); vs=[]
        for n in sorted(os.listdir(VIDEOS),key=str.casefold):
            q=os.path.join(VIDEOS,n)
            if os.path.isfile(q) and n.lower().endswith(P.EXTS) and not os.path.splitext(n)[0].endswith((".pronto",".montado")):
                preparation_state=preparation_state_for_video(n,background_state,foreground_state)
                readiness=video_readiness(n,prepared_cache(q,False,read_only=True),prepared_cache(q,True,read_only=True),ps,transfer_state['installedVideos'],preparation_state)
                meta=video_meta(q);vs.append({"name":n,"size":os.path.getsize(q),**meta,"media":"/media?name="+urllib.parse.quote(n),"thumb":"/api/thumb?name="+urllib.parse.quote(n),**preview_source(q,meta),**readiness})
    installed=transfer_state["installedVideos"]
    for phone in ps:
        phone["installedVideo"]=installed.get(phone["serial"])
        try:
            cfg=open(os.path.join(P.AVD_HOME,phone["avd"]+".avd","config.ini"),encoding="utf-8-sig").read()
            phone["storage"]=re.search(r"(?m)^disk.dataPartition.size\s*=\s*(.*)",cfg).group(1).strip()
        except (OSError,AttributeError):phone["storage"]="Desconhecido"
    known=[(installed[p["serial"]].get("name"),installed[p["serial"]].get("assetId")) if (installed.get(p["serial"],{}).get("confirmed") or installed.get(p["serial"],{}).get("staged")) else None for p in ps]
    common=known[0][0] if known and all(n and n==known[0] for n in known) else ""
    x=snap(); x.update(backgroundVideo=background_state,backgroundVideoVersion=1,videoReadinessVersion=1,phones=ps,videos=vs,current=0,currentName=common,allVideoName=common,analytics=analytics(list(found)),mirror=MIRROR.state(),defaultStorageGiB=DEFAULT_STORAGE_GIB,apiVersion=4,sharedCameraVersion=1,automationVersion=5,queueVersion=2,dailyPlanVersion=1,capacity=capacity_snapshot(len(ps),sum(p['status']=='online' for p in ps)),automation=AUTOMATION.snapshot(),**transfer_state); return x

def start_phone(n,s,p):
    if status(s)!="off":return
    class MemoryStatus(ctypes.Structure):
        _fields_=[("length",ctypes.c_ulong),("load",ctypes.c_ulong)]+[(k,ctypes.c_ulonglong) for k in ("total","available","pageTotal","pageAvailable","virtualTotal","virtualAvailable","extended")]
    memory=MemoryStatus();memory.length=ctypes.sizeof(memory)
    if os.name=="nt" and ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(memory)) and memory.available<2300*1024**2:
        raise RuntimeError(f"RAM insuficiente para ligar {n}: {memory.available/1024**3:.1f} GiB livres. Feche outro celular ou aplicativo antes de continuar.")
    exe=os.path.expandvars(r"%LOCALAPPDATA%\Android\Sdk\emulator\emulator.exe")
    if not os.path.isfile(exe):
        raise RuntimeError(f"Executável do emulador não encontrado: {exe}")
    args=[exe,"-avd",n,"-port",str(p),"-memory","2048","-no-snapshot","-timezone","America/Sao_Paulo","-camera-back","emulated","-camera-front","emulated","-gpu","auto"]+SHARED.arguments(n)
    log_path=os.path.join(AREA,n+"-startup.log")
    try:
        with open(log_path,"ab") as log:
            subprocess.Popen(args,cwd=os.path.dirname(exe),stdin=subprocess.DEVNULL,stdout=log,stderr=log,**hidden())
    except OSError as exc:
        raise RuntimeError(f"Não foi possível iniciar {n} com {exe}: {exc}. Log: {log_path}") from exc
def open_minute(s):
    for n,(serial,_) in devices().items():
        if serial==s:SHARED.activate_pending(n,s);break
    AUTOMATION.launch_minute(s)
def wait_open(s,end):
    while time.monotonic()<end:
        if status(s)=="online":open_minute(s);return True
        time.sleep(2)
    return False
def open_all():
    ds=list(devices().items());update(message="Ligando celulares...",progress=5)
    for n,(s,p) in ds:start_phone(n,s,p)
    end=time.monotonic()+420
    ok=E._paralelo([v[0] for _,v in ds],lambda s:wait_open(s,end))
    if not all(ok.values()):raise RuntimeError("algum celular nao concluiu o boot")
    update(busy=False,message="Tudo aberto: administrador e Minute.",level="ok",progress=100)
def video_control(s,a):
    for n,(serial,_) in devices().items():
        if serial==s:SHARED.activate_pending(n,s);break
    subprocess.run(["powershell.exe","-NoProfile","-ExecutionPolicy","Bypass","-File",os.path.join(RES,"controlar-videocam.ps1"),"-Acao",a,"-Serial",s],check=True,**hidden())
def prepare_video(name,fill,notify=None,background=False,preparation=None,manual=False):
    own=preparation is None
    token=preparation or (FOREGROUND_PREPARATION.start(os.path.basename(name),fill) if manual
                         else PreparationJob(os.path.basename(name),'internal',fill,cancellable=False))
    if manual:update(preparationJobId=token.snapshot()['jobId'])
    callback=notify or update
    def report(**values):
        token.notify(**values)
        if callback!=token.notify:callback(**values)
    acquired=False
    error=None
    try:
        token.check_cancel()
        while not PREPARATION_LOCK.acquire(timeout=.1):token.check_cancel()
        acquired=True
        token.check_cancel()
        return _prepare_video(name,fill,report,background,token)
    except BaseException as exc:
        error=exc
        raise
    finally:
        if acquired:PREPARATION_LOCK.release()
        if own:token.finish(error)

def _prepare_video(name,fill,notify,background,token):
    token.check_cancel()
    src=os.path.join(VIDEOS,os.path.basename(name))
    if not os.path.isfile(src):raise RuntimeError("video nao encontrado")
    if prepared_cache(src,fill):
        token.commit(lambda:None)
        notify(stage="Quadros prontos",progress=100,message="Reutilizando os quadros ja preparados")
        return os.path.basename(name)
    source_stat=os.stat(src)
    os.makedirs(AREA,exist_ok=True);notify(message="Preparando quadros sem compressao a partir do original...",progress=1)
    duration=video_meta(src).get("duration",0)
    token.check_cancel()
    if duration<=0:raise RuntimeError("Nao foi possivel ler a duracao do video")
    required=int(duration*640*360*1.5*30)+512*1024*1024
    cache_dir=os.path.join(AREA,"frame-cache");os.makedirs(cache_dir,exist_ok=True)
    if shutil.disk_usage(cache_dir).free<required:
        # Large frame caches may not fit on the Windows system drive. The
        # library normally lives on the data SSD, so use it transparently.
        cache_dir=os.path.join(VIDEOS,".frame-cache");os.makedirs(cache_dir,exist_ok=True)
    if shutil.disk_usage(cache_dir).free<required:
        raise RuntimeError(f"O PC precisa de {required/1024**3:.1f} GiB livres no C: ou no disco da biblioteca para preparar este video")
    ff=P.achar("ffmpeg")
    if not ff:raise RuntimeError("ffmpeg nao encontrado")
    filt="scale=640:360:force_original_aspect_ratio=increase,crop=640:360,setsar=1" if fill else "scale=640:360:force_original_aspect_ratio=decrease,pad=640:360:(ow-iw)/2:(oh-ih)/2:black,setsar=1"
    raw_path=os.path.join(cache_dir,str(time.time_ns())+'-'+token.snapshot()['jobId']+".i420")
    pending=raw_path+".partial"
    if os.path.lexists(pending) or os.path.lexists(raw_path):raise RuntimeError('Já existe um arquivo reservado para esta preparação.')
    staged=[]
    published=False
    try:
        token.check_cancel()
        with open(os.path.join(AREA,"camera-conversion-background.log" if background else "camera-conversion.log"),"w",encoding="utf-8") as log:
            options=hidden()
            if background and os.name=="nt":options["creationflags"]=options.get("creationflags",0)|subprocess.BELOW_NORMAL_PRIORITY_CLASS
            p=subprocess.Popen([ff,"-y","-v","error","-progress","pipe:1","-nostats","-threads","2" if background else "0","-filter_threads","1" if background else "0","-i",src,"-map","0:v:0","-vf",filt,"-r","30","-an","-pix_fmt","yuv420p","-f","rawvideo",pending],stdout=subprocess.PIPE,stderr=log,text=True,**options)
            def progress(line):
                if line.startswith('out_time_us='):
                    try:
                        percent=min(99,int(float(line.split('=',1)[1])/1e6/duration*100))
                        notify(stage='Preparando quadros',progress=percent,message=f'Preparando quadros da camera: {percent}%')
                    except ValueError:pass
            if run_conversion(p,token,progress):
                raise RuntimeError('Falha na preparação; confira o log de conversão')
        token.check_cancel()
        notify(stage='Identificando vídeo',progress=0,message='Identificando o original para reutilizar os quadros...')
        copied=0;total=source_stat.st_size;digest=hashlib.sha256()
        with open(src,'rb') as inp:
            while True:
                token.check_cancel()
                chunk=inp.read(8*1024**2)
                if not chunk:break
                digest.update(chunk);copied+=len(chunk);notify(progress=int(copied*100/max(1,total)))
        token.check_cancel()
        after=os.stat(src)
        if (after.st_size,after.st_mtime_ns)!=(source_stat.st_size,source_stat.st_mtime_ns):
            raise RuntimeError('O vídeo original mudou durante a preparação. Tente novamente.')
        data={'name':os.path.basename(name),'sha256':digest.hexdigest(),'fill':bool(fill),'sourceSize':source_stat.st_size,
              'sourceMtime':source_stat.st_mtime_ns,'rawSize':os.path.getsize(pending),'rawPath':raw_path}
        destinations=[cache_metadata_path(src,fill)]
        if not background:destinations.append(os.path.join(AREA,'prepared-video.json'))
        for destination in destinations:
            token.check_cancel()
            with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=os.path.dirname(destination),prefix='.preparation-',suffix='.tmp',delete=False) as meta:
                staged.append((meta.name,destination))
                json.dump(data,meta);meta.flush();os.fsync(meta.fileno())
        def publish():
            nonlocal published
            os.replace(pending,raw_path)
            for temporary,destination in staged:
                os.replace(temporary,destination)
                # Once a metadata record points to this raw, it is a valid cache
                # and must survive even if another optional record cannot save.
                published=True
        token.commit(publish)
    finally:
        for temporary,_ in staged:
            if os.path.isfile(temporary):os.remove(temporary)
        if os.path.isfile(pending):os.remove(pending)
        if not published and os.path.isfile(raw_path):os.remove(raw_path)
    return os.path.basename(name)

BACKGROUND_VIDEO=BackgroundVideo(prepare_video)

def cache_metadata_path(src,fill,create=True):
    signature=f"{os.path.abspath(src)}:{os.stat(src).st_mtime_ns}:{os.path.getsize(src)}:{bool(fill)}"
    directory=os.path.join(AREA,"frame-cache")
    if create:os.makedirs(directory,exist_ok=True)
    return os.path.join(directory,hashlib.sha256(signature.encode()).hexdigest()+".json")

def prepared_cache(src,fill,*,read_only=False):
    try:
        cached_path=cache_metadata_path(src,fill,create=not read_only)
        for metadata in [cached_path,os.path.join(AREA,"prepared-video.json")]:
            try:
                with open(metadata,encoding="utf-8") as f:meta=json.load(f)
                if not isinstance(meta,dict):continue
                meta.setdefault("rawPath",RAW_READY)
                if (meta["name"]==os.path.basename(src) and meta["fill"]==bool(fill) and
                    meta["sourceSize"]==os.path.getsize(src) and meta["sourceMtime"]==os.stat(src).st_mtime_ns and
                    meta["rawSize"]==os.path.getsize(meta["rawPath"])):
                    if metadata!=cached_path and not read_only:
                        with open(cached_path,"w",encoding="utf-8") as f:json.dump(meta,f)
                    return meta
            except (OSError,ValueError,KeyError,TypeError):pass
    except OSError:pass
    return None

def check_camera_space(serial,name):
    src=os.path.join(VIDEOS,os.path.basename(name))
    duration=video_meta(src).get("duration",0)
    if duration<=0:raise RuntimeError("Nao foi possivel ler o video")
    required=int(duration*640*360*1.5*30)+256*1024*1024
    result=E._adb(serial,"shell","df","-k","/data",timeout=15)
    rows=result.stdout.strip().splitlines()
    try:free=int(rows[-1].split()[3])*1024
    except (IndexError,ValueError):raise RuntimeError("Nao foi possivel conferir o espaco do celular")
    if free<required:raise RuntimeError(f"{serial}: video completo precisa de {required/1024**3:.1f} GiB livres; disponivel {free/1024**3:.1f} GiB. Aumente o armazenamento do emulador antes de enviar.")
def remember_video(name):
    with open(SELECTED,"w",encoding="utf-8") as f:json.dump({"name":os.path.basename(name)},f,ensure_ascii=False)

def install_video(s,name,fill,manual=False):
    targets=[(n,s) for n,(serial,_) in devices().items() if serial==s]
    if not targets:raise RuntimeError("Selecione um celular valido")
    install_targets(targets,name,fill,manual=manual)

def install_video_all(name,fill,manual=False):
    targets=[(n,s) for n,(s,_) in devices().items()]
    if not targets:raise RuntimeError("nenhum celular configurado")
    install_targets(targets,name,fill,manual=manual)

def install_targets(targets,name,fill,manual=False):
    name=os.path.basename(name)
    aliases=phone_names()
    TRANSFERS.reset([(aliases.get(s,{}).get("name") or n,s) for n,s in targets],name)
    cache=prepared_cache(os.path.join(VIDEOS,name),fill)
    existing=TRANSFERS.snapshot()["installedVideos"]
    cache_id=(cache["sha256"]+":"+str(bool(fill))) if cache else None
    pending_targets=[(n,s) for n,s in targets if not(cache_id and (existing.get(s,{}).get("confirmed") or existing.get(s,{}).get("staged")) and existing[s].get("assetId")==cache_id and existing[s].get("mode")=="shared")]
    if not pending_targets:
        for n,s in targets:TRANSFERS.mark(s,stage="Concluido",bytes=cache["rawSize"],total=cache["rawSize"],percent=100)
        update(busy=False,stage="Concluido",progress=100,message="Este video ja esta confirmado em todos os destinos",level="ok")
        return
    for n,s in targets:TRANSFERS.mark(s,stage="Aguardando preparação",mode="shared")
    name=prepare_video(name,fill,manual=manual)
    cache=prepared_cache(os.path.join(VIDEOS,name),fill)
    if not cache:raise RuntimeError("Os quadros preparados não foram confirmados")
    asset_id=cache["sha256"]+":"+str(bool(fill));raw_path=cache["rawPath"]
    update(stage="Ativando câmeras",progress=0,message=f"Ativando vídeo compartilhado em {len(targets)} celulares...")
    failures=[]
    def send(target):
        n,s=target
        was_off=status(s)=="off"
        try:
            installed=TRANSFERS.snapshot()["installedVideos"].get(s,{})
            if (installed.get("confirmed") or installed.get("staged")) and installed.get("assetId")==asset_id and installed.get("mode")=="shared":
                TRANSFERS.mark(s,stage="Concluido",bytes=os.path.getsize(raw_path),total=os.path.getsize(raw_path),percent=100)
                return n,None
            SHARED.install(n,s,dict(devices())[n][1],raw_path,name,os.path.getsize(os.path.join(VIDEOS,name)),asset_id,
                           start_phone,lambda serial:status(serial)!="off")
            return n,None
        except Exception as exc:
            TRANSFERS.mark(s,stage="Falhou",error=str(exc));return n,str(exc)
        finally:
            if was_off and len(targets)>1 and not TRANSFERS.snapshot()["installedVideos"].get(s,{}).get("staged") and status(s)!="off":
                E._adb(s,"shell","sync",timeout=90,check=True)
                E._adb(s,"emu","kill",timeout=15)
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(2,len(targets))) as pool:
        futures=[pool.submit(send,target) for target in targets]
        while not all(f.done() for f in futures):
            rows=TRANSFERS.snapshot()["transfers"].values()
            percent=int(sum(r.get("percent",0) for r in rows)/len(targets))
            update(progress=percent,stage="Ativando câmeras",message=f"Ativando {name}: {percent}% • um único arquivo no PC, sem copiar os quadros para cada celular")
            time.sleep(1)
        for future in futures:
            n,error=future.result()
            if error:failures.append(n+": "+error)
    remember_video(name)
    if failures:raise RuntimeError(f"instalado em {len(targets)-len(failures)} de {len(targets)}; falhou: "+", ".join(failures))
    update(busy=False,stage="Concluido",progress=100,message=f"{name}: fonte definida nos {len(targets)} celulares. Desligados serão validados ao abrir, antes de gravar.",level="ok")

def add_phone():
    ds=devices(); idx=max([P.indice_minuteplay(os.path.splitext(n)[0]) or 0 for n in os.listdir(P.AVD_HOME)]+[0])+1;n="MinutePlay"+str(idx);port=str(5554+(idx-1)*2);s="emulator-"+port
    dst=os.path.join(P.AVD_HOME,n+".avd")
    if not os.path.isdir(P.TEMPLATE_AVD):raise RuntimeError("modelo-base nao encontrado")
    clone_offline(P.TEMPLATE_AVD,dst,lambda done,total:update(progress=min(88,int(done/max(1,total)*88)),message="Criando "+n+" com 128 GiB..."))
    with open(os.path.join(P.AVD_HOME,n+".ini"),"w",encoding="utf8") as f:f.write("avd.ini.encoding=UTF-8\npath="+dst+"\npath.rel=avd\\"+n+".avd\ntarget=android-33\n")
    start_phone(n,s,port)
    if not wait_open(s,time.monotonic()+360):raise RuntimeError("boot demorou mais de 6 minutos")
    finish_resize(s,lambda message:update(message=message))
    E._adb(s,"shell","pm","clear","com.bakerdata.minute",timeout=30);open_minute(s)
    update(busy=False,progress=100,message=n+" criado sem login no Minute.",level="ok")
def preflight_plan_video(video):
    video=resolve_name(VIDEOS,AREA,video)
    if video != os.path.basename(video) or not os.path.isfile(os.path.join(VIDEOS,video)):
        raise ValueError('Vídeo não encontrado na biblioteca: '+video)
    cache=prepared_cache(os.path.join(VIDEOS,video),False)
    if not cache:
        raise RuntimeError('Prepare em segundo plano na aba Vídeos antes de iniciar o plano: '+video)
    return cache


def recording_request(options=None,check_sources=True):
    """Validate and resolve a run before any phone or recovery state changes."""
    options=recording_options(options)
    targets=select_participants(devices(),options,status)
    interleaved = validate_plan(options.get('interleavedTasks')) if options.get('interleavedPlan') else None
    if interleaved:
        catalog = read_catalog(os.path.join(AREA,'minute-catalog.json')).get('tasks',[])
        missing = [row['task'] for row in interleaved if row['task'] not in catalog]
        if missing:
            raise ValueError('Tarefas não encontradas no catálogo atual: '+', '.join(missing))
        # A known pending capture may still be saved if a future source is missing.
        if check_sources:
            for video in dict.fromkeys(video for row in interleaved for video in row['videos']):
                preflight_plan_video(video)
    if options.get('dailyPlan') or interleaved:
        options=dict(options, autoNavigate=True, manageRam=True, repeat=True, usageSince=None)
    if not options.get('autoNavigate',True):
        if options['simultaneous'] is not None:
            raise ValueError('Para limitar a quantidade por rodada, use a busca automática da tarefa. Com câmeras prontas, todos os participantes gravam juntos.')
        if any(status(s)!='online' for s,_ in targets.values()):
            raise ValueError('No modo câmeras prontas, escolha somente celulares ligados e com a câmera aberta.')
    since=options.get('usageSince')
    if since:
        from datetime import date
        if date.fromisoformat(since).isoformat()!=since:raise ValueError('Data inicial inválida')
    return options,targets,interleaved


def sync(options=None):
    options,targets,interleaved=recording_request(options)
    AUTOMATION.usage_since=options.get('usageSince') or None
    def start_interleaved(n,s,p):
        if status(s)=='off':
            limit=options.get('simultaneous') or 3
            live=sum(status(serial)!='off' for serial,_ in targets.values())
            if live>=limit:
                raise RuntimeError('Aguardando uma vaga; celulares com gravação pendente continuam preservados.')
        start_phone(n,s,p)
    def prepare(n,s,p):
        if interleaved and s in SUPERVISOR.state().get('pending',{}):
            raise RuntimeError('A gravação anterior está preservada; aguardando confirmação antes de voltar ao grupo.')
        if status(s)!="online":
            if not options.get('autoNavigate',True):
                raise ValueError(n+': abra o celular e deixe a câmera pronta antes de iniciar.')
            if interleaved:start_interleaved(n,s,p)
            else:start_phone(n,s,p)
            if not wait_open(s,time.monotonic()+360):raise RuntimeError(n+": não iniciou em 6 minutos")
        SHARED.activate_pending(n,s)
        if options.get("autoNavigate",True):
            open_minute(s)
            AUTOMATION.mark(s,stage='Aguardando o Minute abrir')
            AUTOMATION.wait_minute_ready(s)
    if (options['simultaneous'] is not None or options.get('manageRam', options.get('scope') != 'online')) and options.get('autoNavigate',True):
        def boot(n,s,p,allow_pending_boot=False):
            def check_boot():
                AUTOMATION.check_cancel()
                if AUTOMATION.stop_after_round.is_set():
                    raise InterruptedError('Início interrompido antes da gravação; os aparelhos não começaram uma rodada parcial.')
            check_boot()
            if interleaved and s in SUPERVISOR.state().get('pending',{}) and not allow_pending_boot:
                raise RuntimeError('Gravação pendente: o celular será tratado separadamente antes de voltar.')
            if interleaved:start_interleaved(n,s,p)
            else:start_phone(n,s,p)
            started=time.monotonic()
            deadline=started+360
            try:
                while time.monotonic()<deadline:
                    check_boot()
                    update(stage='Aguardando aparelhos',message=f'Ligando {n}: aguardando o Android ({int(time.monotonic()-started)}s; até 360s). O grupo começa junto.',
                           bootWaiting=True,bootPhone=n,bootSerial=s,bootElapsed=int(time.monotonic()-started),bootTimeout=360)
                    if status(s)=='online' and E._adb(s,'shell','getprop','sys.boot_completed',timeout=8).stdout.strip()=='1':
                        for _ in range(4):
                            check_boot()
                            time.sleep(1)
                        check_boot()
                        return
                    time.sleep(min(2,max(0,deadline-time.monotonic())))
                check_boot()
                raise RuntimeError(n+': Android não terminou de iniciar em 6 minutos; a rodada não começou.')
            finally:update(bootWaiting=False)
        def shutdown(s):
            if AUTOMATION.snapshot().get(s,{}).get('stage') != 'Salvo':
                if E._camera_pronta(s) is not None:
                    raise RuntimeError('Encerre e salve a câmera aberta em '+s+' antes de reorganizar a fila.')
                if any(n.get('resource-id') in {'minute-save','record-accept'} for n in AUTOMATION.xml(s).iter('node')):
                    raise RuntimeError('Há uma gravação para salvar em '+s+'. A fila foi pausada.')
            E._adb(s,'shell','sync',timeout=90,check=True)
            E._adb(s,'emu','kill',timeout=8,check=True)
            update(message='Aguardando '+s+' desligar após salvar...')
            wait_for_shutdown(s, E._adb, update)
        if options.get('dailyPlan') or interleaved:
            AUTOMATION.usage_since=None
            E.cancelar_sync.clear()
            AUTOMATION.stop_after_round.clear()
            update(planActive=True, planCompleted=False, planStep=0, planMode='interleaved' if interleaved else 'daily',queueFailed=[],queueErrors={})
            participants=None
            if interleaved:
                admission_starts={}
                def start_for_admission(n,s,p):
                    now=time.monotonic()
                    if s in admission_starts and now-admission_starts[s]<60:
                        return  # Keep the already requested boot reserved in admission.
                    states={serial:status(serial) for serial,_ in targets.values()}
                    starting={serial for serial,at in admission_starts.items() if now-at<60 and states.get(serial)=='off'}
                    occupied={serial for serial,state in states.items() if state!='off'} | starting
                    if len(occupied)>=(options.get('simultaneous') or 3):
                        raise RuntimeError('Aguardando uma vaga; celulares iniciando ou com gravações pendentes continuam preservados.')
                    start_interleaved(n,s,p)
                    admission_starts[s]=now
                def release_slot(serial):
                    if serial in SUPERVISOR.state().get('pending',{}):
                        raise RuntimeError('A gravação pendente permanece preservada.')
                    if AUTOMATION.snapshot().get(serial,{}).get('stage')!='Salvo':
                        raise RuntimeError('Aguardando uma rodada salva para liberar esta vaga com segurança.')
                    E._adb(serial,'shell','sync',timeout=3,check=True)
                    E._adb(serial,'emu','kill',timeout=3,check=True)
                update(planLastSaved=[],planLastFailed=[],planContinuingAfterFailure=False)
                participants=InterleavedParticipants(targets,status,start_for_admission,
                    lambda:SUPERVISOR.state().get('pending',{}),SUPERVISOR.recover_quick,AUTOMATION.check_cancel,update,release_slot)
            caches={}
            def preflight(video):
                caches[video]=preflight_plan_video(video)
            def activate(eligible,video):
                source_video=resolve_name(VIDEOS,AREA,video)
                AUTOMATION.check_cancel()
                if interleaved:
                    pending=SUPERVISOR.state().get('pending',{})
                    for n,(s,p) in targets.items():
                        if n not in eligible and n not in participants.deferred and s not in pending and status(s)=='online':
                            try:shutdown(s)
                            except InterruptedError:raise
                            except Exception as exc:participants.defer(n,exc)
                    expected=caches[video]['sha256']+':False'
                    ready={}
                    activation_errors={}
                    for n,(s,p) in eligible.items():
                        AUTOMATION.check_cancel()
                        if s in SUPERVISOR.state().get('pending',{}):
                            activation_errors[n]='Gravação pendente preservada; aguardando antes de iniciar este grupo.'
                            participants.defer(n,activation_errors[n])
                            continue
                        try:
                            if TRANSFERS.snapshot()['installedVideos'].get(s,{}).get('assetId')!=expected:
                                if status(s)=='online':shutdown(s)
                                install_targets([(n,s)],source_video,False)
                            if TRANSFERS.snapshot()['installedVideos'].get(s,{}).get('assetId')!=expected:
                                raise RuntimeError('O vídeo correto não foi confirmado para '+n)
                            ready[n]=(s,p)
                        except InterruptedError:raise
                        except Exception as exc:
                            activation_errors[n]=str(exc)
                            participants.defer(n,exc)
                    if activation_errors:
                        message='A rodada não começou: nem todos os aparelhos escolhidos ficaram prontos. Confira '+', '.join(activation_errors)+'.'
                        update(queueFailed=list(activation_errors),queueErrors=activation_errors,queuePending=list(eligible),
                               planLastFailed=list(activation_errors),planContinuingAfterFailure=False,message=message)
                        raise RuntimeError(message)
                    return ready
                for n,(s,p) in targets.items():
                    if n not in eligible and status(s)=='online':
                        AUTOMATION.check_cancel()
                        shutdown(s)
                expected=caches[video]['sha256']+':False'
                installed=TRANSFERS.snapshot()['installedVideos']
                if any(installed.get(s,{}).get('assetId')!=expected for s,_ in eligible.values()):
                    # Stage offline to avoid restarting several guests simultaneously.
                    for n,(s,p) in targets.items():
                        AUTOMATION.check_cancel()
                        if status(s)=='online':shutdown(s)
                    AUTOMATION.check_cancel()
                    install_targets([(n,s) for n,(s,p) in eligible.items()],source_video,False)
                current=TRANSFERS.snapshot()['installedVideos']
                if any(current.get(s,{}).get('assetId')!=expected for s,_ in eligible.values()):
                    raise RuntimeError('O vídeo correto não foi confirmado para '+video)
            def run_task(eligible,task):
                def round_saved():
                    state=snap()
                    return bool(eligible) and set(eligible)<=set(state.get('queueSaved',[])) and not state.get('queuePending')
                recovery=AUTOMATION.recovery
                if interleaved and recovery is not None:
                    recovery.interleaved_round=rotation.pending_round
                try:
                    outcome=run_queue(AUTOMATION,eligible,prepare,TRANSFERS.snapshot()['installedVideos'],task,True,not bool(interleaved),
                              lambda s:status(s)=='online',boot,shutdown,
                              usage=lambda n:AUTOMATION.task_usage(n,task),
                              lifetime=lambda n:task_usage(E._ler_historico(),n,task),
                              randomize=bool(options.get('randomizePhones',True)),
                              simultaneous=options.get('simultaneous'),reset_controls=False,tolerate_failures=bool(interleaved),require_all_ready=bool(interleaved))
                except InterruptedError:
                    # The stop button still saves first. Commit the next source,
                    # then the plan's next cancel check ends the operation.
                    if not interleaved:raise
                    if not round_saved():
                        rotation.require_all()
                        raise
                    outcome=dict(saved=list(eligible),failed=[])
                finally:
                    if interleaved and recovery is not None:
                        recovery.interleaved_round=None
                if interleaved:
                    if not isinstance(outcome,dict):
                        state=snap()
                        outcome=dict(saved=list(state.get('queueSaved',[])),failed=list(state.get('queueFailed',[])))
                    participants.failed(outcome['failed'],AUTOMATION.snapshot())
                    update(planLastSaved=outcome['saved'],planLastFailed=outcome['failed'],
                           planContinuingAfterFailure=bool(outcome['saved'] and outcome['failed']))
                    return outcome
            try:
                if interleaved:
                    rotation=InterleavedVideoRotation(os.path.join(AREA,'interleaved-video-rotation.json'))
                    rotation.reconcile(E._ler_historico().get('supervisorSessions',{}))
                    admission_attempt=0
                    def admit(candidates,limit,cycle):
                        nonlocal admission_attempt
                        expected=min(limit,len(candidates))
                        pending=SUPERVISOR.state().get('pending',{})
                        if any(serial in pending for serial,_ in candidates.values()):
                            # Open the requested group before waiting on uploads.
                            # Previously only the old captures' devices opened,
                            # while the remaining participants waited offline.
                            order=[name for name,(serial,_) in candidates.items() if serial in pending]
                            order += [name for name in candidates if name not in order]
                            initial={name:candidates[name] for name in order[:expected]}
                            for name,(serial,port) in initial.items():
                                AUTOMATION.check_cancel()
                                if AUTOMATION.stop_after_round.is_set():
                                    raise InterruptedError('Início interrompido antes da abertura do grupo completo.')
                                if status(serial)!='online':boot(name,serial,port,allow_pending_boot=serial in pending)
                            update(message=f'{expected} aparelhos abertos. Conferindo o envio dos vídeos já salvos antes de gravar.',
                                   admissionExpected=expected)
                        deadline=time.monotonic()+360
                        try:
                            while True:
                                AUTOMATION.check_cancel()
                                if AUTOMATION.stop_after_round.is_set():
                                    raise InterruptedError('Início interrompido antes da gravação; aguardávamos o grupo completo.')
                                admission_attempt+=1
                                admitted=participants.admit(candidates,limit,admission_attempt)
                                rotation.reconcile(E._ler_historico().get('supervisorSessions',{}))
                                if len(admitted)>=expected:
                                    update(admissionReady=len(admitted),admissionExpected=expected,queueErrors={})
                                    return admitted
                                missing=[name for name in candidates if name not in admitted]
                                errors={name:participants.deferred.get(name,'Aguardando liberação para entrar no grupo.') for name in missing}
                                message=f'Aguardando o grupo completo ({len(admitted)}/{expected} liberados): '+', '.join(missing)+'. Conferindo aparelhos e gravações anteriores antes de começar.'
                                update(admissionWaiting=True,admissionReady=len(admitted),admissionExpected=expected,admissionMissing=missing,
                                       stage='Aguardando todos os aparelhos',queuePending=missing,queueErrors=errors,message=message)
                                if time.monotonic()>=deadline:
                                    update(queueFailed=missing)
                                    raise RuntimeError('A rodada não começou: não foi possível liberar o grupo completo em 6 minutos. Confira '+', '.join(missing)+'. As gravações pendentes permanecem preservadas.')
                                time.sleep(min(2,max(0,deadline-time.monotonic())))
                        finally:update(admissionWaiting=False)
                    return continuous_daily_plan(
                        lambda: run_interleaved_plan(interleaved,targets,AUTOMATION.task_usage,preflight,activate,run_task,
                                                     AUTOMATION.check_cancel,AUTOMATION.stop_after_round.is_set,update,
                                                     simultaneous=options.get('simultaneous') or 3,rotation=rotation,
                                                     continue_after_failure=True,admit=admit,pause=E.cancelar_sync.wait),
                        AUTOMATION.check_cancel,AUTOMATION.stop_after_round.is_set,E.cancelar_sync.wait,E._hoje,update,
                        retry_preparation=AUTOMATION.recovery is None)
                return continuous_daily_plan(
                    lambda: run_daily_plan(targets,AUTOMATION.task_usage,preflight,activate,run_task,
                                           AUTOMATION.check_cancel,AUTOMATION.stop_after_round.is_set,update),
                    AUTOMATION.check_cancel,AUTOMATION.stop_after_round.is_set,
                    E.cancelar_sync.wait,E._hoje,update,retry_preparation=AUTOMATION.recovery is None)
            finally:
                update(planActive=False,busy=False,queueActive=False,loopActive=False)
        return run_queue(AUTOMATION,targets,prepare,TRANSFERS.snapshot()['installedVideos'],
                         str(options.get('taskName','')),True,bool(options.get('repeat',False)),
                         lambda s:status(s)=='online',boot,shutdown,
                         usage=lambda n:AUTOMATION.task_usage(n,str(options.get('taskName',''))),
                         lifetime=lambda n:task_usage(E._ler_historico(),n,str(options.get('taskName',''))),
                         randomize=bool(options.get('randomizePhones',True)),
                         resume_phones=options.get('resumePhones',()),
                         simultaneous=options.get('simultaneous'))
    update(queueActive=False,queueBatch=0,queueSaved=[],queuePending=[])
    AUTOMATION.run(targets,prepare,TRANSFERS.snapshot()["installedVideos"],
                   str(options.get("taskName", "")),bool(options.get("autoNavigate",True)),
                   repeat=bool(options.get("repeat",False)))


def job(kind,fn):
    with LOCK:
        if S["busy"]:raise RuntimeError("ja existe uma operacao em andamento")
        S.update(busy=True,level="info",progress=0,stage="Iniciando",operation=kind,preparationJobId='')
    def work():
        try:fn()
        except PreparationCancelled as x:update(busy=False,level='warn',stage='Preparação cancelada',message=str(x),progress=0)
        except InterruptedError:update(busy=False,level="warn",message="Automação interrompida; confira os resultados por celular.")
        except Exception as x:update(busy=False,level="error",message=str(x))
    threading.Thread(target=work,daemon=True).start()

def edit_video_library(data):
    """Reserve all source readers/writers before any rename or recycle call."""
    acquired=[]
    reserved=False
    try:
        for mutex in (PREPARATION_LOCK,UPLOAD_LOCK,LIBRARY_LOCK,PROXY_LOCK,TRANSFERS.lock,SHARED.lock):
            if not mutex.acquire(blocking=False):
                raise ValueError('Aguarde a preparação, importação ou leitura do vídeo terminar e tente novamente.')
            acquired.append(mutex)
        with LOCK:
            supervisor=SUPERVISOR.state()
            live=TIKTOK_VIDEO.snapshot()
            if (LIBRARY_READERS or S.get('busy') or S.get('planActive') or S.get('queueActive') or BACKGROUND_VIDEO.snapshot().get('busy')
                    or supervisor.get('enabled') or supervisor.get('pending') or PROXY_JOBS
                    or live.get('busy') or live.get('active') or LIVE_VOICE.snapshot().get('active')):
                raise ValueError('Aguarde a leitura da prévia, gravação, preparação, importação ou sessão ativa terminar para alterar este vídeo.')
            S.update(busy=True,libraryEditing=True)
            reserved=True
        name=data.get('video')
        source_path(VIDEOS,name)
        if not name.lower().endswith(P.EXTS):
            raise ValueError('Selecione um vídeo da biblioteca.')
        if data['action']=='rename_video':
            result=rename_video(VIDEOS,AREA,name,data.get('name'),RAW_READY)
        else:
            result=delete_video(VIDEOS,name)
        META_CACHE.clear()
        return result
    finally:
        if reserved:
            with LOCK:S.update(busy=False,libraryEditing=False)
        for mutex in reversed(acquired):mutex.release()


def start_background_video(name,fill):
    # Background preparation is allowed during recordings, but cannot reserve
    # an old filename while a synchronous library edit is committing it.
    with LOCK:
        if S.get('libraryEditing'):raise ValueError('Aguarde a alteração da biblioteca terminar.')
        if not name or not os.path.isfile(os.path.join(VIDEOS,name)):raise ValueError('Selecione um vídeo da biblioteca')
        BACKGROUND_VIDEO.start(name,fill)


def cancel_preparation(data):
    kind=data.get('kind')
    if kind not in {'background','foreground'}:raise ValueError('Modalidade de preparação inválida.')
    with LOCK:
        if kind=='foreground' and (S.get('planActive') or S.get('queueActive')):
            raise ValueError('Este controle cancela somente uma preparação manual, antes da ativação das câmeras.')
        tracker=BACKGROUND_VIDEO if kind=='background' else FOREGROUND_PREPARATION
        result=tracker.cancel(data.get('jobId'),data.get('video',data.get('name')))
        if (result.get('cleared') and kind=='foreground' and not S.get('busy')
                and S.get('preparationJobId')==data.get('jobId')):
            S.update(stage='Aguardando',progress=0,level='ok',message='Falha de preparação limpa. Você pode tentar novamente.')
        return result


def action(d):
    if d.get('action')=='cancel_preparation':return cancel_preparation(d)
    if d.get('action') in {'rename_video','delete_video'}:return edit_video_library(d)
    a=d.get("action");s=d.get("serial","");by={v[0]:(n,v[1]) for n,v in devices().items()}
    if a=="mirror_stop":MIRROR.stop()
    elif a=="mirror_start":
        if snap()["busy"]:raise ValueError("Aguarde a operacao atual terminar")
        if s not in by or status(s)!="online":raise ValueError("Selecione um celular ligado")
        MIRROR.start(s,[serial for serial in by if serial!=s and status(serial)=="online"])
    elif a=="rename":rename_phone(s,d.get("name",""),d.get("label",""))
    elif a=="all_start":job(a,open_all)
    elif a=="start":n,p=by[s];start_phone(n,s,p)
    elif a=="stop":
        E._adb(s,"shell","sync",timeout=90,check=True)
        E._adb(s,"emu","kill",timeout=8)
    elif a=="minute":open_minute(s)
    elif a=="control":video_control(s,d["control"])
    elif a=="prepare_background":
        name=os.path.basename(str(d.get("video","")))
        start_background_video(name,bool(d.get("fill",False)))
    elif a=="install":job(a,lambda:install_video(s,d["video"],d.get("fill",False),manual=True))
    elif a=="install_all":job(a,lambda:install_video_all(d["video"],d.get("fill",False),manual=True))
    elif a=="add":job(a,add_phone)
    elif a=="sync":
        if MIRROR.state()["active"]:raise ValueError("Pare o espelhamento antes da gravacao automatica")
        job(a,lambda:supervised_sync(d) if d.get('supervisor',True) or d.get('interleavedPlan') else sync(d))
    elif a=='minute_catalog':
        if s not in by: raise ValueError('Selecione o celular para ler as tarefas.')
        def scan():
            E.cancelar_sync.clear()
            n,p=by[s]
            if status(s)!='online':
                start_phone(n,s,p)
                if not wait_open(s,time.monotonic()+360): raise RuntimeError('O celular não terminou de iniciar.')
            collect_catalog(AUTOMATION,s,os.path.join(AREA,'minute-catalog.json'),update)
        job(a,scan)
    elif a=="cancel":SUPERVISOR.stop();E.cancelar_sync.set()
    elif a=="loop_stop_after_round":SUPERVISOR.stop();AUTOMATION.request_stop_after_round()
    elif a=="adjust":
        if not snap()["task"]:raise RuntimeError("nenhuma tarefa detectada")
        E._definir_uso_tarefa(by[s][0],snap()["task"],int(d["minutes"])*60)
    else:raise RuntimeError("acao invalida")

class H(BaseHTTPRequestHandler):
    def log_message(self,*_):pass
    def sendj(self,x,c=200):
        b=json.dumps(x,ensure_ascii=False).encode();self.send_response(c);self.send_header("Content-Type","application/json; charset=utf-8");self.send_header("Content-Length",str(len(b)));self.end_headers();self.wfile.write(b)
    def video_path(self):
        name=os.path.basename(urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).get("name",[""])[0]);path=os.path.abspath(os.path.join(VIDEOS,name))
        return path if path.startswith(os.path.abspath(VIDEOS)+os.sep) and os.path.isfile(path) else None
    def send_media(self,path):
        size=os.path.getsize(path);start,end=0,size-1;partial=False
        match=re.match(r"bytes=(\d*)-(\d*)",self.headers.get("Range", ""))
        if match:
            partial=True
            if match.group(1):start=int(match.group(1))
            if match.group(2):end=min(end,int(match.group(2)))
            elif start==0:end=min(end,4*1024*1024-1)
        if start<0 or start>end or start>=size:return self.send_error(416)
        length=end-start+1;self.send_response(206 if partial else 200)
        self.send_header("Content-Type",mimetypes.guess_type(path)[0] or "video/mp4");self.send_header("Accept-Ranges","bytes");self.send_header("Content-Length",str(length))
        if partial:self.send_header("Content-Range",f"bytes {start}-{end}/{size}")
        self.end_headers()
        with open(path,"rb") as f:
            f.seek(start);left=length
            while left:
                chunk=f.read(min(left,1024*1024))
                if not chunk:break
                try:self.wfile.write(chunk)
                except (BrokenPipeError,ConnectionResetError):break
                left-=len(chunk)
    def send_thumb(self,path):
        os.makedirs(THUMBS,exist_ok=True);st=os.stat(path);name=hashlib.sha1((path+str(st.st_mtime_ns)).encode()).hexdigest()+".jpg";out=os.path.join(THUMBS,name)
        if not os.path.isfile(out):
            ff=P.achar("ffmpeg")
            if ff:subprocess.run([ff,"-y","-ss","1","-i",path,"-frames:v","1","-vf","scale=640:-2","-q:v","3",out],capture_output=True,timeout=45,**hidden())
        if not os.path.isfile(out):return self.send_error(404)
        b=open(out,"rb").read();self.send_response(200);self.send_header("Content-Type","image/jpeg");self.send_header("Cache-Control","public, max-age=86400");self.send_header("Content-Length",str(len(b)));self.end_headers();self.wfile.write(b)
    def do_GET(self):
        path=urllib.parse.urlparse(self.path).path
        if path=="/api/version":return self.sendj(RUNTIME_ID)
        if path=='/api/health':
            with LOCK:health=dict(busy=S['busy'],lastProgress=LAST_PROGRESS,waiting=S.get('planWaitingNextDay',False))
            return self.sendj(health)
        if path=="/api/state":return self.sendj(payload())
        if path=="/api/tiktok/state":return self.sendj(dict(TIKTOK_VIDEO.snapshot(),phones=TIKTOK_VIDEO.phones()))
        if path=="/api/voice/state":return self.sendj(dict(VOICE.snapshot(),live=LIVE_VOICE.snapshot()))
        if path=="/api/voice/audio":
            ident=urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).get("id",[""])[0]
            try:q=VOICE.clip_path(ident)
            except ValueError:return self.send_error(404)
            return self.send_media(q) if q.is_file() and q.with_suffix('.json').is_file() else self.send_error(404)
        if path=="/media":
            with library_read():
                q=self.video_path();return self.send_media(q) if q else self.send_error(404)
        if path=="/preview":
            ident=urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).get("id",[""])[0]
            q=os.path.join(THUMBS,ident+".mp4") if re.fullmatch(r"[0-9a-f]{40}",ident) else ""
            return self.send_media(q) if q and os.path.isfile(q) else self.send_error(404)
        if path=="/api/thumb":
            with library_read():
                q=self.video_path();return self.send_thumb(q) if q else self.send_error(404)
        if path=="/":path="/index.html"
        q=os.path.abspath(os.path.join(WEB,path.lstrip("/")))
        if not q.startswith(os.path.abspath(WEB)) or not os.path.isfile(q):return self.send_error(404)
        b=open(q,"rb").read();mime={".html":"text/html",".css":"text/css",".js":"application/javascript"}.get(os.path.splitext(q)[1],"application/octet-stream")
        self.send_response(200);self.send_header("Content-Type",mime+"; charset=utf-8");self.send_header("Cache-Control","no-cache");self.send_header("Content-Length",str(len(b)));self.end_headers();self.wfile.write(b)
    def do_POST(self):
        if self.path=="/api/voice/action":
            origin=self.headers.get("Origin")
            if origin and origin != "http://"+self.headers.get("Host", ""):
                return self.sendj({"error":"Origem não autorizada"},403)
            try:
                size=int(self.headers.get("Content-Length", "0"))
                if not 0<size<=16384:return self.sendj({"error":"Requisição inválida"},400)
                data=json.loads(self.rfile.read(size))
                if not isinstance(data,dict):raise ValueError("Requisição inválida")
                command=data.get("action")
                result={"ok":True}
                if LIVE_VOICE.snapshot()['active'] and command in {'generate','play','unload','sale_demo'}:
                    raise ValueError('Pare a sessão contínua antes de usar este controle.')
                if command=="save_openai_key":WRITER.save_key(data.get('key'))
                elif command=="save_product":WRITER.save_product(data.get('product'))
                elif command in {'live_prepare','live_start'}:
                    with LOCK:
                        if S.get('libraryEditing'):raise ValueError('Aguarde a alteração da biblioteca terminar.')
                        LIVE_VOICE.start(data.get('product'),data.get('output',''),data.get('volume',.8),
                            data.get('minutes',60),data.get('steps',32),continuous=command=='live_start')
                elif command=="live_stop":LIVE_VOICE.stop()
                elif command=="unload":VOICE.unload()
                elif command=="sale_demo":result["id"]=VOICE.sale_demo()
                elif command=="sales_config":LIVE_VOICE.configure_sales(data.get('minimum'),data.get('maximum'))
                elif command=="stock_update":LIVE_VOICE.update_stock(data.get('product'),data.get('remaining'))
                elif command=="sales_add_batch":result.update(LIVE_VOICE.add_sales(data.get('entries'),data.get('confirmed')))
                elif command=="sales_add":result.update(LIVE_VOICE.add_sale(data.get('order'),data.get('confirmed')))
                elif command=="generate":result["id"]=VOICE.generate(data.get("text"),data.get("style","natural"),data.get('steps',32))
                elif command=="play":VOICE.play(data.get("id"),data.get("output"),data.get("volume",0.8))
                elif command=="stop":VOICE.stop("playback")
                elif command=="cancel_generation":VOICE.stop("generation")
                elif command=="outputs":VOICE.refresh_outputs()
                elif command=="tiktok_video_connect":
                    with LOCK:
                        if S.get('libraryEditing'):raise ValueError('Aguarde a alteração da biblioteca terminar.')
                        TIKTOK_VIDEO.start(data.get('serial'),data.get('video'),data.get('output'),data.get('volume',.8))
                elif command in {"tiktok_video_play","tiktok_video_pause","tiktok_video_stop"}:
                    TIKTOK_VIDEO.control(command.rsplit('_',1)[1])
                elif command in {"tiktok_check","tiktok_open","tiktok_store","microphone_on","microphone_off"}:
                    if snap()["busy"]:raise ValueError("Aguarde a operação atual do painel terminar.")
                    serial=data.get("serial", "")
                    if command=="tiktok_check":result.update(TIKTOK.inspect(serial))
                    elif command=="tiktok_open":result.update(TIKTOK.open(serial))
                    elif command=="tiktok_store":result.update(TIKTOK.store(serial))
                    else:result.update(TIKTOK.microphone(serial,command=="microphone_on"))
                else:raise ValueError("Ação de voz inválida")
                return self.sendj(result)
            except (ValueError,TypeError,KeyError) as error:return self.sendj({"error":str(error)},400)
            except Exception as error:return self.sendj({"error":str(error)},500)
        if self.path=="/api/upload":
            n=os.path.basename(urllib.parse.unquote(self.headers.get("X-Filename","video.mp4")));z=int(self.headers.get("Content-Length","0"));os.makedirs(VIDEOS,exist_ok=True)
            if not n.lower().endswith(P.EXTS):return self.sendj({"error":"formato de video invalido"},400)
            if not n or z<=0:return self.sendj({"error":"Arquivo vazio"},400)
            background=self.headers.get("X-Background")=="1"
            if not UPLOAD_LOCK.acquire(blocking=False):return self.sendj({"error":"Já existe uma importação em andamento"},409)
            with LOCK:
                if S["busy"] and not background:
                    UPLOAD_LOCK.release()
                    return self.sendj({"error":"Aguarde a operacao atual"},409)
                if not background:S.update(busy=True,stage="Importando",progress=0,level="info",message="Importando "+n)
            stem,extension=os.path.splitext(n);suffix=2
            while os.path.exists(os.path.join(VIDEOS,n)) or os.path.exists(os.path.join(VIDEOS,n)+".uploading"):
                n=f"{stem} ({suffix}){extension}";suffix+=1
            total=z;pending=os.path.join(VIDEOS,n)+".uploading"
            try:
                if shutil.disk_usage(VIDEOS).free<z+256*1024**2:raise RuntimeError("Espaco insuficiente no PC")
                with open(pending,"wb") as f:
                    while z:
                        q=self.rfile.read(min(z,8*1024*1024))
                        if not q:raise RuntimeError("Upload interrompido")
                        f.write(q);z-=len(q)
                        if not background:update(progress=int((total-z)*100/total),message="Importando "+n)
                os.replace(pending,os.path.join(VIDEOS,n))
                if not background:update(busy=False,progress=100,message=n+" importado",stage="Concluido",level="ok")
                return self.sendj({"ok":True,"name":n})
            except Exception as exc:
                if os.path.isfile(pending):os.remove(pending)
                if not background:update(busy=False,level="error",message=str(exc))
                return self.sendj({"error":str(exc)},400)
            finally:
                UPLOAD_LOCK.release()
        try:
            d=json.loads(self.rfile.read(int(self.headers.get('Content-Length','0'))) or b'{}')
            if isinstance(d,dict) and d.get('action') in {'rename_video','delete_video','cancel_preparation'}:
                origin=self.headers.get('Origin')
                if self.path!='/api/action' or (origin and origin!='http://'+self.headers.get('Host','')):
                    return self.sendj({'error':'Origem não autorizada'},403)
            result=action(d)
            self.sendj(dict(ok=True,**result) if isinstance(result,dict) else {'ok':True},200 if isinstance(result,dict) else 202)
        except Exception as x:self.sendj({"error":str(x)},400)
def open_ui():
    url=f"http://127.0.0.1:{PORT}/";edge=next((x for x in [os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe")] if os.path.isfile(x)),None)
    subprocess.Popen([edge,"--app="+url,"--start-maximized"],**hidden()) if edge else webbrowser.open(url)
class PanelServer(ThreadingHTTPServer):
    # Windows SO_REUSEADDR allows multiple processes to steal the same listener.
    allow_reuse_address=False

    def server_bind(self):
        if os.name=="nt":
            self.socket.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1)
        super().server_bind()


def main():
    global PORT
    if FROZEN and len(sys.argv)>1 and sys.argv[1]=="--montar":import montar;montar.main(sys.argv[2:]);return
    # Closing the Edge window does not stop the backend. Reuse only an exact
    # compatible version, otherwise bind a free local port and leave it intact.
    first_port=PORT
    existing=find_running_backend(first_port,RUNTIME_ID)
    if existing is not None:
        PORT=existing
        publish_runtime()
        if "--no-open" not in sys.argv:open_ui()
        return
    server=None
    for candidate in range(first_port,first_port+32):
        try:server=PanelServer(("127.0.0.1",candidate),H)
        except OSError:continue
        PORT=candidate
        break
    if server is None:raise RuntimeError("Não há uma porta local disponível para abrir o painel atualizado.")
    publish_runtime()
    if '--supervisor-resume' in sys.argv:
        saved=SUPERVISOR.state()
        if saved.get('enabled') and saved.get('options'):
            threading.Timer(1,lambda:job('sync',lambda:supervised_sync(saved['options']))).start()
    if "--no-open" not in sys.argv:threading.Timer(.5,open_ui).start()
    if "--abrir-tudo" in sys.argv:threading.Timer(1,lambda:job("all",open_all)).start()
    server.serve_forever()
def publish_runtime():
    target=os.path.join(WEB,'current-runtime.json')
    temporary=target+'.tmp'
    with open(temporary,'w',encoding='utf-8') as out:
        json.dump(dict(RUNTIME_ID,url=f'http://127.0.0.1:{PORT}/'),out)
    os.replace(temporary,target)

if __name__=="__main__":main()
