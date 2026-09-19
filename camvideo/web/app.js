function panelMessage(value) {
  const text = String(value || '');
  if (text.includes('Current Input Method Manager state:')) return 'Gravação interrompida ao consultar o teclado do Android. A correção está na versão 2.3.3; reabra pelo atalho do painel para carregá-la.';
  return text.length > 600 ? text.slice(0, 600) + '… (diagnóstico extenso; consulte os logs)' : text;
}
const app={state:{},phone:"",video:"",view:localStorage.getItem("emulation-view")||"dashboard",phoneHash:"",videoHash:"",preview:""};

// Keep playback audio preference across video changes and panel reloads.
function setupPlaybackMute(){
  const player=document.getElementById("preview");
  const label=document.createElement("label");
  label.className="check";
  label.innerHTML='<input id="playback-muted" type="checkbox"><span></span>Reproduzir no mudo';
  document.querySelector(".install-box").prepend(label);
  const toggle=label.querySelector("input");
  const saved=localStorage.getItem("emulation-playback-muted")==="true";
  player.defaultMuted=saved;
  player.muted=saved;
  toggle.checked=saved;
  toggle.addEventListener("change",()=>{
    player.muted=toggle.checked;
    player.defaultMuted=toggle.checked;
    localStorage.setItem("emulation-playback-muted",String(toggle.checked));
  });
  player.addEventListener("volumechange",()=>{
    toggle.checked=player.muted;
    player.defaultMuted=player.muted;
    localStorage.setItem("emulation-playback-muted",String(player.muted));
  });
}
setupPlaybackMute();
const $=id=>document.getElementById(id);const esc=value=>String(value??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
function icons(){if(window.lucide)window.lucide.createIcons({attrs:{"stroke-width":1.8}})}
function formatTime(seconds,compact=false){seconds=Math.max(0,Number(seconds)||0);const h=Math.floor(seconds/3600),m=Math.floor(seconds%3600/60);return compact?`${h}h ${String(m).padStart(2,"0")}min`:`${String(Math.floor(seconds/60)).padStart(2,"0")}:${(seconds%60).toFixed(1).padStart(4,"0")}`}
function size(bytes){if(!bytes)return "0 MB";return bytes>=1073741824?`${(bytes/1073741824).toFixed(1)} GiB`:`${(bytes/1048576).toFixed(1)} MiB`}
function duration(seconds){const m=Math.floor((seconds||0)/60),s=Math.floor((seconds||0)%60);return `${m}:${String(s).padStart(2,"0")}`}
function toast(text){const el=$("toast");el.textContent=text;el.classList.add("show");clearTimeout(app.toastTimer);app.toastTimer=setTimeout(()=>el.classList.remove("show"),2800)}
async function call(action,data={}){let response;try{response=await fetch("/api/action",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({...data,action}),signal:AbortSignal.timeout(30000)})}catch{throw Error("Sem confirmação do painel. Confira o andamento antes de tentar novamente; se estiver desconectado, abra ABRIR-PAINEL.bat.")}const body=await response.json();if(!response.ok)throw Error(body.error||"Não foi possível concluir");return body}
async function act(action,data){try{await call(action,data);toast("Comando enviado");setTimeout(refresh,250)}catch(error){toast(error.message)}}
function showView(name){if(!document.getElementById(`view-${name}`))name="dashboard";app.view=name;localStorage.setItem("emulation-view",name);document.querySelectorAll(".view").forEach(v=>v.classList.toggle("active",v.id===`view-${name}`));document.querySelectorAll(".nav-item").forEach(v=>v.classList.toggle("active",v.dataset.view===name));const labels={dashboard:"Visão geral",devices:"Celulares",videos:"Vídeos",automation:"Automação",tiktok:"TikTok Lives"};$("crumb").textContent=labels[name];$("sidebar").classList.remove("open");$("mobile-overlay").classList.remove("show");icons()}
function empty(icon,title,text){return `<div class="empty-state"><div><i data-lucide="${icon}"></i><strong>${title}</strong><span>${text}</span></div></div>`}
const dashboardFilter = {preset:'today',start:'',end:''};
function renderWeek(rows=[]){
const max=Math.max(1,...rows.map(x=>x.seconds));
$("week-chart").innerHTML=rows.map(x=>`<div class="day-column" title="${esc(x.date)}"><strong>${formatTime(x.seconds,true)}</strong><div class="day-bar-track"><i class="day-bar" style="height:${Math.max(x.seconds?5:0,x.seconds/max*100)}%"></i></div><span>${new Date(x.date+'T12:00:00').toLocaleDateString('pt-BR',{day:'2-digit',month:'2-digit'})}</span></div>`).join('');
}
const brl=value=>value.toLocaleString('pt-BR',{style:'currency',currency:'BRL'});
function renderEarnings(seconds){
const rate=Number($('dashboard-exchange').value),valid=Number.isFinite(rate)&&rate>0;
const hours=seconds/3600;
$('earnings-today').textContent=valid?brl(Dashboard.reais(seconds,rate)):'Informe a cotação';
$('earnings-breakdown').textContent=valid?`Base: ${brl(hours*3*rate)} + bônus: ${brl(hours*rate)}`:'';
$('earnings-rate').textContent=valid?`${brl(4*rate)} por hora`:'';
$('earnings-hours').textContent=`${formatTime(seconds,true)} salvas no período, somando todas as tarefas e celulares`;
$('earnings-history').textContent='Estimativa de ganhos; não representa saldo aprovado a receber.';
}
function renderUsage(analytics){
if(!analytics.day)return;
let period;
try {period=Dashboard.range(dashboardFilter.preset,analytics.day,dashboardFilter.start,dashboardFilter.end);}
catch(error){$('dashboard-filter-error').textContent=error.message;return;}
const data=Dashboard.aggregate(analytics,period),isToday=period.start===analytics.day&&period.end===analytics.day;
const label=period.start===period.end?new Date(period.start+'T12:00:00').toLocaleDateString('pt-BR'):`${new Date(period.start+'T12:00:00').toLocaleDateString('pt-BR')} a ${new Date(period.end+'T12:00:00').toLocaleDateString('pt-BR')}`;
$('today-label').textContent=label;
$('today-hours').textContent=formatTime(data.seconds,true);
$('saved-today-note').textContent=`${label} • histórico local`;
$('task-count').textContent=data.activeTasks;
$('chart-period-title').textContent='Atividade no período';
$('task-period-title').textContent=isToday?'Uso por tarefa hoje':'Total por tarefa no período';
renderWeek(data.chart);renderEarnings(data.seconds);
const tasks=isToday?(analytics.byTask||[]):data.byTask;
$('task-usage').innerHTML=tasks.length?tasks.map(x=>`<div class="usage-row"><header><span>${esc(x.name)}</span><strong>${formatTime(x.seconds,true)}</strong></header>${(x.phones||[]).map(p=>`<div class="usage-row"><header><span>${esc(p.name)}</span><strong>${formatTime(p.seconds,true)}${isToday?' / 2h 00min':''}</strong></header>${isToday?`<div class="mini-track"><i style="width:${Math.min(100,p.seconds/7200*100)}%"></i></div><small>${p.available?'Disponível para esta tarefa':'Limite de hoje concluído para esta tarefa'}</small>`:''}</div>`).join('')}</div>`).join(''):empty('clock','Nenhuma tarefa registrada','Não há horas salvas neste período');
const max=Math.max(1,...data.byPhone.map(x=>x.seconds));
$('phone-usage').innerHTML=data.byPhone.map(x=>`<div class="usage-row"><header><span>${esc(x.name)}</span><strong>${formatTime(x.seconds,true)}</strong></header><div class="mini-track"><i style="width:${x.seconds/max*100}%"></i></div></div>`).join('');
for(const id of ['dashboard-start','dashboard-end'])$(id).max=analytics.day;
}
function setupDashboard(){
try { const saved=JSON.parse(localStorage.getItem('emulation-dashboard-filter')||'null');if(saved&&['today','yesterday','7','15','30','custom'].includes(saved.preset))Object.assign(dashboardFilter,saved); }catch{}
$('dashboard-period').value=dashboardFilter.preset;
$('dashboard-custom').hidden=dashboardFilter.preset!=='custom';
$('dashboard-start').value=dashboardFilter.start;$('dashboard-end').value=dashboardFilter.end;
const savedRate=Number(localStorage.getItem('emulation-dashboard-exchange'));
if(Number.isFinite(savedRate)&&savedRate>0)$('dashboard-exchange').value=savedRate;
const rateNote=()=>{$('exchange-note').innerHTML=localStorage.getItem('emulation-dashboard-exchange')?'Cotação manual salva neste navegador.':'Referência inicial: PTAX venda de 10/09/2026 — <a href="https://ptax.bcb.gov.br/ptax_internet/consultarUltimaCotacaoDolar.do" target="_blank" rel="noopener">Banco Central</a>. Não atualiza automaticamente.'};
rateNote();
const apply=()=>{try{Dashboard.range($('dashboard-period').value,app.state.analytics?.day,$('dashboard-start').value,$('dashboard-end').value);}catch(error){$('dashboard-filter-error').textContent=error.message;return;}
Object.assign(dashboardFilter,{preset:$('dashboard-period').value,start:$('dashboard-start').value,end:$('dashboard-end').value});
localStorage.setItem('emulation-dashboard-filter',JSON.stringify(dashboardFilter));$('dashboard-filter-error').textContent='';renderUsage(app.state.analytics);};
$('dashboard-period').onchange=()=>{const custom=$('dashboard-period').value==='custom';$('dashboard-custom').hidden=!custom;$('dashboard-filter-error').textContent='';if(custom){$('dashboard-start').value||=app.state.analytics?.day||'';$('dashboard-end').value||=app.state.analytics?.day||'';}else apply();};
$('dashboard-filter').onsubmit=event=>{event.preventDefault();apply();};
$('dashboard-exchange').onchange=()=>{const rate=Number($('dashboard-exchange').value);if(!Number.isFinite(rate)||rate<=0){$('dashboard-exchange').setCustomValidity('Informe uma cotação maior que zero.');$('dashboard-exchange').reportValidity();}else{$('dashboard-exchange').setCustomValidity('');localStorage.setItem('emulation-dashboard-exchange',String(rate));rateNote();}if(app.state.analytics)renderUsage(app.state.analytics);};
}
setupDashboard();
function renderPhones(phones){const hash=JSON.stringify([app.phone,phones]);if(hash===app.phoneHash)return;app.phoneHash=hash;$("phones").innerHTML=phones.length?phones.map(p=>`<article class="phone-card ${p.serial===app.phone?"selected":""}" data-serial="${esc(p.serial)}"><div class="phone-top"><span class="device-visual"></span><span class="pill ${esc(p.status)}">${p.status==="online"?"ONLINE":p.status==="booting"?"INICIANDO":"DESLIGADO"}</span></div><h3>${esc(p.name)}</h3><small>${esc(p.serial)} • porta ${esc(p.port)}</small><div class="phone-actions"><button data-action="start"><i data-lucide="power"></i> Ligar</button><button data-action="stop"><i data-lucide="power-off"></i> Desligar</button><button class="open-minute" data-action="minute"><i data-lucide="external-link"></i> Abrir Minute</button></div></article>`).join(""):empty("smartphone","Nenhum celular configurado","Adicione um celular para começar");document.querySelectorAll(".phone-card").forEach(card=>card.addEventListener("click",event=>{app.phone=card.dataset.serial;const action=event.target.closest("[data-action]")?.dataset.action;if(action)act(action,{serial:app.phone});app.phoneHash="";renderPhones(app.state.phones||[]);updateSelectionLabels()}));icons()}
function setPreview(item){const player=$("preview"),emptyEl=$("player-empty");if(!item){player.removeAttribute("src");player.removeAttribute("poster");player.load();emptyEl.classList.remove("hidden");$("preview-name").textContent="Nenhum vídeo selecionado";$("preview-meta").textContent="—";return}$("preview-name").textContent=item.name;$("preview-meta").textContent=`${duration(item.duration)} • ${item.width||"?"}×${item.height||"?"} • ${String(item.codec||"codec desconhecido").toUpperCase()} • ${size(item.size)}`;player.poster=item.thumb;if(!item.previewReady){emptyEl.classList.remove("hidden");emptyEl.innerHTML='<div><i data-lucide="loader-circle"></i><strong>Preparando prévia compatível</strong><span>O vídeo original continua disponível normalmente</span></div>';if(player.getAttribute("src")){player.removeAttribute("src");player.load()}icons();return}emptyEl.classList.add("hidden");const key=item.name+item.playback;if(app.preview!==key){app.preview=key;player.src=item.playback||item.media;player.load()}}
function renderVideos(videos){
  const hash=JSON.stringify([app.video,videos]);
  if(hash!==app.videoHash){
    app.videoHash=hash;
    $("videos").innerHTML=videos.length?videos.map(v=>`<article class="video-card ${v.name===app.video?"selected":""}" data-video="${encodeURIComponent(v.name)}"><img class="video-thumb" src="${esc(v.thumb)}" alt="Prévia de ${esc(v.name)}" loading="lazy"><div class="video-copy"><strong>${esc(v.name)}</strong><span>${duration(v.duration)} • ${size(v.size)} • ${esc((v.codec||"vídeo").toUpperCase())}</span><div class="video-readiness"></div></div><div class="video-library-actions"><button type="button" class="video-library-action" data-video-library-action="rename" title="Renomear ${esc(v.name)}" aria-label="Renomear ${esc(v.name)}" disabled><i data-lucide="pencil" aria-hidden="true"></i></button><button type="button" class="video-library-action" data-video-library-action="delete" title="Excluir ${esc(v.name)}" aria-label="Excluir ${esc(v.name)}" disabled><i data-lucide="trash-2" aria-hidden="true"></i></button></div></article>`).join(""):empty("clapperboard","Biblioteca vazia","Importe o primeiro vídeo");
    document.querySelectorAll(".video-card").forEach(card=>card.addEventListener("click",event=>{
      const action=event.target.closest('[data-video-library-action]');
      if(action){event.stopPropagation();if(!action.disabled)window.VideoLibrary?.open(action.dataset.videoLibraryAction,decodeURIComponent(card.dataset.video));return;}
      app.video=decodeURIComponent(card.dataset.video);app.videoHash="";renderVideos(app.state.videos||[]);
    }));
    icons();
  }
  setPreview(videos.find(v=>v.name===app.video));
  $("video-count").textContent=`${videos.length} vídeo${videos.length===1?"":"s"}`;
  window.VideoLibrary?.update();
  window.VideoReadiness?.update(videos);
}
function updateSelectionLabels(){const p=(app.state.phones||[]).find(x=>x.serial===app.phone);$("selected-phone-label").textContent=p?`Selecionado: ${p.name}`:"Nenhum selecionado"}
function render(state){app.state=state;if(!app.phone&&state.phones[0])app.phone=state.phones[0].serial;if(!state.phones.some(p=>p.serial===app.phone)&&state.phones[0])app.phone=state.phones[0].serial;if(!app.video&&state.videos[0])app.video=state.currentName&&state.videos.some(v=>v.name===state.currentName)?state.currentName:state.videos[0].name;if(!state.videos.some(v=>v.name===app.video)&&state.videos[0])app.video=state.videos[0].name;const online=state.phones.filter(p=>p.status==="online").length,analytics=state.analytics||{};$("online").textContent=`${online} / ${state.phones.length}`;$("online-note").textContent=online===state.phones.length&&online?"Todos operacionais":online?`${state.phones.length-online} indisponível(is)`:"Nenhum conectado";$("nav-online").textContent=online;$("nav-videos").textContent=state.videos.length;$("today-hours").textContent=formatTime(analytics.todaySeconds,true);$("saved-today-note").textContent=`Histórico acumulado: ${formatTime(analytics.totalSeconds,true)}`;$("task-count").textContent=analytics.activeTasks||0;$("current").textContent=state.currentName||(state.current?"Vídeo ativo":"Nenhum");$("current-size").textContent=state.current?`${size(state.current)} instalado`:"Nenhum arquivo ativo";$("detected").textContent=state.task||"Aguardando a gravação";$("timer").innerHTML=`${formatTime(state.elapsed)} <span>/ ${formatTime(state.total)}</span>`;$("syncbar").style.width=`${state.progress||0}%`;$("jobbar").style.width=`${state.progress||0}%`;$("timer-percent").textContent=`${state.progress||0}%`;$("percent").textContent=`${state.progress||0}%`;$("message").textContent=panelMessage(state.message);$("operation-label").textContent=state.busy?"Operação em andamento":"Sistema pronto";const badge=$("badge");badge.textContent=state.level==="error"?"ERRO":state.busy?"EM CURSO":"OK";badge.style.color=state.level==="error"?"var(--red)":state.level==="warn"?"var(--amber)":"var(--green)";$("adjust-context").textContent=state.task?`${state.task} • ${((state.phones||[]).find(x=>x.serial===app.phone)||{}).name||"celular selecionado"}`:"A tarefa aparecerá após ser detectada.";renderWeek(analytics.last7Days||[]);renderUsage(analytics);renderPhones(state.phones||[]);renderVideos(state.videos||[]);updateSelectionLabels();icons()}
let refreshing=false;
async function refresh(){if(refreshing)return;refreshing=true;try{const response=await fetch("/api/state",{cache:"no-store",signal:AbortSignal.timeout(15000)});if(!response.ok)throw Error();const state=await response.json();render(state);window.dispatchEvent(new CustomEvent('panel-connection',{detail:{connected:true}}))}catch(error){const badge=$("badge");badge.textContent="OFFLINE";badge.style.color="var(--red)";window.dispatchEvent(new CustomEvent('panel-connection',{detail:{connected:false,message:'Não foi possível atualizar o painel. Reabra ABRIR-PAINEL.bat e use a janela que ele abrir. O início está bloqueado até a conexão voltar.'}}));console.error('Falha ao atualizar painel',error)}finally{refreshing=false}}
document.querySelectorAll(".nav-item").forEach(btn=>btn.addEventListener("click",()=>showView(btn.dataset.view)));document.querySelectorAll("[data-go]").forEach(btn=>btn.addEventListener("click",()=>showView(btn.dataset.go)));$("menu-toggle").onclick=()=>{$("sidebar").classList.toggle("open");$("mobile-overlay").classList.toggle("show")};$("mobile-overlay").onclick=()=>showView(app.view);$("all").onclick=()=>act("all_start");$("add").onclick=()=>act("add");$("sync").onclick=()=>act("sync");$("cancel").onclick=()=>act("cancel");$("install").onclick=()=>app.video?act("install",{serial:app.phone,video:app.video,fill:$("fill").checked}):toast("Selecione um vídeo");document.querySelectorAll("[data-c]").forEach(btn=>btn.onclick=()=>act("control",{serial:app.phone,control:btn.dataset.c}));$("adjust").onclick=()=>app.state.task?act("adjust",{serial:app.phone,minutes:Number($("minutes").value)}):toast("Aguarde a tarefa ser detectada");
$("install-all").onclick=()=>app.video?act("install_all",{video:app.video,fill:$("fill").checked}):toast("Selecione um vídeo");
$("upload").onchange=async event=>{const file=event.target.files[0];if(!file)return;toast("Importando vídeo...");try{const response=await fetch("/api/upload",{method:"POST",headers:{"X-Filename":encodeURIComponent(file.name),"Content-Length":String(file.size)},body:file});const body=await response.json();if(!response.ok)throw Error(body.error);app.video=body.name;app.videoHash="";toast("Vídeo importado");await refresh()}catch(error){toast(error.message)}event.target.value=""};
$("preview").addEventListener("error",()=>{$("player-empty").classList.remove("hidden");$("player-empty").innerHTML='<div><i data-lucide="image"></i><strong>Miniatura disponível</strong><span>Este codec não reproduz diretamente no navegador</span></div>';icons()});$("today-label").textContent=new Date().toLocaleDateString("pt-BR",{weekday:"long",day:"2-digit",month:"long"});showView(app.view);icons();refresh();setInterval(refresh,1800);

// Reload saved interface changes, following a newer local panel if one exists.
document.getElementById('refresh-panel')?.addEventListener('click', async event => {
  event.currentTarget.disabled = true;
  try {
    const response = await fetch('/current-runtime.json', {cache:'no-store', signal:AbortSignal.timeout(3000)});
    const latest = response.ok ? await response.json() : {};
    if (/^http:\/\/127\.0\.0\.1:\d+\/$/.test(latest.url) && latest.url !== location.origin + '/') {
      location.assign(latest.url);
      return;
    }
  } catch {}
  location.reload();
});
