# TikTok Lives e voz local

## Versão 2.2.5 — estoque promocional manual

O card Unidades no valor promocional vincula a quantidade ao nome do produto
preenchido. O número confirmado é enviado à OpenAI nos roteiros de amostra e
sessão contínua; o prompt exige a quantidade exata e proíbe inventar prazo ou
demanda. Não há decremento automático ao registrar vendas. Confira o roteiro
e ouça a amostra: o texto ainda é produzido por um modelo de linguagem.

Atualizar ou desativar a quantidade interrompe o áudio atual e descarta os áudios
de produto pendentes na fila, incluindo resultados de geração iniciados antes
da alteração. Os próximos roteiros usam o novo valor, sem o histórico anterior.
Agradecimentos de vendas pendentes são preservados. Uma pausa de preparação é
esperada. Zero encerra a sessão e impede reinício até ajustar/desativar o estoque.

A configuração fica em memória nesta execução do servidor. Ao trocar o nome do
produto, cadastre sua quantidade novamente. Falas manuais e WAVs já salvos na
biblioteca não são alterados; cuidado ao reproduzir gravações antigas.

## Versão 2.2.4 — registro em lote com nomes reais

O formulário atual aceita uma venda por linha no formato `PED-1042; Ana`.
Informe o código de cada pedido e o nome real a anunciar, confirmando que as
compras foram concluídas. O agradecimento usa diretamente esse nome, sem aviso
de pseudônimo. Não há sorteio de nomes nesse formulário.

É possível acrescentar lotes durante a reprodução: até 50 pedidos por envio,
1000 pendentes e 10000 códigos por execução. O lote é validado por inteiro antes
de entrar: se houver nome ausente, pedido inválido ou duplicado, nada é incluído
e o texto preenchido permanece para correção. Pedidos válidos são acrescentados
ao fim da fila; o sininho e os intervalos configurados continuam valendo.

## Versão 2.2.3 — privacidade no agradecimento

O card de vendas confirmadas não solicita mais o nome real. Cada pedido recebe
um pseudônimo sorteado localmente de uma lista de nomes, sem repetir o anterior
e sem chamada adicional à OpenAI. O áudio explica que usa um nome fictício para
preservar a privacidade. O código do pedido e a confirmação de venda continuam
obrigatórios. O nome fictício aparece na confirmação do registro.

## Versão 2.2.2 — vendas confirmadas

O card Sininho e agradecimentos recebe manualmente código do pedido e nome do
comprador, com confirmação de compra concluída. Exige sessão contínua ativa.
O intervalo sorteado varia entre os limites configurados (10 a 3600 segundos);
o agradecimento toca após terminar a fala atual, com o mesmo sininho da prévia.
Não há integração automática com pedidos do TikTok nesta versão.

Cada código é aceito uma vez nesta execução do servidor. A fila comporta 50
pedidos e só gera agradecimentos registrados, sem nomes sorteados. Os avisos
usam síntese local, sem chamadas adicionais à OpenAI. Ao parar ou ocorrer erro,
os avisos pendentes são cancelados; os códigos continuam registrados até encerrar
o servidor, evitando repetição acidental. O estado da fila não persiste após
reiniciar. A biblioteca contém os WAVs gerados e seus nomes de exibição.

O teste da fila com processos simulados verifica um único anúncio por pedido,
rejeição de duplicatas e ausência de anúncios espontâneos. A reprodução na
transmissão TikTok continua dependendo da saída de áudio configurada.

## Versão 2.2.1 — prévia do sininho

Em TikTok Lives, “Gerar simulação de venda” cria um sininho de duas notas seguido
de uma fala OmniVoice com nome fictício sorteado. O áudio anuncia explicitamente
a simulação antes do agradecimento e ao final. A prévia é reproduzida pelo player
quando solicitado, sem entrar automaticamente na fila contínua. O teste usa
apenas síntese local, sem chamar a OpenAI. O WAV também fica na biblioteca.

## Versão 2.2.0

Na aba TikTok Lives, preencha nome, características e oferta do produto. Cadastre
a chave da OpenAI no campo de senha do painel: ela fica protegida pelo DPAPI do
Windows para o usuário atual, sem aparecer nas respostas da API local.

O GPT-4o mini escreve os roteiros usando os dados do produto e os três últimos
textos para variar a fala. Essas informações são enviadas à OpenAI, com
`store: false`; cada pedido consome créditos da API. A voz continua sendo gerada
localmente pelo OmniVoice. Use a amostra de um minuto para avaliar o resultado.

Para reprodução contínua, escolha a saída de áudio e a duração da sessão, depois
inicie. O painel prepara dois áudios antes de começar e gera os próximos enquanto
reproduz a fila. A opção até parar mantém os pedidos ativos até a interrupção;
um pedido de API já enviado pode concluir mesmo após parar. Erros interrompem a
sessão. Não existe garantia de ausência de pausas sob carga ou falhas de rede.

