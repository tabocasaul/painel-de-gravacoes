# Projeto Emulation

## Versão atual: 2.3.33 — operação dos celulares

**Leia primeiro o [padrão dos celulares e checklist de gravação](docs/padrao-celulares.md).**
O guia explica a preparação de cada aparelho, como iniciar pelo painel,
como conferir o salvamento e quais falhas o supervisor consegue recuperar.
É uma referência do funcionamento deste projeto, não uma certificação do Minute
nem garantia de aprovação de conteúdo pelo serviço.

Novidades desta atualização:

- Plano diário: limite separado de 2 horas por tarefa, celular e dia local; espera pelo próximo dia ao completar o plano.
- Plano intercalado: catálogo importado do Minute, seleção de tarefas e vínculo de um vídeo por tarefa; sorteia a ordem em ciclos e troca depois de salvar a rodada.
- Rodadas com dois celulares, priorizando os que menos gravaram; o modo fixo tenta abrir o par mesmo com pouca RAM disponível.
- Supervisor local: registro persistente das capturas, tentativa de recuperação, confirmação de salvamento e proteção contra contagem duplicada; processo auxiliar para reiniciar o servidor quando necessário.
- Visão geral com filtros de período e estimativa de ganhos em reais.

Abra pelo iniciador do projeto e use a versão atual indicada no painel. A porta
local pode mudar quando já existe outro servidor aberto; não fixe uma porta antiga.
O endereço publicado está em `camvideo/web/current-runtime.json`, arquivo local
que não acompanha o GitHub. Inicie as gravações pelo botão do painel.

As seções antigas abaixo registram etapas anteriores do projeto. Valores históricos
de resolução, espaço e limites não substituem o guia operacional acima.


## Câmera compartilhada e automação

O painel agora prepara os quadros uma vez no PC e conecta essa mesma fonte
às câmeras por pequenos discos virtuais. Não copia mais um I420 inteiro para
cada celular. Os quadros ficam em cache para reutilização, e os celulares
mantêm controles de reprodução independentes. As contas e os 128 GiB de
armazenamento são preservados; a reserva padrão de RAM passou a 2 GiB.

A automação procura a tarefa pelo nome, confirma as dicas, gira à esquerda,
reinicia o vídeo e encerra ao final dele ou antes do limite de 29min59s.
O painel mostra o resultado por celular e verifica a confirmação de salvamento.
Veja [funcionamento, medições e limites](docs/camera-compartilhada.md).

As estimativas históricas abaixo referentes ao I420 **por celular** descrevem
o modo antigo de cópia. No modo compartilhado, os quadros ocupam espaço uma
vez por vídeo preparado no PC, além dos dados de cada conta e suas gravações.

## Atualização v1.1.0

- Cartões de celulares redesenhados, com edição dos dois nomes exibidos. A porta e o endereço ADB continuam iguais.
- Opção persistente para silenciar a prévia no painel.
- Espelhamento de toques e arrastos da janela principal para os outros emuladores ligados. Requer root; repete o gesto após soltar o mouse, sem garantia de simultaneidade exata. Digitação e multitoque não estão incluídos. A validação com emuladores reais ainda está pendente.
- Preparação da câmera diretamente a partir do original, sem recompressão MP4 intermediária. O original é preservado. A HAL atual continua usando I420 sem áudio em **640×360 a 30 fps**; isso não preserva a resolução 4K da fonte.
- Verificação de espaço antes de preparar o vídeo: um vídeo de 31min24s ocupa aproximadamente **18,2 GiB** em I420 dentro de cada celular, independentemente do tamanho do arquivo comprimido de origem. Um emulador configurado com 8 GB não comporta esse vídeo. O painel informa o espaço necessário antes de iniciar.

Rodar o app **Minute** (`com.bakerdata.minute`) num emulador Android com a câmera
funcionando, e usar a câmera do emulador como saída para vídeos e para a câmera
do celular ao vivo.

---

## Instalar em outro computador — comece aqui

O repositório contém tudo que é exclusivo deste sistema: painel, automações,
módulos Magisk, HAL de câmera já compilada e scripts de instalação. **O outro
PC não precisa baixar os 186 GB do código-fonte do Android nem recompilar a
HAL.** Essa compilação já foi feita e o binário necessário está em
`magisk/videocam/`.

### Compatibilidade e requisitos

- Windows 10 ou 11 de 64 bits;
- processador Intel ou AMD com virtualização (VT-x/SVM/AMD-V) ativada no BIOS;
- SSD/NVMe — não é recomendado usar HD mecânico;
- acesso de administrador uma vez, para ativar o hipervisor do Windows;
- internet para baixar aproximadamente 6–10 GB e acessar a Play Store;
- conta Google e contas do Minute. Senhas e sessões **não** ficam no GitHub.

