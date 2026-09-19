const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

// Exercise actual handlers with a small DOM fixture; never contact a server.
function setup(call = async () => {}, options = {}) {
  const nodes = new Map(), listeners = {};
  const storage = options.storage || new Map([['automation-plan','single']]);
  const defaults = {'automation-plan':'daily','automation-mode':'auto','automation-repeat':'once','automation-scope':'all','automation-simultaneous-mode':'custom','automation-simultaneous':'2'};
  const unescape = value => value.replace(/&quot;/g,'"').replace(/&#39;/g,"'").replace(/&lt;/g,'<').replace(/&gt;/g,'>').replace(/&amp;/g,'&');
  const node = key => {
    if (nodes.has(key)) return nodes.get(key);
    const el = {value:defaults[key] || '',disabled:false,hidden:false,checked:false,dataset:{},style:{},textContent:'',rows:[],checks:[],catalogRows:[],videos:[],handlers:{},
      prepend(){},after(){},append(){},setAttribute(){},focus(){this.focused=true;},
      addEventListener(name,handler){this.handlers[name]=handler;},
      matches(selector){return selector.startsWith('.') && (this.className || '').split(' ').includes(selector.slice(1));},
      closest(selector){return this.matches(selector) ? this : this.row?.matches(selector) ? this.row : null;},
      querySelector(selector){return selector === '.catalog-check' ? this.check : null;},
      querySelectorAll(selector){
        if(selector === '.participant-row')return this.rows;
        if(selector === '.participant-check')return this.checks;
        if(selector === '.catalog-row')return this.catalogRows;
        if(selector === '.catalog-video')return this.videos;
        if(selector === 'button,select,input' && this.html?.includes('id="catalog-choices"'))return node('catalog-choices').catalogRows.flatMap(row=>[row.check,...row.videos,row.add,...row.removes]);
        return [];
      },
      set innerHTML(value){
        this.html = value; this.rows = []; this.checks = [];
        if (key === 'automation-participant-list') {
          for (const match of value.matchAll(/<label class="participant-row" data-search="([^"]*)"><input type="checkbox" class="participant-check" data-serial="([^"]*)">/g)) {
            this.rows.push({dataset:{search:unescape(match[1])},hidden:false});
            const check = node(Symbol()); check.className='participant-check'; check.dataset.serial=unescape(match[2]); this.checks.push(check);
          }
        }
        if(key === 'catalog-choices') {
          this.catalogRows=[];
          for(const match of value.matchAll(/<div class="catalog-row" data-task="([^"]*)">([\s\S]*?)(?=<div class="catalog-row"|$)/g)) {
            const row=node(Symbol());row.className='catalog-row';row.dataset.task=unescape(match[1]);row.html=match[2];row.removes=[];
            row.check=node(Symbol());row.check.className='catalog-check';row.check.row=row;row.check.checked=/class="catalog-check" type="checkbox" checked/.test(row.html);
            for(const select of row.html.matchAll(/<select id="([^"]*)" aria-label="([^"]*)" class="catalog-video" data-index="(\d+)">([\s\S]*?)<\/select>/g)) {
              const input=node(Symbol());input.row=row;input.className='catalog-video';input.dataset.index=select[3];input.ariaLabel=unescape(select[2]);input.html=select[4];
              input.value=unescape(select[4].match(/<option value="([^"]*)" selected>/)?.[1] || '');row.videos.push(input);
              const remove=node(Symbol());remove.row=row;remove.className='catalog-remove-video';remove.dataset.index=select[3];row.removes.push(remove);
            }
            row.add=node(Symbol());row.add.row=row;row.add.className='catalog-add-video';this.catalogRows.push(row);
          }
        }
      },get innerHTML(){return this.html || '';}
    };
    nodes.set(key,el); return el;
  };
  const context = {document:{querySelector:node,getElementById:node,createElement:()=>node(Symbol()),head:node('head')},window:{addEventListener:(name,fn)=>listeners[name]=fn},localStorage:{getItem:key=>storage.get(key) ?? null,setItem:(key,value)=>storage.set(key,String(value))},render(){},call,refresh:async()=>{},act(){},esc:value=>String(value ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])),duration:String,panelMessage:String};
  vm.createContext(context);
  vm.runInContext(fs.readFileSync(path.join(__dirname,'web/automation.js'),'utf8'),context);
  const phones = options.phones || Array.from({length:8},(_,i)=>({serial:`emulator-${5554+i*2}`,name:`Celular ${i+1}`,status:i%2 ? 'off' : 'online'}));
  const state = {busy:false,supervisorVersion:1,participantSelectionVersion:1,automationVersion:5,sharedCameraVersion:1,queueVersion:2,dailyPlanVersion:1,interleavedPlanVersion:1,interleavedVideoListsVersion:1,interleavedSkipFailedRoundsVersion:1,phones,...options.state};
  context.render(state);
  const change = (id,value) => { const el=node(id);el.value=String(value);el.onchange?.({target:el}); };
  const choose = serials => {
    change('automation-scope','selected');
    for (const check of node('automation-participant-list').checks) {
      check.checked=serials.includes(check.dataset.serial);
      node('automation-participant-list').handlers.change({target:check});
    }
  };
  const catalogRow=name=>node('catalog-choices').catalogRows.find(row=>row.dataset.task===name);
  const catalogCheck=(name,checked=true)=>{const input=catalogRow(name).check;input.checked=checked;node('catalog-choices').handlers.change({target:input});};
  const catalogSelect=(name,index,value)=>{const input=catalogRow(name).videos[index];input.value=value;node('catalog-choices').handlers.change({target:input});};
  const catalogAdd=name=>node('catalog-choices').handlers.click({target:catalogRow(name).add});
  const catalogRemove=(name,index)=>node('catalog-choices').handlers.click({target:catalogRow(name).removes[index]});
  return {node,context,state,listeners,storage,change,choose,catalogRow,catalogCheck,catalogSelect,catalogAdd,catalogRemove,feedback:()=>[...nodes.values()].find(n=>n.id==='automation-start-feedback')};
}

