# Emulador TikTok

O atalho ABRIR-TIKTOK.bat abre TikTokAtual: Android 16 (API 36, imagem oficial Google Play x86_64, revisao 7), 4096 MB de RAM, 2 nucleos, tela 720 x 1280 e 32 GB de armazenamento virtual. O Android confirma ARM64 com libndk_translation.so. A porta ADB e automatica.

Para criar em outro PC, execute setup/criar-tiktok.ps1. O script recusa substituir um AVD existente e instala a imagem pelo SDK Manager oficial.

## Validacao em 09/09/2026

TikTok 46.8.3 instalado com sucesso com os APKs extraidos da instalacao oficial da Play Store anterior. A primeira abertura chegou ao primeiro uso, mas encerrou com SIGKILL sem causa identificada. A segunda abertura levou 2,36 segundos ate MainActivity e mostrou a tela principal com For You, Shop, Home e Profile. Isso confirma a abertura, nao estabilidade de longo prazo nem funcionamento de LIVE, camera, login ou reproducao do feed.

O antigo TikTokEspecial (Android 11) foi preservado desligado. Ele falhava repetidamente com SIGABRT em libndk_translation.so e Bad 'ubidi_openSized_66' call, mesmo com 3 GB de RAM. O atalho nao o utiliza.

O novo AVD exige login proprio. Ele nao possui a camera modificada nem as automacoes dos celulares Minute e seu nome separado o mantem fora das operacoes de gravacao em todos. Os celulares Minute foram preservados.

Logs: %LOCALAPPDATA%/emulation-cam/tiktok-atual-startup.log e tiktok-atual-error.log.

## Teste de captura em 09/09/2026

Dois testes de 15 segundos dentro do TikTok com camera nativa videofile (caminho absoluto e relativo) apresentaram imagem preta. O primeiro foi exportado sem postagem publica para artifacts/tiktok-capture-test.mp4: duracao 15,20 s, AAC 44,1 kHz, volume maximo -90,3 dB (praticamente silencio). A segunda captura chegou ao editor, mas a exportacao nao foi concluida antes de o usuario assumir a janela. Nao ha confirmacao de audio no segundo teste.

A entrada de captura padrao do Windows foi restaurada a partir de artifacts/tiktok-input-before.json e hostmicon foi desligado ao terminar. O emulador em execucao ainda usa videofile temporario; o atalho normal abre a configuracao original. Nao houve publicacao em feed, Story ou LIVE. A exportacao com marca-dagua do TikTok informa envio ao servidor para moderacao.

## Conexao da aba TikTok Lives

O painel identifica TikTokAtual separadamente dos celulares Minute. O video selecionado e enviado pelo driver oficial DroidCam Video 7.1.2, enumerado pelo Android Emulator via Media Foundation. Nao depende do OBS aberto. DroidCam Source 3 (Classic) nao e compativel com este transporte. OBS Virtual Camera permanece como alternativa apenas quando enumerado pelo emulador.

Instalar o driver: setup/INSTALAR-TIKTOK-CAMERA.ps1 (confere assinatura DEV47 APPS LTD antes de executar o instalador oficial). Instalar bibliotecas: setup/INSTALAR-TIKTOK-VIDEO.ps1. VB-CABLE e o ambiente de voz local tambem sao necessarios.

O produtor escreve quadros YUY2 no protocolo compartilhado documentado em https://github.com/dev47apps/droidcam-obs-virtual-output/blob/master/src/structs.h . O consumidor informa tamanho e intervalo; cabecalhos invalidos e dimensoes fora do limite sao recusados. Conversao RGB/YUY2 usa OpenCV: aproximadamente 2 ms por quadro de 1280x720 neste PC. O enquadramento final no TikTok ainda precisa ser validado; a rotacao experimental foi revertida.

Conectar reinicia somente TikTokAtual. Reproduzir do inicio reinicia imagem e audio, em repeticao. Pausar silencia o audio e segura o quadro. Parar encerra o motor e restaura a entrada anterior do Windows, caso o usuario nao a tenha alterado durante o teste. Imagem e audio nao sao declarados confirmados pelo simples envio de quadros.

Validacao parcial em 09/09/2026: driver instalado com assinatura valida, enumerado como webcam1; arquivo real 20260812_183002_2bbra8.mp4 capturado pelo driver em artifacts/droidcam-proof.png e exibido na camera nativa do Android. Validacao de enquadramento e captura no TikTok ainda em andamento. O instalador OBS2MF foi bloqueado pelo Controle de Aplicativo do Windows e nao foi instalado; nenhuma protecao foi alterada.


Ultimo teste: 82 testes Python passaram. A camera nativa do Android exibiu o video, mas com enquadramento incorreto; o TikTok apresentou previa preta e erros EGL. ANGLE por aplicativo foi testado e carregou via Vulkan/NVIDIA, mas apresentou artefatos no feed. Em seguida o TikTok mostrou "Your account was logged out". As duas configuracoes globais ANGLE criadas para esse teste foram removidas, a conexao de video foi parada e hostmicon desligado. O usuario entrou novamente; os resultados da retomada estao abaixo. Nao considerar a captura TikTok pronta.


## Retomada apos login e reversao da atualizacao

Depois do novo login, a previa continuou preta. Ao iniciar uma captura de 15 segundos, TikTok encerrou com SIGABRT na thread VE-MainRender-0. O log artifacts/tiktok-record-crash.txt aponta CHECK de mmap em libndk_translation.so (ExecRegionAnonymousFactory::Create), com libeffect.so/libttvesdk.so na pilha ARM. Nenhuma nova captura valida nem audio captado pelo TikTok foram confirmados.

Foi testada a imagem oficial Google Play x86_64 Android 36.1 revisao 4, com download de 2.001.299.692 bytes e SHA1 ab58abb8dbbc8a00c9437c30c210e8b6a5286795 verificados. Antes do teste, TikTokAtual foi desligado e seu diretorio completo, dados e chaves foram copiados e conferidos. A imagem 36.1 iniciou, mas nao manteve os aplicativos da instalacao anterior; portanto nao houve teste de captura TikTok nela e ela nao foi adotada.

O diretorio experimental foi preservado em failed-36.1.avd dentro do backup. TikTokAtual foi restaurado integralmente com a imagem API 36 anterior. O SHA256 do userdata restaurado coincidiu com o backup. O caminho local do backup esta em artifacts/tiktok-361-backup-path.txt. A imagem 36.1 baixada permanece no SDK sem uso pelo atalho.

Os produtores de diagnostico foram encerrados, hostmicon desligado e as tres entradas padrao de captura Windows conferidas como Microfone Realtek original. Nao houve LIVE nem postagem publica. A conexao do painel permanece experimental: transporte de quadros no driver comprovado, captura final TikTok ainda incompativel neste teste.