O instalador baixa Git, JDK 21, Python 3.12, Android SDK/Emulator, imagem Android
13 com Play Store e ffmpeg. Inter e Lucide já estão no repositório e o painel
não depende da internet depois de instalado.

### Espaço, RAM e escala

Medidas reais do PC de referência em 08/09/2026:

| Componente | Uso observado |
|---|---:|
| Android SDK completo | 4,39 GB |
| Cada celular `MinutePlay` | 12,10 GB |
| Modelo-base para criar clones | 8,10 GB |
| Vídeo I420 da câmera | cerca de 0,58 GB por minuto, por celular |

Recomendações práticas, incluindo folga para conversão e atualizações:

| Escala | SSD livre | RAM | CPU sugerida |
|---|---:|---:|---:|
| 1 celular | 45 GB | 16 GB | 6–8 threads |
| 3 celulares | 75 GB | 24–32 GB | 8–12 threads |
| 10 celulares | 220 GB | 48–64 GB | 16+ threads |
| 50 celulares | 850 GB–1 TB | 160–256 GB | workstation, 32+ threads |

Para calcular conforme a quantidade de celulares e a duração habitual do vídeo:

```powershell
powershell -ExecutionPolicy Bypass -File .\setup\planejar-capacidade.ps1 `
  -Celulares 3 -DuracaoVideoMinutos 3
```

O cálculo considera uma cópia I420 dentro de cada aparelho. Cinquenta
emuladores simultâneos exigem uma workstation/servidor; criar 50 entradas no
gerenciador não faz um desktop comum ganhar CPU, RAM ou espaço para executá-las.

### Quanto tempo demora

| Etapa | Tempo típico |
|---|---:|
| Ferramentas + Android SDK | 20–60 min |
| Criar o primeiro AVD | 5–15 min |
| Play Store + instalar Minute | 10–30 min |
| Magisk + módulos da câmera | 15–40 min |
| Criar o modelo-base | 10–25 min |
| **Total normal** | **1–3 horas** |

Internet lenta, BIOS/hipervisor ainda desligado ou reinicializações pendentes
podem aumentar esse tempo. A compilação AOSP de várias horas não faz parte da
instalação de outro PC.

### Passo a passo no PC novo

1. No GitHub, abra **Releases**, baixe `Emulation-Control-Windows.zip` e extraia
   para uma pasta local. Também é possível usar **Code → Download ZIP**.
2. Ative VT-x/SVM no BIOS. No Windows Pro/Enterprise, abra PowerShell como
   administrador, execute o comando abaixo e reinicie:

   ```powershell
   dism /online /enable-feature /featurename:HypervisorPlatform /all /norestart
   ```

3. Na pasta extraída, execute em um PowerShell normal:

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\setup\INSTALAR-NOVO-PC.ps1 `
     -CelularesPlanejados 3 -DuracaoVideoMinutos 3
   ```

4. Abra o `MinutePlay`, entre na Play Store e instale **Minute Data pela Play
   Store**. Não use APK por sideload, pois ele não passa na verificação PAIRIP.
   Ainda não entre na conta Minute: assim o modelo-base nascerá deslogado.
5. Abra o **Git Bash** na raiz do projeto e execute:

   ```bash
   bash setup/03-rootear.sh
   # siga as instruções do Magisk impressas na tela
   bash setup/04-modulos.sh
   ```

6. Com o primeiro aparelho preparado e sem login no Minute, crie o modelo-base:

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\setup\05-criar-template.ps1 `
     -Origem MinutePlay
   ```

7. Abra novamente o primeiro celular, entre na conta Minute dele e execute
   `ABRIR-TUDO.bat`. Novos celulares criados pelo painel herdam Play Store,
   Minute instalado, Magisk e câmera, mas começam sem conta Minute logada.
8. Confira a instalação:

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\setup\VERIFICAR-AMBIENTE.ps1
   ```

### Atualizações e versões no GitHub

Todo `push` em `main` gera o pacote Windows nos artefatos do GitHub Actions. Ao
criar uma tag como `v1.0.0`, o workflow também publica automaticamente uma
Release contendo `Emulation-Control-Windows.zip` e `CameraEmulador.exe`.
Vídeos pessoais, AVDs, logins, caches e os 186 GB do AOSP ficam fora do Git.

---

## 1. O que já funciona