test('Unicode task submits once and locks the controls while pending',async()=>{
  let resolve;const requests=[];
  const ui=setup((...args)=>{requests.push(args);return new Promise(r=>resolve=r)});
  ui.node('automation-task').value='Lavar Louça na Pia';
  const pending=ui.node('sync').onclick();
  assert.equal(ui.node('sync').disabled,true);await ui.node('sync').onclick();
  assert.equal(requests.length,1);assert.equal(requests[0][1].taskName,'Lavar Louça na Pia');
  assert.match(ui.feedback().textContent,/Enviando/);resolve();await pending;
  assert.equal(ui.node('sync').disabled,false);
});
test('missing task, request errors, disconnect and busy state remain visible',async()=>{
  const ui=setup(async()=>{throw Error('RAM insuficiente')});
  await ui.node('sync').onclick();assert.match(ui.feedback().textContent,/nome completo/);
  ui.node('automation-task').value='Lavar Louça na Pia';await ui.node('sync').onclick();assert.equal(ui.feedback().textContent,'RAM insuficiente');
  ui.listeners['panel-connection']({detail:{connected:false,message:'Sem conexão'}});assert.equal(ui.node('sync').disabled,true);assert.equal(ui.feedback().textContent,'Sem conexão');
  ui.context.render({...ui.state,busy:true,operation:'install',message:'Enviando vídeo'});assert.equal(ui.node('sync').disabled,true);assert.equal(ui.feedback().textContent,'Enviando vídeo');
});
for(const count of [4,6]) test(`submits ${count} with the precise selected devices and restores both after reload`,async()=>{
  const requests=[];const ui=setup((...args)=>requests.push(args));
  const chosen=ui.state.phones.slice(0,7).map(phone=>phone.serial);ui.choose(chosen);
  ui.node('automation-task').value='Tarefa';ui.change('automation-simultaneous',count);
  assert.equal(ui.node('sync').textContent,'Iniciar nos aparelhos escolhidos');assert.equal(ui.node('sync').disabled,false);
  await ui.node('sync').onclick();assert.equal(requests.length,1);assert.equal(requests[0][1].scope,'selected');
  assert.deepEqual(Array.from(requests[0][1].selectedSerials),chosen);assert.equal(requests[0][1].simultaneous,count);assert.equal(requests[0][1].manageRam,true);
  const restored=setup(undefined,{storage:ui.storage});assert.equal(restored.node('automation-scope').value,'selected');assert.equal(restored.node('automation-simultaneous').value,String(count));
  assert.deepEqual(restored.node('automation-participant-list').checks.filter(check=>check.checked).map(check=>check.dataset.serial),chosen);
});
test('search filters names and serials without changing choices, and all/clear controls work',()=>{
  const ui=setup();ui.choose([ui.state.phones[0].serial,ui.state.phones[1].serial]);const search=ui.node('automation-participant-search');
  for(const query of ['celular 2','5554']) {search.value=query;search.oninput();assert.equal(ui.node('automation-participant-list').rows.filter(row=>!row.hidden).length,1);assert.equal(ui.node('automation-participant-list').checks.filter(check=>check.checked).length,2);}
  ui.node('automation-participants-all').onclick();assert.equal(ui.node('automation-participant-list').checks.filter(check=>check.checked).length,8);
  ui.node('automation-participants-clear').onclick();assert.equal(ui.node('automation-participant-list').checks.filter(check=>check.checked).length,0);assert.equal(ui.node('sync').disabled,true);
});
test('refresh, rename, new registrations and deleted devices cannot silently broaden selection',async()=>{
  let requests=0;const ui=setup(()=>requests++);const chosen=ui.state.phones[2].serial;ui.choose([chosen]);
  const phones=ui.state.phones.map(phone=>({...phone,name:`Novo nome ${phone.serial}`})).reverse();phones.push({serial:'emulator-5998',name:'Novo aparelho',status:'off'});
  ui.context.render({...ui.state,phones});assert.deepEqual(ui.node('automation-participant-list').checks.filter(check=>check.checked).map(check=>check.dataset.serial),[chosen]);assert.match(ui.node('automation-participant-count').textContent,/1 escolhido\(s\) de 9/);
  ui.context.render({...ui.state,phones:phones.filter(phone=>phone.serial!==chosen)});assert.equal(ui.storage.get('automation-selected-serials'),'[]');assert.equal(ui.node('sync').disabled,true);assert.match(ui.feedback().textContent,/Marque pelo menos/);await ui.node('sync').onclick();assert.equal(requests,0);
  const stale=setup(undefined,{storage:new Map([['automation-scope','selected'],['automation-selected-serials','["emulator-9999"]']])});assert.equal(stale.storage.get('automation-selected-serials'),'[]');assert.equal(stale.node('sync').disabled,true);
});
for(const plan of ['single','daily','interleaved']) test(`${plan} retains scope and quantity after refresh and submits the right plan`,async()=>{
  const requests=[];const storage=new Map([['automation-plan',plan],['interleaved-task-videos',JSON.stringify({'Tarefa':'fonte.mov'})]]);
  const ui=setup((...args)=>requests.push(args),{storage,state:{videos:[{name:'fonte.mov'}],minuteCatalog:{tasks:['Tarefa']}}});
  ui.choose(ui.state.phones.slice(0,3).map(phone=>phone.serial));ui.change('automation-simultaneous',3);ui.node('automation-task').value='Tarefa';ui.context.render(ui.state);
  assert.equal(ui.node('automation-scope').value,'selected');assert.equal(ui.node('automation-simultaneous').value,'3');assert.equal(ui.node('automation-scope').disabled,false);assert.equal(ui.node('automation-simultaneous').disabled,false);
  await ui.node('sync').onclick();assert.equal(requests.length,1);const payload=requests[0][1];assert.equal(payload.simultaneous,3);assert.equal(payload.selectedSerials.length,3);assert.equal(payload.dailyPlan,plan==='daily');assert.equal(payload.interleavedPlan,plan==='interleaved');
  if(plan!=='single') {assert.equal(payload.autoNavigate,true);assert.equal(payload.repeat,true);}
});
test('empty, zero, negative, fractional and unsafe counts cannot start',async()=>{
  let requests=0;const ui=setup(()=>requests++);ui.node('automation-task').value='Tarefa';
  for(const value of ['','0','-2','1.5','NaN','Infinity','9007199254740992']) {ui.change('automation-simultaneous',value);assert.equal(ui.node('sync').disabled,true,value);assert.match(ui.feedback().textContent,/quantidade inteira/);await ui.node('sync').onclick();}
  assert.equal(requests,0);ui.change('automation-simultaneous','8');assert.equal(ui.node('sync').disabled,false);
});
test('a count above selected participants is allowed with an explanation',async()=>{
  const requests=[];const ui=setup((...args)=>requests.push(args));ui.choose([ui.state.phones[0].serial]);ui.node('automation-task').value='Tarefa';ui.change('automation-simultaneous','6');assert.equal(ui.node('sync').disabled,false);
  assert.match(ui.node('automation-simultaneous-help').textContent,/apenas os disponíveis/);assert.match(ui.node('automation-simultaneous-help').textContent,/até 4/);await ui.node('sync').onclick();assert.equal(requests[0][1].simultaneous,6);
});
test('old backends cannot ignore the chosen subset',async()=>{
  let requests=0;const ui=setup(()=>requests++,{state:{participantSelectionVersion:undefined}});ui.choose([ui.state.phones[0].serial]);ui.node('automation-task').value='Tarefa';assert.equal(ui.node('sync').disabled,true);assert.match(ui.feedback().textContent,/Reabra o painel atualizado pelo atalho/);await ui.node('sync').onclick();assert.equal(requests,0);
});
for(const saved of ['2','5','auto']) test(`saved legacy count ${saved} remains usable`,async()=>{
  const requests=[];const ui=setup((...args)=>requests.push(args),{storage:new Map([['automation-plan','single'],['automation-simultaneous',saved]])});ui.node('automation-task').value='Tarefa';
  assert.equal(ui.node('automation-simultaneous-mode').value,saved==='auto'?'auto':'custom');assert.equal(ui.node('automation-simultaneous').value,saved==='auto'?'2':saved);await ui.node('sync').onclick();assert.equal(requests[0][1].simultaneous,saved==='auto'?null:Number(saved));
});
test('automatic mode saves the last custom count for switching back',()=>{
  const ui=setup();ui.change('automation-simultaneous','6');ui.change('automation-simultaneous-mode','auto');assert.equal(ui.storage.get('automation-simultaneous'),'auto');
  const restored=setup(undefined,{storage:ui.storage});assert.equal(restored.node('automation-simultaneous').value,'6');assert.equal(restored.node('automation-simultaneous').disabled,true);restored.change('automation-simultaneous-mode','custom');assert.equal(restored.storage.get('automation-simultaneous'),'6');assert.equal(restored.node('automation-simultaneous').disabled,false);
});
test('ready cameras mode retains selected participants, disables count and submits null',async()=>{
  const requests=[];const ui=setup((...args)=>requests.push(args));ui.choose([ui.state.phones[0].serial]);ui.change('automation-simultaneous','4');ui.change('automation-mode','ready');
  assert.equal(ui.node('automation-simultaneous').disabled,true);assert.equal(ui.node('automation-simultaneous-mode').disabled,true);assert.match(ui.node('automation-simultaneous-help').textContent,/participantes escolhidos precisam estar ligados e com a câmera aberta/);
  await ui.node('sync').onclick();assert.equal(requests[0][1].autoNavigate,false);assert.equal(requests[0][1].simultaneous,null);assert.equal(requests[0][1].selectedSerials.length,1);ui.change('automation-mode','auto');assert.equal(ui.node('automation-simultaneous').disabled,false);assert.equal(ui.node('automation-simultaneous').value,'4');
});
test('online scope sends the explicit count to queue management',async()=>{
  const requests=[];const ui=setup((...args)=>requests.push(args));ui.change('automation-scope','online');ui.change('automation-simultaneous','3');ui.node('automation-task').value='Tarefa';assert.equal(ui.node('automation-simultaneous').disabled,false);
  await ui.node('sync').onclick();assert.equal(requests[0][1].scope,'online');assert.equal(requests[0][1].simultaneous,3);assert.equal(requests[0][1].manageRam,true);
});
test('video summary checks only the chosen participants',()=>{
  const ui=setup();const phones=ui.state.phones.map((phone,index)=>({...phone,installedVideo:index<2?{name:'fonte.mov',assetId:'source-1',confirmed:true}:null}));ui.context.render({...ui.state,phones,allVideoName:null});ui.choose(phones.slice(0,2).map(phone=>phone.serial));
  assert.equal(ui.node('automation-video').textContent,'Vídeo nos 2 participante(s): fonte.mov');ui.choose([phones[2].serial]);assert.match(ui.node('automation-video').textContent,/não confirmado em algum participante/);
});

