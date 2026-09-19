# Painel de Gravações

Painel local para Windows com biblioteca de vídeos, preparação de câmera e
automação de aparelhos Android. **Versão 2.3.43.**

Esta cópia contém o código atual do projeto, inclusive as correções de seleção
de aparelhos, início em grupo, alternância de vídeos e retomada de envios.

## Usar em outro computador

1. Entre na conta do GitHub que tem acesso a este repositório.
2. Clique em **Code → Download ZIP** e extraia a pasta inteira. Também pode usar:

   ```powershell
   git clone https://github.com/tabocasaul/painel-de-gravacoes.git
   ```

3. No Windows, abra o PowerShell na pasta extraída e execute:

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\setup\INSTALAR-NOVO-PC.ps1 -CelularesPlanejados 4
   ```

4. Siga as etapas de instalação das ferramentas, Android/Minute, câmera e contas.
   O instalador inclui etapas manuais e pode solicitar permissão do Windows.
   Consulte as instruções de [instalação detalhada](README-HISTORICO.md#instalar-em-outro-computador--comece-aqui).
5. Abra **ABRIR-PAINEL.bat**. Para acesso rápido, crie um atalho desse arquivo
   na Área de Trabalho.
6. Adicione seus vídeos, conclua a preparação da câmera, escolha as tarefas e
   os aparelhos e inicie pelo botão do painel.

São necessários Windows de 64 bits, virtualização habilitada, espaço em SSD e
memória suficiente para os aparelhos escolhidos. A instalação baixa dependências;
o aplicativo Minute precisa de conexão para acessar tarefas e enviar gravações.

## Recursos atuais

- Participantes escolhidos pelo usuário e quantidade simultânea configurável.
- Início da rodada intercalada condicionado à preparação de todo o grupo previsto.
- Listas de vídeos por tarefa: a cada nova passagem pela tarefa, avança para
  o próximo vídeo da lista e reinicia a lista ao chegar ao fim.
- Ordenação das tarefas em ciclos, histórico local e acompanhamento por aparelho.
- Retomada do envio de gravações aceitas que ainda aguardam upload.
- Biblioteca com renomeação, exclusão para a lixeira, indicação de preparação e
  cancelamento de uma preparação específica.
- Execução da automação local de gravação independente do chat ou do Codex.

O botão do painel inicia a gravação. Baixar ou abrir o código deste repositório
não inicia aparelhos nem gravações automaticamente.

## O que esta cópia preserva

O repositório guarda o painel, scripts, módulos de câmera, recursos da interface,
testes e documentação. A publicação foi feita a partir dos arquivos atuais,
sem incorporar o histórico Git antigo.

**Não é uma clonagem do PC.** Vídeos pessoais, caches de câmera, discos dos
emuladores, sessões de contas, histórico pessoal e configurações de execução
não são enviados ao GitHub. As escolhas guardadas no navegador também são locais.

Para transferir as contas e os celulares existentes, é necessária uma cópia
separada dos discos com os emuladores desligados e ajuste dos caminhos no destino.
Os vídeos podem ser levados separadamente e preparados novamente no computador novo.

## Desenvolvimento e empacotamento

- Código do servidor: `camvideo/modern_server.pyw`.
- Interface: `camvideo/web/`.
- Instalação: `setup/`.
- Compilação opcional do executável: `build-exe.ps1`.
- O workflow **Build Windows package** só é iniciado manualmente em **Actions → Run workflow**.
  O envio inicial ao repositório não executa compilação na nuvem.

Os testes usam simulações; não substituem a validação dos aparelhos no computador
de destino. Os guias antigos estão em [README-HISTORICO.md](README-HISTORICO.md)
e `docs/`; descrições antigas de dois aparelhos, um vídeo por tarefa e tamanho
de cache por aparelho podem se referir a versões anteriores.
