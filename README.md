# AutoWord — Condomínio Fácil

Aplicativo Windows para atualizar, individualmente ou em lote, os documentos mensais dos condomínios. Usa Microsoft Word instalado, Python 3.11+ e processamento local. Baixe AutoWord-Setup.exe na Release para instalar o executável e criar o atalho. Não exige Python instalado; Word continua necessário. O ZIP de código permanece disponível para instalações anteriores.

## Funcionalidades

- Mês/ano e último dia do mês; reconhecimento de CAPA, CAPA LIVRO, ANEXO 1/I e ANEXO 2/II.
- Atualização direta ou em subpasta opcional, preservando arquivos não selecionados.
- Busca em lote na pasta principal, com prévia opcional e validação automática.
- Planilha de responsáveis com associação de colunas e monitoramento seletivo.
- Impressão individual de arquivos existentes ou recém-atualizados, sem exigir atualização.
- Interface simples com controles padrão e paleta clara, sem desenhos personalizados ou animações.
- Atualização automática do programa pelas Releases públicas deste repositório, sem token no computador.

## Publicação automática

O workflow .github/workflows/release.yml executa testes em Windows e verifica o pacote. Alterações de código na main publicam uma Release após os testes; pull requests somente testam. A versão é numerada automaticamente como major.minor.número da execução. O job de publicação usa o token automático do GitHub com contents: write; não é preciso upload manual de ZIP.

O atualizador verifica o SHA-256 fornecido pelo GitHub, a versão interna e os arquivos permitidos antes da instalação. Mantém documentos e configurações locais; restaura o código anterior em falhas. A primeira instalação precisa ser feita uma vez; depois abra o aplicativo normalmente. O cache de verificação é de seis horas e pode ser limpo em Opções → Atualizações do aplicativo.

## Privacidade dos documentos

A comparação textual dos relatórios PDF usa pdfplumber, incluindo texto girado.
A identificação de extratos pelo cabeçalho mantém a leitura rápida com pypdf.
Ambos são carregados somente quando necessários. PDFs sem texto, com formulário
ou leitura incompleta exigem conferência manual; o Word original continua sendo
a fonte da coluna Próxima realização. A comparação textual não verifica aparência
de impressão, assinaturas gráficas ou conteúdo que exista apenas como imagem.

## Abertura e troca de telas

A Central reaproveita o catálogo e a seleção ao voltar da atualização em lote,
sem varrer as pastas novamente. Na abertura seguinte, usa uma lista local dos
condomínios e caminhos já encontrados enquanto confere as pastas em segundo
plano. A lista não substitui a leitura e a validação dos arquivos antes de
atualizar ou imprimir. Mudanças de pastas ou vínculos invalidam esse cache.
Use **Atualizar lista** para procurar condomínios adicionados durante a sessão.

O campo Condomínio mantém a lista em ordem alfabética, sem priorizar os últimos
usados. Digite parte do nome para filtrar, sem diferenciar acentos ou maiúsculas.
Selecione na lista ou pressione Enter quando houver um único resultado. Apagar a
pesquisa mostra todos os nomes. O Controle mensal sempre inclui a lista completa.

Consultas do catálogo e leituras comuns de planilha não impedem fechar a janela.
Se houver uma operação em andamento com documentos, fechar solicita cancelamento
e encerra o aplicativo automaticamente assim que a operação termina com segurança.
Planilhas antigas XLS abertas pelo Excel aguardam a liberação do Excel antes de
encerrar, sem exigir clicar em fechar novamente.

## Mensagens da Central

O painel Resumo mostra o resultado da consulta ou operação, documentos localizados,
envios confirmados e os avisos que exigem ação. Os avisos aparecem antes das
contagens. **Ver detalhes** abre caminhos completos, diferenças dos relatórios,
alterações previstas e o registro da operação. A prévia agrupa alterações repetidas
por documento; o conteúdo completo permanece disponível para conferência.

## Proteção do controle mensal

O histórico é salvo localmente, fora da instalação, com gravação atômica e cópias
da versão recente e anterior. As janelas releem o histórico antes de salvar para preservar
operações registradas por outra janela. A identidade da pasta de rede é mantida
entre execuções, mesmo quando a resolução da unidade mapeada muda.

