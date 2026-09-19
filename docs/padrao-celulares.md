# Padrão operacional dos celulares — v2.3.33

Este guia descreve o ambiente esperado pelo código do projeto. Não existe uma
configuração que garanta ausência de falhas ou aceitação de toda gravação pelo
Minute. A confirmação técnica de envio é diferente da aprovação do conteúdo.
Use contas, tarefas e conteúdo permitidos pelo serviço no seu ambiente de teste.

## 1. Padrão de todos os celulares

| Item | Estado esperado antes de iniciar |
|---|---|
| Sistema | AVD do projeto, Android 13 / API 33, x86_64 com Google Play, criado pelos scripts de instalação. |
| Cadastro | Cada AVD com nome, porta e serial próprios e corretos no painel. Não executar duas instâncias do mesmo AVD. |
| Inicialização | Android terminou o boot; ADB mostra `device`, nunca `offline` ou `unauthorized`. |
| Minute | Instalado pela Play Store, conta correta conectada e lista de tarefas acessível, sem tela de login, atualização ou diálogo bloqueando. |
| Permissões | Permissões solicitadas pelo aplicativo concedidas, especialmente câmera e microfone; confira dentro das configurações do Android. |
| Interface | Nomes e identificadores das tarefas disponíveis no aplicativo. A automação foi desenvolvida para a interface observada; mudanças do Minute podem exigir atualização do código. |
| Câmera | Integração de câmera do projeto instalada e prévia validada. Abra o AVD pelo painel, que aplica os parâmetros de câmera esperados. |
| Vídeo | Arquivo original presente na biblioteca e preparação concluída; tarefa vinculada ao vídeo correspondente. Não remover nem mover o arquivo/cache durante a execução. |
| Captura anterior | Nenhuma gravação ou tela de revisão abandonada. Se houver uma, conferir e salvar antes de iniciar outra; não limpar dados do aplicativo. |
| Armazenamento | Espaço disponível tanto no SSD do PC quanto no Android para cache e capturas. A capacidade configurada do disco virtual não representa espaço livre real. |
| Rede e horário | Internet estável para o aplicativo e envio; relógio e fuso corretos. O histórico diário segue a data local do PC. |

O instalador configura 2048 MiB de RAM e partição de dados de 128 GiB para o AVD.
Isso não garante que vários aparelhos caibam na memória física: Android, câmera,
Windows e demais processos também consomem recursos. O lançamento atual usa GPU
`auto`, fuso `America/Sao_Paulo` e não restaura snapshots. Mantenha o mesmo conjunto
de scripts e componentes testados; não copie somente um arquivo de configuração
sobre um aparelho em execução.

O pipeline atual prepara imagem em 1280 × 720, 30 fps. Essa é a configuração do
projeto, não uma especificação oficial de elegibilidade do Minute. Uma prévia
visível sozinha não prova que a gravação começou: o sistema também verifica a
sessão e o crescimento do arquivo. O áudio da voz/TikTok tem fluxo separado.

## 2. Como iniciar corretamente

1. Execute `ABRIR-TUDO.bat` e abra o painel atual. Confira a versão no rodapé.
2. Na biblioteca, confira o vídeo e aguarde sua preparação terminar.
3. Abra **Automação → Gravação sincronizada** e escolha o plano.
4. No plano intercalado, selecione um celular com acesso às tarefas e use
   **Atualizar tarefas do Minute** quando precisar renovar o catálogo. A lista
   representa esse celular; outras contas podem ter tarefas diferentes.
5. Marque as tarefas desejadas e selecione um vídeo para cada uma. O catálogo
   importado neste ambiente tinha 65 tarefas; essa quantidade pode mudar.
6. Confira os participantes e clique **Iniciar e salvar em todos** no painel.
   Não é necessário abrir todos os emuladores manualmente.
7. Confira o andamento de cada celular: tarefa correta, imagem em movimento,
   cronômetro avançando e, ao encerrar, confirmação de salvamento/envio.

As escolhas do randomizador ficam no navegador. Depois de iniciar, as opções
do supervisor também são persistidas no PC para recuperação do servidor.

## 3. Planos, duração e distribuição

- **Plano diário:** completa o saldo de hoje de uma categoria antes de avançar
  para a próxima. O plano atual contém louça, ervas e jardim.
- **Plano intercalado:** sorteia a ordem das tarefas selecionadas; percorre o
  ciclo antes de repetir e evita repetição imediata quando há alternativa elegível.
  Troca o vídeo somente depois que o par terminou e salvou.
- **Tarefa única:** usa a tarefa e a repetição escolhidas no painel.
- O teto local é **7200 segundos por tarefa, celular e dia**. Uma categoria não
  gasta o saldo de outra. O histórico é preservado ao virar o dia.
