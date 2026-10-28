# Instalação do AutoWord no Windows

Baixe **AutoWord-Setup.exe** na Release e execute uma vez. O instalador cria o
atalho AutoWord na área de trabalho e no menu Iniciar. Python não precisa estar
instalado. Microsoft Word continua necessário; para planilhas XLS, também Excel.

A instalação é por usuário, sem exigir administrador, em
`%LOCALAPPDATA%\Programs\AutoWord`. O ícone identifica documento conferido.
A interface permanece simples, com a paleta clara e controles padrão.

O executável verifica novas Releases em segundo plano. Depois de baixar e
verificar o SHA-256 do instalador, avisa na tela. Feche o AutoWord para instalar
e reabrir automaticamente. O processo aguarda o programa encerrar para substituir
os arquivos. Sem internet, a versão instalada continua funcionando.

Configurações e cadastros continuam em `%LOCALAPPDATA%\CondominioFacil`; o
instalador não apaga essa pasta nem altera os documentos dos condomínios.
Não abra a versão antiga por INICIAR.vbs ao mesmo tempo que o novo atalho.

O ZIP de código continua disponível para instalações anteriores. O atualizador
dessa versão não converte automaticamente uma instalação Python em executável:
faça a primeira instalação pelo Setup. Depois use somente o atalho AutoWord.

---

# Condomínio Fácil 0.6.0

Aplicativo local para Windows, Python 3.11 ou superior e Microsoft Word instalado e ativado. Abra **INICIAR.vbs** após extrair o ZIP para iniciar sem janela de CMD. A primeira execução pode levar alguns minutos enquanto prepara o ambiente sem abrir o CMD e instala a dependência pywin32 já usada pelo programa; a leitura de PDF usa também pypdf; o OCR é o mecanismo local do Windows. Se precisar instalar Python, use https://www.python.org/downloads/windows/ com Python Launcher e Tcl/Tk.

## Uso diário

1. Selecione a pasta dos condomínios ou diretamente a pasta com os arquivos Word.
2. Confira **Salvar em**. Ao escolher um único condomínio, o programa preenche sua pasta. Em lote, deixar o destino vazio usa a própria pasta de cada condomínio. Você pode selecionar ou digitar outra pasta.
3. Escolha mês e ano.
4. Deixe **Criar subpasta (AAAA-MM)** desmarcado para substituir os documentos existentes diretamente no destino, com os mesmos nomes. Marque apenas se quiser salvar dentro de uma subpasta como `2026-11`.
5. Clique diretamente em **Atualizar documentos**. Se quiser ver a prévia antes, use **Conferir alterações (opcional)**. As validações são executadas automaticamente na geração.

Somente os documentos selecionados são substituídos. Outros arquivos são mantidos, inclusive os documentos que você não selecionou. Não são criados lotes com data/hora, relatórios nem cópias adicionais na pasta do condomínio. Se um arquivo ainda não existir no destino, ele é criado com o nome do documento de origem.

Quando vários condomínios estiverem selecionados e você indicar outra pasta de destino, cada condomínio terá sua própria pasta de mesmo nome dentro dela, evitando colisões entre documentos. Com destino vazio, cada um é atualizado em sua própria pasta; a opção de subpasta continua sendo aplicada individualmente.

## Reconhecimento de nomes dos documentos

Os nomes completos anteriores continuam aceitos. A versão 0.4.1 também identifica automaticamente:

| Tipo | Exemplos de nomes aceitos |
| --- | --- |
| Aprovação | APROVAÇÃO DE CONTAS |
| Capa do livro | CAPA, CAPA LIVRO, CAPA DO LIVRO, CAPA DE LIVRO |
| Anexo I | ANEXO 1, ANEXO I, ANEXO1, PRESTAÇÃO DE CONTAS ANEXO 1, PRESTAÇÃO DE CONTAS ANEXO I |
| Anexo II | ANEXO 2, ANEXO II, ANEXO2, PRESTAÇÃO DE CONTAS ANEXO 2, PRESTAÇÃO DE CONTAS ANEXO II |

