const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');

function setup(videos){
  const nodes=new Map(),cards=[],listeners={},opened=[];
  let actions=0;
  const node=key=>{
    if(nodes.has(key))return nodes.get(key);
    const el={dataset:{},hidden:false,textContent:'',handlers:{},writes:0,attributes:{},
      append(child){this.child=child;},after(child){this.afterNode=child;},before(child){this.beforeNode=child;},setAttribute(name,value){this.attributes[name]=value;},
      addEventListener(name,fn){this.handlers[name]=fn;},querySelector(selector){return selector==='.video-readiness'?this.readiness:null;},
      set innerHTML(value){this.html=value;this.writes++;
        if(key==='videos'){
          cards.length=0;
          for(const match of value.matchAll(/<article class="video-card[^"]*" data-video="([^"]*)">([\s\S]*?)<\/article>/g)){
            const card=node(Symbol());card.dataset.video=match[1];card.readiness=node(Symbol());cards.push(card);
          }
        }
      },get innerHTML(){return this.html || '';}
    };nodes.set(key,el);return el;
  };
  const app={state:{videos},video:videos[0]?.name || '',videoHash:''};
  const noAction=()=>{actions++;throw Error('This display must not send an action');};
  const context={app,$:node,document:{getElementById:node,createElement:()=>node(Symbol()),head:node('head'),querySelector:node,querySelectorAll:selector=>selector==='.video-card'?cards:[]},window:{addEventListener:(name,fn)=>listeners[name]=fn,VideoLibrary:{update(){},open:(...args)=>opened.push(args)}},icons(){},setPreview(){},empty:()=>'',duration:String,size:String,esc:value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])),call:noAction,act:noAction,fetch:noAction};
  vm.createContext(context);
  const source=fs.readFileSync(path.join(__dirname,'web/app.js'),'utf8');
  vm.runInContext(source.slice(source.indexOf('function renderVideos('),source.indexOf('function updateSelectionLabels(')),context);
  vm.runInContext(fs.readFileSync(path.join(__dirname,'web/video-readiness.js'),'utf8'),context);
  context.renderVideos(videos);
  return {node,app,cards,context,opened,actions:()=>actions,selected:()=>[...nodes.values()].find(el=>el.id==='selected-video-readiness'),card:name=>cards.find(card=>decodeURIComponent(card.dataset.video)===name).readiness,
    render:next=>{app.state={videos:next};context.renderVideos(next);},connection:connected=>listeners['panel-connection']({detail:{connected}})};
}

const cameras={total:4,confirmed:2,staged:2,allConfirmed:false,allAssigned:true};
const video=(preparation,extra={})=>({name:'Catando feijão.MOV',preparation,cameras,...extra});

test('readiness uses the automation cache rather than browser preview or camera assignment',()=>{
  const ui=setup([video({ready:false,state:'missing',croppedReady:false,progress:0},{previewReady:true,currentName:'Catando feijão.MOV',cameras:{total:4,confirmed:4,staged:0,allConfirmed:true,allAssigned:true}})]);
  assert.equal(ui.card('Catando feijão.MOV').dataset.readiness,'missing');assert.match(ui.card('Catando feijão.MOV').innerHTML,/Falta preparar/);assert.match(ui.card('Catando feijão.MOV').innerHTML,/ainda não reconhece uma preparação válida/);
  ui.render([video({ready:true,state:'ready',croppedReady:false,progress:100},{previewReady:false})]);assert.equal(ui.card('Catando feijão.MOV').dataset.readiness,'ready');assert.match(ui.card('Catando feijão.MOV').innerHTML,/Preparado/);assert.equal(ui.actions(),0);
});

test('render transitions identify preparing progress and failure without requesting any work',()=>{
  const ui=setup([video({ready:false,state:'missing',croppedReady:false,progress:0})]);
  ui.render([video({ready:false,state:'preparing',croppedReady:false,progress:42.4})]);assert.equal(ui.card('Catando feijão.MOV').dataset.readiness,'preparing');assert.match(ui.card('Catando feijão.MOV').innerHTML,/Preparando 42%/);
  ui.render([video({ready:false,state:'error',croppedReady:false,progress:42,error:'Arquivo incompleto'})]);assert.equal(ui.card('Catando feijão.MOV').dataset.readiness,'error');assert.match(ui.selected().innerHTML,/Falha no preparo/);assert.match(ui.selected().innerHTML,/Arquivo incompleto/);
  ui.render([video({ready:true,state:'ready',croppedReady:false,progress:100})]);assert.equal(ui.selected().dataset.readiness,'ready');assert.equal(ui.actions(),0);
});