Em **Controle mensal → Restaurar controle**, escolha os registros da competência
atual no histórico ou no backup e confirme a origem. A recuperação combina os
registros dos condomínios visíveis com os atuais, sem alterar documentos ou outros
meses. Se o arquivo principal faltar ou estiver inválido e existir backup válido,
o aplicativo recupera essa cópia e informa o ocorrido. Um arquivo inválido é
preservado para análise. O backup pode não conter a última operação; registros
que não existem em nenhuma cópia não podem ser reconstruídos automaticamente.

Este repositório contém somente código, instruções e testes sintéticos. Os PDFs e os documentos reais dos condomínios, o texto bruto de OCR, configurações locais e credenciais não são publicados. O pacote de Release é montado por uma lista de arquivos de programa; não inclui testes, exemplos ou documentos.

## Atualizar e imprimir na mesma tela

A Central é a tela principal. Escolha condomínio e competência uma vez e use:

- **Atualizar e imprimir**: atualiza os Words configurados e, após sucesso, imprime os arquivos marcados.
- **Só atualizar**: atualiza o fechamento sem enviar nada às impressoras.
- **Só imprimir**: imprime os arquivos existentes sem alterar mês, dia ou responsáveis.

As caixas da lista escolhem somente a impressão. Em **Opções → Atualização e responsáveis**,
escolha quais Words atualizar, destino, subpasta AAAA-MM, cadastro manual ou planilha.
A conferência de alterações é opcional. Uma falha na atualização impede a impressão
combinada. Uma falha na impressão não desfaz uma atualização já concluída e nunca
provoca reenvio automático. O destino e os nomes dos documentos são preservados.

A ordem é capa, aprovação, anexo I, anexo II e extratos. O relatório de obrigações
é opcional e usa a outra impressora. A coluna Próxima realização do Word original
é verificada contra mês e ano selecionados mesmo quando o relatório está desmarcado.
A comparação do PDF pessoal com o Word do Jurídico continua disponível.

**Atualização em lote** abre a seleção de vários condomínios, com o motor e as
regras existentes. **Voltar à Central** retorna ao fluxo individual. A planilha
continua monitorada enquanto o aplicativo estiver aberto e atualiza somente os
condomínios afetados; não dispara impressão automática.

## Desenvolvimento

python -m pip install -r CondominioFacil/requirements.txt

python -m unittest discover -s CondominioFacil/tests -v

python scripts/build_release.py --output dist/CondominioFacil.zip

A interface é testada no Windows. Word e impressão são simulados nos testes; a validação física da impressão depende do Word e da impressora instalados. Os módulos antigos de PDF permanecem apenas para compatibilidade e não são chamados pela interface.

## Executável e instalador

O CI gera um pacote PyInstaller onedir sem console e um instalador Inno Setup por usuário.
Antes da publicação, abre e fecha a interface do executável, instala silenciosamente
em uma pasta temporária com espaços, testa a versão instalada e repete a instalação
para verificar a preservação de arquivos desconhecidos. Não há Word ou impressora
no runner: essas integrações continuam sendo simuladas nos testes.

O ícone é gerado em múltiplas resoluções no build a partir do desenho de documento
conferido em assets/autoword.svg. Pillow e PyInstaller são dependências apenas de build.
O executável baixa o instalador oficial com hash verificado em segundo plano e o
executa após o processo fechar; não tenta sobrescrever o próprio executável em uso.

## Impressão de Word e PDF

Words são abertos pelo Word instalado, somente para leitura, no caminho original.
A prévia de impressão é preparada antes do envio para preservar o cabeçalho; a
janela do Word pode aparecer brevemente. O aplicativo não salva alterações durante
uma ação de só impressão.

PDFs são encaminhados ao Adobe Acrobat/Reader instalado pelo comando /t com o
nome, driver e porta da impressora selecionada. O AutoWord não converte as páginas
em imagens nem regrava o PDF. O Adobe pode aparecer durante o envio. Configure uma
cópia e somente frente nas preferências das duas impressoras. Preferências incompatíveis
ou Adobe ausente são informados antes de iniciar a impressão. Não é alterada a
impressora padrão do Windows.