const playlistState={minuteCatalog:{tasks:['Louça','Jardim']},videos:['louca-1.mov','louca-2.mov','louca-3.mov','louca-4.mov','jardim.mov'].map(name=>({name}))};
const playlistStorage=links=>new Map([['automation-plan','interleaved'],['interleaved-task-videos',JSON.stringify(links)]]);
const savedPlaylists=ui=>JSON.parse(ui.storage.get('interleaved-task-videos'));

test('legacy strings migrate to one-element video lists without losing chosen tasks',async()=>{
  const requests=[];const ui=setup((...args)=>requests.push(args),{storage:playlistStorage({'Louça':'louca-1.mov','Jardim':'jardim.mov'}),state:playlistState});
  assert.deepEqual(savedPlaylists(ui),{'Louça':['louca-1.mov'],'Jardim':['jardim.mov']});
  assert.equal(ui.catalogRow('Louça').check.checked,true);assert.equal(ui.catalogRow('Louça').videos[0].value,'louca-1.mov');
  await ui.node('sync').onclick();assert.equal(requests.length,1);
  assert.deepEqual(JSON.parse(JSON.stringify(requests[0][1].interleavedTasks)),[{task:'Louça',videos:['louca-1.mov']},{task:'Jardim',videos:['jardim.mov']}]);
});