O botão de upload aceita vários vídeos e os adiciona à biblioteca. A seleção
atualiza o rascunho, sem trocar automaticamente a câmera ou iniciar uma live.
Use demonstrações, tomadas e conteúdos diferentes: o painel não promete evitar
a detecção de conteúdo repetitivo pelo TikTok.

O rodapé consulta `/api/version` para mostrar a versão do servidor em execução.
Após carregar a interface atual, uma janela ligada a servidor antigo mostra
um aviso com acesso à instância atual, registrada em `web/current-runtime.json`.
Os atalhos existentes continuam abrindo a versão compatível automaticamente.

O worker também encaminha chamadas feitas pelo Python anterior para
`omnivoice-runtime`, preservando argumentos, saída e código de retorno. Isso
corrige `No module named 'omnivoice'` mesmo em servidores de voz já abertos.
Validação: síntese real pelo servidor antigo na porta 8770 gerou WAV de 3,32 s
com OmniVoice/CUDA; testes em `test_voice_runtime` cobrem encaminhamento e
prevenção de recursão. Uma janela que já estava carregada precisa ser
recarregada para exibir o novo rodapé.

A aba TikTok Lives inclui geração de falas femininas em português brasileiro,
prévia, download WAV e reprodução em uma saída de áudio do Windows. O motor é
o [OmniVoice](https://huggingface.co/k2-fsa/OmniVoice),
com a amostra feminina aprovada na demonstração como referência neste PC. A naturalidade depende do
texto e da interpretação; a escolha deve ser avaliada ouvindo as amostras.

## Instalação

Execute `setup/INSTALAR-VOZ-LOCAL.ps1`. O script cria um ambiente Python separado
em `%LOCALAPPDATA%\emulation-cam\omnivoice-runtime`, instala PyTorch com CUDA e
baixa os arquivos para `omnivoice-assets` na mesma pasta. Reserve cerca de 12 GB
para bibliotecas, pesos e arquivos de instalação. Não é necessário instalar
CUDA Toolkit separadamente. Python 3.12 de 64 bits é o ambiente de referência.

Os downloads são das fontes oficiais PyTorch, PyPI e Hugging Face/k2-fsa.
A revisão dos pesos fica fixada em `setup/omnivoice_assets.py` e as bibliotecas
principais em `setup/omnivoice-requirements.txt`. O arquivo
`omnivoice-assets/manifest.json` registra a origem.

O código do OmniVoice é Apache 2.0, mas os pesos são CC-BY-NC (uso não comercial).
Essa licença precisa ser resolvida com os responsáveis pelo modelo antes de
usar a integração em lives comerciais/monetizadas.

Neste PC, `omnivoice-assets/reference-female.wav` guarda a voz sintética aprovada,
com a transcrição definida no worker. Não é necessário baixar Whisper.
O instalador copia a referência de `setup/omnivoice-reference.wav`, acompanhada
da origem e hash em `setup/omnivoice-reference.json`. Se a referência for removida,
o worker usa Voice Design feminino jovem adulto e o timbre pode variar.
A biblioteca de falas anterior permanece disponível.

Depois da instalação, a geração usa os arquivos locais e configura Hugging
Face e Transformers em modo offline. Texto e áudio não são enviados para uma
API de síntese. O primeiro uso pode demorar para carregar o modelo e inicializar
as bibliotecas. O processo mantém o modelo e a referência carregados entre
gerações. Use Liberar memória quando não estiver gerando ou reproduzindo, ou
encerre o servidor, para liberar os recursos. Prepare as falas antes de ligar
muitos emuladores. Não há garantia de geração em tempo real.

No Windows, o carregamento inicial é bloqueado com menos de 3,5 GiB de RAM disponíveis ou
6 GiB de memória de compromisso disponível (RAM + paginação). Essa verificação
evita iniciar uma carga pesada quando o PC já está sem memória; não garante
que haverá VRAM suficiente. O instalador verifica presença das bibliotecas e
arquivos sem carregar o modelo. A síntese efetiva é validada separadamente.

## Gerar e tocar

1. Abra TikTok Lives e escreva uma fala de até 2400 caracteres.
2. Escolha o ritmo Natural, Um pouco mais calma ou Um pouco mais rápida e clique em Gerar fala.
3. Ouça a prévia. As falas ficam na biblioteca do PC após fechar o painel.
4. Atualize as saídas, escolha o dispositivo de áudio e clique em Tocar na saída.
5. Use Parar voz para interromper a reprodução; Cancelar geração interrompe a síntese.

Os WAVs e seus metadados ficam em `%LOCALAPPDATA%\emulation-cam\voices`.
A geração manual e a amostra não iniciam reprodução automaticamente. A sessão
contínua, quando iniciada pelo usuário, reproduz na saída escolhida.
O player de prévia usa a saída do navegador; Tocar na saída usa o dispositivo
selecionado no painel. O volume do painel vale para essa reprodução.

## Levar a voz ao microfone da live

O [VB-CABLE](https://vb-audio.com/Cable/) encaminha o som de CABLE Input para
CABLE Output. A instalação do driver exige administrador e o fabricante
orienta reiniciar o Windows para concluir a instalação. O driver não faz
parte do pacote redistribuído deste projeto.

- No painel: selecione CABLE Input como saída da voz.
- No TikTok LIVE Studio: configure CABLE Output como microfone.
- No emulador: configure CABLE Output como entrada padrão de gravação do Windows
  e habilite o microfone do PC no celular selecionado. Isso pode afetar outros
  aplicativos que usam o microfone padrão. O painel não altera essa preferência.
- Confira o medidor de áudio do aplicativo e faça uma gravação de teste.

O botão de microfone usa o comando oficial do emulador `avd hostmicon`.
Habilitá-lo não comprova que o TikTok está recebendo áudio. Uma entrada padrão
compartilhada pode ser captada por vários emuladores: não há isolamento de
áudio por conta nesta versão. O áudio original do vídeo não é misturado
automaticamente à voz.

## TikTok

Selecione o celular no rascunho e use Verificar TikTok ou Abrir TikTok.
O aplicativo deve estar instalado pela Play Store e a conta precisa ter
acesso ao LIVE. Os comandos não iniciam uma transmissão pública. Confira
imagem, áudio e conta e inicie a LIVE no aplicativo.

Fontes: [Microfone do Android Emulator](https://developer.android.com/studio/run/emulator-extended-controls),
[modelo e referência oficial PT-BR](https://huggingface.co/spaces/ResembleAI/Chatterbox-Multilingual-TTS-pt-br/tree/main).

## Desenvolvimento

O painel importa apenas a biblioteca padrão de Python para gerenciar as falas.
`voice_worker.py` roda no ambiente isolado. Os endpoints `/api/voice/state`,
`/api/voice/action` e `/api/voice/audio` são servidos somente pelo servidor local.
Geração e reprodução têm processos separados, exclusão por operação, cancelamento
e tempo limite. Arquivos incompletos não aparecem na biblioteca.

Validação: `python -m unittest test_voice test_voice_runtime test_live_voice test_voice_http test_panel_runtime test_panel_upload`, dentro de `camvideo`.
Para testar mudanças sem interromper o painel em uso:
`python camvideo/modern_server.pyw --port 8769 --no-open`.

Ao reabrir pelos atalhos, o servidor compara a versão do código e a pasta do
projeto pelo endpoint `/api/version`. Reutiliza uma instância compatível ou abre
a versão atual na primeira porta livre entre 8768 e 8799. Instâncias antigas
continuam abertas; use a janela aberta pelo atalho para acessar a integração nova.
Teste dessa seleção: `python -m unittest test_panel_runtime`, dentro de `camvideo`.

### Validação neste PC em 09/09/2026

- 32 testes passaram, incluindo proteção da chave, payload da OpenAI, processo
  persistente, fila, amostra e cancelamento. Os testes da fila usam áudio simulado.
- Uma chamada real à OpenAI gerou um roteiro de demonstração com 157 palavras.
  A síntese real desse texto na RTX 3070 produziu cerca de 60 segundos de áudio:
  30,86 s na primeira geração com 32 passos; 11,62 s com o modelo carregado e
  os mesmos 32 passos; 6,20 s com 16 passos. Tempos incluem a espera do gerenciador.
  O modo rápido pode alterar a qualidade; compare as amostras. Medição sem
  emuladores ativos, registrada em `artifacts/benchmark_omni_live.json`.
- RTX 3070 com 8 GB de VRAM; 16 GB de RAM no sistema.
- OmniVoice 0.2.1, Transformers 5.3.0 e PyTorch 2.8.0+cu128 instalados em ambiente
  separado. Pesos verificados por SHA-256; Chatterbox anterior preservado.
- Geração local offline validada com a referência aprovada: WAV mono de 5,56 s
  a 24 kHz, dispositivo CUDA, 6,56 s para carregar modelos e sintetizar (esse
  tempo não inclui importação das bibliotecas/inicialização do processo).
  Arquivo de teste: `voices/3b7ae95fc9554e25bb452e6367efe478.wav`.
- VB-CABLE instalado e reprodução para CABLE Input capturada em CABLE Output
  com um sinal de calibração (correlação 0,93). Isso valida o caminho de áudio
  do Windows, não a recepção pelo TikTok. O teste de reprodução do novo WAV
  OmniVoice no cabo virtual não foi executado: a revisão automática do executor
  rejeitou esse comando combinado com a abertura do painel, sem motivo detalhado.
- A conta TikTok e a transmissão pública ainda precisam de validação no aplicativo.
