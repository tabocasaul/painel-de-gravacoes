const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');

function setup(options={}){
  const nodes=new Map(),listeners={},requests=[],toasts=[];
  const node=key=>{
    if(!nodes.has(key))nodes.set(key,{value:0,textContent:'',style:{},dataset:{},disabled:false,hidden:false,checked:false,attributes:{},before(){},append(){},setAttribute(name,value){this.attributes[name]=value;}});
    return nodes.get(key);
  };
  const app={state:{},video:'Outro vídeo selecionado.MOV',uploadProgress:null};
  const context={app,$:node,document:{createElement:()=>node(Symbol()),getElementById:node,querySelector:node,head:node('head')},window:{addEventListener:(name,fn)=>listeners[name]=fn},render(state){app.state=state;},size:String,esc:String,toast:value=>toasts.push(value),call:async(action,payload)=>{requests.push({action,payload});return options.call?options.call(action,payload):{...payload,cancelRequested:true};},refresh:async()=>{},location:{replace(){throw Error('Unexpected navigation');}},XMLHttpRequest:class{constructor(){throw Error('No upload request expected');}}};
  vm.createContext(context);
  for(const file of ['transfers.js','background-video.js','preparation-cancel.js'])vm.runInContext(fs.readFileSync(path.join(__dirname,'web',file),'utf8'),context);
  const state={apiVersion:4,sharedCameraVersion:1,backgroundVideoVersion:1,preparationCancellationVersion:1,busy:false,phones:[],videos:[],...options.state};context.render(state);
  return {node,context,app,state,requests,toasts,render:state=>context.render(state),button:kind=>node(`${kind}-cancel-preparation`),feedback:kind=>node(`${kind}-cancel-feedback`),connection:connected=>listeners['panel-connection']({detail:{connected}})};
}
const running=(id='job-1',name='Vídeo em preparação.MOV')=>({jobId:id,name,busy:true,canCancel:true,cancelRequested:false,progress:47,stage:'Convertendo quadros',error:'',status:'running'});

test('background cancel targets the displayed preparation rather than the selected library video',async()=>{
  const ui=setup({state:{backgroundVideo:running()}});assert.equal(ui.node('background-percent').textContent,'47%');assert.equal(ui.button('background').hidden,false);assert.equal(ui.button('background').disabled,false);assert.match(ui.button('background').title,/Vídeo em preparação.MOV/);
  ui.app.video='Outro arquivo escolhido depois.mp4';await ui.button('background').onclick();assert.equal(ui.requests.length,1);assert.equal(ui.requests[0].action,'cancel_preparation');assert.deepEqual(JSON.parse(JSON.stringify(ui.requests[0].payload)),{jobId:'job-1',kind:'background'});assert.equal(ui.button('background').textContent,'Cancelando...');assert.equal(ui.node('background-prepare').disabled,true);
  ui.render({...ui.state,backgroundVideo:{...running(),busy:false,status:'cancelled',canCancel:true,cancelRequested:true}});assert.equal(ui.node('background-prepare').disabled,false);assert.equal(ui.requests.length,1);assert.equal(ui.button('background').textContent,'Limpar aviso');assert.equal(ui.button('background').disabled,false);
});

test('foreground cancel and percentage belong to the manual preparation while existing recording controls are untouched',async()=>{
  const ui=setup({state:{busy:true,operation:'install_all',progress:99,foregroundPreparation:running('fg-2','Louça.MOV')}});
  assert.equal(ui.node('video-stage-percent').textContent,'47%');assert.match(ui.node('video-stage').textContent,/Louça.MOV/);assert.equal(ui.button('foreground').hidden,false);assert.equal(ui.node('install-all').disabled,true);
  await ui.button('foreground').onclick();assert.equal(ui.requests[0].action,'cancel_preparation');assert.deepEqual(JSON.parse(JSON.stringify(ui.requests[0].payload)),{jobId:'fg-2',kind:'foreground'});assert.equal(ui.requests.some(request=>request.action==='cancel'),false);
  ui.render({...ui.state,busy:false,foregroundPreparation:{...running('fg-2'),busy:false,status:'cancelled',cancelRequested:true,canCancel:true}});assert.equal(ui.node('install-all').disabled,false);assert.equal(ui.requests.length,1);
});

test('cancellation is sent once while pending and neither acceptance nor a stale snapshot unlocks preparation',async()=>{
  let resolve;const ui=setup({state:{backgroundVideo:running()},call:(action,payload)=>new Promise(done=>resolve=()=>done({...payload,cancelRequested:true}))});
  const pending=ui.button('background').onclick();assert.equal(ui.button('background').disabled,true);await ui.button('background').onclick();assert.equal(ui.requests.length,1);ui.render(ui.state);assert.equal(ui.node('background-prepare').disabled,true);resolve();await pending;assert.equal(ui.button('background').disabled,true);assert.equal(ui.node('background-prepare').disabled,true);
  ui.render({...ui.state,backgroundVideo:{...running(),busy:false,status:'completed',canCancel:false}});assert.equal(ui.button('background').hidden,true);assert.equal(ui.node('background-prepare').disabled,false);assert.equal(ui.requests.length,1);
});

