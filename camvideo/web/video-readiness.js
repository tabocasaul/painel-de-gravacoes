(() => {
  const selected=document.createElement('div');
  selected.id='selected-video-readiness';
  selected.className='video-readiness selected-video-readiness';
  selected.setAttribute('role','status');
  selected.setAttribute('aria-live','polite');
  selected.hidden=true;
  document.querySelector('.player-info').after(selected);
  const legend=document.createElement('p');
  legend.className='video-readiness-legend';
  legend.textContent='Preparado: versão pronta para automação. Câmeras: registros locais; não indica aparelhos ligados.';
  document.getElementById('videos').before(legend);
  const style=document.createElement('style');
  style.textContent='.video-readiness{min-width:0;margin-top:7px;display:grid;justify-items:start;gap:4px}.video-readiness .readiness-badge{display:inline-flex;align-items:center;gap:5px;max-width:100%;margin:0;padding:3px 6px;border-radius:6px;font-size:10px;font-weight:650;line-height:1.35;white-space:normal;overflow-wrap:anywhere;color:#94a3b8;background:#94a3b812}.readiness-dot{display:inline-block;width:6px;height:6px;flex:0 0 6px;border-radius:50%;background:currentColor}.video-readiness .readiness-ready{color:#4ade80;background:#4ade8014}.video-readiness .readiness-missing,.video-readiness .readiness-error{color:#fb7185;background:#fb718514}.video-readiness .readiness-preparing{color:#fbbf24;background:#fbbf2414}.video-readiness .readiness-cameras,.video-readiness .readiness-note{display:block;min-width:0;max-width:100%;font-size:9px;line-height:1.45;color:#94a3b8;overflow-wrap:anywhere}.video-readiness .readiness-note{color:#c5a96e}.selected-video-readiness{margin:0 0 14px;padding:10px 12px;border:1px solid #233149;border-radius:9px;background:#0b111b}.selected-video-readiness .readiness-cameras,.selected-video-readiness .readiness-note{font-size:11px}.selected-video-readiness .readiness-badge{font-size:11px}.selected-video-readiness[hidden]{display:none}.video-readiness-legend{font-size:10px;line-height:1.5;color:#94a3b8;margin:0 0 10px}';
  document.head.append(style);
  let connected=true;
  function readiness(video){
    const preparation=video?.preparation;
    if(!connected || !preparation || typeof preparation.ready!=='boolean')return {state:'unknown',label:'Sem confirmação',title:!connected?'Sem conexão com o painel.':'O painel ainda não informou a preparação deste vídeo.'};
    if(preparation.ready)return {state:'ready',label:'Preparado',title:'Versão sem corte preparada para a automação no computador.'};
    if(preparation.state==='preparing'){
      const progress=Number(preparation.progress);
      return {state:'preparing',label:`Preparando${preparation.preparingCropped?' corte':''}${Number.isFinite(progress)?` ${Math.round(Math.min(100,Math.max(0,progress)))}%`:''}`,title:preparation.preparingCropped?'Preparação com corte em andamento. A automação ainda precisa de uma versão válida sem corte.':'A preparação da versão usada pela automação está em andamento.'};
    }
    if(preparation.state==='error')return {state:'error',label:'Falha no preparo',title:preparation.error || 'Não foi possível preparar a versão da automação.'};
    if(preparation.state==='missing')return {state:'missing',label:'Falta preparar',title:'A automação ainda não reconhece uma preparação válida para este arquivo.'};
    return {state:'unknown',label:'Sem confirmação',title:'O painel ainda não confirmou a preparação deste vídeo.'};
  }
  function cameraSummary(video){
    const cameras=video?.cameras;
    if(!connected || !cameras || !Number.isFinite(cameras.total) || !Number.isFinite(cameras.confirmed))return 'Câmeras: sem confirmação';
    const total=Math.max(0,Math.trunc(cameras.total)),confirmed=Math.min(total,Math.max(0,Math.trunc(cameras.confirmed)));
    const staged=Number.isFinite(cameras.staged)?Math.max(0,Math.trunc(cameras.staged)):0;
    return `Câmeras: ${confirmed}/${total} confirmadas${staged?` • ${staged} aguardam validação`:''}`;
  }
  function draw(target,video){
    if(!target)return;
    const status=readiness(video), cameras=cameraSummary(video);
    const cropped=connected && video?.preparation?.croppedReady && !video.preparation.ready;
    const hash=JSON.stringify([status,cameras,!!cropped]);
    if(target.dataset.readinessHash===hash)return;
    target.dataset.readinessHash=hash;target.dataset.readiness=status.state;
    target.innerHTML=`<span class="readiness-badge readiness-${status.state}" title="${esc(status.title)}"><i class="readiness-dot" aria-hidden="true"></i>${esc(status.label)}</span><small class="readiness-cameras" title="Registros locais do painel; não indicam celulares ligados nem gravação em andamento.">${esc(cameras)}</small>${cropped?'<small class="readiness-note">Com corte; falta versão da automação.</small>':''}`;
  }
  function update(videos=app.state.videos || []){
    const byName=new Map(videos.map(video=>[video.name,video]));
    document.querySelectorAll('.video-card').forEach(card=>draw(card.querySelector('.video-readiness'),byName.get(decodeURIComponent(card.dataset.video))));
    const current=byName.get(app.video);selected.hidden=!current;
    if(current)draw(selected,current);else{selected.innerHTML='';selected.dataset.readinessHash='';}
  }
  window.addEventListener('panel-connection',event=>{connected=!!event.detail.connected;update();});
  window.VideoReadiness={update};
  update();
})();
