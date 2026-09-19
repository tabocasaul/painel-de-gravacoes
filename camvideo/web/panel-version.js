(() => {
  const label = document.querySelector('.version');
  async function checkVersion() {
    try {
      const response = await fetch('/api/version', {cache: 'no-store'});
      const running = response.ok ? await response.json() : {};
      const latestResponse = await fetch('/current-runtime.json', {cache: 'no-store'});
      const latest = latestResponse.ok ? await latestResponse.json() : {};
      label.textContent = running.appVersion ? `v${running.appVersion} • execução local` : 'Servidor antigo • atualização disponível';
      let notice = document.getElementById('panel-update-notice');
      if (latest.revision && (latest.revision !== running.revision || latest.url !== location.origin + '/') && /^http:\/\/127\.0\.0\.1:\d+\/$/.test(latest.url)) {
        if (!notice) {
          notice = document.createElement('p');
          notice.id = 'panel-update-notice';
          notice.style.cssText = 'padding:12px;background:#332810;color:#fff;border-radius:8px';
          const link = document.createElement('a');
          link.textContent = 'Abrir painel atualizado';
          link.style.color = '#7fe8ff';
          notice.append('Há outra execução do painel. Use a janela mais recente para enviar os comandos. ', link);
          document.querySelector('main').prepend(notice);
        }
        notice.querySelector('a').href = latest.url;
      } else if (notice) notice.remove();
    } catch { label.textContent = 'Versão indisponível • verifique a conexão'; }
  }
  checkVersion();
  setInterval(checkVersion, 10000);
})();
