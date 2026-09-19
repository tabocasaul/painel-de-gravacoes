(() => {
  const section = $('view-tiktok');
  const studio = document.createElement('div');
  studio.className = 'voice-studio';
  studio.innerHTML = `
    <div class="tiktok-layout">
      <article class="panel"><div class="panel-heading"><div><span class="eyebrow">VOZ LOCAL · PORTUGUÊS BRASILEIRO</span><h2>O que você quer falar?</h2></div><span class="tiktok-status" id="voice-model-status">Verificando</span></div>
        <p class="tiktok-note">Voz feminina do OmniVoice em português. Prepare as falas, ouça e toque quando quiser durante a live.</p>
        <form id="voice-form" class="tiktok-form">
          <label for="voice-text">Texto da fala <span id="voice-count">0 / 2400</span></label>
          <textarea id="voice-text" maxlength="2400" rows="4" required placeholder="Oi, gente! Que bom ter vocês aqui. Me conta de qual cidade você está assistindo!"></textarea>
          <label for="voice-style">Ritmo da fala</label><select id="voice-style"><option value="natural">Natural</option><option value="acolhedora">Um pouco mais calma</option><option value="animada">Um pouco mais rápida</option></select>
          <label for="voice-quality">Geração</label><select id="voice-quality"><option value="32">Qualidade original</option><option value="16">Mais rápida (pode mudar a qualidade)</option></select><div class="tiktok-actions"><button type="submit" id="voice-generate" class="button button-primary" disabled><i data-lucide="audio-lines"></i>Gerar fala</button><button type="button" id="voice-cancel" class="button button-secondary" disabled>Cancelar geração</button></div>
          <p id="voice-generation-status" class="tiktok-note" role="status">Conectando ao motor de voz...</p>
        </form>
      </article>
      <article class="panel"><div class="panel-heading"><div><span class="eyebrow">ÁUDIO DA TRANSMISSÃO</span><h2>Para onde a voz vai?</h2></div></div>
        <div class="tiktok-form"><label for="voice-output">Saída de áudio do Windows</label><select id="voice-output"><option value="">Atualize as saídas de áudio</option></select>
          <label for="voice-volume">Volume <span id="voice-volume-label">80%</span></label><input id="voice-volume" type="range" min="0" max="100" value="80">
          <div class="tiktok-actions"><button type="button" id="voice-outputs" class="button button-secondary">Atualizar saídas</button><button type="button" id="voice-stop" class="button cancel-button" disabled><i data-lucide="square"></i>Parar voz</button></div>
          <p id="voice-route" class="tiktok-note">Escolha uma saída antes de tocar uma fala.</p><p id="voice-playback-status" class="tiktok-note" role="status"></p>
        </div>
        <details class="voice-help"><summary>Conectar o áudio à live</summary><ol><li>Com VB-CABLE instalado, selecione <strong>CABLE Input</strong> como saída da voz aqui.</li><li>No LIVE Studio, selecione <strong>CABLE Output</strong> como microfone. No emulador, use CABLE Output como entrada padrão de gravação do Windows e habilite o microfone do PC abaixo.</li><li>Confira o medidor de áudio e faça uma gravação de teste antes de transmitir.</li></ol><p class="tiktok-note">Uma mesma entrada padrão pode ser captada por vários emuladores. Esta integração não isola o áudio por conta. O som do vídeo não é misturado automaticamente à voz.</p><a href="https://vb-audio.com/Cable/" target="_blank" rel="noopener noreferrer">Baixar VB-CABLE no site oficial</a></details>
      </article>
    </div>
    <article class="panel voice-library"><div class="panel-heading"><div><span class="eyebrow">SUAS FALAS</span><h2>Prontas para tocar</h2></div><span id="voice-library-count">0 falas</span></div><div id="voice-clips"></div></article>
    <article class="panel voice-device"><div class="panel-heading"><div><span class="eyebrow">TIKTOK NO EMULADOR</span><h2>Conectar celular</h2></div></div><p class="tiktok-note">Escolha o celular no rascunho abaixo. A transmissão é iniciada no aplicativo TikTok, após conferir imagem, áudio e conta.</p><div class="tiktok-actions"><button class="button button-secondary" data-tiktok-action="tiktok_check">Verificar TikTok</button><button class="button button-secondary" data-tiktok-action="tiktok_open">Abrir TikTok</button><button class="button button-secondary" data-tiktok-action="tiktok_store">Instalar pela Play Store</button><button class="button button-secondary" data-tiktok-action="microphone_on">Habilitar microfone do PC</button><button class="button button-secondary" data-tiktok-action="microphone_off">Desabilitar microfone</button></div><p id="tiktok-device-status" class="tiktok-note" role="status">Nenhum celular verificado.</p></article>`;
  section.querySelector('.page-heading').after(studio);
  const text = $('voice-text'), output = $('voice-output');
  text.value = localStorage.getItem('emulation-voice-text') || '';
  const updateCount = () => { $('voice-count').textContent = `${text.value.length} / 2400`; };
  updateCount();
  text.addEventListener('input', () => { updateCount(); localStorage.setItem('emulation-voice-text', text.value); });
  let state = null, clipsHash = '', outputsHash = '', polling = false, scanned = false;
  let generationError = '';
  let outputKey = localStorage.getItem('emulation-voice-output') || '';
  async function request(action, data = {}) {
    const response = await fetch('/api/voice/action', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({action, ...data})});
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || 'Não foi possível concluir.');
    return result;
  }
  function route() {
    const selected = state?.outputs.find(item => item.key === output.value);
    $('voice-route').textContent = selected ? selected.virtual
      ? 'Saída virtual selecionada. O aplicativo da live precisa captar a entrada correspondente; confira o medidor de áudio.'
      : 'A voz será reproduzida neste dispositivo. Para chegar ao microfone da live, selecione uma saída virtual.'
      : 'Selecione uma saída de áudio. Nenhum dispositivo será escolhido automaticamente.';
    document.querySelectorAll('[data-voice-play]').forEach(button => { button.disabled = !selected || !!state?.playback.busy; });
  }
  function renderVoice(value) {
    state = value;
    window.dispatchEvent(new CustomEvent('voice-state', {detail:value}));
    $('voice-model-status').textContent = value.installed ? 'Instalada no PC' : 'Instalação pendente';
    $('voice-generate').disabled = !value.installed || value.generation.busy;
    $('voice-cancel').disabled = !value.generation.busy;
    $('voice-stop').disabled = !value.playback.busy;
    $('voice-outputs').disabled = !value.installed || value.scanning;
    $('voice-generation-status').textContent = value.installed ? (generationError || value.generation.message) : 'O motor de voz precisa ser instalado neste PC. Execute setup/INSTALAR-VOZ-LOCAL.ps1.';
    $('voice-generation-status').classList.toggle('voice-error', !!value.generation.error || !!generationError);
    $('voice-playback-status').textContent = value.outputError || value.playback.message;
    $('voice-playback-status').classList.toggle('voice-error', !!value.playback.error || !!value.outputError);
    const oh = JSON.stringify(value.outputs);
    if (oh !== outputsHash) {
      outputsHash = oh;
      output.innerHTML = '<option value="">Selecione uma saída</option>' + value.outputs.map(item => `<option value="${esc(item.key)}">${esc(item.name)}${item.virtual ? ' · Áudio virtual' : ''}</option>`).join('');
      output.value = value.outputs.some(item => item.key === outputKey) ? outputKey : '';
    }
    const hash = JSON.stringify(value.clips);
    if (hash !== clipsHash) {
      clipsHash = hash;
      $('voice-library-count').textContent = `${value.clips.length} fala(s)`;
      $('voice-clips').innerHTML = value.clips.length ? value.clips.map(clip => `<div class="voice-clip"><div><strong>${esc(clip.text)}</strong><small>${esc(clip.model || "Voz local")} · ${esc(clip.style)} · ${Number(clip.duration).toFixed(1)} s · ${esc(clip.voice)}</small></div><audio controls preload="none" src="${esc(clip.url)}" aria-label="Ouvir prévia: ${esc(clip.text)}"></audio><div class="tiktok-actions"><button class="button button-primary" data-voice-play="${esc(clip.id)}" disabled><i data-lucide="play"></i>Tocar na saída</button><a class="button button-secondary" href="${esc(clip.url)}" download="fala-${esc(clip.id)}.wav">Baixar WAV</a></div></div>`).join('') : '<p class="tiktok-note">Suas falas aparecerão aqui depois de geradas. Elas ficam salvas no PC para reutilizar sem gerar novamente.</p>';
      $('voice-clips').querySelectorAll('audio').forEach(player => player.addEventListener('play', () => {
        $('voice-clips').querySelectorAll('audio').forEach(other => { if (other !== player) other.pause(); });
      }));
      icons();
    }
    route();
    if (value.installed && !scanned) { scanned = true; request('outputs').catch(error => toast(error.message)); }
  }
  async function poll() {
    if (polling) return;
    polling = true;
    try {
      const response = await fetch('/api/voice/state', {cache:'no-store'});
      if (!response.ok) throw new Error('Reabra o painel para carregar a integração de voz.');
      renderVoice(await response.json());
    } catch (error) {
      $('voice-generation-status').textContent = error.message;
      $('voice-model-status').textContent = 'Sem conexão';
      $('voice-generate').disabled = true;
    } finally { polling = false; }
  }
  async function actVoice(action, data) {
    try { const result = await request(action, data); if (action === 'generate') generationError = ''; await poll(); return result; }
    catch (error) {
      if (action === 'generate') { generationError = error.message; if (state) renderVoice(state); }
      toast(error.message); return null;
    }
  }
  $('voice-form').addEventListener('submit', async event => {
    event.preventDefault();
    $('voice-generate').disabled = true;
    await actVoice('generate', {text:text.value.trim(), style:$('voice-style').value, steps:Number($('voice-quality').value)});
  });
  $('voice-outputs').onclick = () => actVoice('outputs');
  $('voice-cancel').onclick = () => actVoice(state?.live?.active ? 'live_stop' : 'cancel_generation');
  $('voice-stop').onclick = () => actVoice(state?.live?.active ? 'live_stop' : 'stop');
  $('voice-volume').oninput = () => { $('voice-volume-label').textContent = $('voice-volume').value + '%'; };
  output.onchange = () => { outputKey = output.value; localStorage.setItem('emulation-voice-output', outputKey); route(); };
  $('voice-clips').addEventListener('click', async event => {
    const button = event.target.closest('[data-voice-play]');
    if (button) {
      $('voice-clips').querySelectorAll('audio').forEach(player => player.pause());
      await actVoice('play', {id:button.dataset.voicePlay, output:output.value, volume:Number($('voice-volume').value) / 100});
    }
  });
  document.querySelectorAll('[data-tiktok-action]').forEach(button => {
    button.onclick = async () => {
      const serial = $('tiktok-phone').value;
      if (!serial) return toast('Selecione o celular no rascunho da transmissão.');
      button.disabled = true;
      try {
        const result = await request(button.dataset.tiktokAction, {serial});
        $('tiktok-device-status').textContent = result.message;
      } catch (error) { $('tiktok-device-status').textContent = error.message; }
      finally { button.disabled = false; }
    };
  });
  $('tiktok-phone').addEventListener('change', () => { $('tiktok-device-status').textContent = 'Celular alterado. Verifique a conexão novamente.'; });
  poll();
  setInterval(() => { if (app.view === 'tiktok' || state?.generation.busy || state?.playback.busy) poll(); }, 2000);
  icons();
})();
