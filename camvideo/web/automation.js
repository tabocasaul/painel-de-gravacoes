(() => {
  const main = document.querySelector('.automation-main');
  const config = document.createElement('div');
  config.className = 'automation-config';
  config.innerHTML = `<label for="automation-plan">Plano de gravação</label>
    <select id="automation-plan"><option value="daily">Plano diário — louça, ervas e jardim</option><option value="interleaved">Plano intercalado — tarefas aleatórias</option><option value="single">Uma tarefa escolhida abaixo</option></select>
    <div class="automation-rule"><strong>Plano diário: até 6h por celular</strong><p>1. Lavar Louça na Pia — 2h — Lavando louça .MOV<br>2. Arrancar ervas daninhas à mão / com garfo de mão — 2h — Arrancando ervas .mov<br>3. Manutenção completa do jardim — 2h — Arrancando ervas .mov</p><p>Completa o saldo de hoje dos celulares participantes antes da próxima categoria. Troca a fonte após salvar, usa a quantidade escolhida por rodada e respeita o limite separado por tarefa. À meia-noite o saldo diário reseta. Pode restar menos de 90 segundos para respeitar a duração mínima de gravação do Minute.</p></div>
    <label for="automation-mode">Como entrar na tarefa</label>
    <select id="automation-mode"><option value="auto">Procurar a tarefa e confirmar as dicas</option><option value="ready">Usar as câmeras já abertas</option></select>
    <label for="automation-task">Nome completo da tarefa no Minute</label>
    <input id="automation-task" placeholder="Ex.: Lavar Louça na Pia" maxlength="160">
    <label for="automation-scope">Celulares participantes</label>
    <select id="automation-scope"><option value="all">Todos os cadastrados — rodadas em sequência</option><option value="online">Somente os ligados</option><option value="selected">Escolher aparelhos</option></select>
    <div id="automation-participants" hidden>
      <label for="automation-participant-search">Buscar aparelho pelo nome ou identificação</label>
      <input id="automation-participant-search" type="search" placeholder="Buscar entre os aparelhos cadastrados">
      <div class="participant-actions"><button type="button" class="button button-secondary" id="automation-participants-all">Marcar todos</button><button type="button" class="button button-secondary" id="automation-participants-clear">Limpar</button></div>
      <p id="automation-participant-count" class="automation-steps" aria-live="polite"></p>
      <div id="automation-participant-list"></div>
      <p class="automation-steps">Marque quantos aparelhos quiser. A quantidade por rodada é escolhida abaixo; os demais aguardam sua vez. Novos aparelhos só entram nesta escolha quando você os marcar.</p>
    </div>
    <label for="automation-simultaneous-mode">Celulares simultâneos</label>
    <select id="automation-simultaneous-mode"><option value="custom">Quantidade que eu escolher</option><option value="auto">Automático conforme a RAM</option></select>
    <label for="automation-simultaneous">Quantidade por rodada</label>
    <input id="automation-simultaneous" type="number" min="1" step="1" inputmode="numeric" value="2" aria-describedby="automation-simultaneous-help">
    <p id="automation-simultaneous-help" class="automation-steps"></p>
    <label for="automation-repeat">Repetição</label>
    <select id="automation-repeat"><option value="once">Executar uma rodada</option><option value="repeat">Loop contínuo — repetir até eu parar</option></select>
    <p class="automation-steps">O botão abre o Minute nos aparelhos participantes, procura a tarefa e confirma as dicas. Prioriza os celulares que menos gravaram e pula os que estão sem saldo diário. Cada rodada usa até a quantidade escolhida. Após salvar, libera os aparelhos da rodada anterior quando há outros aguardando. Não é necessário abrir todos manualmente.</p><p id="automation-loop-help" class="automation-steps">No loop, todos salvam antes da próxima rodada. O vídeo vinculado à próxima tarefa recomeça do zero. O supervisor tenta recuperar falhas com intervalos de 30 a 120 segundos. Ao concluir os limites, o plano diário aguarda o próximo dia. Falhas de gravação ou salvamento preservam o vídeo; a fila retoma após a recuperação e a confirmação do salvamento.</p>
    <div class="automation-rule"><strong>Encerrar e salvar automaticamente</strong><p>Ao terminar o vídeo instalado ou atingir o limite de 29min59s, o que acontecer primeiro. O tempo de preparação já gravado pelo Minute entra nesse limite.</p></div>
    <p id="automation-video"></p><p class="automation-steps">1. Girar à esquerda → 2. Abrir a tarefa → 3. Vídeo do zero e gravação → 4. Encerrar e salvar</p>`;
  main.prepend(config);
  const ram = document.createElement('div');
  ram.className = 'automation-rule';
  ram.innerHTML = '<strong>Capacidade do PC agora</strong><p id="automation-ram-live" aria-live="polite">Medindo a memória disponível...</p><small>Estimativa do modo automático. Reserva 2,5 GiB para o Windows e considera 3 GiB por novo celular. Feche programas para liberar RAM; o consumo pode variar.</small>';
  config.prepend(ram);
  const supervisorBox=document.createElement('div');
  supervisorBox.className='automation-rule';
  supervisorBox.innerHTML='<strong>Recuperação automática</strong><p>Ativada ao iniciar. Confere o crescimento do vídeo, tenta salvar capturas pendentes e retoma após falhas. Se o painel fechar ou não responder, um processo local tenta reabri-lo com o plano salvo. Os botões de parar desativam a retomada automática.</p><p id="supervisor-status">Pronto para acompanhar a próxima execução.</p>';
  config.append(supervisorBox);
  const result = document.createElement('article');
  result.className = 'panel automation-results';
  result.innerHTML = '<h2>Andamento por celular</h2><p id="automation-loop-status"></p><p id="automation-queue-status"></p><p id="automation-next-task-status" role="status" aria-live="polite" hidden></p><button class="button button-secondary" id="loop-stop-after" disabled>Parar após salvar esta rodada</button><p id="automation-message">Escolha a tarefa e confira o vídeo antes de iniciar.</p><div id="automation-rows"></div>';
  document.querySelector('#view-automation .automation-layout').after(result);
  const style = document.createElement('style');
  style.textContent = `.automation-config{display:grid;gap:10px;margin-bottom:24px}.automation-config label{font-weight:600;font-size:13px}.automation-config input,.automation-config select{width:100%;padding:12px;border:1px solid var(--border,#334155);border-radius:10px;background:var(--bg,#101827);color:var(--text,#eee)}.automation-rule{padding:14px;background:#112f32;border-radius:12px;margin-top:8px}.automation-rule p,.automation-steps,#automation-video{font-size:13px;line-height:1.6;margin:6px 0}.automation-results{margin-top:20px;padding:22px}.automation-device{padding:15px 0;border-bottom:1px solid var(--border,#334155)}.automation-device header{display:flex;justify-content:space-between;gap:12px}.automation-device small{display:block;margin:8px 0;color:var(--muted,#9ca3af)}.automation-device.error{color:var(--red,#ff7373)}.automation-device .progress{margin-top:10px}.automation-actions button:disabled{opacity:.45;cursor:not-allowed}.automation-config [hidden]{display:none!important}#automation-participants{display:grid;gap:10px;padding:14px;border:1px solid var(--border,#334155);border-radius:12px}.participant-actions{display:flex;gap:10px;flex-wrap:wrap}#automation-participant-list{max-height:300px;overflow:auto}.participant-row{display:flex;align-items:center;gap:12px;padding:12px 4px;border-bottom:1px solid var(--border,#334155)}.participant-row span{min-width:0;overflow-wrap:anywhere}.participant-row small{display:block;font-weight:400;color:var(--muted,#9ca3af);margin-top:5px}.automation-config .participant-check{width:19px;height:19px;flex:0 0 19px;accent-color:var(--cyan,#22d3ee)}.automation-config :disabled{opacity:.55;cursor:not-allowed}`;
  document.head.append(style);
  const task = document.getElementById('automation-task');
  const plan = document.getElementById('automation-plan');
  const rememberedPlan=localStorage.getItem('automation-plan');
  if(['daily','single','interleaved'].includes(rememberedPlan))plan.value=rememberedPlan;
  const dailyDescription=[...config.querySelectorAll('.automation-rule')].find(el=>el.textContent.startsWith('Plano diário:'));
  const interleavedBox = document.createElement('div');
  interleavedBox.className='automation-rule'; interleavedBox.hidden=true;
  interleavedBox.innerHTML=`<strong>Plano intercalado</strong><p>Selecione tarefas do Minute e adicione os vídeos de cada uma. As tarefas continuam em ordem sorteada. Cada vez que uma tarefa voltar, ela usará o próximo vídeo de sua própria lista, em ordem; depois do último, volta ao primeiro. Com um único vídeo, repete esse vídeo. Limite: 2h por tarefa, por celular, por dia; até 29min59s por rodada.</p><p>Depois de iniciar, o painel segue sozinho neste computador. Se um aparelho falhar, ele aguarda os demais terminarem e salvarem. O grupo segue para a próxima tarefa e o aparelho com falha tenta voltar junto nessa próxima rodada, sem tentar refazer a rodada que falhou. Uma captura pendente é preservada; se ainda impedir o retorno daquele aparelho, os demais continuam.</p><label for="catalog-phone">Celular para ler o catálogo</label><select id="catalog-phone"></select><button type="button" class="button button-secondary" id="catalog-refresh">Atualizar tarefas do Minute</button><p id="catalog-status"></p><label for="catalog-search">Buscar no catálogo</label><input id="catalog-search" placeholder="Filtrar tarefas"><div id="catalog-choices"></div><p id="catalog-selection-count"></p>`;
  plan.after(interleavedBox);
  let links=Object.create(null);
  try {
    const saved=JSON.parse(localStorage.getItem('interleaved-task-videos')||'{}');
    if(saved && typeof saved==='object' && !Array.isArray(saved)) {
      for(const [name,value] of Object.entries(saved)) links[name]=Array.isArray(value) && value.length ? value.map(video=>typeof video==='string'?video:'') : [typeof value==='string'?value:''];
      localStorage.setItem('interleaved-task-videos',JSON.stringify(links));
    }
  } catch {}
  const catalogDrafts=Object.create(null);
  const catalogChoices=document.getElementById('catalog-choices');
  const saveLinks=()=>localStorage.setItem('interleaved-task-videos',JSON.stringify(links));
  const rowVideos=name=>links[name] || catalogDrafts[name] || [''];
  function applyLibraryRename(detail,fromStorage=false){
    const {oldName,name}=detail || {};
    if(typeof oldName!=='string' || typeof name!=='string' || !oldName || !name || oldName===name)return;
    {
      try{
        const saved=JSON.parse(localStorage.getItem('interleaved-task-videos') || '{}');
        if(!saved || typeof saved!=='object' || Array.isArray(saved))return;
        links=Object.fromEntries(Object.entries(saved).map(([task,videos])=>[task,Array.isArray(videos) && videos.length?videos.map(video=>typeof video==='string'?video:''):[typeof videos==='string'?videos:'']]));
      }catch{return;}
    }
    let changed=false;
    for(const collection of [links,catalogDrafts])for(const [task,videos] of Object.entries(collection)){
      if(videos.includes(oldName)){collection[task]=videos.map(video=>video===oldName?name:video);changed=true;}
    }
    if(changed && !fromStorage)saveLinks();
    if(latestState){
      latestState={...latestState,videos:(latestState.videos || []).map(video=>video.name===oldName?{...video,name}:video)};
      drawCatalog(latestState);updateStart();
    }
  }
  window.addEventListener('video-library-renamed',event=>applyLibraryRename(event.detail));
  window.addEventListener('storage',event=>{
    if(event.key==='video-library-last-rename' && event.newValue){try{applyLibraryRename(JSON.parse(event.newValue),true);}catch{}}
  });
  function filterCatalog(){
    const query=document.getElementById('catalog-search').value.toLocaleLowerCase('pt-BR');
    catalogChoices.querySelectorAll('.catalog-row').forEach(row=>row.hidden=!row.dataset.task.toLocaleLowerCase('pt-BR').includes(query));
  }
  function playlistValidation(){
    if(plan.value!=='interleaved')return '';
    if(latestState && !(latestState.interleavedVideoListsVersion>=1))return 'Reabra o painel atualizado pelo atalho para usar listas de vídeos por tarefa.';
    if(latestState && !(latestState.interleavedSkipFailedRoundsVersion>=1))return 'Reabra o painel atualizado pelo atalho para continuar na próxima tarefa após uma falha.';
    if(!Object.keys(links).length)return 'Selecione pelo menos uma tarefa e um vídeo para cada tarefa.';
    const tasks=new Set(latestState?.minuteCatalog?.tasks || []), videos=new Set((latestState?.videos || []).map(video=>video.name));
    for(const [name,playlist] of Object.entries(links)) {
      if(!tasks.has(name))return `A tarefa "${name}" não está no catálogo atual. Atualize as tarefas do Minute ou desmarque essa tarefa.`;
      if(!playlist.length || playlist.some(video=>!video))return `Escolha um vídeo em cada posição de "${name}", ou remova as posições vazias.`;
      const missing=playlist.find(video=>!videos.has(video));
      if(missing)return `O vídeo "${missing}" de "${name}" está indisponível. Escolha outro vídeo ou remova essa posição.`;
    }
    return '';
  }
  let catalogHash='';
  function drawCatalog(state){
    const catalog=state.minuteCatalog||{tasks:[]};
    const catalogTasks=catalog.tasks||[], availableTasks=new Set(catalogTasks);
    const availableVideos=new Set((state.videos||[]).map(video=>video.name));
    const online=state.phones||[], phoneSelect=document.getElementById('catalog-phone');
    const phoneHash=JSON.stringify(online.map(p=>[p.serial,p.name]));
    if(phoneSelect.dataset.hash!==phoneHash){const old=phoneSelect.value;phoneSelect.innerHTML=online.map(p=>`<option value="${esc(p.serial)}">${esc(p.name)}</option>`).join('');if(online.some(p=>p.serial===old))phoneSelect.value=old;phoneSelect.dataset.hash=phoneHash;}
    const hash=JSON.stringify([catalog,state.videos?.map(v=>v.name),links,catalogDrafts]);
    if(hash!==catalogHash){
      catalogHash=hash;
      const shownTasks=[...new Set([...catalogTasks,...Object.keys(links)])];
      catalogChoices.innerHTML=shownTasks.map((name,i)=>{
        const playlist=rowVideos(name), missingTask=!availableTasks.has(name);
        return `<div class="catalog-row" data-task="${esc(name)}"><div><label><input class="catalog-check" type="checkbox" ${Object.hasOwn(links,name)?'checked':''}>${esc(name)}</label>${missingTask?'<p class="catalog-warning">Tarefa ausente no catálogo atual. Atualize o catálogo ou desmarque esta tarefa.</p>':''}</div><div class="catalog-videos">${playlist.map((video,j)=>{
          const missing=video && !availableVideos.has(video);
          return `<div class="catalog-video-entry"><label for="catalog-video-${i}-${j}">Vídeo ${j+1}</label><div class="catalog-video-controls"><select id="catalog-video-${i}-${j}" aria-label="Vídeo ${j+1} para ${esc(name)}" class="catalog-video" data-index="${j}"><option value="">Selecione um vídeo</option>${missing?`<option value="${esc(video)}" selected>Indisponível: ${esc(video)}</option>`:''}${(state.videos||[]).map(v=>`<option value="${esc(v.name)}" ${video===v.name?'selected':''}>${esc(v.name)}</option>`).join('')}</select><button type="button" class="button button-secondary catalog-remove-video" data-index="${j}" aria-label="Remover vídeo ${j+1} de ${esc(name)}">Remover</button></div>${missing?'<p class="catalog-warning">Escolha outro vídeo ou remova esta posição.</p>':''}</div>`;
        }).join('')}<button type="button" class="button button-secondary catalog-add-video">+ Adicionar vídeo</button></div></div>`;
      }).join('');
    }
    document.getElementById('catalog-status').textContent=catalog.tasks?.length?`${catalog.tasks.length} tarefas • atualizado em ${catalog.updatedAt} • catálogo do celular ${catalog.serial}.`:'Clique em Atualizar tarefas do Minute para carregar a lista. O celular será aberto, sem iniciar gravação.';
    if(state.operation==='minute_catalog')document.getElementById('catalog-status').textContent=panelMessage(state.message);
    interleavedBox.querySelectorAll('button,select,input').forEach(el=>el.disabled=pending || !!state.busy);
    document.getElementById('catalog-selection-count').textContent=`${Object.keys(links).length} tarefa(s) selecionada(s)`;
    filterCatalog();
  }
  catalogChoices.addEventListener('change',event=>{
    const row=event.target.closest('.catalog-row');if(!row || pending || latestState?.busy)return;
    const name=row.dataset.task, playlist=[...row.querySelectorAll('.catalog-video')].map(select=>select.value);
    catalogDrafts[name]=playlist;
    if(row.querySelector('.catalog-check').checked)links[name]=[...playlist];else delete links[name];
    saveLinks();notice='';drawCatalog(latestState);updateStart();
  });
  catalogChoices.addEventListener('click',event=>{
    const add=event.target.closest('.catalog-add-video'), remove=event.target.closest('.catalog-remove-video');
    const row=event.target.closest('.catalog-row');if(!row || (!add && !remove) || pending || latestState?.busy)return;
    const name=row.dataset.task, playlist=[...row.querySelectorAll('.catalog-video')].map(select=>select.value);
    if(add)playlist.push('');else {playlist.splice(Number(remove.dataset.index),1);if(!playlist.length)playlist.push('');}
    catalogDrafts[name]=playlist;if(row.querySelector('.catalog-check').checked)links[name]=[...playlist];
    saveLinks();notice='';drawCatalog(latestState);updateStart();
    if(add){const updated=[...catalogChoices.querySelectorAll('.catalog-row')].find(item=>item.dataset.task===name);const selects=updated?.querySelectorAll('.catalog-video');if(selects?.length)selects[selects.length-1].focus();}
  });
  document.getElementById('catalog-search').oninput=filterCatalog;
  document.getElementById('catalog-refresh').onclick=()=>act('minute_catalog',{serial:document.getElementById('catalog-phone').value});
  const catalogStyle=document.createElement('style');catalogStyle.textContent='.automation-rule[hidden],.catalog-row[hidden]{display:none!important}.catalog-row{display:grid;grid-template-columns:minmax(0,1fr) minmax(220px,1.2fr);gap:12px;padding:16px 0;border-bottom:1px solid #334155}.catalog-row label{display:flex;align-items:center;gap:9px;overflow-wrap:anywhere}.automation-config .catalog-check{width:18px;flex-shrink:0}.catalog-videos{display:grid;gap:12px;min-width:0}.catalog-video-entry{display:grid;gap:6px;min-width:0}.catalog-video-controls{display:flex;gap:8px;min-width:0}.catalog-video-controls select{min-width:0}.catalog-add-video{justify-self:start}.catalog-warning{font-size:12px!important;color:#fbbf24;overflow-wrap:anywhere}#catalog-choices{max-height:520px;overflow:auto;margin-top:12px}@media(max-width:600px){.catalog-row{grid-template-columns:1fr}}';document.head.append(catalogStyle);
  task.value = localStorage.getItem('automation-task') || '';
  task.onchange = () => localStorage.setItem('automation-task', task.value.trim());
  const mode = document.getElementById('automation-mode');
  const repeat = document.getElementById('automation-repeat');
  const scope = document.getElementById('automation-scope');
  const rememberedScope = localStorage.getItem('automation-scope');
  if (['all','online','selected'].includes(rememberedScope)) scope.value = rememberedScope;
  const simultaneous = document.getElementById('automation-simultaneous');
  const simultaneousMode = document.getElementById('automation-simultaneous-mode');
  const validQuantity = value => String(value).trim() !== '' && Number.isSafeInteger(Number(value)) && Number(value) > 0;
  const rememberedSimultaneous = localStorage.getItem('automation-simultaneous');
  const rememberedCount = localStorage.getItem('automation-simultaneous-count');
  simultaneousMode.value = rememberedSimultaneous === 'auto' ? 'auto' : 'custom';
  simultaneous.value = validQuantity(rememberedSimultaneous) ? String(Number(rememberedSimultaneous)) : validQuantity(rememberedCount) ? String(Number(rememberedCount)) : '2';
  let selectedSerials = new Set();
  try {
    const saved = JSON.parse(localStorage.getItem('automation-selected-serials') || '[]');
    if (Array.isArray(saved)) selectedSerials = new Set(saved.filter(serial => typeof serial === 'string' && serial.trim()));
  } catch {}
  const participants = document.getElementById('automation-participants');
  const participantList = document.getElementById('automation-participant-list');
  const participantSearch = document.getElementById('automation-participant-search');
  let participantHash = '', removedParticipants = 0;
  const saveParticipants = () => localStorage.setItem('automation-selected-serials', JSON.stringify([...selectedSerials]));
  const participatingPhones = state => (state.phones || []).filter(phone => scope.value === 'selected' ? selectedSerials.has(phone.serial) : scope.value !== 'online' || phone.status === 'online');
  function filterParticipants() {
    const query = participantSearch.value.trim().toLocaleLowerCase('pt-BR');
    participantList.querySelectorAll('.participant-row').forEach(row => row.hidden = !row.dataset.search.includes(query));
  }
  function drawParticipants(state) {
    const phones = state.phones || [];
    if (Array.isArray(state.phones)) {
      const available = new Set(phones.map(phone => phone.serial));
      let removed = 0;
      for (const serial of selectedSerials) if (!available.has(serial)) { selectedSerials.delete(serial); removed++; }
      if (removed) { removedParticipants += removed; saveParticipants(); }
    }
    const hash = JSON.stringify(phones.map(phone => [phone.serial,phone.name,phone.status]));
    if (hash !== participantHash) {
      participantHash = hash;
      participantList.innerHTML = phones.map(phone => {
        const status = phone.status === 'online' ? 'Ligado' : phone.status === 'booting' ? 'Iniciando' : phone.status === 'off' ? 'Desligado' : 'Indisponível';
        const name = phone.name || phone.serial;
        return `<label class="participant-row" data-search="${esc(`${name} ${phone.serial}`.toLocaleLowerCase('pt-BR'))}"><input type="checkbox" class="participant-check" data-serial="${esc(phone.serial)}"><span>${esc(name)}<small>${esc(phone.serial)} • ${status}</small></span></label>`;
      }).join('') || '<p class="automation-steps">Nenhum aparelho cadastrado. Adicione aparelhos na aba Celulares.</p>';
    }
    participantList.querySelectorAll('.participant-check').forEach(input => { input.checked = selectedSerials.has(input.dataset.serial); input.disabled = pending || !!state.busy; });
    document.getElementById('automation-participant-count').textContent = `${selectedSerials.size} escolhido(s) de ${phones.length} cadastrado(s)${removedParticipants ? ` • ${removedParticipants} aparelho(s) deixou/deixaram de estar cadastrado(s) e saiu/saíram da escolha.` : ''}`;
    filterParticipants();
  }
  function drawVideo(state) {
    const phones = participatingPhones(state);
    const videos = phones.map(phone => phone.installedVideo || state.installedVideos?.[phone.serial]);
    const first = videos[0];
    const common = first?.name && videos.every(video => video && (video.confirmed || video.staged) && video.name === first.name && video.assetId === first.assetId);
    document.getElementById('automation-video').textContent = !phones.length ? 'Escolha os aparelhos participantes para conferir o vídeo.' : common ? `Vídeo nos ${phones.length} participante(s): ${first.name}` : scope.value === 'all' && state.allVideoName ? `Vídeo em todos: ${state.allVideoName}` : 'Vídeo diferente ou não confirmado em algum participante. Confira a aba Vídeos.';
  }
  function updateControls() {
    const locked = pending || !!latestState?.busy;
    interleavedBox.querySelectorAll('button,select,input').forEach(input => input.disabled = locked);
    const daily = plan.value !== 'single';
    if (daily) { mode.value = 'auto'; repeat.value = 'repeat'; }
    plan.disabled = locked;
    scope.disabled = locked;
    participants.hidden = scope.value !== 'selected';
    participantSearch.disabled = locked;
    document.getElementById('automation-participants-all').disabled = locked;
    document.getElementById('automation-participants-clear').disabled = locked;
    participantList.querySelectorAll('.participant-check').forEach(input => input.disabled = locked);
    const ready = mode.value === 'ready';
    simultaneousMode.disabled = locked || ready;
    simultaneous.disabled = locked || ready || simultaneousMode.value === 'auto';
    mode.disabled = locked || daily;
    task.disabled = locked || daily || ready;
    repeat.disabled = locked || daily || !supportsLoop;
    document.getElementById('automation-simultaneous-help').textContent = ready ? 'Neste modo, todos os participantes escolhidos precisam estar ligados e com a câmera aberta. Para definir a quantidade por rodada, escolha "Procurar a tarefa e confirmar as dicas".' : simultaneousMode.value === 'auto' ? 'O modo automático ajusta a quantidade pela RAM, com limite de 3 por rodada. Para usar 4, escolha a quantidade manual.' : 'Neste PC, use até 4 ao mesmo tempo. Cada rodada usa até a quantidade informada e apenas os disponíveis. Quando houver mais participantes que vagas, os demais aguardam sua vez.';
  }
  function validationMessage() {
    if (latestState && (!latestState.supervisorVersion || !(latestState.participantSelectionVersion >= 1))) return 'Reabra o painel atualizado pelo atalho para escolher aparelhos e a quantidade por rodada.';
    const playlistError=playlistValidation();if(playlistError)return playlistError;
    if (scope.value === 'selected') {
      if (!selectedSerials.size) return 'Marque pelo menos um aparelho para iniciar.';
      const available = new Set((latestState?.phones || []).map(phone => phone.serial));
      if ([...selectedSerials].some(serial => !available.has(serial))) return 'Um aparelho escolhido não está mais cadastrado. Confira a lista de aparelhos.';
    }
    if (mode.value !== 'ready' && simultaneousMode.value !== 'auto' && !validQuantity(simultaneous.value)) return 'Informe uma quantidade inteira de celulares, a partir de 1.';
    return '';
  }
  simultaneous.oninput = simultaneous.onchange = () => {
    if (validQuantity(simultaneous.value)) {
      localStorage.setItem('automation-simultaneous-count', String(Number(simultaneous.value)));
      if (simultaneousMode.value !== 'auto') localStorage.setItem('automation-simultaneous', String(Number(simultaneous.value)));
    }
    notice = ''; updateStart();
  };
  simultaneousMode.onchange = () => {
    if (simultaneousMode.value === 'auto') localStorage.setItem('automation-simultaneous', 'auto');
    else simultaneous.onchange();
    notice = ''; updateStart();
  };
  scope.onchange = () => { localStorage.setItem('automation-scope', scope.value); notice = ''; if (latestState) { drawParticipants(latestState); drawVideo(latestState); } updateStart(); };
  participantSearch.oninput = filterParticipants;
  participantList.addEventListener('change', event => {
    const input = event.target;
    if (!input.matches('.participant-check') || pending || latestState?.busy || !(latestState?.phones || []).some(phone => phone.serial === input.dataset.serial)) return;
    if (input.checked) selectedSerials.add(input.dataset.serial); else selectedSerials.delete(input.dataset.serial);
    removedParticipants = 0; notice = ''; saveParticipants(); drawParticipants(latestState); drawVideo(latestState); updateStart();
  });
  document.getElementById('automation-participants-all').onclick = () => {
    if (pending || latestState?.busy) return;
    selectedSerials = new Set((latestState?.phones || []).map(phone => phone.serial));
    removedParticipants = 0; notice = ''; saveParticipants(); if (latestState) { drawParticipants(latestState); drawVideo(latestState); } updateStart();
  };
  document.getElementById('automation-participants-clear').onclick = () => {
    if (pending || latestState?.busy) return;
    selectedSerials.clear(); removedParticipants = 0; notice = ''; saveParticipants(); if (latestState) { drawParticipants(latestState); drawVideo(latestState); } updateStart();
  };
  let supportsLoop = false;
  let pending = false, connected = false, latestState = null, notice = '';
  const start = document.getElementById('sync');
  const feedback = document.createElement('p');
  feedback.id = 'automation-start-feedback';
  feedback.setAttribute('role', 'status');
  feedback.setAttribute('aria-live', 'polite');
  document.querySelector('.automation-actions').after(feedback);
  const updateStart = () => {
    updateControls();
    const invalid = validationMessage();
    start.disabled = !!invalid || pending || !connected || !latestState || latestState.busy || !latestState.automationVersion || !latestState.sharedCameraVersion || (simultaneousMode.value !== 'auto' && simultaneous.value === '2' && !(latestState.queueVersion >= 2)) || (plan.value === 'daily' && !latestState.dailyPlanVersion) || (plan.value === 'interleaved' && !latestState.interleavedPlanVersion);
    start.textContent = pending ? 'Enviando início...' : latestState?.busy && latestState.operation === 'sync' ? 'Automação em andamento' : scope.value === 'selected' ? 'Iniciar nos aparelhos escolhidos' : scope.value === 'online' ? 'Iniciar nos aparelhos ligados' : 'Iniciar e salvar em todos';
    if (connected && latestState && !pending && !latestState.busy) feedback.textContent = invalid || notice || (latestState.operation === 'sync' ? panelMessage(latestState.message) : 'Pronto para iniciar. Confira a tarefa e o vídeo.');
  };
  feedback.textContent = 'Conectando ao painel...';
  plan.onchange = () => { localStorage.setItem('automation-plan',plan.value); if (latestState) render(latestState); updateStart(); };
  updateStart();
  window.addEventListener('panel-connection', event => {
    connected = event.detail.connected;
    if (!connected) feedback.textContent = event.detail.message;
    updateStart();
  });
  mode.onchange = e => { if (e.target.value === 'ready') repeat.value = 'once'; notice = ''; updateStart(); };
  repeat.onchange = () => { if (repeat.value === 'repeat') mode.value = 'auto'; notice = ''; updateStart(); };
  document.getElementById('loop-stop-after').onclick = () => act('loop_stop_after_round');
  start.onclick = async () => {
    const invalid = validationMessage();
    if (invalid) { feedback.textContent = invalid; updateStart(); return; }
    if (start.disabled) return;
    const autoNavigate = document.getElementById('automation-mode').value === 'auto';
    if (repeat.value === 'repeat' && !supportsLoop) return feedback.textContent = notice = 'Reinicie o painel para ativar o loop contínuo';
    if (plan.value === 'single' && autoNavigate && !task.value.trim()) { task.focus(); return feedback.textContent = notice = 'Informe o nome completo da tarefa no Minute'; }
    const interleavedTasks=Object.entries(links).map(([task,videos])=>({task,videos:[...videos]}));
    notice = '';
    pending = true; updateStart();
    feedback.textContent = 'Enviando comando para iniciar a tarefa...';
    try {
      await call('sync', {interleavedPlan:plan.value==='interleaved',interleavedTasks,dailyPlan: plan.value === 'daily', autoNavigate, taskName: task.value.trim(), scope: scope.value, selectedSerials: scope.value === 'selected' ? [...selectedSerials] : [], manageRam: autoNavigate, repeat: repeat.value === 'repeat', simultaneous: !autoNavigate || simultaneousMode.value === 'auto' ? null : Number(simultaneous.value), randomizePhones: true, usageSince: null});
      feedback.textContent = 'Comando recebido. Preparando os celulares...';
      await refresh();
    } catch (error) {
      feedback.textContent = notice = error.message;
    } finally { pending = false; updateStart(); }
  };
  document.getElementById('cancel').textContent = 'Encerrar agora e salvar';
  const originalRender = render;
  render = state => {
    originalRender(state);
    latestState = state;
    supportsLoop = state.automationVersion >= 4;
    drawParticipants(state);
    drawVideo(state);
    document.getElementById('supervisor-status').textContent=state.supervisorStage?`${state.supervisorStage}${state.supervisorAttempts?' • '+state.supervisorAttempts+' tentativa(s) de recuperação':''}`:'Ativa ao iniciar • vídeos sem confirmação são preservados, sem descarte automático.';
    const capacity = state.capacity;
    document.getElementById('automation-ram-live').textContent = !capacity ? 'Abra o painel atualizado para ver a RAM.' : capacity.error || `RAM livre: ${(capacity.freeBytes/1073741824).toFixed(1)} GiB de ${(capacity.totalBytes/1073741824).toFixed(1)} GiB • Pode iniciar mais ${capacity.additional} celular(es) • Total estimado: ${capacity.estimatedTotal} simultâneos${capacity.lowMemory ? ' • Pouca memória disponível.' : ''}`;
    const active = state.busy && state.operation === 'sync';
    const daily = plan.value !== 'single';
    if(dailyDescription)dailyDescription.hidden=plan.value!=='daily';
    document.getElementById('automation-loop-help').hidden=plan.value==='interleaved';
    task.hidden=plan.value!=='single';
    document.querySelector('label[for="automation-task"]').hidden=plan.value!=='single';
    interleavedBox.hidden=plan.value!=='interleaved';drawCatalog(state);
    const phoneLabel = name => (state.phones || []).find(p => p.avd === name || p.serial === name)?.name || name;
    const nextTaskStatus=document.getElementById('automation-next-task-status');
    const deferred=Array.isArray(state.planDeferredPhones)?state.planDeferredPhones:[];
    const failed=Array.isArray(state.planLastFailed)?state.planLastFailed:[];
    const saved=Array.isArray(state.planLastSaved)?state.planLastSaved:[];
    nextTaskStatus.hidden=state.planMode!=='interleaved' || (plan.value!=='interleaved' && !state.planActive) || (!deferred.length && !failed.length && !state.planContinuingAfterFailure);
    const continuation=[];
    if(state.planContinuingAfterFailure)continuation.push('O grupo segue para a próxima tarefa; os aparelhos disponíveis entram juntos.');
    if(deferred.length)continuation.push(`Aguardando nova tentativa na próxima tarefa: ${deferred.map(phone=>`${phone.name || phoneLabel(phone.serial)}${phone.reason ? ' — '+panelMessage(phone.reason) : ''}`).join('; ')}. Capturas pendentes são preservadas, sem parar os outros aparelhos.`);
    if(saved.length)continuation.push(`Salvos na última rodada: ${saved.map(phoneLabel).join(', ')}.`);
    if(failed.length)continuation.push(`Falharam na última rodada: ${failed.map(phoneLabel).join(', ')}.`);
    nextTaskStatus.textContent=nextTaskStatus.hidden?'':continuation.join(' ');
    document.getElementById('automation-queue-status').textContent = state.queueBatch ? `Rodada ${state.queueBatch} • ${state.queueSaved?.length || 0} salvo(s) • Aguardando: ${(state.queuePending || []).map(phoneLabel).join(', ') || 'ninguém'}${state.queueFreeGiB != null ? ' • RAM livre ao iniciar: ' + state.queueFreeGiB.toFixed(1) + ' GiB' : ''}${state.queueSkipped?.length ? ' • Sem saldo diário: ' + state.queueSkipped.map(phoneLabel).join(', ') : ''}` : '';
    document.getElementById('loop-stop-after').disabled = !active || !(state.planActive || state.loopActive || state.queueActive) || state.loopStopping;
    document.getElementById('automation-loop-status').textContent = !supportsLoop ? 'Reinicie o painel para ativar o loop contínuo.' : state.loopActive ? `Loop: rodada ${state.loopCycle || 1} • ${state.loopCompleted || 0} rodada(s) salva(s)${state.loopStopping ? ' • Parando após esta rodada' : ''}` : state.loopCompleted ? `${state.loopCompleted} rodada(s) salva(s) na última execução.` : '';
    connected = true; updateStart();
    feedback.textContent = pending ? 'Enviando comando para iniciar a tarefa...' : state.busy ? (panelMessage(state.message) || 'Operação em andamento. Aguarde.') : notice || (!state.automationVersion || !state.sharedCameraVersion ? 'Reabra o painel atualizado para iniciar.' : state.operation === 'sync' ? panelMessage(state.message) : 'Pronto para iniciar. Confira a tarefa e o vídeo.');
    if (!state.busy && mode.value !== 'ready' && simultaneousMode.value !== 'auto' && simultaneous.value === '2' && !(state.queueVersion >= 2)) feedback.textContent = 'Reabra o painel atualizado para iniciar com dois celulares. Esta execução ainda usa a fila antiga.';
    if (!state.busy && plan.value === 'daily' && !state.dailyPlanVersion) feedback.textContent = 'Reabra o painel atualizado para usar o plano diário com os vídeos corretos.';
    if (!state.busy && plan.value === 'interleaved' && !state.interleavedPlanVersion) feedback.textContent = 'Reabra o painel atualizado para usar o plano intercalado.';
    if (!state.busy && validationMessage()) feedback.textContent = validationMessage();
    if (state.planActive) document.getElementById('automation-loop-status').textContent = `${state.planMode==='interleaved'?'Plano intercalado • rodada':'Plano diário • etapa'} ${state.planStep}${state.planMode==='interleaved'?'':'/3'} • ${state.planTask || 'Preparando'} • Vídeo: ${state.planVideo || 'Conferindo fontes'}${state.planMode==='interleaved' && state.planVideoIndex && state.planVideoCount ? ` • Vídeo ${state.planVideoIndex} de ${state.planVideoCount} desta tarefa` : ''}`;
    document.getElementById('cancel').disabled = !active;
    document.querySelector('#view-automation .ready-badge').textContent = active ? 'EM ANDAMENTO' : 'AGUARDANDO INÍCIO';
    document.getElementById('automation-message').textContent = state.automationVersion ? (state.operation === 'sync' ? panelMessage(state.message) : 'Gravações menores que 1 minuto não podem ser salvas pelo Minute.') : 'Reinicie o painel para carregar a nova automação.';
    const rows = Object.entries(state.automation || {});
    document.getElementById('automation-rows').innerHTML = rows.map(([serial, row]) => {
      const phone = (state.phones || []).find(p => p.serial === serial);
      return `<div class="automation-device ${row.error ? 'error' : ''}"><header><strong>${esc(phone?.name || row.name)}</strong><span>${esc(row.stage)}</span></header><small>${esc(row.video || '')} ${row.task ? ' • ' + esc(row.task) : ''}</small><span>${duration(row.elapsed)} / ${duration(row.total)} • ${row.percent || 0}%</span>${row.error ? `<p>${esc(panelMessage(row.error))}</p>` : ''}<div class="progress"><span style="width:${row.percent || 0}%"></span></div></div>`;
    }).join('') || '<p>O resultado de cada celular aparecerá aqui.</p>';
    if (state.operation !== 'sync') {
      document.getElementById('syncbar').style.width = '0%';
      document.getElementById('timer-percent').textContent = '0%';
    }
  };
})();