A Central aguarda identificar o documento correspondente na fila antes de avançar.
Se não conseguir confirmar, interrompe o restante e pede conferência do Adobe e da
fila. O arquivo pode já ter sido enviado: não existe repetição automática. O comando
/t e as configurações de página dependem da versão do Adobe/driver; a impressão física
precisa ser validada no computador do usuário, inclusive letras nas bordas das tabelas.

Arquivos de exemplo e caminhos pessoais reais não são publicados.

## Controle mensal e histórico local

Controle mensal mostra Pendente, Atualizado, Enviado à impressão, Revisar envio e
Concluído por condomínio e competência. Concluir livro é uma confirmação manual de
conferência das folhas e montagem; envio à fila nunca significa conclusão física.
Atualizações em lote e automáticas também retiram a confirmação de conclusão.

O resumo da Central apresenta Words processados, arquivos enviados, pendências e
tempo da operação, inclusive em falhas parciais. Cada tentativa é registrada antes
do envio e marcada como confirmada após sucesso. Arquivos idênticos já enviados ou
com confirmação incerta exigem confirmação antes de repetir; versões alteradas não
são consideradas duplicatas. Não há reenvio automático. O registro local não é uma
garantia da fila nem impede impressões realizadas fora do aplicativo.

Recentes aparecem primeiro na lista de condomínios. O controle e os tempos ficam em
livros.json na configuração local do AutoWord, sem relatórios nas pastas da rede.
Tempo medido é o tempo das operações da Central, incluindo espera durante o envio,
e não mede exatamente atenção humana ou impressão física. Economia só é estimada
quando o usuário fornece seu tempo manual de referência e conclui livros com
operações registradas. Repetições não contam como novos livros.

## Inicialização

A janela abre antes de consultar a pasta da rede. O caminho canônico usado pelo
controle mensal é preparado no carregamento em segundo plano, preservando os
mesmos identificadores do histórico. A biblioteca de leitura de PDFs só é importada
quando um PDF é lido. Os testes verificam que a montagem da Central não resolve
caminhos de rede na thread da interface. O teste do executável instalado também
registra o tempo de construção da interface; esse valor não inclui toda a partida
do processo nem o tempo de acesso à rede no computador do usuário.

## Competência atual dos Words

Ao selecionar o condomínio, a Central consulta automaticamente os fechamentos em
segundo plano e exibe a competência encontrada, separada do mês escolhido para
atualização. Divergências entre arquivos, datas conflitantes, arquivos ausentes e
falhas de leitura aparecem nos detalhes. A consulta não altera documentos. DOCX é
lido diretamente; DOC utiliza uma instância exclusiva do Word em leitura apenas.
Um cache em memória por caminho e conteúdo evita reler arquivos inalterados, e a
consulta é renovada depois da atualização. Esta identificação não substitui a
conferência opcional das alterações nem muda o fluxo de impressão.

O alerta de Próxima realização considera datas do mês escolhido e de todos os
meses anteriores, inclusive de anos anteriores. Itens anteriores recebem uma
indicação nos detalhes; datas futuras não geram este alerta. A referência é a
competência escolhida, e não o relógio do computador. O relatório original
continua sendo corrigido manualmente e sua impressão permanece opcional.

## Nomes alternativos de extratos

Em Opções → Nomes de extratos, escolha o condomínio e informe um nome alternativo
por linha. Salvar mantém os nomes para todos os meses; o nome da pasta também
continua válido. A identificação busca esses termos no nome do PDF ou no cabeçalho
da primeira página, respeitando palavras inteiras, acentos e nomes compostos. Use
nomes específicos, sem o mês/ano. O cadastro não renomeia nem copia arquivos e não
altera a identificação dos relatórios de obrigações.

Nomes iguais para condomínios diferentes são recusados ao salvar. Se o arquivo
contiver nomes de mais de um condomínio, ele fica pendente com um aviso, sem
escolha automática. Vincular arquivo continua disponível para exceções individuais
na competência escolhida.