São aceitas extensões .doc e .docx, diferenças de maiúsculas e acentos e separadores por espaço, hífen ou sublinhado. A mesma regra é aplicada na seleção individual e na busca em lote dentro das pastas de fechamento.

O aplicativo mantém os nomes reais na geração: CAPA.doc continua CAPA.doc, sem criar uma segunda cópia chamada CAPA LIVRO.doc. O reconhecimento usa padrões completos; nomes como CAPA ANTIGA, CAPA CONTRATO, ANEXO III ou ANEXO 10 não são escolhidos por semelhança.

Se houver dois candidatos para o mesmo tipo, como CAPA.doc e CAPA LIVRO.doc na mesma pasta, a ambiguidade é sinalizada com os nomes dos arquivos. O aplicativo não escolhe o primeiro nem o mais recente. Use **Opções → Selecionar os 4 arquivos…** para definir qual usar; a seleção manual salva continua tendo prioridade. O conteúdo dos documentos continua sendo validado durante a atualização.

## Atualizar todos os condomínios no fim do mês

Selecione a pasta principal, por exemplo `Z:\_CONDOMÍNIOS ATIVOS`. O aplicativo procura os documentos de cada condomínio, inclusive dentro de pastas como `FECHAMENTO DE LIVRO`, `FECHAMENTO DE LIVROS` e `PRESTAÇÃO DE CONTAS`. Os nomes dos condomínios são mantidos na lista para facilitar a identificação e a associação com a planilha.

Todos os condomínios encontrados ficam selecionados automaticamente. Escolha mês/ano e clique em **Atualizar documentos**, sem precisar entrar em cada pasta nem executar a prévia. O botão **Selecionar todos** permite restaurar a seleção completa. Para atualizar só alguns, use Ctrl ou Shift na lista.

Deixe **Salvar em** vazio para atualizar cada condomínio na própria pasta. A opção **Criar subpasta (AAAA-MM)** vale para todos os selecionados. Pastas de competências anteriores, como `2026-10`, e lotes antigos com data/hora não são percorridos como novos condomínios. Se duas pastas de fechamento forem encontradas dentro do mesmo condomínio, o aplicativo sinaliza a ambiguidade e pede a seleção individual da pasta correta.

Uma falha em um condomínio não interrompe os demais. A tela mostra o progresso, como `Atualizando 18/70`, e um resumo ao concluir com a quantidade processada, os documentos gravados e os condomínios pendentes de revisão. Não são criados relatórios.

## Otimizações de processamento

A geração direta usa uma única sessão de Word para o lote e faz a validação por condomínio quando necessário. Uma prévia disponível pode ser reutilizada, sem obrigar uma nova conferência. Depois de uma atualização, a prévia daquele condomínio é descartada para não reaproveitar referências antigas.

A edição e o salvamento do Word passam a ocorrer em um temporário local. Depois da confirmação de salvamento pelo próprio Word, o resultado é transferido para a área temporária de publicação no destino e substitui o arquivo correspondente. Isso reduz as operações do Word sobre a unidade de rede. A reabertura adicional de cada documento após salvar foi removida; a confirmação de conteúdo e a propriedade de salvamento do Word continuam sendo verificadas. Os temporários são removidos ao terminar.

Arquivos sem mudanças continuam evitando regravações. O desempenho real depende do computador, da versão do Word e da rede; não há promessa de tempo fixo para os 280 documentos. As otimizações específicas de Word precisam de validação no Windows.

## Opções reunidas

O botão **Opções…** reúne funções usadas ocasionalmente:

- Escolher quais documentos atualizar: aprovação, capa, anexo I e anexo II.
- Selecionar os quatro arquivos manualmente quando os nomes forem diferentes. São aceitos .doc e .docx, sem conversão.
- Editar responsáveis do condomínio selecionado.
- Importar ou desvincular a planilha de responsáveis.

Para editar responsáveis ou selecionar arquivos, selecione somente um condomínio na lista antes de abrir a opção correspondente. A importação e a seleção de arquivos mantêm os cadastros existentes.

