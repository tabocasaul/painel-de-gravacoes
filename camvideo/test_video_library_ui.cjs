const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');

function setup(options={}){
  const nodes=new Map(),listeners={},events=[],requests=[],toasts=[],cards=[];
  const storage=options.storage || new Map();
  const node=key=>{
    if(nodes.has(key))return nodes.get(key);
    const el={value:'',disabled:false,hidden:false,required:false,textContent:'',dataset:{},handlers:{},attributes:{},open:false,
      append(){},setAttribute(name,value){this.attributes[name]=value;},removeAttribute(name){delete this.attributes[name];this.removedAttribute=name;},pause(){this.paused=true;},load(){this.loads=(this.loads||0)+1;},focus(){this.focused=true;},select(){this.selectedText=true;},showModal(){this.open=true;},close(){this.open=false;},
      addEventListener(name,handler){this.handlers[name]=handler;},
      closest(selector){return selector==='[data-video-library-action]' && this.dataset.videoLibraryAction ? this:null;},
      set innerHTML(value){this.html=value;
        if(key==='videos'){
          cards.length=0;
          for(const match of value.matchAll(/<article class="video-card[^"]*" data-video="([^"]*)">([\s\S]*?)<\/article>/g)){
            const card=node(Symbol());card.dataset.video=match[1];card.buttons=[];
            for(const action of match[2].matchAll(/data-video-library-action="([^"]*)"/g)){
              const button=node(Symbol());button.dataset.videoLibraryAction=action[1];button.disabled=true;card.buttons.push(button);
            }
            cards.push(card);
          }
        }
      },get innerHTML(){return this.html || '';}
    };nodes.set(key,el);return el;
  };
  const videos=options.videos || [{name:'Catando feijão - cozinhar.MOV'},{name:'Jardim.mp4'}];
  const app={state:{busy:false,videoLibraryVersion:1,videos,...options.state},video:options.selected ?? videos[0]?.name ?? '',videoHash:'',preview:'old-preview'};
  const context={app,document:{getElementById:node,createElement:()=>node(Symbol()),body:node('body'),head:node('head'),querySelectorAll:selector=>selector==='.video-card'?cards:selector==='.video-library-action'?cards.flatMap(card=>card.buttons):[]},window:{addEventListener:(name,fn)=>(listeners[name] ||= []).push(fn),dispatchEvent:event=>{events.push(event);for(const listener of listeners[event.type]||[])listener(event);}},CustomEvent:class{constructor(type,options){this.type=type;this.detail=options.detail;}},localStorage:{getItem:key=>storage.get(key) ?? null,setItem:(key,value)=>storage.set(key,String(value))},$ :node,icons(){},empty:()=>'',size:String,duration:String,setPreview(){},esc:value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])),call:async(action,payload)=>{requests.push({action,payload});return options.call ? options.call(action,payload):action==='rename_video'?{oldName:payload.video,name:payload.name}:{name:payload.video,deleted:true};},refresh:async()=>{},toast:value=>toasts.push(value),panelMessage:String};
  vm.createContext(context);
  const source=fs.readFileSync(path.join(__dirname,'web/app.js'),'utf8');
  vm.runInContext(source.slice(source.indexOf('function renderVideos('),source.indexOf('function updateSelectionLabels(')),context);
  vm.runInContext(fs.readFileSync(path.join(__dirname,'web/video-library.js'),'utf8'),context);
  context.renderVideos(app.state.videos);
  const dialog=()=>[...nodes.values()].find(el=>el.id==='video-library-dialog');
  const click=(filename,kind)=>{const card=cards.find(card=>decodeURIComponent(card.dataset.video)===filename),button=card.buttons.find(button=>button.dataset.videoLibraryAction===kind);let stopped=false;card.handlers.click({target:{closest:selector=>selector==='[data-video-library-action]'?button:null},stopPropagation(){stopped=true;}});return stopped;};
  const input=value=>{node('video-library-name').value=value;node('video-library-name').oninput();};
  const submit=()=>node('video-library-form').onsubmit({preventDefault(){}});
  return {node,app,cards,context,requests,storage,events,toasts,dialog,click,input,submit,storageEvent:data=>(listeners.storage||[]).forEach(fn=>fn(data)),connection:connected=>(listeners['panel-connection']||[]).forEach(fn=>fn({detail:{connected}}))};
}

