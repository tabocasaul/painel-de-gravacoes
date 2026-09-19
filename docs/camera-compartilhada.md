# Câmera compartilhada e automação

O painel mantém os quadros I420 em um único arquivo no PC. Cada emulador usa
um pequeno disco QCOW2 com esse arquivo como base. O Android recebe uma fonte
de leitura para a câmera; não recebe outra cópia dos 18,2 GiB do exemplo.
O controle de pausa, reinício e reprodução continua separado por celular.

## Trocar o vídeo

1. Importe o original na aba Vídeos.
2. Selecione o vídeo e use **Usar em todos**.
3. Na primeira utilização, aguarde a preparação dos quadros no PC.
4. O painel conecta a fonte às câmeras, reiniciando até dois celulares por vez.
5. Confira o nome do vídeo confirmado em todos e o resultado de cada celular.

Os vídeos preparados ficam em cache, inclusive ao alternar entre arquivos.
A primeira conversão ainda depende da duração, codec e velocidade do PC.
O original fica preservado na biblioteca, sem uma segunda cópia intermediária.
Os arquivos de quadros ativos precisam permanecer no PC: não remova o cache
manualmente. O cartão virtual associado aos quadros é reservado à câmera.

Na validação de 09/09/2026, o vídeo de 31min24s tinha 19.534.348.800 bytes
de quadros. Um celular foi validado primeiro; ativar os seis restantes levou
141,2 segundos, reutilizando os quadros existentes. Todos os sete foram
confirmados por leitura do início, meio e fim pelo caminho real da câmera.
Esse tempo não inclui a conversão inicial nem promete o mesmo desempenho
em qualquer computador.

## Automação

- Informe o nome completo da tarefa, por exemplo **Lavar Louça na Pia**.
- Escolha buscar a tarefa e confirmar as dicas, ou usar câmeras já abertas.
- Escolha todos os cadastrados ou somente os ligados.
- Todos os participantes precisam ter o mesmo vídeo confirmado.
- A preparação gira o emulador para a esquerda, deixando o botão de gravação
  à direita, e abre a tarefa escolhida. Uma falha nessa etapa impede o início.
- O vídeo volta ao primeiro quadro. Após a contagem do Minute e a identificação
  da tarefa, os participantes recebem o comando de reprodução.
- Cada celular encerra ao terminar o vídeo ou alcançar o limite de 29min59s.
  O tempo já gravado durante a preparação entra no limite, com margem para o
  comando de parada. O prazo é local a cada celular e não espera o salvamento
  dos outros. ADB e Android não são sistemas de tempo real: travamentos ou
  desconexões precisam de atenção no celular indicado.
- **Encerrar agora e salvar** interrompe antes do prazo. O Minute exige pelo
  menos um minuto; gravações mais curtas ficam sinalizadas para conferência.
- O painel pausa a prévia, toca Salvar, confirma o diálogo de envio e aguarda
  **Minute salvo.** ou o retorno à navegação. O estado de cada celular e seus
  erros ficam visíveis. Um teste real de 65 segundos percorreu esse fluxo.

As configurações novas usam 2 GiB de RAM por emulador, mantendo 128 GiB de
armazenamento. A fonte compartilhada reduz cópias e espaço, mas não elimina
o consumo de CPU e RAM das gravações. O PC de 16 GiB não foi validado para
20 gravações simultâneas; dimensione a quantidade conforme a memória livre.
O painel recusa novas inicializações quando a memória livre está insuficiente,
em vez de deixar o Android falhar silenciosamente durante o boot.

## Arquivos e compatibilidade

- `frame-cache`: quadros imutáveis e metadados de reutilização.
- `shared-disks`: pequenos discos por emulador e vídeo.
- `shared-cameras.json`: vínculo persistente entre emulador e fonte no PC.
- `camera-installed.json`: confirmação e modo de cada câmera.
- `shared-camera.sh`: identifica o disco pelo tamanho e assinatura, marca como
  somente leitura e conecta ao caminho consumido pela HAL no Android.

Esses dados ficam em `%LOCALAPPDATA%\emulation-cam`. Os arquivos antigos e os
envios parciais foram preservados. As contas e seus dados não são substituídos.
O mecanismo anterior de cópia com retomada permanece no código para
compatibilidade, mas o painel atualizado usa a fonte compartilhada.

### Velocidade de reprodução

A HAL usa um relógio monotônico compartilhado para selecionar o quadro a 30 fps.
Solicitações adicionais da prévia ou do gravador reutilizam a posição temporal;
elas não consomem o próximo quadro. Cada thread mantém seu próprio buffer para
evitar que outra saída altere os pixels durante a conversão. Pausar conserva o
tempo acumulado; mudar a geração reinicia no quadro zero. Ao chegar ao fim, a
posição volta ao começo do vídeo.

O patch `patches/emulated-camera-video.patch` inclui `VideoPlaybackClock.h`.
O teste independente pode ser executado em Linux/WSL com:

```sh
g++ -std=c++17 patches/test-video-clock.cpp -o /tmp/test-video-clock
/tmp/test-video-clock
```

Ele cobre solicitações a 30, 60 e 120 Hz, saídas duplicadas, pausa, retomada e
reinício. A biblioteca compilada fica no módulo `magisk/videocam`; os celulares
existentes precisam receber essa biblioteca e reiniciar para carregar a mudança.

### Repetição automática

Na aba Automação, escolha **Loop contínuo — repetir até eu parar** e informe o
nome completo da tarefa. A busca automática fica selecionada nesse modo. Os
mesmos celulares e o mesmo vídeo são usados em todas as rodadas. Cada rodada
reinicia os quadros do zero e mantém o limite de 29min59s.

A próxima rodada só começa depois que todos confirmam o salvamento. Falhas de
preparação, gravação ou salvamento interrompem o loop, assim como o limite diário
de 2 horas por tarefa e conta. O contador mostra a rodada atual e quantas foram
salvas. **Parar após salvar esta rodada** conclui a rodada sem iniciar outra;
**Encerrar agora e salvar** interrompe a gravação atual e também encerra o loop
(gravações com menos de um minuto continuam sujeitas ao mínimo do Minute).

O loop depende do painel permanecer aberto como processo no PC; ele não é
retomado automaticamente após desligar o computador ou reiniciar o servidor.