test('add controls grow a task to two, three and four videos while blanks survive refresh and reload',async()=>{
  let requests=0;const ui=setup(()=>requests++,{storage:playlistStorage({'Louça':'louca-1.mov'}),state:playlistState});
  for(let index=1;index<=3;index++) {
    ui.catalogAdd('Louça');assert.equal(ui.catalogRow('Louça').videos.length,index+1);assert.equal(ui.catalogRow('Louça').videos[index].value,'');assert.equal(ui.node('sync').disabled,true);
    ui.context.render(ui.state);assert.equal(ui.catalogRow('Louça').videos.length,index+1);assert.equal(ui.catalogRow('Louça').videos[index].value,'');
    const reloaded=setup(undefined,{storage:ui.storage,state:playlistState});assert.equal(reloaded.catalogRow('Louça').videos.length,index+1);assert.equal(reloaded.catalogRow('Louça').videos[index].value,'');
    await ui.node('sync').onclick();assert.equal(requests,0);assert.match(ui.feedback().textContent,/posição/);
    ui.catalogSelect('Louça',index,`louca-${index+1}.mov`);assert.equal(ui.catalogRow('Louça').videos[index].ariaLabel,`Vídeo ${index+1} para Louça`);assert.equal(ui.node('sync').disabled,false);
  }
  assert.deepEqual(savedPlaylists(ui)['Louça'],['louca-1.mov','louca-2.mov','louca-3.mov','louca-4.mov']);
  assert.equal(ui.catalogRow('Jardim').videos.length,1);
});

