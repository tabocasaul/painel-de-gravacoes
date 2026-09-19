"""One-time, resumable offline account clones. Original AVDs are retained."""
import json
import os
from pathlib import Path
import subprocess
import time
import xml.etree.ElementTree as ET
from storage import SDK, clone_offline, finish_resize

HOME=Path.home()/'.android/avd'
AREA=Path(os.path.expandvars(r'%LOCALAPPDATA%\emulation-cam'))
REPORT=AREA/'storage-migration.json'
ADB=str(SDK/'platform-tools/adb.exe')
HIDDEN={'creationflags':subprocess.CREATE_NO_WINDOW}
MAPPING=[(2,9),(1,10),(3,11),(4,12),(5,13),(6,14),(7,15)]

def name(i):return 'MinutePlay'+(str(i) if i>1 else '')
def serial(i):return 'emulator-'+str(5554+(i-1)*2)
def adb(s,*args,check=True):
    return subprocess.run([ADB,'-s',s]+list(args),capture_output=True,text=True,encoding="utf-8",errors="replace",timeout=45,check=check,**HIDDEN).stdout
def save(report):
    temp=REPORT.with_suffix('.tmp');temp.write_text(json.dumps(report,indent=2),encoding='utf-8');temp.replace(REPORT)

def validate_login(s):
    adb(s,'shell','monkey','-p','com.bakerdata.minute','-c','android.intent.category.LAUNCHER','1')
    end=time.monotonic()+90
    last=[]
    while time.monotonic()<end:
        time.sleep(5)
        adb(s,'shell','uiautomator','dump','/data/local/tmp/migration-validation.xml',check=False)
        raw=adb(s,'shell','cat','/data/local/tmp/migration-validation.xml',check=False)
        try:
            nodes=list(ET.fromstring(raw).iter('node'))
            last=[n.get('text','') for n in nodes if n.get('text')]
            text=' '.join(last).casefold()
            # Screen evidence only; never read or print auth-token databases.
            if any(x in text for x in ['available tasks','earnings','wallet','tarefas','carteira','ganhos','projects','projetos']):
                return {'confirmed':True,'screen':last[:30]}
            if any(x in text for x in ['sign in','log in','entrar com','welcome to minute']):
                return {'confirmed':False,'screen':last[:30]}
        except ET.ParseError:pass
    return {'confirmed':False,'screen':last[:30]}

def main():
    report=json.loads(REPORT.read_text()) if REPORT.exists() else {}
    for source_index,target_index in MAPPING:
        source,target=name(source_index),name(target_index)
        s=serial(target_index)
        if report.get(target,{}).get('complete'):continue
        print(f'{source} -> {target}: copiando',flush=True)
        if not (HOME/(target+'.avd')).exists():
            if adb(serial(source_index),'get-state',check=False).strip()=='device':
                adb(serial(source_index),'shell','sync')
                adb(serial(source_index),'emu','kill');time.sleep(8)
            clone_offline(HOME/(source+'.avd'),HOME/(target+'.avd'))
        (HOME/(target+'.ini')).write_text('avd.ini.encoding=UTF-8\npath='+str(HOME/(target+'.avd'))+'\npath.rel=avd\\'+target+'.avd\ntarget=android-33\n',encoding='utf-8')
        if adb(s,'get-state',check=False).strip()!='device':
            log=(AREA/(target+'-migration-boot.log')).open('wb')
            subprocess.Popen([str(SDK/'emulator/emulator.exe'),'-avd',target,'-port',s.split('-')[1],'-no-snapshot','-no-window','-timezone','America/Sao_Paulo','-gpu','auto'],stdout=log,stderr=subprocess.STDOUT,**HIDDEN)
        capacity=finish_resize(s,lambda message:print(target+': '+message,flush=True))
        login=validate_login(s)
        report[target]={'source':source,'serial':s,**capacity,'login':login,'complete':True}
        save(report)
        print(target+': '+str(round(capacity['free']/1024**3,1))+' GiB livres; login='+str(login['confirmed']),flush=True)
        adb(s,'shell','sync');adb(s,'emu','kill');time.sleep(6)

if __name__=='__main__':main()
