# AutoWord — Condomínio Fácil

Aplicativo Windows para atualizar, individualmente ou em lote, os documentos mensais dos condomínios. Usa Microsoft Word instalado, Python 3.11+ e processamento local. Abra INICIAR.vbs após extrair o pacote da Release.

## Funcionalidades

- Mês/ano e último dia do mês; reconhecimento de CAPA, CAPA LIVRO, ANEXO 1/I e ANEXO 2/II.
- Atualização direta ou em subpasta opcional, preservando arquivos não selecionados.
- Busca em lote na pasta principal, com prévia opcional e validação automática.
- Planilha de responsáveis com associação de colunas e monitoramento seletivo.
- Leitura de renúncias em PDF, inclusive OCR local do Windows, com revisão inicial de identidade e vigência antes da exclusão automática de assinaturas.
- Atualização automática do programa pelas Releases públicas deste repositório, sem token no computador.

## Publicação automática

O workflow .github/workflows/release.yml executa testes em Windows e verifica o pacote. Alterações de código na main publicam uma Release após os testes; pull requests somente testam. A versão é numerada automaticamente como major.minor.número da execução. O job de publicação usa o token automático do GitHub com contents: write; não é preciso upload manual de ZIP.

O atualizador verifica o SHA-256 fornecido pelo GitHub, a versão interna e os arquivos permitidos antes da instalação. Mantém documentos e configurações locais; restaura o código anterior em falhas. A primeira instalação precisa ser feita uma vez; depois abra o aplicativo normalmente. O cache de verificação é de seis horas e pode ser limpo em Opções → Atualizações do aplicativo.

## Privacidade dos documentos

Este repositório contém somente código, instruções e testes sintéticos. Os PDFs e os documentos reais dos condomínios, o texto bruto de OCR, configurações locais e credenciais não são publicados. O pacote de Release é montado por uma lista de arquivos de programa; não inclui testes, exemplos ou documentos. A leitura de renúncias usa pypdf/OCR do Windows localmente, sem enviar os PDFs a APIs de IA.

## Renúncias

Em Opções → Renúncias em PDF, adicione os documentos ou busque nas pastas selecionadas. Confirme condomínio, nome exato no Word, cargo, unidade e início dos efeitos. Datas ambíguas, manuscritos e cláusulas de recebimento exigem conferência inicial. Depois, os meses são atualizados automaticamente. O programa não inventa substitutos e não promove suplentes sem cadastro explícito. Detalhes em CondominioFacil/LEIA-ME.md.

## Desenvolvimento

python -m pip install -r CondominioFacil/requirements.txt

python -m unittest discover -s CondominioFacil/tests -v

python scripts/build_release.py --output dist/CondominioFacil.zip

Os testes de Word são simulados; a integração COM, a disponibilidade de idiomas de OCR e a qualidade do reconhecimento manuscrito dependem do Windows. O workflow verifica também a sintaxe do script de OCR.