## Substituição direta e continuidade

A substituição direta é autorizada pelo próprio modo escolhido: **Criar subpasta** desmarcado. Não há uma etapa adicional de confirmação a cada arquivo. Faça o primeiro teste com um condomínio e confira os resultados no Word.

Ao substituir o próprio arquivo de origem, o aplicativo conserva internamente o modelo necessário para novas trocas de mês e para preencher novamente os marcadores de responsáveis. Ele usa o arquivo de configuração já existente, sem criar outros documentos na pasta do condomínio. Isso permite continuar as atualizações após reabrir o programa. Se você editar o arquivo no Word, a alteração é reconhecida e passa a valer como novo modelo; mantenha os marcadores necessários caso queira continuar preenchendo campos de planilha.

A gravação usa temporários somente enquanto o Word salva e confere o resultado. Eles são removidos ao terminar ou falhar. Uma falha durante a preparação preserva o arquivo existente. Em encerramento forçado, falha de energia ou falha do sistema de arquivos no momento de publicar vários documentos, confira o resultado antes de usar o lote.

## Importar planilha de responsáveis

1. Selecione primeiro a pasta dos condomínios.
2. Em **Opções…**, clique em **Importar planilha de responsáveis…** e escolha CSV, TSV, XLSX ou XLS.
3. Selecione a aba, quando houver. Em XLSX, a lista de abas é preenchida; em XLS, pode digitar o nome da aba ou deixar vazio para usar a primeira.
4. Mapeie a coluna de condomínio. Os cabeçalhos reais aparecem exatamente como no arquivo, incluindo acentos, espaços e capitalização; o programa não renomeia nenhuma coluna nem modifica a planilha.
5. Para assinaturas dos modelos antigos, mapeie nome e cargo e, se aplicável, apartamento e nome que consta no documento original. Para modelos inteiramente baseados em marcadores, o mapeamento de nome pode ficar vazio.
6. Quando o nome/código da planilha for diferente do nome da pasta, use **Associar um nome ou código diferente a uma pasta…**. Repita para os valores necessários.
7. Clique em **Vincular e monitorar**. O painel informa o número de cada linha não associada ou ambígua. Essas linhas não são aplicadas a outro condomínio por aproximação.

A primeira linha não vazia da aba deve conter cabeçalhos únicos e não vazios. Cada linha seguinte representa um responsável. Um condomínio pode ter várias linhas. CSV aceita vírgula, ponto e vírgula ou tabulação, em UTF-8 ou Windows-1252. XLSX é lido sem Excel instalado. XLS binário precisa de Microsoft Excel instalado e usa a dependência pywin32 já existente. Fórmulas em XLSX precisam ter resultados salvos: recalcule e salve no Excel se houver aviso. Identificações devem preferencialmente estar como texto; zeros iniciais com formatos simples e máscaras usuais de CPF/CNPJ são preservados. Formatos numéricos personalizados complexos podem precisar ser convertidos em texto na fonte.

## Campos nas capas e documentos

Os dados de qualquer coluna podem preencher marcadores no corpo dos modelos Word:

- `{{Nome completo}}` usa a coluna chamada exatamente `Nome completo`.
- `{{CPF / RG}}` usa exatamente a coluna `CPF / RG`.
- `{{Síndico|Nome completo}}` escolhe a linha cujo valor na coluna mapeada de cargo é `Síndico`.
- `{{ID=Conselho 1|CPF}}` escolhe a linha cuja coluna chamada exatamente `ID` tem valor `Conselho 1`, útil para vários conselheiros do mesmo cargo.

Marcadores simples exigem uma única linha ou o mesmo valor em todas as linhas daquele condomínio. Se houver vários valores possíveis, a conferência bloqueia o campo e pede um seletor. Nomes de colunas são sempre exatos; a comparação de valores de associação ignora diferenças de maiúsculas, acentos e espaços repetidos.