| | Estado |
|---|---|
| Minute instalado, logado, passando pelo PAIRIP | ✅ |
| Trava de modelo "Galaxy S22 ou superior" | ✅ contornada (`s22spoof`) |
| Trava de câmera ultra-wide na gravação | ✅ contornada (`uwcam`) — a frontal vira simples, ver [docs/uwcam.md](docs/uwcam.md) |
| Vídeo do PC entrando como câmera | ✅ via HAL `emulated` customizada (`videocam`) |
| Câmera do celular ao vivo entrando como câmera | ❌ dependia do OBS → DroidCam, que não existe mais (§4) |
| Vídeo sobreposto à câmera ao vivo | ❌ mesma causa (§4) |
| **Vídeo pré-gravado dentro da gravação do Minute** | ✅ preservando a ultra-wide lógica — ver §6 |

---

## 2. Instalação detalhada e solução de problemas

> **O repositório tem a receita, não contém contas ou emuladores pessoais.**
> Cada AVD usa atualmente cerca de 12,1 GB e não está no Git. Clonando você
> *reconstrói* o ambiente:
> os scripts automatizam o download e a configuração, mas três coisas são
> manuais e não têm como automatizar — login na conta Google, instalar o
> Minute pela Play Store e login no Minute. Conte com 1–3 horas, quase tudo
> esperando download.
>
> Se puder levar a pasta do AVD por pendrive, pule para *"Atalho"* abaixo:
> a diferença é 10 minutos contra 2 horas.

Precisa somente de **PowerShell** e **winget** (App Installer). O script baixa o
Git e todas as outras ferramentas.

O `01-ferramentas.ps1` instala pelo winget somente o necessário ao fluxo atual:

| Programa | Para quê |
|---|---|
| Git + JDK 21 + Python 3.12 | rootAVD, SDK e painel local |
| SDK do Android | emulador, adb, build-tools |
| ffmpeg | utilitário de vídeo |

### Pré-requisito: aceleração por hardware (precisa de admin)

O emulador x86_64 **não sobe** sem hipervisor. O sintoma é morrer no boot com:

```
ERROR | x86_64 emulation currently requires hardware acceleration!
CPU acceleration status: Android Emulator hypervisor driver is not installed
```

Isso é anterior a tudo neste repositório e os scripts não conseguem resolver:
exige elevação.

**Passo 0 — a virtualização precisa estar ligada no firmware:**

```powershell
(Get-CimInstance Win32_Processor).VirtualizationFirmwareEnabled   # tem que ser True
```

Se der `False`, ligue VT-x (Intel) ou SVM/AMD-V (AMD) no BIOS/UEFI. Sem isso
nenhum dos caminhos abaixo funciona — e essa é a causa mais comum de emulador
travado em PC recém-formatado.

Existem **dois** hipervisores possíveis, e eles são **mutuamente exclusivos**.
Escolher o errado custa caro: o AEHD instala sem reclamar, o driver não carrega,
e você continua com 0% de CPU — agora com um driver a mais no sistema.

#### Preferir WHPX (recurso do Windows)

É o que roda no PC de referência deste projeto, e não envolve driver de
terceiros. Precisa de Windows **Pro/Enterprise**. Num PowerShell **como
administrador**:

```powershell
dism /online /enable-feature /featurename:HypervisorPlatform /all /norestart
```

Reiniciar, e conferir com `emulator -accel-check`.

#### AEHD, só se o WHPX não servir

Cabe quando a edição do Windows é Home, ou quando o WHPX não está disponível.
**Antes**, confirme que nada mais está segurando o hipervisor — se qualquer um
destes estiver ativo, o AEHD não vai carregar:

```powershell
Get-Service vmcompute,vmms -ErrorAction SilentlyContinue   # Hyper-V / WSL2 / Sandbox
Get-CimInstance Win32_DeviceGuard -Namespace root\Microsoft\Windows\DeviceGuard |
    Select-Object -Expand SecurityServicesRunning          # Integridade de memória
(Get-CimInstance Win32_ComputerSystem).HypervisorPresent   # tem que ser False
```

Se estiver tudo limpo, o `01-ferramentas.ps1` já baixou o pacote:

```powershell
cd "$env:LOCALAPPDATA\Android\Sdk\extras\google\Android_Emulator_Hypervisor_Driver"
.\silent_install.bat
```

Em qualquer um dos dois casos, o veredito final é o `emulator -accel-check`.

OBS, DroidCam e Iriun pertencem aos experimentos antigos de câmera ao vivo e
não são instalados pelo fluxo atual. O painel de vídeos pré-gravados não depende
deles. A seção §4 mantém apenas o histórico técnico dessa tentativa.

