(() => {
  const key = 'emulation-tiktok-draft';
  let draft = {};
  try { draft = JSON.parse(localStorage.getItem(key) || '{}') || {}; } catch {}
  if (typeof draft !== 'object' || Array.isArray(draft)) draft = {};
  const title = $('tiktok-title'), phone = $('tiktok-phone'), video = $('tiktok-video');
  title.value = typeof draft.title === 'string' ? draft.title : '';
  let choicesHash = '';
  let connectedPhones = [], connectionAvailable = false, transportError = '';
  function choices(state) {
    const phones = connectedPhones, videos = state.videos || [];
    const hash = JSON.stringify([phones.map(p => [p.serial, p.name, p.status]), videos.map(v => v.name)]);
    if (hash === choicesHash) return;
    choicesHash = hash;
    phone.innerHTML = '<option value="">Selecione um celular</option>' + phones.map(p => `<option value="${esc(p.serial)}">${esc(p.name)} · ${p.status === 'online' ? 'Online' : p.status === 'booting' ? 'Iniciando' : 'Desligado'}</option>`).join('');
    video.innerHTML = '<option value="">Selecione um vídeo</option>' + videos.map(v => `<option value="${esc(v.name)}">${esc(v.name)}</option>`).join('');
    phone.value = phones.some(p => p.serial === draft.phone) ? draft.phone : '';
    video.value = videos.some(v => v.name === draft.video) ? draft.video : '';
  }
  for (const select of [phone, video]) select.addEventListener('change', () => {
    draft.phone = phone.value;
    draft.video = video.value;
  });
  $('tiktok-draft').addEventListener('submit', event => {
    event.preventDefault();
    draft = {title: title.value.trim(), phone: phone.value, video: video.value};
    try {
      localStorage.setItem(key, JSON.stringify(draft));
      toast('Rascunho da live salvo neste navegador');
    } catch { toast('Não foi possível salvar o rascunho neste navegador'); }
  });
  const previousRender = render;
  render = state => { previousRender(state); choices(state); };
  choices(app.state);
  const transport = document.createElement('div');
  transport.innerHTML = `<div class="tiktok-actions"><button type="button" id="tiktok-connect" class="button button-primary" disabled>Conectar vídeo e reiniciar TikTok Atual</button><button type="button" id="tiktok-play" class="button button-secondary" disabled>Reproduzir do início</button><button type="button" id="tiktok-pause" class="button button-secondary" disabled>Pausar vídeo e áudio</button><button type="button" id="tiktok-stop" class="button cancel-button" disabled>Parar conexão</button></div><p class="tiktok-note">Conectar reinicia apenas o TikTok Atual. A entrada de gravação do Windows fica temporariamente no CABLE Output; Parar conexão restaura a entrada anterior. Confira a câmera antes de iniciar uma LIVE. O botão Reproduzir reinicia o vídeo e seu áudio, em repetição.</p><p id="tiktok-transport-status" class="tiktok-note" role="status">Verificando conexão...</p>`;
  $('tiktok-draft').appendChild(transport);
  async function command(action, data = {}) {
    try {
      const response = await fetch('/api/voice/action', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({action, ...data})});
      const value = await response.json();
      if (!response.ok || value.error) throw Error(value.error || 'Falha na conexão.');
      transportError = '';
      await pollConnection();
    } catch (error) { transportError = error.message; $('tiktok-transport-status').textContent = transportError; }
  }
  $('tiktok-connect').onclick = () => {
    if (!connectionAvailable || !phone.value || !video.value) return toast('Selecione TikTok Atual e um vídeo.');
    command('tiktok_video_connect', {serial:phone.value, video:video.value, output:$('voice-output')?.value || '', volume:Number($('voice-volume')?.value || 80)/100});
  };
  for (const mode of ['play','pause','stop']) $('tiktok-' + mode).onclick = () => command('tiktok_video_' + mode);
  let polling = false;
  async function pollConnection() {
    if (polling) return;
    polling = true;
    try {
      const response = await fetch('/api/tiktok/state', {cache:'no-store'});
      if (!response.ok) throw Error('Abra o painel atualizado para conectar o vídeo ao TikTok.');
      const value = await response.json();
      connectedPhones = value.phones || []; connectionAvailable = true;
      choices(app.state);
      if (!phone.value && connectedPhones.length === 1) {
        phone.value = connectedPhones[0].serial; phone.dispatchEvent(new Event('change'));
      }
      $('tiktok-connect').disabled = value.busy || value.active;
      $('tiktok-play').disabled = $('tiktok-pause').disabled = value.busy || !value.active;
      $('tiktok-stop').disabled = !value.busy && !value.active;
      $('tiktok-transport-status').textContent = transportError || `${value.video ? value.video + ' · ' : ''}${value.message} · Imagem: ${value.imageConfirmed ? 'confirmada' : 'não confirmada'} · Áudio: ${value.audioConfirmed ? 'confirmado' : 'não confirmado'}`;
    } catch (error) {
      connectionAvailable = false;
      for (const id of ['connect','play','pause','stop']) $('tiktok-' + id).disabled = true;
      $('tiktok-transport-status').textContent = error.message;
    } finally { polling = false; }
  }
  pollConnection();
  setInterval(() => { if (app.view === 'tiktok') pollConnection(); }, 2500);
})();
