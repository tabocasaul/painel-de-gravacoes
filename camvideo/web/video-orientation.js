(() => {
  const button=document.createElement('button');
  button.className='button button-secondary';button.type='button';button.textContent='↻ Girar vídeo';
  document.getElementById('preview-name').parentElement.append(button);
  const dialog=document.createElement('dialog');dialog.className='video-library-dialog';
  dialog.innerHTML='<h2>Girar vídeo</h2><p class="filename"></p><canvas width="640" height="360" style="width:100%;background:#080b12"></canvas><label>Posição<select><option value="90">↻ 90° para a direita</option><option value="-90">↺ 90° para a esquerda</option><option value="180">180° — virar de cabeça para baixo</option></select></label><p>Salva uma cópia na pasta de importação, mantendo o original. Depois, selecione a cópia e prepare nas câmeras. Funciona neste computador, sem tokens.</p><p class="feedback" role="status"></p><div class="video-library-dialog-actions"><button type="button" class="button button-secondary close">Fechar</button><button type="button" class="button button-primary save">Salvar cópia girada</button></div>';
  document.body.append(dialog);
  const select=dialog.querySelector('select'),save=dialog.querySelector('.save'),close=dialog.querySelector('.close'),feedback=dialog.querySelector('.feedback'),canvas=dialog.querySelector('canvas');
  let name='',pending=false,connected=false,img=null;
  function update(){button.disabled=pending||!connected||!app.video||!app.state?.videoOrientationVersion||!!app.state?.busy||!!app.state?.videoLibraryBusy;button.title=!app.state?.videoOrientationVersion?'Reabra o painel para carregar a opção de girar':'Girar uma cópia do vídeo selecionado';}
  function draw(){if(!img?.naturalWidth)return;const ctx=canvas.getContext('2d'),angle=Number(select.value),quarter=Math.abs(angle)===90;ctx.clearRect(0,0,640,360);const factor=Math.min(640/(quarter?img.naturalHeight:img.naturalWidth),360/(quarter?img.naturalWidth:img.naturalHeight));ctx.save();ctx.translate(320,180);ctx.rotate(angle*Math.PI/180);ctx.drawImage(img,-img.naturalWidth*factor/2,-img.naturalHeight*factor/2,img.naturalWidth*factor,img.naturalHeight*factor);ctx.restore();}
  button.onclick=()=>{update();if(button.disabled)return;name=app.video;dialog.querySelector('.filename').textContent=name;feedback.textContent='';img=new Image();img.onload=draw;img.src=(app.state.videos||[]).find(v=>v.name===name).thumb+'&orientation='+Date.now();dialog.showModal();};
  select.onchange=draw;close.onclick=()=>{if(!pending)dialog.close();};dialog.oncancel=e=>{if(pending)e.preventDefault();};
  save.onclick=async()=>{if(pending)return;pending=true;save.disabled=close.disabled=select.disabled=true;save.textContent='Girando…';feedback.textContent='Salvando a cópia. Aguarde a confirmação.';update();
    try{const response=await fetch('/api/action',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:'rotate_video',video:name,degrees:Number(select.value)})});const result=await response.json();if(!response.ok)throw Error(result.error||'Não foi possível girar.');if(!result.rotated)throw Error('O painel não confirmou a cópia.');app.video=result.name;app.videoHash='';app.preview='';await refresh();feedback.textContent='Cópia salva: '+result.name+'. Aguarde a prévia terminar e prepare esta cópia nas câmeras.';toast('Cópia girada salva');}
    catch(error){feedback.textContent=error.message||'Sem confirmação. Confira a biblioteca antes de tentar novamente.';}
    finally{pending=false;save.disabled=close.disabled=select.disabled=false;save.textContent='Salvar cópia girada';update();}
  };
  window.addEventListener('panel-connection',event=>{connected=!!event.detail.connected;update();});update();
})();