```powershell
# a partir da raiz do repositório clonado
cd .\setup
powershell -ExecutionPolicy Bypass -File .\01-ferramentas.ps1
```
Instala Git, JDK, Python, ffmpeg e o SDK do Android (~4,4 GB no PC de referência).

O script confere no fim se os cinco pacotes do SDK chegaram mesmo. Se ele
terminar sem reclamar, o ambiente está de pé; se reclamar, ele diz qual faltou.

**Abra um PowerShell novo** (para o PATH valer) e:

```powershell
powershell -ExecutionPolicy Bypass -File .\02-criar-avd.ps1
```

Depois, **manualmente dentro do emulador**:

1. Abrir a Play Store e fazer login na conta Google
2. Instalar o **Minute Data** pela Play Store
   *(sideload dos APKs em `/apk` **não** passa no PAIRIP — eles são só backup)*
3. Fazer login no Minute

Então, no **Git Bash**:

```bash
bash 03-rootear.sh     # instala o Magisk
# ... seguir as instruções que ele imprime ...
bash 04-modulos.sh     # instala s22spoof e uwcam
```

### Atalho: levar o AVD pronto

O AVD `MinutePlay` usa atualmente ~12,1 GB e guarda o login da Play, o Minute instalado e o
root já feito. Copiando ele você pula os passos 02–04:

> Não envie esse AVD para o GitHub nem compartilhe publicamente: ele pode conter
> sessão Google, dados do Minute e outros identificadores da máquina. Use apenas
> transferência privada e criptografada entre computadores seus.

```
%USERPROFILE%\.android\avd\MinutePlay.avd\     (pasta)
%USERPROFILE%\.android\avd\MinutePlay.ini      (arquivo)
```

O `.ini` tem caminho absoluto dentro — abra e corrija o nome do usuário se mudar.
Ainda precisa rodar o `01-ferramentas.ps1` para ter o SDK.

---

## 3. Estrutura

```
PROJETO EMULATION/
├── README.md              este arquivo
├── setup/                 instalação do zero no PC novo
├── ABRIR-TUDO.bat         abre o painel e todos os celulares configurados
├── camvideo/
│   ├── modern_server.pyw  backend local do painel moderno
│   ├── web/               interface HTML/CSS/JS, Inter e Lucide locais
│   ├── painel.pyw         motor legado reutilizado pelo backend
│   ├── montar.py          compõe a cena (fundo + sobreposto + texto)
│   ├── preparar.py        só encaixa um vídeo no tamanho da câmera
│   ├── camvideo.py        montava no OBS — via quebrada, ver §4
│   └── videos/            << jogue seus vídeos aqui
├── lentes/                app Android que inspeciona as câmeras (diagnóstico)
├── magisk/                os dois módulos, prontos para instalar
├── docs/                  JSONs originais das câmeras, log de crash
│   └── uwcam.md           como o módulo uwcam é feito, e o que ele custa
└── apk/                   (NÃO vem no clone — está no .gitignore)
```

> `apk/` guardava um backup dos 4 splits do Minute 1.22.0. Fica fora do
> repositório de propósito: é app de terceiros, e sideload não passa no PAIRIP
> de qualquer jeito — a instalação boa é pela Play Store. Se quiser o backup,
> crie a pasta e puxe do próprio emulador depois de instalar:
>
> ```bash
> mkdir -p apk
> adb shell pm path com.bakerdata.minute | sed 's/^package://' \
>   | tr -d '\r' | xargs -I{} adb pull {} apk/
> ```

---

## 4. Como usar

### Trocar o vídeo da câmera — o jeito fácil

Abra **`dist/CameraEmulador.exe`** (recomendado) ou dê dois cliques em
**`camvideo/PAINEL.bat`** durante o desenvolvimento. A janela permite escolher
o vídeo, abrir o `MinutePlay`, verificar ADB/root/módulo, pausar, continuar e
reiniciar o vídeo do zero.

Para abrir tudo de uma vez, use **`ABRIR-TUDO.bat`** ou o atalho
**EMULATION - ABRIR TUDO** criado na Área de Trabalho. Esse modo abre o
administrador, liga todos os `MinutePlay` cadastrados e abre o Minute em cada
um assim que o Android concluir o boot.

A interface principal agora é um painel desktop feito em **HTML, CSS e
JavaScript**, servido somente em `127.0.0.1` e aberto pelo Edge em modo de
aplicativo (sem barra de endereço). O motor local continua em Python porque é
ele que controla ADB, Magisk, ffmpeg e os AVDs; PHP não é usado no projeto.
O painel usa a fonte Inter e ícones Lucide locais, separa Visão geral,
Celulares, Vídeos e Automação no menu lateral e resume no dashboard as horas
dos últimos sete dias, o uso por tarefa e por celular. A biblioteca exibe
miniaturas, duração, resolução e codec; vídeos HEVC ganham automaticamente uma
prévia H.264 compatível com o navegador sem alterar o arquivo original.
Na biblioteca, **Usar em todos** prepara o vídeo uma única vez e distribui o
mesmo arquivo de câmera para todos os celulares online em grupos paralelos,
com progresso e indicação nominal de falhas.

