const videoProgress=document.createElement('article');
videoProgress.className='panel';
videoProgress.style.cssText='padding:24px;margin:0 0 24px';
videoProgress.innerHTML='<div class="panel-heading"><h2>Preparação e ativação nas câmeras</h2><div class="preparation-cancel-actions"><strong id="video-stage-percent">0%</strong><button type="button" class="button button-secondary" id="foreground-cancel-preparation" hidden disabled>Cancelar</button></div></div><p id="video-stage">Aguardando</p><p id="foreground-cancel-feedback" role="status" aria-live="polite"></p><div class="progress"><span id="video-stage-bar"></span></div><p id="all-camera-video"></p><div id="camera-transfers"></div>';
document.querySelector('.video-layout').before(videoProgress);
const previousRender=render;
render=function(state){
  if(state.apiVersion!==4){location.replace("http://127.0.0.1:8768/");return}
  previousRender(state);
  const upload=app.uploadProgress;
  const preparation=state.foregroundPreparation || {};
  const manualPreparation=preparation.jobId && (preparation.busy || !state.busy) && (preparation.canCancel || preparation.status==='cancelling');
  const percent=upload?upload.percent:manualPreparation?preparation.progress||0:state.progress||0;
  $('video-stage-percent').textContent=`${percent}%`;
  $('video-stage-bar').style.width=`${percent}%`;
  $('video-stage').textContent=upload?`${upload.name} • Importando ${size(upload.loaded)} de ${size(upload.total)}`:manualPreparation?`${preparation.name || 'Vídeo'} — ${preparation.stage || 'Preparando'}${preparation.error?': '+preparation.error:''}`:`${state.stage||'Aguardando'} • ${state.message||''}`;
  const selected=(state.videos||[]).find(v=>v.name===app.video);
  if(selected)$('preview-meta').textContent+=` • Câmera: ~${size(selected.duration*10368000)}`;
  $('all-camera-video').textContent=state.allVideoName?`Vídeo confirmado em todos: ${state.allVideoName}`:'Os celulares têm vídeos diferentes ou ainda não têm instalação confirmada. Confira abaixo.';
  $('current').textContent=state.allVideoName||'Confira por celular';
  $('current-size').textContent=state.allVideoName?'Confirmado em todos os celulares':'Vídeos diferentes ou não confirmados';
  $('camera-transfers').innerHTML=(state.phones||[]).map(phone=>{
    const transfer=(state.transfers||{})[phone.serial];
    const installed=phone.installedVideo;
    return `<div class="usage-row"><header><strong>${esc(phone.name)}</strong><span>${esc(phone.storage||'')} • ${phone.status==='online'?'Online':phone.status==='off'?'Desligado':'Iniciando'}</span></header><p>Na câmera: <strong>${esc(installed?.name||'Não confirmado')+(installed?.staged?' (pronta; valida ao abrir)':installed&&!installed.confirmed?' (aguardando confirmação)':'')}</strong>${installed?` • ${size(installed.bytes)} ${installed.mode === "shared" ? "compartilhados no PC" : "de quadros locais"}`:''}</p>${transfer?`<header><span>${esc(transfer.stage)} • ${esc(transfer.video)}</span><strong>${transfer.percent||0}%</strong></header><div class="mini-track"><i style="width:${transfer.percent||0}%"></i></div><small>${transfer.mode === "shared" ? "Fonte compartilhada • sem cópia do vídeo para o celular" : `${size(transfer.bytes)} / ${size(transfer.total)}`}${transfer.stage==="Enviando"&&transfer.speed?` • ${size(transfer.speed)}/s • ~${Math.ceil(transfer.eta/60)} min`:""}${transfer.error?` • ${esc(transfer.error)}`:''}</small>`:''}</div>`;
  }).join('');
  for(const id of ['install','install-all','add'])$(id).disabled=!!state.busy||!!state.foregroundPreparation?.busy||!!app.uploadProgress;
  $('upload').disabled=!!state.foregroundPreparation?.busy||!!app.uploadProgress;
  if(!state.sharedCameraVersion){
    $('install').disabled=true;$('install-all').disabled=true;
    $('video-stage').textContent='Atualização pronta: reinicie o processo do painel para ativar a câmera compartilhada. O envio antigo foi interrompido e os arquivos parciais foram preservados.';
  }
  window.PreparationCancellation?.update(state,{foreground:!!app.uploadProgress});
};
$('upload').onchange=async event=>{
  const file=event.target.files[0];if(!file)return;
  app.uploadProgress={name:file.name,percent:0,loaded:0,total:file.size};render(app.state);
  try{
    const body=await new Promise((resolve,reject)=>{
      const xhr=new XMLHttpRequest();xhr.open('POST','/api/upload');xhr.setRequestHeader('X-Filename',encodeURIComponent(file.name));xhr.setRequestHeader('X-Background','1');
      xhr.upload.onprogress=e=>{app.uploadProgress={name:file.name,percent:e.lengthComputable?Math.min(99,Math.floor(e.loaded*100/e.total)):0,loaded:e.loaded,total:e.total||file.size};render(app.state)};
      xhr.onload=()=>{try{const body=JSON.parse(xhr.responseText);xhr.status>=200&&xhr.status<300?resolve(body):reject(Error(body.error||'Falha ao importar'))}catch(e){reject(e)}};
      xhr.onerror=()=>reject(Error('Conexão interrompida durante a importação'));
      xhr.onabort=()=>reject(Error('Importação cancelada'));xhr.send(file);
    });
    if(!app.state.busy){app.video=body.name;app.videoHash='';}toast('Vídeo adicionado à biblioteca. Prepare-o quando desejar.');
  }catch(error){toast(error.message)}
  finally{app.uploadProgress=null;event.target.value='';await refresh()}
};
document.querySelector('.bulk-note span').textContent='“Usar em todos” prepara uma única fonte no PC e reinicia os celulares em grupos de dois para conectá-la às câmeras. Os quadros não são copiados para cada celular. Vídeos já preparados ficam em cache.';

const transferStyles=document.createElement("style");transferStyles.textContent="#camera-transfers{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:12px 24px}#camera-transfers p{margin:8px 0;font-size:13px}#camera-transfers small{display:block;overflow-wrap:anywhere}.usage-row header{gap:10px}";document.head.append(transferStyles);