test('a late response for an old job cannot cancel or disable the new job',async()=>{
  let resolve;const ui=setup({state:{backgroundVideo:running('old-job','Antigo.MOV')},call:(action,payload)=>new Promise(done=>resolve=()=>done({...payload,cancelRequested:true}))});
  const pending=ui.button('background').onclick();ui.render({...ui.state,backgroundVideo:running('new-job','Novo.MOV')});assert.equal(ui.button('background').dataset.jobId,'new-job');assert.equal(ui.button('background').disabled,false);resolve();await pending;assert.equal(ui.button('background').disabled,false);assert.equal(ui.button('background').textContent,'Cancelar');assert.equal(ui.feedback('background').textContent,'');assert.equal(ui.requests.length,1);assert.equal(ui.requests[0].payload.jobId,'old-job');
});

test('clearing a failed job uses its identifier and does not restart preparation',async()=>{
  const failed={...running('failed-job','Falhou.MOV'),busy:false,status:'error',error:'Vídeo incompleto'};
  const ui=setup({state:{backgroundVideo:failed},call:(action,payload)=>({...payload,cleared:true})});assert.equal(ui.button('background').textContent,'Limpar falha');assert.match(ui.feedback('background').textContent,/nova tentativa deve ser iniciada manualmente/);await ui.button('background').onclick();assert.equal(ui.requests.length,1);assert.equal(ui.requests[0].payload.jobId,'failed-job');assert.equal(ui.button('background').textContent,'Limpando...');
  ui.render({...ui.state,backgroundVideo:{status:'idle',busy:false,canCancel:false}});assert.equal(ui.button('background').hidden,true);assert.equal(ui.requests.length,1);assert.equal(ui.node('background-prepare').disabled,false);
});

test('protected plan, publication and camera transfer phases have no cancellation action',async()=>{
  for(const status of ['idle','completed','running']){
    const ui=setup({state:{busy:true,operation:'sync',foregroundPreparation:{...running(),status,canCancel:false,cancelRequested:false},backgroundVideo:{}}});assert.equal(ui.button('foreground').hidden,true);assert.equal(ui.button('background').hidden,true);await ui.button('foreground').onclick();assert.equal(ui.requests.length,0);
  }
});

test('offline and old-server controls cannot submit cancellation',async()=>{
  const ui=setup({state:{backgroundVideo:running(),preparationCancellationVersion:undefined}});assert.equal(ui.button('background').disabled,true);assert.match(ui.feedback('background').textContent,/Atualize o painel/);await ui.button('background').onclick();assert.equal(ui.requests.length,0);
  ui.render({...ui.state,preparationCancellationVersion:1});ui.connection(false);assert.equal(ui.button('background').disabled,true);assert.match(ui.feedback('background').textContent,/Sem conexão/);await ui.button('background').onclick();assert.equal(ui.requests.length,0);ui.connection(true);assert.equal(ui.button('background').disabled,false);
});

test('request errors remain visible for their job and allow another explicit cancellation attempt',async()=>{
  const ui=setup({state:{foregroundPreparation:running()},call:()=>{throw Error('Este trabalho não pode ser cancelado agora');}});await ui.button('foreground').onclick();assert.equal(ui.button('foreground').disabled,false);assert.match(ui.feedback('foreground').textContent,/não pode ser cancelado agora/);assert.equal(ui.requests.length,1);
  ui.render({...ui.state,foregroundPreparation:running('different-job')});assert.equal(ui.feedback('foreground').textContent,'');assert.equal(ui.requests.length,1);
});

test('the cancel button is not an upload-abort button and unrelated jobs are not sent',async()=>{
  const ui=setup({state:{backgroundVideo:running(),foregroundPreparation:running('foreground')}});
  vm.runInContext("backgroundUpload={name:'Importando.MOV',percent:30};app.uploadProgress={name:'Outro.MOV',percent:20,loaded:20,total:100}",ui.context);ui.render(ui.state);assert.equal(ui.button('background').hidden,true);assert.equal(ui.button('foreground').hidden,true);assert.equal(ui.node('background-percent').textContent,'30%');assert.equal(ui.node('video-stage-percent').textContent,'20%');await ui.button('background').onclick();await ui.button('foreground').onclick();assert.equal(ui.requests.length,0);
});

test('a mismatched cancellation response cannot be mistaken for acknowledgment of this job',async()=>{
  const ui=setup({state:{backgroundVideo:running()},call:()=>({jobId:'wrong-job',kind:'foreground',cancelRequested:true})});await ui.button('background').onclick();assert.match(ui.feedback('background').textContent,/não confirmou o cancelamento/);assert.equal(ui.node('background-prepare').disabled,true);assert.equal(ui.requests.length,1);
});

test('an old failed foreground preparation does not mask a later operation and returns as an idle warning',()=>{
  const oldFailure={...running('old-failed','Vídeo antigo.MOV'),busy:false,status:'error',error:'Falha anterior'};
  const ui=setup({state:{busy:true,operation:'minute_catalog',stage:'Lendo catálogo',message:'Consultando tarefas atuais',progress:83,foregroundPreparation:oldFailure}});
  assert.equal(ui.node('video-stage-percent').textContent,'83%');assert.match(ui.node('video-stage').textContent,/Lendo catálogo/);assert.doesNotMatch(ui.node('video-stage').textContent,/Vídeo antigo|Falha anterior/);assert.equal(ui.button('foreground').hidden,true);assert.equal(ui.feedback('foreground').textContent,'');
  ui.render({...ui.state,busy:false});assert.equal(ui.node('video-stage-percent').textContent,'47%');assert.match(ui.node('video-stage').textContent,/Vídeo antigo.MOV/);assert.equal(ui.button('foreground').hidden,false);assert.equal(ui.button('foreground').textContent,'Limpar falha');assert.equal(ui.requests.length,0);
});
