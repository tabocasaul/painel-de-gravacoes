# Vídeos grandes e cópias das contas

O painel atual usa [câmera compartilhada](camera-compartilhada.md), que elimina
a cópia integral dos quadros para cada Android. As instruções sobre transferência
com retomada abaixo documentam o mecanismo anterior; a migração das contas e
o armazenamento de 128 GiB continuam válidos.

Painel atualizado: http://127.0.0.1:8768/. O executável e o lançador do projeto
usam essa porta. A biblioteca de vídeos é compartilhada entre o executável e
a execução pelo Python por meio de `video-library.json` na pasta de dados.
Use `ABRIR-PAINEL.bat` para abrir pelo Python instalado. Durante esta atualização,
o Controle de Aplicativo do Windows bloqueou a execução do binário de diagnóstico;
as proteções do Windows foram mantidas.

O painel mede separadamente a importação para o PC, a preparação dos quadros,
a cópia do original e o envio para as câmeras. A porcentagem de uma etapa não
representa a conclusão das etapas seguintes. A instalação só é confirmada
depois do reinício do Android e da verificação do arquivo montado na câmera.

O envio usa blocos de 128 MiB, com SHA-256 de cada bloco, até cinco tentativas
por bloco e um ponto de retomada no emulador. Uma nova tentativa reutiliza os
quadros preparados quando o original e o ajuste de imagem não mudaram.
Celulares que já receberam esse conteúdo são ignorados na repetição.
O vídeo anterior permanece instalado até a conclusão do novo envio.

“Usar em todos” considera todos os aparelhos ativos do painel, inclusive os
desligados. Trabalha com dois por vez e restaura o estado desligado dos que
precisaram ser ligados para a instalação. O registro do vídeo por aparelho
fica em `%LOCALAPPDATA%\emulation-cam\camera-installed.json`.
Instalações anteriores sem registro não recebem um nome presumido.

Os novos aparelhos usam discos virtuais de 128 GiB, com aproximadamente
126 GiB utilizáveis no Android. O tamanho do arquivo original não determina
sozinho o espaço da câmera: os quadros atuais consomem aproximadamente
9,89 MiB por segundo de vídeo. A interface mostra uma estimativa antes do envio.
O painel verifica o espaço disponível no aparelho e no disco físico do PC.
Os discos virtuais compartilham esse espaço físico; a capacidade virtual não
cria armazenamento físico adicional.

As cópias das contas preservam os dados e as chaves do AVD original. Os
originais permanecem em `%USERPROFILE%\.android\avd`; a lista
`%LOCALAPPDATA%\emulation-cam\retired-emulators.json` apenas os oculta do painel.
O relatório `storage-migration.json`, na mesma pasta de dados, registra a
origem, o destino, a capacidade verificada e a tela usada para validar o login.
Não abra o original e sua cópia ao mesmo tempo para a mesma conta.

O botão “Adicionar celular” cria um novo aparelho com 128 GiB a partir do
modelo-base. Ele começa sem uma conta Minute; as cópias das sete contas já
existentes são um procedimento separado e preservam seus respectivos logins.

Validações automatizadas: `test_camera_transfer.py` cobre falhas, retomada sem
duplicar bytes, isolamento entre vídeos e registros persistidos.
`test_panel_upload.py` cobre importação completa, interrupção preservando o
arquivo anterior e bloqueio de importação durante uma instalação.