Dados sem um marcador no modelo não são acrescentados em posições adivinhadas. Nos documentos de aprovação antigos, os blocos de assinatura já existentes podem receber nome, cargo e apartamento. Para vários conselheiros, uma coluna mapeada de nome original permite indicar exatamente qual assinatura atualizar. Não há inclusão ou exclusão automática de blocos de assinatura. Para CPF, RG, datas de mandato e outros campos novos, inclua seus marcadores na posição desejada do modelo. Cabeçalhos, rodapés e caixas de texto com datas continuam exigindo revisão específica.

Enquanto a planilha estiver vinculada, seus dados têm prioridade sobre o cadastro manual dos responsáveis nos condomínios associados. Não havendo linha associada, a geração daquele condomínio é bloqueada e sinalizada. **Opções → Desvincular planilha** restaura o uso do cadastro manual. O cadastro manual existente e suas vigências continuam disponíveis como antes.

## Atualizações automáticas

Com o aplicativo aberto, o arquivo é verificado aproximadamente a cada 3 segundos. Uma mudança no conteúdo recarrega os dados sem nova importação. Apenas os condomínios cujo conjunto de dados mudou são afetados; reordenar linhas/colunas, tocar na data do arquivo ou salvar os mesmos dados não provoca regeneração.

Se já houver uma geração registrada, somente os documentos afetados da **última geração de cada condomínio** são atualizados, no mesmo destino e na mesma competência. Não são criados novos lotes pelo monitor e outras competências históricas não são atualizadas. Uma mudança em coluna que não alimenta nenhum campo do documento não regrava esse documento. Documentos não selecionados na geração original não são acrescentados automaticamente.

O vínculo com a planilha, as associações, os destinos anteriores e as impressões de conteúdo são mantidos no arquivo de configuração já existente. Ao reabrir o aplicativo, selecione a pasta dos condomínios: o monitoramento é retomado sem importar de novo, e mudanças ocorridas com o programa fechado são detectadas. O programa precisa estar aberto para efetuar atualizações; ele não instala serviço de Windows nem tarefa agendada.

Se a planilha estiver temporariamente indisponível, inválida ou em gravação, o aplicativo avisa e preserva os documentos existentes. A leitura é tentada novamente. Atualizações automáticas de documentos que falharem são sinalizadas e tentadas novamente após aproximadamente 15 segundos. Cancelar interrompe a fila automática pendente. Linhas removidas deixam o condomínio pendente de revisão, sem apagar documentos nem restaurar nomes antigos silenciosamente.

## Arquivos de configuração e cuidados

As configurações continuam em `%LOCALAPPDATA%\CondominioFacil`: `responsaveis.json` para o cadastro manual e `arquivos.json` para os arquivos escolhidos, os modelos internos necessários à substituição direta e o estado de retomada. Nenhum arquivo de controle é criado junto dos documentos. Não são mais criadas cópias .bak das configurações; faça seu próprio backup desses dois arquivos se desejar. Configurações antigas são aceitas e as pastas e os nomes dos documentos são preservados.

Não edite os modelos durante o processamento. Alterações depois da conferência interrompem a gravação daquele condomínio. Macros são desabilitadas e links externos não são atualizados. Os documentos e os dados da planilha são processados localmente.

A primeira validação visual deve ser feita com cópias de um condomínio: abra os resultados no seu Word e confira datas, campos e assinaturas antes do uso em lote. Nomes longos podem alterar quebras de linha. A integração Word/Excel e a interface precisam de validação no Windows; os testes deste pacote verificam as regras e o fluxo de arquivos com um serviço de documentos simulado.

## Testes

Na pasta do aplicativo, execute `python -m unittest discover -s tests -v`. Os testes não precisam de Word para executar. O GitHub Actions valida regras, arquivos, impressão simulada e interface no Windows antes de publicar.

## Abertura sem console

Use **INICIAR.vbs** com dois cliques. Ele prepara o ambiente quando necessário em segundo plano e inicia a interface com pythonw.exe. O aplicativo fica sem uma janela de CMD ao lado. INICIAR.bat permanece compatível e encaminha a abertura para o iniciador sem console; ao usar o BAT pode haver um breve aparecimento do console antes de ele fechar.