test('ordered arrays are sent per task and unchecked tasks are excluded',async()=>{
  const requests=[];const ui=setup((...args)=>requests.push(args),{storage:playlistStorage({}),state:playlistState});
  ui.catalogSelect('Louça',0,'louca-1.mov');ui.catalogCheck('Louça');ui.catalogAdd('Louça');ui.catalogSelect('Louça',1,'louca-2.mov');
  ui.catalogSelect('Jardim',0,'jardim.mov');ui.catalogCheck('Jardim');ui.catalogCheck('Jardim',false);
  assert.deepEqual(savedPlaylists(ui),{'Louça':['louca-1.mov','louca-2.mov']});assert.equal(ui.catalogRow('Jardim').videos[0].value,'jardim.mov');
  await ui.node('sync').onclick();assert.deepEqual(JSON.parse(JSON.stringify(requests[0][1].interleavedTasks)),[{task:'Louça',videos:['louca-1.mov','louca-2.mov']}]);
  ui.catalogCheck('Jardim');await ui.node('sync').onclick();assert.deepEqual(JSON.parse(JSON.stringify(requests[1][1].interleavedTasks)),[{task:'Louça',videos:['louca-1.mov','louca-2.mov']},{task:'Jardim',videos:['jardim.mov']}]);
});

test('removing entries preserves the remaining order and keeps a blank selector for the last entry',async()=>{
  let requests=0;const ui=setup(()=>requests++,{storage:playlistStorage({'Louça':['louca-1.mov','louca-2.mov','louca-3.mov','louca-4.mov']}),state:playlistState});
  ui.catalogRemove('Louça',1);assert.deepEqual(savedPlaylists(ui)['Louça'],['louca-1.mov','louca-3.mov','louca-4.mov']);assert.equal(ui.catalogRow('Louça').videos[1].ariaLabel,'Vídeo 2 para Louça');
  ui.catalogRemove('Louça',2);ui.catalogRemove('Louça',1);assert.deepEqual(savedPlaylists(ui)['Louça'],['louca-1.mov']);
  ui.catalogRemove('Louça',0);assert.deepEqual(savedPlaylists(ui)['Louça'],['']);assert.equal(ui.catalogRow('Louça').videos.length,1);assert.equal(ui.catalogRow('Louça').check.checked,true);assert.equal(ui.node('sync').disabled,true);await ui.node('sync').onclick();assert.equal(requests,0);
});