test('pencil and trash controls have per-file labels and opening either does not select or prepare a video',()=>{
  const ui=setup();assert.equal(ui.cards.length,2);assert.equal(ui.cards[0].buttons.length,2);assert.match(ui.node('videos').innerHTML,/data-lucide="pencil"/);assert.match(ui.node('videos').innerHTML,/data-lucide="trash-2"/);assert.match(ui.node('videos').innerHTML,/aria-label="Excluir Jardim.mp4"/);
  assert.equal(ui.click('Jardim.mp4','rename'),true);assert.equal(ui.app.video,'Catando feijão - cozinhar.MOV');assert.equal(ui.dialog().open,true);assert.equal(ui.node('video-library-name').value,'Jardim');assert.equal(ui.requests.length,0);
  ui.node('video-library-cancel').onclick();ui.click('Jardim.mp4','delete');assert.equal(ui.app.video,'Catando feijão - cozinhar.MOV');assert.equal(ui.node('video-library-filename').textContent,'Jardim.mp4');assert.match(ui.node('video-library-explanation').textContent,/Lixeira do Windows/);assert.equal(ui.requests.length,0);
});

test('renaming preserves extension and selected video, and updates all saved references only after success',async()=>{
  const old='Catando feijão - cozinhar.MOV',renamed='Feijão novo.MOV';
  const storage=new Map([['interleaved-task-videos',JSON.stringify({'Louça':[old,'Jardim.mp4',old,''],'Legada':old})]]);
  const ui=setup({storage});ui.click(old,'rename');ui.input('Feijão novo.mov');await ui.submit();
  assert.equal(ui.requests.length,1);assert.equal(ui.requests[0].action,'rename_video');assert.deepEqual(JSON.parse(JSON.stringify(ui.requests[0].payload)),{video:old,name:renamed});assert.equal(ui.app.video,renamed);assert.equal(ui.dialog().open,false);
  assert.deepEqual(JSON.parse(storage.get('interleaved-task-videos')),{'Louça':[renamed,'Jardim.mp4',renamed,''],'Legada':renamed});assert.deepEqual(JSON.parse(JSON.stringify(ui.events.find(event=>event.type==='video-library-renamed').detail)),{oldName:old,name:renamed});
});

test('renaming another file leaves the current selection alone',async()=>{
  const ui=setup();ui.click('Jardim.mp4','rename');ui.input('Flores');await ui.submit();assert.equal(ui.app.video,'Catando feijão - cozinhar.MOV');assert.equal(ui.requests[0].payload.name,'Flores.mp4');
});

test('delete requires its own confirmation and leaves playlist references visible as missing',async()=>{
  const storage=new Map([['interleaved-task-videos',JSON.stringify({'Jardim':['Jardim.mp4']})]]);const ui=setup({storage});
  ui.click('Jardim.mp4','delete');ui.node('video-library-cancel').onclick();assert.equal(ui.requests.length,0);ui.click('Jardim.mp4','delete');await ui.submit();
  assert.equal(ui.requests.length,1);assert.equal(ui.requests[0].action,'delete_video');assert.deepEqual(JSON.parse(JSON.stringify(ui.requests[0].payload)),{video:'Jardim.mp4'});assert.equal(ui.app.state.videos.some(video=>video.name==='Jardim.mp4'),false);assert.equal(ui.app.video,'Catando feijão - cozinhar.MOV');assert.deepEqual(JSON.parse(storage.get('interleaved-task-videos')),{'Jardim':['Jardim.mp4']});assert.equal(ui.events.some(event=>event.type==='video-library-renamed'),false);
});

