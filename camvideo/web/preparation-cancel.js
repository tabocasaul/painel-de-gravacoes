(() => {
  const kinds=['background','foreground'];
  const buttons=Object.fromEntries(kinds.map(kind=>[kind,document.getElementById(`${kind}-cancel-preparation`)]));
  const feedback=Object.fromEntries(kinds.map(kind=>[kind,document.getElementById(`${kind}-cancel-feedback`)]));
  const requests={background:null,foreground:null};
  const uploads={background:false,foreground:false};
  let latestState=app.state || {}, connected=true;
  const jobFor=kind=>latestState[kind==='background'?'backgroundVideo':'foregroundPreparation'] || {};
  const terminal=job=>['error','cancelled'].includes(job.status);
  const text=(element,value)=>{if(element && element.textContent!==value)element.textContent=value;};
  function update(state=latestState,uploadState={}){
    latestState=state || {};Object.assign(uploads,uploadState);
    for(const kind of kinds){
      const button=buttons[kind],message=feedback[kind];if(!button)continue;
      const job=jobFor(kind),current=requests[kind];
      const request=current?.jobId===job.jobId?current:null;
      if(request?.accepted && request.mode==='cancel' && !job.busy && ['idle','completed','cancelled','error'].includes(job.status))requests[kind]=null;
      const waiting=requests[kind]?.jobId===job.jobId?requests[kind]:null;
      const anotherForegroundOperation=kind==='foreground' && terminal(job) && !!latestState.busy && !job.busy;
      const visible=!!job.jobId && !anotherForegroundOperation && !uploads[kind] && (!!job.canCancel || (!!job.busy && !!job.cancelRequested) || job.status==='cancelling');
      button.hidden=!visible;
      const cancelling=(!terminal(job) && !!job.cancelRequested && !!job.busy) || job.status==='cancelling' || !!waiting?.sending || !!waiting?.accepted;
      button.disabled=!visible || !connected || !(latestState.preparationCancellationVersion>=1) || !job.canCancel || cancelling;
      const clear=terminal(job), label=clear?(job.status==='error'?'Limpar falha':'Limpar aviso'):'Cancelar';
      text(button,cancelling?(clear?'Limpando...':'Cancelando...'):label);
      button.dataset.jobId=job.jobId || '';
      button.title=`${clear?'Limpar o aviso da preparação de':'Cancelar a preparação de'} ${job.name || 'este vídeo'}${clear?'. Não reinicia a preparação.':''}`;
      button.setAttribute('aria-label',`${label} preparação de ${job.name || 'este vídeo'}`);
      let description='';
      if(visible && !connected)description='Sem conexão. Aguarde o painel voltar para cancelar esta preparação.';
      else if(visible && !(latestState.preparationCancellationVersion>=1))description='Atualize o painel para cancelar a preparação deste vídeo.';
      else if(visible && waiting?.error)description=waiting.error;
      else if(waiting?.sending)description=`Enviando ${clear?'limpeza do aviso':'cancelamento'} de ${waiting.name}...`;
      else if(cancelling && visible)description=`${job.name || 'Vídeo'}: cancelamento solicitado. Aguarde o painel confirmar o encerramento.`;
      else if(clear && visible)description=`Limpa o aviso de ${job.name || 'este vídeo'}. Uma nova tentativa deve ser iniciada manualmente.`;
      if(anotherForegroundOperation)description='';
      text(message,description);
    }
  }
  for(const kind of kinds){
    const button=buttons[kind];if(!button)continue;
    button.onclick=async()=>{
      // Capture the displayed job. The currently selected library file is unrelated.
      const shownId=button.dataset.jobId;
      update();const job=jobFor(kind);
      if(button.disabled || button.hidden || !shownId || job.jobId!==shownId)return;
      const request={jobId:shownId,name:job.name || 'vídeo',mode:terminal(job)?'clear':'cancel',sending:true,accepted:false,error:''};
      requests[kind]=request;update();
      try{
        const result=await call('cancel_preparation',{jobId:request.jobId,kind});
        if(result.jobId!==request.jobId || result.kind!==kind || (!result.cancelRequested && !result.cleared))throw Error('O painel não confirmou o cancelamento desta preparação. Atualize para conferir.');
        request.sending=false;request.accepted=true;update();
        await refresh();
      }catch(failure){request.error=String(failure.message || failure);}
      finally{request.sending=false;update();}
    };
  }
  const style=document.createElement('style');
  style.textContent='.preparation-cancel-actions{display:flex;align-items:center;gap:12px;justify-content:flex-end;flex-wrap:wrap}.preparation-cancel-actions button{padding:7px 12px;font-size:11px;min-height:32px}.preparation-cancel-actions button[hidden]{display:none!important}.preparation-cancel-actions button:disabled{opacity:.55;cursor:not-allowed}#background-cancel-feedback,#foreground-cancel-feedback{font-size:12px;line-height:1.5;overflow-wrap:anywhere}#background-cancel-feedback:empty,#foreground-cancel-feedback:empty{display:none}';
  document.head.append(style);
  window.addEventListener('panel-connection',event=>{connected=!!event.detail.connected;update();});
  window.PreparationCancellation={update};
  update();
})();