test('missing videos remain visible and saved until corrected rather than being silently discarded',async()=>{
  let requests=0;const ui=setup(()=>requests++,{storage:playlistStorage({'Louça':['louca-1.mov','arquivo-removido.mov']}),state:playlistState});
  assert.deepEqual(savedPlaylists(ui)['Louça'],['louca-1.mov','arquivo-removido.mov']);assert.equal(ui.catalogRow('Louça').videos[1].value,'arquivo-removido.mov');assert.match(ui.catalogRow('Louça').videos[1].html,/Indisponível/);assert.equal(ui.node('sync').disabled,true);await ui.node('sync').onclick();assert.equal(requests,0);
  ui.context.render({...ui.state,videos:[]});assert.deepEqual(savedPlaylists(ui)['Louça'],['louca-1.mov','arquivo-removido.mov']);assert.equal(ui.catalogRow('Louça').videos.length,2);
  ui.context.render(ui.state);ui.catalogSelect('Louça',1,'louca-2.mov');assert.equal(ui.node('sync').disabled,false);assert.deepEqual(savedPlaylists(ui)['Louça'],['louca-1.mov','louca-2.mov']);
});

test('a transient empty catalog or a removed task preserves the selected playlist for recovery',async()=>{
  let requests=0;const ui=setup(()=>requests++,{storage:playlistStorage({'Louça':['louca-1.mov','louca-2.mov']}),state:playlistState});
  for(const minuteCatalog of [undefined,{tasks:[]},{tasks:['Jardim']}]) {
    ui.context.render({...ui.state,minuteCatalog});assert.equal(ui.catalogRow('Louça').check.checked,true);assert.equal(ui.catalogRow('Louça').videos.length,2);assert.equal(ui.node('sync').disabled,true);await ui.node('sync').onclick();assert.equal(requests,0);assert.deepEqual(savedPlaylists(ui)['Louça'],['louca-1.mov','louca-2.mov']);
  }
  ui.context.render(ui.state);assert.equal(ui.node('sync').disabled,false);
});