- Cada captura termina ao acabar o vídeo ou chegar a **29min59s**, considerando
  também o tempo de preparação já gravado. Vídeos curtos produzem rodadas menores.
- Saldos inferiores a 90 segundos não iniciam nova captura; por isso pode restar
  uma pequena diferença para 2 horas. O aplicativo impõe duração mínima para salvar.
- O modo fixo prepara dois aparelhos e prioriza os com menor uso. Se apenas um
  tiver saldo elegível, ele termina sozinho. Tentar com pouca RAM não garante
  estabilidade nem capacidade para manter o par.

## 4. Recuperação automática

O supervisor é ativado ao iniciar pelo painel. Não é uma tarefa cron do GPT.

| Situação | Comportamento implementado |
|---|---|
| Falha na preparação, gravação ou salvamento | Registra o erro e tenta recuperar com espera progressiva de 30 a 120 segundos. |
| Captura pendente conhecida | Confere a sessão, tenta salvar e aguarda confirmação de envio; não a descarta automaticamente. |
| Queda após salvar, antes de contabilizar | Usa o identificador da sessão para evitar crédito duplicado; mantém o dia original da captura. |
| Aplicativo ocioso travado, sem pendências | Pode fechar o app/emulador identificado como ocioso e preparar a próxima tentativa. |
| Servidor caiu | O processo auxiliar local tenta relançá-lo com o plano salvo. |
| Servidor sem resposta | O auxiliar verifica a saúde aproximadamente a cada 10 segundos; ausência de resposta por cerca de 120 segundos pode provocar reinício. |
| Trabalho sem progresso | Aproximadamente 12 minutos sem atualização relevante pode provocar reinício; espera normal pelo próximo dia é excluída. |
| Usuário pede para parar | Desativa a retomada automática. Use os botões do painel para encerrar/salvar ou parar após a rodada. |

O auxiliar acompanha apenas o processo que iniciou a execução. Na versão em
código-fonte Python ele é lançado pelo servidor; o caminho empacotado como
executável não inicia esse auxiliar atualmente. Fechar uma aba do navegador não
é o mesmo que parar a execução. Use **Parar após salvar esta rodada** quando quiser
um encerramento ordenado.

Apenas aparecer “Minute salvo” não basta para contar o tempo: o código procura a
confirmação da sessão aceita e enviada. Isso confirma o registro técnico observado,
não aprovação final do conteúdo. Capturas ambíguas, envio que nunca confirma,
conta desconectada ou mudança da interface podem continuar exigindo intervenção.

## 5. Se algo não funcionar

| Sintoma | O que conferir |
|---|---|
| Só um celular iniciou | Saldo por tarefa, disponibilidade do segundo aparelho, estado ADB, erro no card e recursos do PC. |
| Celular parado na tela inicial | Boot concluído, login e abertura do Minute; leia o erro de preparação antes de reiniciar manualmente. |
| Prévia parada ou vídeo acelerado | Vídeo selecionado, preparação e movimento real; não iniciar novas capturas até validar a fonte. |
| Parado em revisão/salvamento | Internet, confirmação do envio e estado do supervisor; preserve a captura. |
| Painel não abre | Reabra pelo iniciador e confira o endereço atual; a porta pode ter mudado. |
| Tarefa não encontrada | Atualize o catálogo usando a conta correspondente e confira se a tarefa está disponível nessa conta. |

Antes de deixar o PC sem acompanhamento, valide uma rodada completa com os
aparelhos desejados e confirme que a próxima começa. Mantenha o computador ligado,
na energia, com suspensão/hibernação desativadas durante o uso e SSD com folga.
O supervisor não funciona com o Windows desligado ou suspenso e não substitui
reinicialização automática após uma queda de energia.

## 6. Dados locais e atualização

Os arquivos abaixo ficam em `%LOCALAPPDATA%/emulation-cam/` e não devem ser
publicados com contas, sessões ou dados pessoais:

- `controle-tarefas.json`: histórico e identificadores já contabilizados.
- `loop-supervisor.json`: intenção de execução, plano e capturas pendentes.
- `minute-catalog.json`: último catálogo importado.

Faça backup antes de manutenção; não apague esses arquivos para tentar destravar
uma captura. Vídeos pessoais, AVDs, logins, chaves de API e caches não acompanham
o GitHub. O repositório contém código, testes e documentação.

## 7. Validação desta versão

Há testes automatizados de fila, limite diário, alternância de tarefas, catálogo,
recuperação persistente, contagem única e processo auxiliar. A seleção de tarefa e
vídeo também foi conferida no painel após recarregar a página. Isso não equivale a
um teste ininterrupto de um dia inteiro nem garante compatibilidade com futuras
versões do Minute.
