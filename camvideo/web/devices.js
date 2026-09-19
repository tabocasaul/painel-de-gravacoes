// Display names are aliases: ADB serials and ports remain stable for automation.
const mirrorPanel=document.createElement('article');
mirrorPanel.className='panel';
mirrorPanel.style.cssText='padding:20px;margin-bottom:20px';
mirrorPanel.innerHTML='<h2>Espelhar comandos</h2><p>Selecione o celular principal e ative. Toques e arrastos feitos na janela dele serão repetidos nos outros celulares ligados, após soltar o mouse. Mantenha todos na mesma tela e orientação. Não replica digitação, pinça ou botões da barra lateral do emulador.</p><div class="install-actions"><button class="button button-primary" id="mirror-start">Espelhar selecionado em todos</button><button class="button button-secondary" id="mirror-stop">Parar espelhamento</button></div><p id="mirror-status" role="status">Desativado</p>';
document.getElementById('phones').before(mirrorPanel);
document.getElementById('mirror-start').onclick=()=>act('mirror_start',{serial:app.phone});
document.getElementById('mirror-stop').onclick=()=>act('mirror_stop');
const deviceStyles=document.createElement('link');
deviceStyles.rel='stylesheet';deviceStyles.href='/devices.css';document.head.append(deviceStyles);
const renameDialog=document.createElement('dialog');
renameDialog.className='device-dialog';
renameDialog.innerHTML='<form><div class="dialog-heading"><div><span class="eyebrow">PERSONALIZAR</span><h2>Editar celular</h2></div><button type="button" class="icon-button close-dialog" aria-label="Fechar"><i data-lucide="x"></i></button></div><label>Nome do celular<input name="deviceName" maxlength="60" required autocomplete="off"></label><label>Identificação<input name="deviceLabel" maxlength="60" autocomplete="off"></label><p>Esses nomes aparecem no painel. A conexão e a porta do emulador permanecem iguais.</p><div class="rename-error" role="alert"></div><footer><button type="button" class="button button-secondary close-dialog">Cancelar</button><button type="submit" class="button button-primary">Salvar alterações</button></footer></form>';
document.body.append(renameDialog);
renameDialog.querySelectorAll('.close-dialog').forEach(button=>button.onclick=()=>renameDialog.close());
renameDialog.addEventListener('click',event=>{if(event.target===renameDialog){const r=renameDialog.getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)renameDialog.close()}});
let editingSerial='';
function editPhone(phone){
  editingSerial=phone.serial;
  renameDialog.querySelector('[name=deviceName]').value=phone.name;
  renameDialog.querySelector('[name=deviceLabel]').value=phone.label||phone.serial;
  renameDialog.querySelector('.rename-error').textContent='';
  renameDialog.showModal();icons();
}
renameDialog.querySelector('form').onsubmit=async event=>{
  event.preventDefault();
  const button=renameDialog.querySelector('[type=submit]');button.disabled=true;
  try{
    await call('rename',{serial:editingSerial,name:renameDialog.querySelector('[name=deviceName]').value,label:renameDialog.querySelector('[name=deviceLabel]').value});
    renameDialog.close();app.phoneHash='';await refresh();toast('Nomes salvos');
  }catch(error){renameDialog.querySelector('.rename-error').textContent=error.message}
  finally{button.disabled=false}
};
renderPhones=function(phones){
  const mirror=app.state.mirror||{};
  document.getElementById('mirror-status').textContent=mirror.active?`${phones.find(p=>p.serial===mirror.source)?.name||mirror.source} → ${mirror.targets.length} celulares • ${mirror.message}`:mirror.message||'Desativado';
  document.getElementById('mirror-start').disabled=!!mirror.active;
  document.getElementById('mirror-stop').disabled=!mirror.active;
  const hash=JSON.stringify([app.phone,phones]);if(hash===app.phoneHash)return;app.phoneHash=hash;
  document.getElementById('phones').innerHTML=phones.length?phones.map(phone=>{
    const selected=phone.serial===app.phone,online=phone.status==='online',off=phone.status==='off';
    return `<article class="phone-card ${selected?'selected':''}" data-serial="${esc(phone.serial)}"><div class="device-card-header"><span class="device-avatar"><i data-lucide="smartphone"></i></span><span class="pill ${esc(phone.status)}"><span></span>${online?'Online':off?'Desligado':'Iniciando'}</span><button class="device-edit" aria-label="Editar ${esc(phone.name)}" title="Editar nomes"><i data-lucide="pencil"></i></button></div><div class="device-identity"><h3>${esc(phone.name)}</h3><p>${esc(phone.label||phone.serial)}</p></div><div class="device-details"><span>PORTA <b>${esc(phone.port)}</b></span><button class="device-select" aria-pressed="${selected}"><i data-lucide="${selected?'circle-check':'circle'}"></i>${selected?'Selecionado':'Selecionar'}</button></div><div class="phone-actions"><button data-action="${off?'start':'stop'}" class="device-power ${off?'':'is-on'}"><i data-lucide="power"></i>${off?'Ligar celular':'Desligar'}</button><button class="open-minute" data-action="minute" ${online?'':'disabled'}><i data-lucide="external-link"></i>Abrir Minute</button></div></article>`;
  }).join(''):empty('smartphone','Nenhum celular configurado','Adicione um celular para começar');
  document.querySelectorAll('.phone-card').forEach(card=>{
    const phone=phones.find(p=>p.serial===card.dataset.serial);
    card.onclick=event=>{
      if(event.target.closest('.device-edit')){editPhone(phone);return}
      const command=event.target.closest('[data-action]');
      if(command?.disabled)return;
      app.phone=phone.serial;
      if(command)act(command.dataset.action,{serial:phone.serial});
      app.phoneHash='';renderPhones(app.state.phones||[]);updateSelectionLabels();
    };
  });
  icons();
};