test('an older backend cannot start a playlist it would not support',async()=>{
  let requests=0;const ui=setup(()=>requests++,{storage:playlistStorage({'Louça':'louca-1.mov'}),state:{...playlistState,interleavedVideoListsVersion:undefined}});
  assert.equal(ui.node('sync').disabled,true);assert.match(ui.feedback().textContent,/listas de vídeos por tarefa/);await ui.node('sync').onclick();assert.equal(requests,0);
  ui.change('automation-plan','daily');assert.equal(ui.node('sync').disabled,false);
});

test('playlist controls are locked while a start request is pending and during a busy state',async()=>{
  let resolve;const ui=setup(()=>new Promise(r=>resolve=r),{storage:playlistStorage({'Louça':'louca-1.mov'}),state:playlistState});
  const pending=ui.node('sync').onclick();assert.equal(ui.catalogRow('Louça').add.disabled,true);ui.catalogAdd('Louça');assert.deepEqual(savedPlaylists(ui)['Louça'],['louca-1.mov']);resolve();await pending;
  ui.context.render({...ui.state,busy:true});assert.equal(ui.catalogRow('Louça').videos[0].disabled,true);ui.catalogRemove('Louça',0);assert.deepEqual(savedPlaylists(ui)['Louça'],['louca-1.mov']);
});

test('task search remains applied after adding entries and progress identifies the current video',()=>{
  const ui=setup(undefined,{storage:playlistStorage({'Louça':'louca-1.mov'}),state:playlistState});const search=ui.node('catalog-search');search.value='louça';search.oninput();ui.catalogAdd('Louça');assert.equal(ui.catalogRow('Jardim').hidden,true);assert.equal(ui.catalogRow('Louça').hidden,false);
  ui.context.render({...ui.state,planActive:true,planMode:'interleaved',planStep:4,planTask:'Louça',planVideo:'louca-2.mov',planVideoIndex:2,planVideoCount:3});assert.match(ui.node('automation-loop-status').textContent,/Vídeo 2 de 3 desta tarefa/);
});

test('interleaved recovery describes the deferred devices and the group moving to the next task',()=>{
  const ui=setup(undefined,{storage:playlistStorage({'Louça':'louca-1.mov'}),state:playlistState});
  ui.context.render({...ui.state,planActive:true,planMode:'interleaved',planContinuingAfterFailure:true,planDeferredPhones:[{serial:ui.state.phones[1].serial,reason:'Captura pendente preservada'}],planLastSaved:[ui.state.phones[0].serial],planLastFailed:[ui.state.phones[1].serial]});
  const status=ui.node('automation-next-task-status');assert.equal(status.hidden,false);assert.match(status.textContent,/grupo segue para a próxima tarefa/);assert.match(status.textContent,/Celular 2 — Captura pendente preservada/);assert.match(status.textContent,/Salvos na última rodada: Celular 1/);assert.match(status.textContent,/Falharam na última rodada: Celular 2/);assert.equal(ui.node('automation-loop-help').hidden,true);
  ui.context.render({...ui.state,planActive:true,planMode:'interleaved',planContinuingAfterFailure:true,planDeferredPhones:[],planLastFailed:[]});assert.doesNotMatch(status.textContent,/Aguardando nova tentativa/);assert.match(status.textContent,/aparelhos disponíveis entram juntos/);
  ui.context.render({...ui.state,planActive:true,planMode:'interleaved',planContinuingAfterFailure:false,planDeferredPhones:[],planLastFailed:[]});assert.equal(status.hidden,true);assert.equal(status.textContent,'');
});

