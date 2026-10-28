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