Em PCs com Controle de Aplicativo bloqueando executáveis locais sem assinatura,
o atalho usa `pythonw.exe` com o mesmo painel, sem janela preta. O `.bat` faz
essa escolha automaticamente.

O seletor **Emulador** escolhe entre `MinutePlay (5554)` e
`MinutePlay2 (5556)`. Cada clone tem dados, login do Minute e vídeo de câmera
independentes. Para abrir os dois de uma vez, use
`camera/ABRIR-2-EMULADORES.bat`.

O quadro **Gerenciador de celulares** mostra cada AVD pelo nome e seu estado.
Nele é possível ligar, desligar, abrir o Minute e ligar todos. O botão
**+ ADICIONAR CELULAR** cria automaticamente `MinutePlay3`, `MinutePlay4` etc.,
com barra de porcentagem. Cada aparelho novo mantém Play Store, Minute, root e
`videocam`, mas recebe os dados do Minute limpos para entrar em outra conta.

### Gravação sincronizada

Depois de escolher a tarefa, deixe cada Minute na tela da câmera, antes da
contagem. Clique **INICIAR E SALVAR EM TODOS** no painel. Ele faz sozinho:

1. encontra somente os celulares ligados que estão na câmera da tarefa e têm
   vídeo instalado;
2. zera e pausa o vídeo em todos;
3. toca o botão de gravação simultaneamente;
4. espera cada Minute terminar sua contagem e criar a gravação real;
5. libera o vídeo em todos, mostra o cronômetro e, no último segundo, encerra;
6. encontra o botão `minute-save` e salva em todos.

A duração é calculada pelo arquivo I420 realmente instalado no módulo de cada
celular. O painel bloqueia a operação se os aparelhos prontos estiverem com
vídeos de durações diferentes ou se o clipe não alcançar o mínimo de um minuto
do Minute. **CANCELAR** encerra uma gravação já iniciada sem clicar em salvar.

O campo **Tarefa detectada** é preenchido automaticamente usando o `taskId` e
o `taskName` gravados internamente pelo próprio Minute. Não é preciso digitar
nem escolher a tarefa no painel. Se os celulares estiverem em tarefas
diferentes, a tentativa é encerrada e descartada antes de liberar o vídeo.

O controle aplica o teto diário de **2 horas por tarefa e por celular**. Depois
que o salvamento é confirmado, o tempo do clipe é somado separadamente para
cada `MinutePlay`. Antes de liberar o vídeo, o painel calcula o tempo restante
e encerra a tentativa sem salvar se o novo clipe ultrapassaria 2 horas. O
histórico diário fica em
`%LOCALAPPDATA%\\emulation-cam\\controle-tarefas.json` e muda automaticamente
quando vira o dia. Use **AJUSTAR TEMPO** para informar gravações feitas hoje
antes do gerenciador começar a controlá-las.

Antes da primeira clonagem, crie uma vez o modelo-base a partir de um AVD já
preparado e sem login do Minute:

```powershell
powershell -ExecutionPolicy Bypass -File .\setup\05-criar-template.ps1
```

O modelo ocupa aproximadamente o mesmo espaço de um AVD. Cada celular novo
também usa cerca de 9,5 GB neste perfil.

Escolha o vídeo
da lista (ou de qualquer pasta), opcionalmente escreve um texto por cima, e
clica em **USAR ESTE VÍDEO NA CAMERA**. Duplo clique no nome já aplica.

Ele processa e grava em `%LOCALAPPDATA%\emulation-cam\atual.mp4`, que é o
arquivo que o emulador lê. **Trocar esse arquivo troca o que a câmera mostra.**

O painel converte o vídeo para I420 640×360, envia ao módulo Magisk `videocam`
e reinicia o Android. A HAL continua sendo `emulated`, portanto o Minute ainda
enxerga a câmera lógica e a física ultra-wide.

Para gerar novamente o executável:

```powershell
powershell -ExecutionPolicy Bypass -File .\build-exe.ps1
```

O resultado fica em `dist/CameraEmulador.exe`. Python só é necessário para
compilar; quem usa o `.exe` ainda precisa de ffmpeg, Android SDK, AVD
`MinutePlay` enraizado e o módulo `videocam` instalado.