test('polling and preparation lock the modal without losing the entered name',async()=>{
  const ui=setup();ui.click('Jardim.mp4','rename');ui.input('Minhas flores');ui.app.state={...ui.app.state,backgroundVideo:{busy:true}};ui.context.renderVideos(ui.app.state.videos);
  assert.equal(ui.dialog().open,true);assert.equal(ui.node('video-library-name').value,'Minhas flores');assert.equal(ui.node('video-library-name').disabled,true);assert.equal(ui.node('video-library-confirm').disabled,true);await ui.submit();assert.equal(ui.requests.length,0);
  ui.app.state={...ui.app.state,backgroundVideo:{busy:false}};ui.context.renderVideos(ui.app.state.videos);assert.equal(ui.node('video-library-name').value,'Minhas flores');assert.equal(ui.node('video-library-confirm').disabled,false);await ui.submit();assert.equal(ui.requests[0].payload.name,'Minhas flores.mp4');
});

test('old backend, busy operations and disconnection disable all library mutations',()=>{
  for(const state of [{videoLibraryVersion:undefined},{busy:true},{backgroundVideo:{busy:true}},{videoLibraryBusy:true}]){
    const ui=setup({state});assert.equal(ui.cards.every(card=>card.buttons.every(button=>button.disabled)),true);ui.click('Jardim.mp4','delete');assert.equal(ui.dialog().open,false);assert.equal(ui.requests.length,0);
  }
  const ui=setup();ui.click('Jardim.mp4','rename');ui.input('Flores');ui.connection(false);assert.equal(ui.node('video-library-confirm').disabled,true);assert.match(ui.node('video-library-feedback').textContent,/Sem conexão/);ui.connection(true);assert.equal(ui.node('video-library-confirm').disabled,false);
});

test('a pending rename is sent once and errors preserve the old names and input for correction',async()=>{
  let reject;const storage=new Map([['interleaved-task-videos',JSON.stringify({'Jardim':['Jardim.mp4']})]]);const ui=setup({storage,call:()=>new Promise((resolve,fail)=>reject=fail)});
  ui.click('Jardim.mp4','rename');ui.input('Flores');const pending=ui.submit();assert.equal(ui.node('video-library-confirm').disabled,true);assert.equal(ui.node('video-library-cancel').disabled,true);await ui.submit();assert.equal(ui.requests.length,1);reject(Error('O arquivo está em uso'));await pending;
  assert.equal(ui.dialog().open,true);assert.equal(ui.node('video-library-name').value,'Flores');assert.equal(ui.app.state.videos.some(video=>video.name==='Jardim.mp4'),true);assert.deepEqual(JSON.parse(storage.get('interleaved-task-videos')),{'Jardim':['Jardim.mp4']});assert.match(ui.node('video-library-feedback').textContent,/arquivo está em uso/);assert.equal(ui.events.length,0);
});

test('invalid names never reach an action and removing the last selected video clears the preview selection',async()=>{
  const ui=setup({videos:[{name:'Único.MOV'}]});ui.click('Único.MOV','rename');
  for(const value of ['','Único','../fora','pasta\\fora','nome:inválido']){ui.input(value);await ui.submit();assert.equal(ui.requests.length,0,value);}
  ui.node('video-library-cancel').onclick();ui.click('Único.MOV','delete');await ui.submit();assert.equal(ui.app.video,'');assert.equal(ui.app.state.videos.length,0);assert.equal(ui.requests[0].action,'delete_video');
});

test('a currently selected preview is paused and released before the rename request',async()=>{
  let ui;ui=setup({call:(action,payload)=>{assert.equal(ui.node('preview').paused,true);assert.equal(ui.node('preview').removedAttribute,'src');assert.equal(ui.node('preview').loads,1);return {oldName:payload.video,name:payload.name};}});
  ui.click('Catando feijão - cozinhar.MOV','rename');ui.input('Feijão');await ui.submit();assert.equal(ui.app.video,'Feijão.MOV');assert.equal(ui.requests.length,1);
});

test('a confirmed rename from another window follows the selection without issuing any command',()=>{
  const ui=setup();ui.storageEvent({key:'video-library-last-rename',newValue:JSON.stringify({oldName:'Catando feijão - cozinhar.MOV',name:'Feijão.MOV'})});assert.equal(ui.app.video,'Feijão.MOV');assert.equal(ui.requests.length,0);assert.equal(ui.app.state.videos[0].name,'Feijão.MOV');
});
