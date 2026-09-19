# Iniciar e salvar em todos

Na aba Automação, informe o nome completo da tarefa, selecione **Procurar a tarefa e confirmar as dicas** e **Todos os cadastrados — rodadas conforme a RAM**. Use o mesmo vídeo em todos os participantes na aba Vídeos antes de iniciar. As contas precisam estar logadas no Minute; o painel abre o aplicativo.

O botão liga os celulares um por vez, aguarda o Android iniciar, gira à esquerda, procura a tarefa e prepara a câmera. Depois da contagem e confirmação de gravação em todos os celulares da rodada, libera o vídeo do zero. Salva ao terminar o vídeo ou atingir o limite de 29min59s, incluindo a preparação já gravada pelo Minute.

A capacidade usa a RAM livre do Windows, reserva 2,5 GiB para outros processos e estima 3 GiB por novo celular (2 GiB de Android mais despesas do emulador). A memória é medida novamente após cada inicialização. Não existe limite fixo de dois ou três aparelhos; outros PCs podem comportar mais. O cálculo é conservador e não garante capacidade sob mudanças de carga de outros aplicativos. O painel não fecha outros aplicativos para liberar memória.

Quem não couber fica na fila. Só depois de todos da rodada confirmarem **Salvo**, esses celulares são desligados para liberar memória e a próxima rodada começa. Os aparelhos da última rodada permanecem ligados. Erros interrompem a fila sem desligar celulares cuja gravação não foi confirmada como salva. O painel mostra rodada, contas salvas, pendentes e memória disponível ao iniciar.

**Encerrar agora e salvar** interrompe a gravação e não inicia a próxima rodada. **Parar após salvar esta rodada** termina a rodada atual e interrompe a fila. O loop contínuo só reinicia o conjunto depois de terminar todas as rodadas, mantendo a proteção de limite diário. **Somente os ligados** mantém a execução simultânea manual, sem ligar outros aparelhos.

Para ativar esta versão a partir do código atualizado, abra ABRIR-PAINEL.bat depois que as operações do painel antigo terminarem. Não finalize um processo que esteja gravando. A identidade do painel inclui automation_queue.py para que o atalho não reutilize uma versão antiga.

Validação: testes automatizados de dimensionamento, distribuição sem duplicação, confirmação de salvamento, vídeos incompatíveis, cancelamento e falta de memória, além dos testes existentes de navegação e sincronização.

## Horas e prioridade

A visão geral mostra TOTAL SALVO acumulado e, logo abaixo, o total de hoje. São registros locais confirmados como salvos pelo painel, não uma consulta ao saldo do serviço Minute. A virada do dia zera apenas o indicador diário, sem apagar o acumulado.

A fila prioriza menor uso da tarefa no dia local do PC. Em empate, usa o menor acumulado histórico nessa tarefa. Singular/plural simples e acentos usam a mesma comparação da busca. Contas no limite de 2 horas são puladas; saldos menores que 90 segundos também, para reservar a contagem do aplicativo e o mínimo salvável. Rodadas são reduzidas ao saldo disponível quando necessário. O loop termina quando não há participantes com saldo.

Celulares ligados com maior uso cedem lugar aos prioritários; câmeras abertas e gravações em revisão impedem o desligamento até serem salvas. Nenhum histórico foi inventado ou remanejado entre dias.

## Busca completa e memória ao vivo

A busca usa o título completo, preservando cedilha e acentos. A escrita usa UiAutomator2 3.7.0 pelo campo de acessibilidade, sem converter a consulta em palavras soltas ou enviar teclas ASCII. A leitura de volta exige os acentos informados. O limite da pesquisa é 60 segundos com até quatro posições da lista filtrada, sujeito aos timeouts das operações Android. O servidor auxiliar é encerrado após a escrita para liberar a navegação existente.

Instale essa dependência com setup/INSTALAR-BUSCA-UNICODE.ps1. O instalador de PC novo também executa essa etapa. Os pacotes ficam em LOCALAPPDATA/emulation-cam/automation-runtime. Referência técnica: https://github.com/openatx/uiautomator2 .

A aba Automação mostra RAM livre e total, celulares adicionais que cabem e total simultâneo estimado, atualizados a cada consulta de estado. O cálculo usa a mesma reserva e orçamento da fila; é uma estimativa e não uma garantia de desempenho. Não fecha outros aplicativos.
# Recuperação da abertura do Minute — v2.3.4

A abertura agora usa `am start` com a intenção de launcher, em lugar do processo
`monkey`, que excedeu o prazo de 15 segundos durante uma rodada. Antes de abrir,
confere se o aplicativo já está em primeiro plano. Após timeout, confere novamente
para não tratar um comando concluído com resposta atrasada como falha. Há até
três tentativas, com prazo de 30 segundos por comando de abertura. A confirmação
da tela e da tarefa continua obrigatória antes de gravar.

Validação: testes cobrem recuperação após timeout, falha transitória e esgotamento
das tentativas. Gravações já salvas e limites diários são preservados ao retomar.
