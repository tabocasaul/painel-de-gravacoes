"""Mirror physical emulator touch gestures, never injected follower events."""
import concurrent.futures
import re
import subprocess
import threading
import time


class TouchMirror:
    def __init__(self, adb, hidden):
        self.adb=adb; self.hidden=hidden
        self.lock=threading.Lock();self.process=None;self.worker=None;self.stop_event=threading.Event()
        self.info={"active":False,"source":"","targets":[],"message":"Desativado"}

    def state(self):
        with self.lock:return dict(self.info)

    def stop(self):
        self.stop_event.set()
        if self.process and self.process.poll() is None:self.process.terminate()
        if self.worker:self.worker.join(timeout=12)
        if self.worker and self.worker.is_alive():raise RuntimeError("Aguardando o ultimo comando terminar; tente parar novamente")
        with self.lock:self.info["active"]=False

    def run_adb(self, serial, *args):
        result=subprocess.run([self.adb,"-s",serial,*args],capture_output=True,text=True,timeout=10,**self.hidden())
        if result.returncode:raise RuntimeError(result.stderr.strip() or "Falha ADB")
        return result.stdout

    def start(self, source, targets):
        if self.state()["active"]:raise ValueError("Pare o espelhamento atual primeiro")
        if not targets:raise ValueError("Ligue pelo menos dois celulares")
        listing=self.run_adb(source,"shell","su","-c","getevent -lp")
        device=None
        for block in re.split(r"add device",listing):
            path=re.search(r"(/dev/input/event\d+)",block)
            x=re.search(r"ABS_MT_POSITION_X[^\n]*min\s+(-?\d+),\s+max\s+(\d+)",block)
            y=re.search(r"ABS_MT_POSITION_Y[^\n]*min\s+(-?\d+),\s+max\s+(\d+)",block)
            if path and x and y:
                device=path.group(1);bounds=tuple(map(int,(*x.groups(),*y.groups())));break
        if not device:raise ValueError("Touchscreen nao encontrado; confira o root do celular principal")
        sizes={}
        for serial in [source,*targets]:
            found=re.findall(r"(\d+)x(\d+)",self.run_adb(serial,"shell","wm","size"))
            if not found:raise ValueError("Nao foi possivel ler a resolucao")
            sizes[serial]=tuple(map(int,found[-1]))
        self.stop_event=threading.Event()
        self.process=subprocess.Popen([self.adb,"-s",source,"shell","su","-c","getevent -lt"],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,bufsize=1,**self.hidden())
        with self.lock:self.info={"active":True,"source":source,"targets":targets,"message":"Espelhando toques e arrastos"}
        self.worker=threading.Thread(target=self.watch,args=(self.process,self.stop_event,device,bounds,sizes,targets),daemon=True)
        self.worker.start()

    def watch(self, process, stop, device, bounds, sizes, targets):
        gesture=Gesture(bounds)
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=min(50,len(targets))) as pool:
                for line in process.stdout:
                    if stop.is_set():break
                    match=re.search(r"(/dev/input/event\d+):\s+(EV_\w+)\s+(\w+)\s+(\w+)",line)
                    if not match:continue
                    path,kind,code,value=match.groups()
                    keys={"KEY_BACK":"4","KEY_HOMEPAGE":"3","KEY_VOLUMEUP":"24","KEY_VOLUMEDOWN":"25","KEY_POWER":"26"}
                    command=keys.get(code) if kind=="EV_KEY" and value in ("UP","00000000") else None
                    if command is None:
                        if path!=device:continue
                        command=gesture.feed(code,value)
                    if command:
                        # Complete each gesture on all followers before dispatching the next.
                        futures=[pool.submit(self.send,serial,command,sizes[serial]) for serial in targets]
                        for future in futures:future.result()
        except Exception as error:
            with self.lock:self.info["message"]=str(error)
        finally:
            if process.poll() is None:process.terminate()
            with self.lock:
                self.info["active"]=False
                if stop.is_set():self.info["message"]="Espelhamento parado"
                elif self.info["message"]=="Espelhando toques e arrastos":self.info["message"]="Conexao com o principal encerrada"

    def send(self, serial, command, size):
        if isinstance(command,str):
            self.run_adb(serial,"shell","input","keyevent",command);return
        x,y,x2,y2,duration=command;w,h=size
        points=[str(round(a*(b-1))) for a,b in zip((x,y,x2,y2),(w,h,w,h))]
        args=["tap",*points[:2]] if duration<250 and abs(x-x2)+abs(y-y2)<.015 else ["swipe",*points,str(max(1,min(duration,10000))) ]
        self.run_adb(serial,"shell","input",*args)


class Gesture:
    def __init__(self,bounds):
        self.bounds=bounds;self.x=None;self.y=None;self.start=None;self.active=False;self.up=False;self.multi=False;self.slot=0

    def feed(self,code,value):
        try:v=int(value,16)
        except ValueError:v=1 if value=="DOWN" else 0
        if code=="ABS_MT_SLOT":self.slot=v
        if code=="ABS_MT_TRACKING_ID":
            if self.slot>0:
                if v!=0xffffffff:self.multi=True
            elif v==0xffffffff:self.up=True
            else:self.active=True;self.up=False;self.start=None;self.multi=False;self.x=None;self.y=None;self.began=time.monotonic()
        if self.slot==0:
            if code=="ABS_MT_POSITION_X":self.x=v
            if code=="ABS_MT_POSITION_Y":self.y=v
        if code!="SYN_REPORT" or not self.active or self.x is None or self.y is None:return
        lo,hi,loy,hiy=self.bounds
        point=(max(0,min(1,(self.x-lo)/max(1,hi-lo))),max(0,min(1,(self.y-loy)/max(1,hiy-loy))))
        if self.start is None:self.start=point
        if self.up:
            self.active=False
            if not self.multi:return (*self.start,*point,int((time.monotonic()-self.began)*1000))