test('daily and single plans keep their recovery help and do not display stale interleaved deferrals',()=>{
  const ui=setup(undefined,{storage:playlistStorage({'Louça':'louca-1.mov'}),state:playlistState});
  for(const plan of ['daily','single']) {
    ui.change('automation-plan',plan);ui.context.render({...ui.state,planActive:false,planMode:'interleaved',planDeferredPhones:[{name:'Aparelho anterior',reason:'Sem resposta'}],planLastFailed:['Aparelho anterior']});assert.equal(ui.node('automation-loop-help').hidden,false);assert.equal(ui.node('automation-next-task-status').hidden,true);
  }
});

test('an older backend cannot promise continuing after a failed interleaved round',async()=>{
  let requests=0;const ui=setup(()=>requests++,{storage:playlistStorage({'Louça':'louca-1.mov'}),state:{...playlistState,interleavedSkipFailedRoundsVersion:undefined}});
  assert.equal(ui.node('sync').disabled,true);assert.match(ui.feedback().textContent,/continuar na próxima tarefa após uma falha/);await ui.node('sync').onclick();assert.equal(requests,0);ui.change('automation-plan','daily');assert.equal(ui.node('sync').disabled,false);
});

test('a confirmed library rename updates all playlist positions and unchecked drafts without changing order',async()=>{
  const requests=[];const ui=setup((...args)=>requests.push(args),{storage:playlistStorage({'Louça':['louca-1.mov','louca-2.mov','louca-1.mov','']}),state:playlistState});
  ui.catalogSelect('Jardim',0,'louca-1.mov');
  ui.listeners['video-library-renamed']({detail:{oldName:'louca-1.mov',name:'renomeado.mov'}});
  assert.deepEqual(savedPlaylists(ui)['Louça'],['renomeado.mov','louca-2.mov','renomeado.mov','']);assert.equal(ui.catalogRow('Jardim').videos[0].value,'renomeado.mov');assert.equal(ui.catalogRow('Jardim').check.checked,false);
  ui.catalogRemove('Louça',3);await ui.node('sync').onclick();assert.deepEqual(JSON.parse(JSON.stringify(requests[0][1].interleavedTasks)),[{task:'Louça',videos:['renomeado.mov','louca-2.mov','renomeado.mov']}]);
});

test('rename from another window reloads current saved lists and cannot overwrite recently added tasks',()=>{
  const ui=setup(undefined,{storage:playlistStorage({'Louça':'louca-1.mov'}),state:playlistState});
  const current={'Louça':['renomeado.mov','louca-2.mov'],'Jardim':['jardim.mov']};ui.storage.set('interleaved-task-videos',JSON.stringify(current));
  ui.listeners.storage({key:'video-library-last-rename',newValue:JSON.stringify({oldName:'louca-1.mov',name:'renomeado.mov'})});
  assert.deepEqual(savedPlaylists(ui),current);assert.equal(ui.catalogRow('Jardim').check.checked,true);assert.equal(ui.catalogRow('Jardim').videos[0].value,'jardim.mov');assert.deepEqual(ui.catalogRow('Louça').videos.map(video=>video.value),['renomeado.mov','louca-2.mov']);
});

test('a local rename also reloads saved lists when another window added a task first',()=>{
  const ui=setup(undefined,{storage:playlistStorage({'Louça':'louca-1.mov'}),state:playlistState});
  const current={'Louça':['renomeado.mov','louca-2.mov'],'Jardim':['jardim.mov']};
  // The library module has already renamed references in the latest shared storage.
  ui.storage.set('interleaved-task-videos',JSON.stringify(current));
  ui.listeners['video-library-renamed']({detail:{oldName:'louca-1.mov',name:'renomeado.mov'}});
  assert.deepEqual(savedPlaylists(ui),current);assert.equal(ui.catalogRow('Jardim').check.checked,true);assert.equal(ui.catalogRow('Jardim').videos[0].value,'jardim.mov');assert.deepEqual(ui.catalogRow('Louça').videos.map(video=>video.value),['renomeado.mov','louca-2.mov']);
});
