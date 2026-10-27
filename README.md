# AutoWord — Condomínio Fácil

Aplicativo Windows para atualizar, individualmente ou em lote, os documentos mensais dos condomínios. Usa Microsoft Word instalado, Python 3.11+ e processamento local. Abra INICIAR.vbs após extrair o pacote da Release.

## Funcionalidades

- Mês/ano e último dia do mês; reconhecimento de CAPA, CAPA LIVRO, ANEXO 1/I e ANEXO 2/II.
- Atualização direta ou em subpasta opcional, preservando arquivos não selecionados.
- Busca em lote na pasta principal, com prévia opcional e validação automática.
- Planilha de responsáveis com associação de colunas e monitoramento seletivo.
- Impressão dos resultados somente após uma atualização individual concluída.
- Interface simples com controles padrão e paleta clara, sem desenhos personalizados ou animações.
- Atualização automática do programa pelas Releases públicas deste repositório, sem token no computador.

## Publicação automática

O workflow .github/workflows/release.yml executa testes em Windows e verifica o pacote. Alterações de código na main publicam uma Release após os testes; pull requests somente testam. A versão é numerada automaticamente como major.minor.número da execução. O job de publicação usa o token automático do GitHub com contents: write; não é preciso upload manual de ZIP.

O atualizador verifica o SHA-256 fornecido pelo GitHub, a versão interna e os arquivos permitidos antes da instalação. Mantém documentos e configurações locais; restaura o código anterior em falhas. A primeira instalação precisa ser feita uma vez; depois abra o aplicativo normalmente. O cache de verificação é de seis horas e pode ser limpo em Opções → Atualizações do aplicativo.

## Privacidade dos documentos

Este repositório contém somente código, instruções e testes sintéticos. Os PDFs e os documentos reais dos condomínios, o texto bruto de OCR, configurações locais e credenciais não são publicados. O pacote de Release é montado por uma lista de arquivos de programa; não inclui testes, exemplos ou documentos.

## Responsáveis e impressão

Os responsáveis são atualizados pela planilha vinculada ou pelo cadastro manual.
A opção de renúncias em PDF foi retirada, e PDFs não bloqueiam mais a geração.

O botão Imprimir é liberado somente após atualizar um único condomínio com sucesso.
Permite escolher impressora e cópias dos documentos resultantes, verificando se os
arquivos ainda correspondem à atualização. Uma geração em lote nunca libera
impressão, mesmo se depois for selecionado apenas um condomínio. Nenhum documento
é impresso automaticamente. Detalhes em CondominioFacil/LEIA-ME.md.

## Desenvolvimento

python -m pip install -r CondominioFacil/requirements.txt

python -m unittest discover -s CondominioFacil/tests -v

python scripts/build_release.py --output dist/CondominioFacil.zip

A interface é testada no Windows. Word e impressão são simulados nos testes; a validação física da impressão depende do Word e da impressora instalados. Os módulos antigos de PDF permanecem apenas para compatibilidade e não são chamados pela interface.