### Painel do emulador

Abrir **`camera/CAMERA.bat`**:

| Opção | Fonte da traseira | Para quê |
|---|---|---|
| 1 | vídeo (via OBS/DroidCam) | ⚠️ **quebrada** — ver abaixo |
| 2 | Iriun | ⚠️ **quebrada** — ver abaixo |
| 3 | Iriun + vídeo por cima | ⚠️ **quebrada** — ver abaixo |
| 4 | `emulated` | **Minute** (é a única com ultra-wide) |

### Via `videofile:` do emulador — alternativa sem Minute

O emulador toca arquivo de vídeo direto como câmera. Dispensa OBS, DroidCam e
ordem de inicialização.

**Passo 1, prepare o vídeo.** Sem isso a imagem chega cortada: o buffer de
câmera do emulador é **1280×720 deitado** e o `sensor.orientation` é 90, então
o app ainda gira o quadro para exibir. Um vídeo vertical 1080×1920 jogado
direto perde ~68% da altura (`1080 ÷ 16/9 = 607` px sobrevivem de 1920).

```bash
cd camvideo
python preparar.py videos/meu.mp4          # gera videos/meu.pronto.mp4
```

Encaixa o vídeo em 1280×720 **sem cortar nada**. Um 16:9 enche o quadro exato;
outros formatos aparecem inteiros, com tarja preta em volta. Não gira — a
orientação fica como estava.

| Opção | Para quê |
|---|---|
| *(padrão)* | cabe inteiro, sem perder nada |
| `--modo cheio` | preenche cortando o excesso |
| `--rot 270` | vídeo vertical em pé numa tela em pé |
| `--espelhar` | espelha na horizontal |

**Precisa compor?** O `montar.py` faz o que o OBS fazia — juntar fundo,
sobreposto e texto — só que o resultado é um arquivo, não um sinal ao vivo:

```bash
python montar.py --fundo videos/base.mp4 --sobre logo.png --texto "AO VIVO" --instalar
python montar.py --cor black --dur 60 --texto "aguarde" --instalar
python montar.py --fundo base.mp4 --sobre pip.mp4 --canto cima-esquerda --escala 0.25 --instalar
```

`--instalar` já copia para `%LOCALAPPDATA%\emulation-cam\atual.mp4`, que é o
caminho sem espaço que o `videofile:` exige. Cantos: `cima-esquerda`,
`cima-direita`, `baixo-esquerda`, `baixo-direita`, `centro`.

**Passo 2, suba com ele:**

```powershell
emulator -avd MinutePlay -no-snapshot -timezone America/Sao_Paulo `
         -camera-back "videofile:C:\caminho\meu.pronto.mp4" -camera-front emulated -gpu auto
