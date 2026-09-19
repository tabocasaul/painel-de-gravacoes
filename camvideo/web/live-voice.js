(() => {
  const panel = document.createElement('article');
  panel.className = 'panel';
  panel.style.marginBottom = '20px';
  panel.innerHTML = `<div class="panel-heading"><div><span class="eyebrow">APRESENTAÇÃO DO PRODUTO</span><h2>Falas contínuas com IA</h2></div><span id="live-key-state" class="tiktok-status">Verificando chave</span></div>
    <p class="tiktok-note">A OpenAI escreve os roteiros com os dados abaixo. O OmniVoice gera a voz no PC. Cada fala tem aproximadamente um minuto; duas ficam prontas antes da reprodução começar.</p>
    <details class="voice-help"><summary>Configurar chave da OpenAI</summary><form id="live-key-form" class="tiktok-form"><label for="live-key">Chave da API</label><input id="live-key" type="password" autocomplete="off" spellcheck="false" maxlength="512" placeholder="Cole sua chave"><button class="button button-secondary">Salvar chave protegida</button><p class="tiktok-note">Armazenada com proteção do Windows. Os roteiros consomem créditos da sua API; o áudio é local.</p></form></details>
    <form id="live-product-form" class="tiktok-form" style="margin-top:16px"><label for="live-name">Nome do produto</label><input id="live-name" maxlength="120" required placeholder="Nome exato do produto">
    <label for="live-features">Características e informações confirmadas</label><textarea id="live-features" rows="5" maxlength="3000" required placeholder="Materiais, medidas, funções, modo de uso e outras informações verdadeiras"></textarea>
    <label for="live-offer">Oferta e condições (opcional)</label><textarea id="live-offer" rows="2" maxlength="600" placeholder="Preço, desconto e condições, se existirem"></textarea>
    <div class="tiktok-actions"><button class="button button-secondary">Salvar produto</button><button type="button" id="live-prepare" class="button button-secondary">Gerar amostra de 1 minuto</button></div></form>
    <div class="tiktok-form" style="margin-top:16px"><label for="live-quality">Qualidade da geração</label><select id="live-quality"><option value="32">Original — 32 etapas</option><option value="16">Rápida — 16 etapas</option></select>
    <label for="live-minutes">Duração da sessão</label><select id="live-minutes"><option value="15">15 minutos</option><option value="30">30 minutos</option><option value="60" selected>1 hora</option><option value="120">2 horas</option><option value="0">Até eu parar</option></select>
    <p class="tiktok-note">A sessão usa a saída e o volume escolhidos em “Para onde a voz vai?”. Iniciar autoriza novas chamadas à sua API até o fim da sessão. Confira os dados e ouça a amostra antes.</p>
    <div class="tiktok-actions"><button id="live-start" class="button button-primary">Iniciar falas contínuas</button><button id="live-stop" class="button cancel-button" disabled>Parar sessão</button><button id="live-unload" class="button button-secondary">Liberar memória da voz</button></div>
    <p id="live-status" class="tiktok-note" role="status"></p><p id="live-counts" class="tiktok-note"></p>
    <details class="voice-help"><summary>Último roteiro gerado</summary><p id="live-script" style="white-space:pre-wrap"></p></details></div>`;
  $('view-tiktok').querySelector('.voice-studio').prepend(panel);
  const demo = document.createElement('article');
  demo.className = 'panel'; demo.style.marginBottom = '20px';
  demo.innerHTML = `<div class="panel-heading"><div><span class="eyebrow">SIMULAÇÃO · NOMES FICTÍCIOS</span><h2>Teste do sininho de venda</h2></div></div><p class="tiktok-note">Prévia com sininho e agradecimento. A própria voz anuncia que é uma simulação. Clique para gerar e depois ouça no player.</p><button id="sale-demo-generate" class="button button-secondary">Gerar simulação de venda</button><p id="sale-demo-status" class="tiktok-note" role="status">Nenhuma simulação gerada.</p><audio id="sale-demo-audio" controls hidden aria-label="Ouvir simulação de venda"></audio>`;
  panel.after(demo);
  const stockCard = document.createElement('article');
  stockCard.className = 'panel'; stockCard.style.marginBottom = '20px';
  stockCard.innerHTML = `<div class="panel-heading"><div><span class="eyebrow">OFERTA · QUANTIDADE REAL</span><h2>Unidades no valor promocional</h2></div></div><p class="tiktok-note">Informe quantas unidades do produto acima ainda têm o valor promocional. A quantidade entra nos roteiros da amostra e das falas contínuas. Atualize manualmente conforme as vendas; não há baixa automática.</p><form id="stock-form" class="tiktok-form"><label for="stock-remaining">Unidades restantes</label><input id="stock-remaining" type="number" min="0" max="1000000" step="1" required placeholder="Ex.: 12"><div class="tiktok-actions"><button class="button button-primary">Atualizar quantidade nos áudios</button><button id="stock-disable" type="button" class="button button-secondary">Não mencionar estoque</button></div></form><p id="stock-status" class="tiktok-note" role="status"></p><p id="stock-current" class="tiktok-note"></p><p class="tiktok-note">A atualização interrompe a reprodução e renova as falas pendentes; pode haver uma pausa. Zero encerra a sessão. A configuração vale para o nome de produto informado e é reiniciada ao fechar o servidor. Áudios já salvos na biblioteca não são reescritos.</p>`;
  panel.after(stockCard);
  async function saveStock(remaining) {
    try {
      await act('stock_update', {product:$('live-name').value.trim(), remaining});
      $('stock-status').textContent = remaining === null ? 'Menção ao estoque desativada.' : remaining === 0 ? 'Estoque zerado. A sessão foi interrompida; atualize antes de reiniciar.' : 'Quantidade atualizada. Os próximos roteiros usarão esse estoque.';
    } catch(error) { $('stock-status').textContent = error.message; }
  }
  $('stock-form').onsubmit = e => {e.preventDefault(); saveStock(Number($('stock-remaining').value));};
  $('stock-disable').onclick = () => saveStock(null);
  let stockLoaded = false;
  window.addEventListener('voice-state', e => {
    const value = e.detail.live?.stock;
    if (!value) return;
    if (!stockLoaded) {stockLoaded=true; $('stock-remaining').value=value.remaining ?? '';}
    $('stock-current').textContent = value.remaining === null ? 'Sem menção de quantidade nos roteiros.' : `${value.product}: ${value.remaining} unidade(s) no valor promocional.`;
  });
  const sales = document.createElement('article');
  sales.className = 'panel'; sales.style.marginBottom = '20px';
  sales.innerHTML = `<div class="panel-heading"><div><span class="eyebrow">🔔 VENDAS CONFIRMADAS</span><h2>Sininho e agradecimentos</h2></div></div><p class="tiktok-note">Durante as falas contínuas, registre cada compra concluída. O painel sorteia a espera e anuncia a venda entre as falas, com sininho e agradecimento ao nome real informado. Sem pedidos na fila, nenhum aviso é criado.</p><form id="sales-timing-form" class="tiktok-form"><label for="sales-min">Intervalo mínimo (segundos)</label><input id="sales-min" type="number" min="10" max="3600" value="30" required><label for="sales-max">Intervalo máximo (segundos)</label><input id="sales-max" type="number" min="10" max="3600" value="90" required><button class="button button-secondary">Salvar intervalos</button></form><form id="sales-order-form" class="tiktok-form" style="margin-top:16px"><label for="sales-order">Pedidos e nomes reais — um por linha</label><textarea id="sales-order" rows="6" maxlength="7000" required placeholder="PED-1042; Ana&#10;PED-1043; Gabriel&#10;PED-1044; Mariana"></textarea><p class="tiktok-note">Formato: código do pedido; nome real do comprador para o agradecimento. Use somente o nome que pode ser anunciado na live. Envie até 50 linhas por vez e acrescente mais lotes durante a reprodução; até 1000 pendentes.</p><label><input id="sales-confirmed" type="checkbox" required> Confirmo que todas estas compras foram concluídas</label><button id="sales-add" class="button button-primary">Adicionar vendas à fila</button></form><p id="sales-status" class="tiktok-note" role="status"></p><p id="sales-counts" class="tiktok-note"></p><p class="tiktok-note">A espera pode aumentar enquanto uma fala termina. Parar a sessão cancela os avisos pendentes. Pedidos são lembrados apenas nesta execução; não registre novamente uma venda já anunciada.</p>`;
  demo.before(sales);
  $('sales-timing-form').onsubmit = async e => {
    e.preventDefault();
    try { await act('sales_config', {minimum:Number($('sales-min').value), maximum:Number($('sales-max').value)}); $('sales-status').textContent = 'Intervalos salvos para os próximos sorteios.'; }
    catch(error) { $('sales-status').textContent = error.message; }
  };
  let saleSubmitting = false, salesLoaded = false;
  $('sales-order-form').onsubmit = async e => {
    e.preventDefault(); saleSubmitting = true; $('sales-add').disabled = true;
    try {
      const entries = $('sales-order').value.split(/\r?\n/).map(line => line.trim()).filter(Boolean).map(line => { const separator=line.indexOf(';'); return separator < 0 ? {order:line, name:''} : {order:line.slice(0,separator).trim(), name:line.slice(separator+1).trim()}; });
      const registered = await act('sales_add_batch', {entries, confirmed:$('sales-confirmed').checked});
      $('sales-order-form').reset(); $('sales-status').textContent = `${registered.added} vendas adicionadas à fila. Nomes: ${registered.names.join(", ")}. Você pode adicionar outro lote.`;
    } catch(error) { $('sales-status').textContent = error.message; }
    finally { saleSubmitting = false; }
  };
  window.addEventListener('voice-state', e => {
    const state = e.detail.live, values = state?.sales;
    $('sales-add').disabled = saleSubmitting || !state?.active || !state?.continuous;
    if (!values) return;
    if (!salesLoaded) { salesLoaded=true; $('sales-min').value=values.minimum; $('sales-max').value=values.maximum; }
    $('sales-counts').textContent = `${values.queued} pedidos aguardando preparação · ${values.announced} agradecimentos concluídos` + (state.active && state.continuous ? '' : ' · Inicie as falas contínuas para registrar vendas.');
  });
  let demoId = null, demoSubmitting = false;
  $('sale-demo-generate').onclick = async () => {
    demoSubmitting = true; $('sale-demo-generate').disabled = true;
    $('sale-demo-status').textContent = 'Gerando sininho e voz de demonstração...';
    $('sale-demo-audio').hidden = true;
    try { demoId = (await act('sale_demo')).id; }
    catch (error) { $('sale-demo-status').textContent = error.message; }
    finally { demoSubmitting = false; }
  };
  window.addEventListener('voice-state', e => {
    $('sale-demo-generate').disabled = demoSubmitting || e.detail.generation.busy || !!e.detail.live?.active;
    if (!demoId) return;
    const clip = e.detail.clips.find(item => item.id === demoId);
    if (clip) {
      $('sale-demo-audio').src = clip.url; $('sale-demo-audio').hidden = false;
      $('sale-demo-status').textContent = 'Simulação pronta. Aperte reproduzir para ouvir o sininho e o agradecimento fictício.';
      demoId = null;
    } else if (!e.detail.generation.busy) {
      $('sale-demo-status').textContent = e.detail.generation.message; demoId = null;
    }
  });
  let loaded = false;
  const product = () => ({name:$('live-name').value.trim(), features:$('live-features').value.trim(), offer:$('live-offer').value.trim()});
  async function act(action, data={}) {
    const response = await fetch('/api/voice/action', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({action,...data})});
    const result = await response.json();
    if (!response.ok) throw Error(result.error || 'Não foi possível concluir.');
    return result;
  }
  async function run(action, data={}) {
    try { await act(action,data); } catch(error) { toast(error.message); $('live-status').textContent=error.message; }
  }
  $('live-key-form').onsubmit = async e => {
    e.preventDefault();
    const key=$('live-key').value; $('live-key').value='';
    try { await act('save_openai_key',{key}); toast('Chave salva com proteção do Windows'); }
    catch(error) { toast(error.message); }
  };
  $('live-product-form').onsubmit = async e => { e.preventDefault(); try { await act('save_product',{product:product()}); toast('Produto salvo'); } catch(error) { toast(error.message); } };
  function start(action) {
    if (!$('live-product-form').reportValidity()) return;
    run(action,{product:product(), output:$('voice-output').value, volume:Number($('voice-volume').value)/100,
                minutes:Number($('live-minutes').value), steps:Number($('live-quality').value)});
  }
  $('live-start').onclick=()=>start('live_start'); $('live-prepare').onclick=()=>start('live_prepare');
  $('live-stop').onclick=()=>run('live_stop'); $('live-unload').onclick=()=>run('unload');
  window.addEventListener('voice-state', e => {
    const value=e.detail.live;
    if (!value) { $('live-status').textContent='Abra o painel atualizado para usar as falas contínuas.'; return; }
    if (!loaded) { loaded=true; $('live-name').value=value.product.name; $('live-features').value=value.product.features; $('live-offer').value=value.product.offer; }
    $('live-key-state').textContent=value.apiKeyConfigured ? 'Chave configurada' : 'Configure sua chave';
    $('live-start').disabled=$('live-prepare').disabled=value.active || !value.apiKeyConfigured;
    $('live-stop').disabled=!value.active;
    $('live-unload').disabled=value.active || e.detail.generation.busy || e.detail.playback.busy;
    $('live-status').textContent=value.message;
    $('live-status').classList.toggle('voice-error',!!value.error);
    $('live-counts').textContent=`${value.generated} falas geradas · ${value.queued} na fila · ${value.played} reproduzidas · ${value.requests} chamadas OpenAI · ${value.tokens} tokens · ${e.detail.engineLoaded ? 'Motor de voz em memória' : 'Motor de voz descarregado'}`;
    $('live-script').textContent=value.script || 'Nenhum roteiro ainda.';
  });

  const uploads=document.createElement('article'); uploads.className='panel'; uploads.style.marginBottom='20px';
  uploads.innerHTML=`<div class="panel-heading"><div><span class="eyebrow">VÍDEOS DA LIVE</span><h2>Adicionar demonstrações do produto</h2></div></div><p class="tiktok-note">Envie seus vídeos para a biblioteca e selecione um no rascunho. O envio não altera a câmera nem inicia uma transmissão. Use demonstrações e ângulos diferentes; edições não garantem que o TikTok considere o conteúdo original.</p><div class="tiktok-actions"><button class="button button-secondary" id="live-upload-open">Enviar vídeos</button><input type="file" id="live-video-upload" accept="video/*" multiple hidden><button class="button button-secondary" id="live-upload-cancel" disabled>Cancelar envio</button></div><progress id="live-upload-progress" max="100" value="0" style="width:100%;margin-top:14px"></progress><p class="tiktok-note" id="live-upload-status" role="status">Nenhum envio em andamento.</p>`;
  $('view-tiktok').querySelector('#tiktok-draft').closest('article').before(uploads);
  let xhr=null, cancelled=false;
  $('live-upload-open').onclick=()=>$('live-video-upload').click();
  $('live-upload-cancel').onclick=()=>{cancelled=true; xhr?.abort();};
  $('live-video-upload').onchange=async e=>{
    const files=Array.from(e.target.files); cancelled=false;
    $('live-upload-cancel').disabled=false; e.target.disabled=true;
    try {
      for(const file of files) {
        if(cancelled) break;
        const name=await new Promise((resolve,reject)=>{
          xhr=new XMLHttpRequest(); xhr.open('POST','/api/upload'); xhr.setRequestHeader('X-Filename',encodeURIComponent(file.name));
          xhr.upload.onprogress=event=>{if(event.lengthComputable) $('live-upload-progress').value=event.loaded/event.total*100;};
          xhr.onload=()=>{try {const value=JSON.parse(xhr.responseText); if(xhr.status!==200) throw Error(value.error || 'Falha no envio'); resolve(value.name);}catch(error){reject(error);}};
          xhr.onerror=()=>reject(Error('Erro de conexão durante o envio.')); xhr.onabort=()=>reject(Error('Envio cancelado.'));
          $('live-upload-status').textContent=`Enviando ${file.name}...`; xhr.send(file);
        });
        await refresh(); $('tiktok-video').value=name; $('tiktok-video').dispatchEvent(new Event('change'));
        $('live-upload-status').textContent=`${name} adicionado à biblioteca.`;
      }
    }catch(error){$('live-upload-status').textContent=error.message;}
    finally{xhr=null; e.target.value=''; e.target.disabled=false; $('live-upload-cancel').disabled=true;}
  };
})();
