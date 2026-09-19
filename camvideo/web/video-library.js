(() => {
  const dialog=document.createElement('dialog');
  dialog.id='video-library-dialog';
  dialog.className='video-library-dialog';
  dialog.setAttribute('aria-labelledby','video-library-title');
  dialog.innerHTML=`<form id="video-library-form"><h2 id="video-library-title"></h2><p id="video-library-filename"></p><div id="video-library-rename-fields"><label for="video-library-name">Novo nome, sem a extensão</label><div class="video-library-name-row"><input id="video-library-name" autocomplete="off" maxlength="200" required><span id="video-library-extension"></span></div></div><p id="video-library-explanation"></p><p id="video-library-feedback" role="status" aria-live="polite"></p><div class="video-library-dialog-actions"><button type="button" class="button button-secondary" id="video-library-cancel">Cancelar</button><button type="submit" class="button button-primary" id="video-library-confirm"></button></div></form>`;
  document.body.append(dialog);
  const style=document.createElement('style');
  style.textContent='.video-card{grid-template-columns:100px minmax(0,1fr) auto}.video-library-actions{display:flex;gap:5px;align-items:center}.video-library-action{width:30px;height:32px;display:grid;place-items:center;border:1px solid #334155;border-radius:7px;background:#141c2b;color:#cbd5e1;cursor:pointer}.video-library-action svg{width:15px;height:15px}.video-library-action:hover{border-color:#6687ff;color:white}.video-library-action[data-video-library-action="delete"]:hover{color:#ff879d;border-color:#ff879d}.video-library-action:disabled{opacity:.4;cursor:not-allowed}.video-library-dialog{width:min(520px,calc(100vw - 32px));padding:24px;border:1px solid #334155;border-radius:15px;background:#101827;color:#e2e8f0}.video-library-dialog::backdrop{background:#020617bb}.video-library-dialog h2{font-size:20px;margin:0 0 14px}.video-library-dialog p{font-size:13px;line-height:1.55;overflow-wrap:anywhere}.video-library-dialog label{display:block;font-size:13px;margin-bottom:8px}.video-library-name-row{display:flex;align-items:center;gap:10px}.video-library-name-row input{min-width:0;flex:1;padding:11px;border:1px solid #475569;border-radius:8px;background:#0b111b;color:#f8fafc}.video-library-name-row span{color:#94a3b8}.video-library-dialog-actions{display:flex;justify-content:flex-end;gap:10px;margin-top:20px}.video-library-dialog [hidden]{display:none!important}.video-library-dialog :disabled{opacity:.5;cursor:not-allowed}#video-library-filename{font-weight:600}#video-library-feedback{color:#fbbf24}@media(max-width:600px){.video-card{grid-template-columns:75px minmax(0,1fr) auto}.video-library-actions{flex-direction:column}}';
  document.head.append(style);
  const get=id=>document.getElementById(id);
  const input=get('video-library-name'), confirm=get('video-library-confirm'), cancel=get('video-library-cancel'), feedback=get('video-library-feedback');
  let operation=null, pending=false, connected=true, error='';
  const busy=()=>!!app.state?.busy || !!app.state?.backgroundVideo?.busy || !!app.state?.videoLibraryBusy;
  function unavailable(){
    if(!connected)return 'Sem conexão. Aguarde o painel voltar antes de alterar arquivos.';
    if(!(app.state?.videoLibraryVersion>=1))return 'Atualize o painel para renomear ou excluir vídeos.';
    if(pending)return 'Aguarde a alteração terminar.';
    if(busy())return 'Aguarde a operação ou a preparação do vídeo terminar.';
    return '';
  }
  function candidate(){
    let base=input.value.trim();
    if(operation?.extension && base.toLocaleLowerCase('pt-BR').endsWith(operation.extension.toLocaleLowerCase('pt-BR')))base=base.slice(0,-operation.extension.length).trim();
    return base ? base+operation.extension : '';
  }
  function nameError(){
    if(operation?.kind!=='rename')return '';
    const value=candidate();
    if(!value)return 'Informe o novo nome do vídeo.';
    if(/[<>:"/\\|?*\u0000-\u001f]/.test(value))return 'Use um nome de arquivo sem barras ou caracteres especiais do Windows.';
    if(value===operation.name)return 'Digite um nome diferente do atual.';
    return '';
  }
  function update(){
    const blocked=unavailable();
    document.querySelectorAll('.video-library-action').forEach(button=>button.disabled=!!blocked);
    if(!operation)return;
    input.disabled=pending || busy() || !connected;
    cancel.disabled=pending;
    const missing=!(app.state.videos||[]).some(video=>video.name===operation.name);
    const invalid=missing?'Este vídeo não está mais na biblioteca. Feche esta janela e confira a lista.':nameError();
    confirm.disabled=!!blocked || !!invalid;
    confirm.textContent=pending ? (operation.kind==='rename'?'Renomeando...':'Enviando para a Lixeira...') : operation.kind==='rename'?'Renomear':'Excluir para a Lixeira';
    feedback.textContent=error || blocked || invalid;
  }
  function open(kind,name){
    if(!['rename','delete'].includes(kind) || unavailable() || !(app.state.videos||[]).some(video=>video.name===name))return;
    const dot=name.lastIndexOf('.'), extension=dot>0?name.slice(dot):'';
    operation={kind,name,extension};error='';
    get('video-library-title').textContent=kind==='rename'?'Renomear vídeo':'Excluir vídeo';
    get('video-library-filename').textContent=name;
    get('video-library-rename-fields').hidden=kind!=='rename';
    input.required=kind==='rename';input.value=extension?name.slice(0,-extension.length):name;
    get('video-library-extension').textContent=extension;
    get('video-library-explanation').textContent=kind==='rename'?`A extensão ${extension || 'do arquivo'} será mantida. As tarefas que usam este vídeo acompanharão o novo nome.`:'Este arquivo será enviado para a Lixeira do Windows. As tarefas que usam este vídeo mostrarão que ele está indisponível. O material já preparado será preservado.';
    update();dialog.showModal();if(kind==='rename'){input.focus();input.select();}else cancel.focus();
  }
  function close(){if(pending)return;dialog.close();operation=null;error='';}
  cancel.onclick=close;
  dialog.addEventListener('cancel',event=>{if(pending)event.preventDefault();else{operation=null;error='';}});
  input.oninput=()=>{error='';update();};
  function renameSavedReferences(oldName,name){
    try {
      const saved=JSON.parse(localStorage.getItem('interleaved-task-videos')||'{}');
      if(!saved || typeof saved!=='object' || Array.isArray(saved))return;
      for(const [task,values] of Object.entries(saved))saved[task]=Array.isArray(values)?values.map(video=>video===oldName?name:video):values===oldName?name:values;
      localStorage.setItem('interleaved-task-videos',JSON.stringify(saved));
    } catch {}
  }
  get('video-library-form').onsubmit=async event=>{
    event.preventDefault();
    if(!operation)return;
    update();if(confirm.disabled)return;
    const current={...operation}, name=current.kind==='rename'?candidate():null;
    pending=true;error='';update();
    const releasedPreview=app.video===current.name;
    try {
      if(releasedPreview){
        const player=get('preview');player.pause();player.removeAttribute('src');player.load();app.preview='';
      }
      const result=await call(current.kind==='rename'?'rename_video':'delete_video',current.kind==='rename'?{video:current.name,name}:{video:current.name});
      if(current.kind==='rename'){
        const renamed=result.name, oldName=result.oldName || current.name;
        if(!renamed)throw Error('O painel não confirmou o novo nome. Atualize a biblioteca para conferir.');
        if(app.video===oldName)app.video=renamed;
        app.state={...app.state,videos:(app.state.videos||[]).map(video=>video.name===oldName?{...video,name:renamed}:video)};
        renameSavedReferences(oldName,renamed);
        window.dispatchEvent(new CustomEvent('video-library-renamed',{detail:{oldName,name:renamed}}));
        localStorage.setItem('video-library-last-rename',JSON.stringify({oldName,name:renamed,at:Date.now()}));
        toast('Vídeo renomeado');
      }else{
        if(!result.deleted)throw Error('O painel não confirmou a exclusão. Atualize a biblioteca para conferir.');
        app.state={...app.state,videos:(app.state.videos||[]).filter(video=>video.name!==current.name)};
        if(app.video===current.name)app.video='';
        toast('Vídeo enviado para a Lixeira');
      }
      app.videoHash='';app.preview='';
      pending=false;close();renderVideos(app.state.videos||[]);
      await refresh();
    }catch(failure){error=panelMessage(failure.message || failure);}
    finally{pending=false;if(releasedPreview){app.preview='';renderVideos(app.state.videos||[]);}update();}
  };
  window.addEventListener('panel-connection',event=>{connected=!!event.detail.connected;update();});
  window.addEventListener('storage',event=>{
    if(event.key!=='video-library-last-rename' || !event.newValue)return;
    try{
      const {oldName,name}=JSON.parse(event.newValue);
      if(typeof oldName!=='string' || typeof name!=='string' || !oldName || !name || oldName===name)return;
      if(app.video===oldName)app.video=name;
      app.state={...app.state,videos:(app.state.videos||[]).map(video=>video.name===oldName?{...video,name}:video)};
      app.videoHash='';app.preview='';renderVideos(app.state.videos||[]);
    }catch{}
  });
  window.VideoLibrary={open,update};
  update();
})();
