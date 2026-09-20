(() => {
  const card=document.createElement('article');
  card.className='panel';card.style.cssText='padding:24px;margin-bottom:24px';
  card.innerHTML=`<div class="panel-heading"><div><span class="eyebrow">ESCOLHA ONDE SALVAR</span><h2>Armazenamento dos vídeos</h2></div></div>
  <p>Escolha os destinos das próximas importações e preparações. Os vídeos anteriores continuam na biblioteca, nas pastas onde já estão.</p>
  <form id="storage-form"><div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:18px;margin:16px 0">
  <div><label for="storage-upload-drive">Disco para vídeos originais</label><select id="storage-upload-drive" style="width:100%;margin:8px 0"></select><label for="storage-upload-path">Pasta de importação</label><input id="storage-upload-path" type="text" required style="width:100%;margin-top:8px" autocomplete="off"><small id="storage-upload-info"></small></div>
  <div><label for="storage-cache-drive">Disco para vídeos preparados</label><select id="storage-cache-drive" style="width:100%;margin:8px 0"></select><label for="storage-cache-path">Pasta de preparação</label><input id="storage-cache-path" type="text" style="width:100%;margin-top:8px" placeholder="Vazio: usar as pastas padrão" autocomplete="off"><small id="storage-cache-info"></small></div>
  </div><p style="font-size:13px">Para vários aparelhos, prefira um SSD para os preparados. Deixe espaço livre para o Windows. Você pode escolher outra pasta digitando o caminho completo acima.</p>
  <button id="storage-save" type="submit" class="button button-primary">Salvar pastas</button><p id="storage-status" role="status" aria-live="polite"></p></form>`;
  const heading=document.querySelector('#view-videos .page-heading');
  if(heading)heading.after(card);else document.querySelector('.video-layout').before(card);
  const get=id=>document.getElementById(id);
  let dirty=false,saving=false,last={},driveKey='';
  const human=bytes=>bytes==null?'disponibilidade não confirmada':`${(bytes/1024**3).toLocaleString('pt-BR',{maximumFractionDigits:1})} GiB livres`;
  function options(drives){
    const key=JSON.stringify(drives.map(d=>[d.path,human(d.freeBytes)]));if(key===driveKey)return;driveKey=key;
    for(const kind of ['upload','cache']){
      const select=get(`storage-${kind}-drive`);const selected=select.value;select.replaceChildren();
      const first=document.createElement('option');first.value='';first.textContent='Escolher disco / pasta personalizada';select.append(first);
      for(const drive of drives){const option=document.createElement('option');option.value=drive.path;option.textContent=`${drive.path} — ${human(drive.freeBytes)}`;select.append(option)}select.value=selected;
    }
  }
  function update(state){
    const enabled=!!state.videoStorageVersion;last=state.videoStorage||{};options(last.drives||[]);
    for(const id of ['storage-upload-drive','storage-cache-drive','storage-upload-path','storage-cache-path','storage-save'])get(id).disabled=!enabled||saving;
    if(!enabled){get('storage-status').textContent='Esta opção será ativada ao abrir a versão atualizada do painel após encerrar a automação.';return}
    if(get('storage-status').textContent.startsWith('Esta opção será ativada'))get('storage-status').textContent='';
    if(!dirty&&!saving){get('storage-upload-path').value=last.upload?.path||'';get('storage-cache-path').value=last.cache?.path||''}
    get('storage-upload-info').textContent=last.upload?`Atual: ${last.upload.realPath} • ${human(last.upload.freeBytes)}`:'';
    get('storage-cache-info').textContent=last.cache?`Atual: ${last.cache.realPath} • ${human(last.cache.freeBytes)}`:`Padrão: ${(last.defaultCaches||[]).map(p=>`${p.realPath} (${human(p.freeBytes)})`).join(' / ')}`;
    if(last.error)get('storage-status').textContent=last.error;
  }
  for(const kind of ['upload','cache']){
    get(`storage-${kind}-path`).oninput=()=>{dirty=true};
    get(`storage-${kind}-drive`).onchange=event=>{
      const drive=(last.drives||[]).find(d=>d.path===event.target.value);if(!drive)return;
      get(`storage-${kind}-path`).value=drive[kind==='upload'?'uploadPath':'cachePath'];dirty=true;
      get('storage-status').textContent='Clique em Salvar pastas para aplicar aos próximos arquivos.';
    };
  }
  get('storage-form').onsubmit=async event=>{
    event.preventDefault();if(saving||!app.state.videoStorageVersion)return;
    saving=true;update(app.state);get('storage-status').textContent='Salvando pastas…';
    try{
      await call('configure_video_storage',{uploadPath:get('storage-upload-path').value.trim(),cachePath:get('storage-cache-path').value.trim()});
      dirty=false;get('storage-status').textContent='Pastas salvas. Valem para os próximos arquivos. Nenhum vídeo anterior foi movido.';
    }catch(error){get('storage-status').textContent=error.message}
    finally{saving=false;await refresh();update(app.state)}
  };
  const previous=render;render=state=>{previous(state);update(state)};update(app.state||{});
})();