```

Também aceita `imagefile:` e `image360:`. Só não serve para o Minute (§6).

> ### ⚠️ O caminho não pode ter espaço
>
> **O `videofile:` do emulador não aceita espaço no caminho, e falha calado.**
> Não é questão de aspas: o emulador sobe normalmente, o `CameraService` abre o
> dispositivo, e simplesmente não chega frame nenhum — o app fica travado
> esperando. Nenhuma mensagem de erro, em lugar nenhum.
>
> Testado com o **mesmo arquivo**, mudando só o caminho:
>
> | Caminho | Resultado |
> |---|---|
> | `C:\PROJETO EMULATION\camvideo\videos\x.mp4` | boot ok, câmera abre, **zero frames** |
> | `C:\Users\...\Temp\x.mp4` | imagem normal |
>
> Isso morde este projeto sempre, porque a pasta se chama **"PROJETO
> EMULATION"**. Copie para um caminho sem espaço antes de usar:
>
> ```powershell
> copy "camvideo\videos\meu.pronto.mp4" "$env:LOCALAPPDATA\Temp\cam.mp4"
> ```
>
> O `camera/CAMERA.bat` já faz isso sozinho (copia para
> `%LOCALAPPDATA%\emulation-cam\atual.mp4`), e o `preparar.py` avisa quando a
> saída cai num caminho com espaço.

### Via OBS — ⚠️ quebrada nas versões atuais

**Não funciona mais**, e não é configuração: a peça que ligava o OBS ao driver
deixou de existir. Verificado com OBS 32.2.1, DroidCam OBS Plugin 2.5.1 e
DroidCam Client 6.5.3:

- O menu **Ferramentas → DroidCam Virtual Output** não existe mais. O
  `droidcam-obs.dll` 2.5.1 não tem nenhuma string "Virtual Output", nem no
  binário nem em `locale/en-US.ini` — ele virou só plugin de *fonte*
  (celular → OBS), com `Activate`, `Deactivate`, `Resolution`, `Device`.
- O DroidCam Client 6.5.3 é só `DroidCamApp.exe`, sem componente de saída.
- A **VirtualCam nativa do OBS não substitui**. O `ffmpeg -list_devices` mostra
  `OBS Virtual Camera` e `DroidCam Source 2` como `@device_sw_` (filtros de
  software), e `DroidCam Source 3` como `@device_pnp_`. O
  `emulator -webcam-list` enumera **só o PnP** — por isso a VirtualCam inicia
  com sucesso e mesmo assim o emulador não a enxerga.

O `camvideo.py` em si continua íntegro: conecta no obs-websocket, autentica,
cria a cena, carrega o vídeo e posiciona — tudo verificado. O que quebrou é o
elo *depois* dele, do OBS para o driver de câmera. Fica no repositório porque
volta a servir se o dev47apps devolver a saída virtual.

Consequência: **câmera do celular ao vivo e vídeo sobreposto não têm caminho
hoje**. Para vídeo, a via nativa acima cobre — e melhor.

```bash
cd camvideo
python camvideo.py --status        # ainda útil para conferir a conexão com o OBS
```

---

## 5. Armadilhas (todas custaram tempo aqui)

**Ordem do DroidCam.** A saída do OBS tem que estar rodando **antes** do emulador
abrir a câmera. Se abrir junto, o driver recusa e a câmera fica preta sem erro
nenhum. Como conferir:

```bash
grep "webcam video active" "$APPDATA/obs-studio/logs/"*.txt | tail -1
```
`video_ok=1` conectou · `video_ok=0` alguém já estava com o dispositivo.

**Locks do AVD.** Se o emulador for morto à força, sobram `*.lock` e o próximo
boot falha com *"Running multiple emulators with the same AVD"*. Apagar:
```
%USERPROFILE%\.android\avd\MinutePlay.avd\*.lock
```

**`-no-snapshot`, não `-no-snapshot-load`.** O emulador estava morrendo com
`exited with code 1` ao salvar o snapshot na saída.

**Iriun é exclusivo.** Se o OBS estiver com ele aberto, o emulador não consegue
usar `webcam1` direto — recebe verde. É um consumidor por vez.

**Iriun em `0x0`.** Se o celular conectar depois que o OBS abriu a fonte, ela fica
sem tamanho. O `camvideo.py --live` desativa e reativa a fonte para reconectar.

**Modelo tem que valer no boot.** `resetprop` com o sistema no ar não adianta,
o Minute já decidiu. Por isso é um módulo Magisk.

**O vídeo chega cortado se não for preparado.** São três reduções empilhadas,
medidas com o `lentes`:

| Etapa | Efeito |
|---|---|
| buffer da câmera | teto de **1280×720**, deitado |
| `sensor.orientation = 90` | o app gira o quadro para exibir |
| exibição em "cheio" | corta para preencher a tela 9:16 |

Um vertical 1080×1920 direto perde ~68% da altura antes de chegar ao app. O
`camvideo/preparar.py` resolve girando e encaixando antes — é o equivalente,
para a via nativa, do que o `recorte_para` do `camvideo.py` fazia dentro do OBS.

**O `uwcam` troca traseira e frontal de lado.** No emulador stock, quem já vem
como multi-camera lógica com físicas é a **frontal** — a traseira é uma câmera
simples. O módulo aproveita o JSON da frontal para montar a traseira, e a
frontal fica com o JSON simples da traseira. Ou seja: **a frontal perde as
câmeras físicas**. Não afeta o Minute (só usa a traseira), mas surpreende quem
for inspecionar a frontal depois. Detalhes e como reverter em
[docs/uwcam.md](docs/uwcam.md).

**`su` via ADB.** Confira primeiro — pode já estar liberado:

```bash
adb shell "su -c id"      # quer ver: uid=0(root)
```

Numa instalação em 2026-09 o root já veio concedido direto do rootAVD, sem
passo manual nenhum. Se **não** responder `uid=0`, aí sim: não basta
*Superuser Access = Apps and ADB* nem *Automatic Response = Grant* — tem que
ligar o botão do **[SharedUID] Shell** na aba Superuser do Magisk.

**Caminhos do Git Bash para o `adb.exe`.** Vale para o `03` **e para o `04`**.
O `pwd` do Git Bash devolve `/c/PROJETO EMULATION`, e o `adb.exe` é binário
Windows: não entende esse formato. No `03` o sintoma é o push falhar calado e o
patch abortar com *"Ramdisk.img uses UNKNOWN compression"*; no `04` é
`adb: error: cannot stat '/c/...': No such file or directory`. Os dois scripts
resolvem com `cygpath -m`, que devolve `C:/PROJETO EMULATION`.

**Caminhos no rootAVD.** `ANDROID_SDK_ROOT` precisa estar no formato `C:/...`.
Com `/c/Users/...` o `adb.exe` não acha o arquivo, o push falha calado e o patch
aborta com *"Ramdisk.img uses UNKNOWN compression"*.

**build-tools 34 quebra com JDK novo.** O `d8` estoura NullPointerException lendo
classe anônima. Use a **37.0.0** (é o que o `01-ferramentas.ps1` instala).

---

## 6. Como o vídeo entra na gravação do Minute

O limite antigo foi superado substituindo somente a biblioteca que produz os
pixels da câmera `emulated`. A identidade Camera2 continua vindo dos JSONs do
`uwcam`, mas o `EmulatedSensor` passa a ler quadros I420 do módulo `videocam`.

O emulador usa dois HALs de câmera diferentes:

| Fonte | Tem câmeras físicas? | Mostra conteúdo seu? |
|---|---|---|
| `emulated` stock | ✅ **sim** — lê nosso JSON | ❌ só a cena 3D sintética |
| `emulated` + `videocam` | ✅ **sim** | ✅ vídeo I420 selecionado no painel |
| `virtualscene` | ❌ não | 🟡 só um pôster estático na parede |
| `webcam0` / `videofile:` | ❌ não (HAL legacy) | ✅ sim |

**Só o `emulated` tem as físicas** — nem mesmo o `virtualscene`, que também é
sintético. Testado: com `-camera-back virtualscene` o `lentes` reporta *"sem
cameras fisicas: nao e multi-camera logica"*, e o `dumpsys media.camera` não
mostra `physicalIds`. Isso mata a ideia de usar `-virtualscene-poster` para
enfiar uma imagem sua numa fonte que o Minute aceite: o pôster carrega, mas as
físicas somem junto.

O Minute exige uma **ultra-wide física** e grava a partir dela:

```
EgoCameraCtrl: resolveUltraWide: logical=0 ultraWide=4
```

Sem ela, a gravação é recusada — o log é explícito, e a mensagem na tela
(*"Recording isn't available"*) só aparece ao apertar gravar, porque a
**prévia funciona normalmente** em qualquer fonte:

```
resolveUltraWide: candidate id=0 fov=43.6 focals=[5.0] physicals=[]
resolveUltraWide: ultraWide=null
[useEgoRecorder] start error: 'No ultra-wide physical camera available'
                             | reason: 'no-ultrawide'
