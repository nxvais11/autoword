# Validação local — 0.6.0

107 testes locais aprovados. Incluem os recursos anteriores, recuperação de atualizações, proteção de arquivos locais e 17 testes de renúncias: ausência de confusão entre posse/eleição e vigência; recebimento obrigatório; remetente original de e-mail; datas abreviadas; sugestão de nome sem confirmação automática; OCR por processo local sem interpolar o caminho; vigência por competência; PDFs novos/alterados; assinatura e unidade exatas; ausência de promoção de suplentes; preservação de substitutos cadastrados; exclusão idempotente; assinatura não encontrada; meses anteriores após substituição direta; e PDF alterado durante a geração sem publicação do resultado.

Os PDFs reais foram examinados localmente e não são incluídos no código ou nos pacotes. OCR de três digitalizações tipográficas foi exercitado localmente para conferir as sugestões; o manuscrito foi inspecionado visualmente e requer revisão de leitura. O OCR do Windows e o Word COM não foram executados neste ambiente Linux; a sintaxe PowerShell será verificada no workflow Windows. Testes de integração usam serviços simulados.

A primeira execução em Windows identificou diferenças entre caminhos 8.3 e seus nomes completos. A busca de vínculos e prévias passou a aceitar caminhos equivalentes; os testes foram padronizados para caminhos canônicos e incluíram duas regressões específicas.