Falhas de preparação aparecem em uma caixa de mensagem. Erros de inicialização e da interface também são mostrados na tela, sem criar arquivos de log. A primeira abertura exige internet para a dependência já usada pelo programa; as seguintes são locais. A abertura no Windows deve ser conferida no seu computador.

## Responsáveis pela planilha

A leitura de renúncias em PDF foi retirada da interface e do fluxo automático.
PDFs existentes na pasta não bloqueiam a geração. As alterações dos responsáveis
devem ser feitas na planilha vinculada ou no cadastro manual. Registros antigos
de renúncia permanecem no cadastro local, mas não são aplicados pelo aplicativo.

## Impressão individual

Selecione a pasta e um único condomínio na lista para habilitar **Imprimir**.
Não é preciso atualizar o Word antes. São usados os documentos já existentes
na pasta selecionada, somente dos tipos marcados em **Opções**. Não é feita
alteração de competência, datas, responsáveis ou conteúdo para imprimir.

Se você acabou de atualizar um condomínio, o botão usa os resultados dessa
atualização, inclusive quando foram salvos em outro destino ou subpasta.
Ao mudar a seleção ou as opções, volta a usar os arquivos da pasta selecionada.

A janela identifica os arquivos e permite escolher impressora e cópias.
Documentos ausentes ou ambíguos devem ser vinculados nas opções antes de imprimir.
Se algum arquivo mudar depois de abrir a janela, feche e selecione novamente.
A impressão continua restrita a um condomínio por vez e não ocorre automaticamente.
Nenhum PDF ou cópia intermediária é criado para imprimir.

Cancelar impede os próximos documentos; páginas já enviadas precisam ser
canceladas na fila do Windows. O envio é testado com Word simulado no CI;
a impressão física depende do Word, da impressora e de seus drivers.

## Atualizações automáticas do próprio aplicativo

O repositório configurado é `nxvais11/autoword`, criado como público. Apenas código, testes sintéticos e instruções são publicados. Documentos, PDFs de exemplo, cadastros e credenciais ficam fora do Git e das Releases. Por ser público, a atualização não precisa de senha ou token no computador.

Após receber esta versão uma vez, continue abrindo por **INICIAR.vbs**. O iniciador consulta Releases estáveis, com cache de seis horas, verifica o SHA-256 fornecido pelo GitHub e a versão interna e substitui apenas o código antes da abertura do programa. Para forçar uma nova consulta na próxima abertura, use **Opções → Atualizações do aplicativo**. Não há CMD permanente.

Em erro de conexão, a versão instalada continua disponível. Em falha de instalação, o código anterior é restaurado. Cadastros, modelos internos e documentos dos condomínios não são substituídos pelo atualizador. O estado da consulta fica em `%LOCALAPPDATA%\CondominioFacil\atualizacao.json`; nenhum token é necessário para este repositório público.

O GitHub Actions executa os testes e monta uma Release numerada a cada alteração de código enviada à branch main. Somente depois dos testes a versão é publicada; não é preciso montar ou subir ZIP manualmente nas próximas alterações.

## Interface 0.8

A tela principal usa cinza suave, branco e azul acinzentado nas ações.
A interface voltou aos controles padrão do Tk, sem cantos personalizados,
imagens geradas ou animações. As cores são aplicadas diretamente aos controles.
Opções reutiliza a mesma janela, e o registro continua sendo atualizado em blocos.
Origem, destino e competência ficam no topo; a lista mostra a quantidade de
condomínios selecionados. A conferência continua opcional.

O registro fica em **Mostrar detalhes**. Abre automaticamente na conferência
e nos avisos de revisão/erro, sem criar arquivos de relatório.
**Opções** mantém responsáveis, planilha, seleção dos documentos e atualizações.

Atalhos: **Ctrl+O** abre uma pasta, **Ctrl+Enter** atualiza, **F1** abre as opções
e **Ctrl+A** seleciona todos quando o foco está na lista. Durante uma tarefa,
os controles ficam bloqueados e **Cancelar** permanece disponível.