```

Isso engana: dá para montar tudo, ver a imagem na prévia e só descobrir o
problema no momento de gravar.

O módulo contém a biblioteca HAL já compilada em
`magisk/videocam/system/vendor/lib64/libgooglecamerahwl_impl.so`. Não é preciso
baixar nem recompilar os 186 GB do AOSP em outro PC. O arquivo selecionado é
convertido para `/vendor/etc/config/emu_camera_video.i420`; o controle fica em
`emu_camera_control.txt` e aceita `play`/`pause` mais uma geração usada para
voltar ao quadro zero.

Use sempre `-camera-back emulated`. `webcam0` e `videofile:` ainda passam pelo
HAL legacy e continuam sem as câmeras físicas exigidas pelo Minute.

---

## 7. Bug para reportar ao dev do Minute

`EgoCameraController.resolveUltraWide` lê `CameraCharacteristics.CONTROL_ZOOM_RATIO_RANGE`
sem checar a versão do Android. Em Android 9/10 isso derruba o app com
`NoSuchFieldError` ao abrir a câmera (log em `docs/minute-crash-camera-android9.txt`).

```kotlin
if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
    // só aqui ler CONTROL_ZOOM_RATIO_RANGE
}
```

E a mensagem *"A câmera deste telefone não está na lista de dispositivos
suportados"* sugere uma allowlist de modelos, quando na verdade é checagem de
capacidade de hardware. Isso levou a horas de investigação na direção errada.

---

## 8. Referência rápida

```
AVD ................ MinutePlay (Android 13, API 33, google_apis_playstore, x86_64)
Modelo forjado ..... SM-S901B (Galaxy S22)
Ultra-wide forjada . física 4, FOV 119,4° (focal 1,7 mm / sensor 4,66×3,50 mm)
Webcams ............ webcam0 = DroidCam (OBS) · webcam1 = Iriun (celular)
Teto de resolução .. 1280×720 quando a fonte é webcam (limite do emulador)
Minute ............. 1.22.0 (versionCode 1004023), React Native + Expo, PAIRIP
```