test('missing information and lost connection are gray and do not retain stale green confirmations',()=>{
  const ui=setup([video(undefined)]);assert.equal(ui.selected().dataset.readiness,'unknown');assert.match(ui.selected().innerHTML,/Sem confirmação/);
  ui.render([video({ready:true,state:'ready',croppedReady:false,progress:100})]);assert.equal(ui.selected().dataset.readiness,'ready');ui.connection(false);assert.equal(ui.selected().dataset.readiness,'unknown');assert.equal(ui.card('Catando feijão.MOV').dataset.readiness,'unknown');assert.match(ui.selected().innerHTML,/Câmeras: sem confirmação/);assert.doesNotMatch(ui.selected().innerHTML,/2\/4 confirmadas/);
  ui.connection(true);assert.equal(ui.selected().dataset.readiness,'ready');assert.equal(ui.actions(),0);
});

test('cropped preparation is identified separately and never marks the automation version as ready',()=>{
  const ui=setup([video({ready:false,state:'missing',croppedReady:true,progress:0})]);assert.equal(ui.selected().dataset.readiness,'missing');assert.match(ui.selected().innerHTML,/Com corte; falta versão da automação/);
  ui.render([video({ready:false,state:'preparing',croppedReady:false,preparingCropped:true,progress:15})]);assert.equal(ui.selected().dataset.readiness,'preparing');assert.match(ui.selected().innerHTML,/Preparando corte 15%/);assert.match(ui.selected().innerHTML,/precisa de uma versão válida sem corte/);
  ui.render([video({ready:true,state:'preparing',croppedReady:false,preparingCropped:true,progress:15})]);assert.equal(ui.selected().dataset.readiness,'ready');assert.equal(ui.actions(),0);
});

test('camera counts distinguish confirmed records from staged records without calling devices active',()=>{
  const ui=setup([video({ready:true,state:'ready',croppedReady:false,progress:100})]);
  for(const target of [ui.selected(),ui.card('Catando feijão.MOV')]){assert.match(target.innerHTML,/Câmeras: 2\/4 confirmadas • 2 aguardam validação/);assert.match(target.innerHTML,/Registros locais/);assert.doesNotMatch(target.innerHTML,/Todas ativas|Em gravação|4\/4 confirmadas/);}
  assert.match(ui.node('videos').beforeNode.textContent,/não indica aparelhos ligados/);assert.equal(ui.actions(),0);
});

test('the selected summary follows the selected file and clears when that file is absent',()=>{
  const ready=video({ready:true,state:'ready',croppedReady:false,progress:100}),missing=video({ready:false,state:'missing',croppedReady:false,progress:0},{name:'Jardim.MOV'});
  const ui=setup([ready,missing]);assert.equal(ui.selected().dataset.readiness,'ready');ui.app.video='Jardim.MOV';ui.context.renderVideos(ui.app.state.videos);assert.equal(ui.selected().dataset.readiness,'missing');assert.equal(ui.card('Catando feijão.MOV').dataset.readiness,'ready');
  ui.render([ready]);assert.equal(ui.selected().hidden,true);assert.equal(ui.selected().innerHTML,'');assert.equal(ui.actions(),0);
});

test('indicators are passive and keep the existing rename and delete controls intact',()=>{
  const ui=setup([video({ready:false,state:'missing',croppedReady:false,progress:0})]);const markup=ui.node('videos').innerHTML;
  assert.match(markup,/data-lucide="pencil"/);assert.match(markup,/data-lucide="trash-2"/);assert.match(markup,/aria-label="Renomear Catando feijão.MOV"/);assert.match(markup,/aria-label="Excluir Catando feijão.MOV"/);
  assert.doesNotMatch(ui.selected().innerHTML,/<button|<input|<form/);assert.equal(ui.actions(),0);
  const action={disabled:false,dataset:{videoLibraryAction:'rename'}};let stopped=false;ui.cards[0].handlers.click({target:{closest:()=>action},stopPropagation(){stopped=true;}});assert.equal(stopped,true);assert.deepEqual(ui.opened,[['rename','Catando feijão.MOV']]);assert.equal(ui.actions(),0);
});

test('error text is escaped and repeated updates do not rebuild unchanged status content',()=>{
  const ui=setup([video({ready:false,state:'error',croppedReady:false,progress:0,error:'Falha <img src=x onerror=alert(1)>'})]);assert.match(ui.selected().innerHTML,/&lt;img/);assert.doesNotMatch(ui.selected().innerHTML,/<img/);
  const selectedWrites=ui.selected().writes,cardWrites=ui.card('Catando feijão.MOV').writes;ui.context.window.VideoReadiness.update();assert.equal(ui.selected().writes,selectedWrites);assert.equal(ui.card('Catando feijão.MOV').writes,cardWrites);
  assert.match(ui.node('head').child.textContent,/max-width:100%/);assert.match(ui.node('head').child.textContent,/overflow-wrap:anywhere/);assert.equal(ui.actions(),0);
});
