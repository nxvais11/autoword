"""Resumos da Central; detalhes completos continuam disponíveis para conferência."""
from pathlib import Path
from document_period import period_summary
from book_history import file_id
from textwrap import shorten


def message(summary,details):
    return {'summary':summary,'details':details}


def search_message(result,selected):
    rows=result['rows'];warnings=list(dict.fromkeys(result.get('warnings',[])))
    closing=[r for r in rows if r['group']=='closing']
    statements=[r for r in rows if r['group']=='statement' and r.get('path')]
    report_selected=any(i in selected and r['group']=='obligations' for i,r in enumerate(rows))
    lines=[f"{result['name']} · competência selecionada: {result['period'][5:]}/{result['period'][:4]}",
           f"Fechamento: {sum(bool(r.get('path')) for r in closing)}/{len(closing)} documentos localizados.",
           f'Extratos: {len(statements)} localizado(s).',
           'Obrigações: selecionadas para impressão.' if report_selected else 'Obrigações: fora da impressão.']
    attention=[]
    missing=[r['label'] for i,r in enumerate(rows) if not r.get('path') and (r['group']=='closing' or i in selected)]
    if missing:attention.append('Vincule os arquivos ausentes: '+', '.join(dict.fromkeys(missing))+'.')
    if any(not r.get('printer') for i,r in enumerate(rows) if i in selected):
        attention.append('Configure a impressora dos documentos selecionados em Opções.')
    period=period_summary(result)
    if '\n' in period:attention.append(period.splitlines()[0]+' Abra Ver detalhes para conferir cada arquivo.')
    due=result.get('due_obligations',[])
    if due:
        attention.append(f'Obrigações a revisar: {len(due)} até esta competência, incluindo meses anteriores.')
        attention.extend(due[:3])
        if len(due)>3:attention.append(f'Mais {len(due)-3} obrigação(ões) em Ver detalhes.')
    for warning in warnings:
        if warning==result.get('due_notice') or warning==period:continue
        if not report_selected and warning.startswith(('PDF pessoal:','Word do Jurídico:')):continue
        if 'Próxima realização' in warning or warning.startswith('Word original não localizado'):
            attention.append('Não foi possível conferir os vencimentos das obrigações. Revise o Word do Jurídico.');continue
        attention.append(warning)
    attention=list(dict.fromkeys(attention))
    if attention:
        # Os avisos vêm antes das contagens para ficarem visíveis sem rolar.
        lines=lines[:1]+['Atenção:']+[shorten(' '.join(v.split()),width=200,placeholder='… Veja detalhes.') for v in attention[:6]]+['']+lines[1:]
    if len(attention)>6:lines.append('Há outros avisos em Ver detalhes.')
    if not attention:lines.append('Pronto para a ação escolhida. Confira a seleção na lista acima.')
    details=[period]+warnings
    if result.get('due_notice') and result['due_notice'] not in details:details.append(result['due_notice'])
    details+=['\nArquivos localizados:']+[r['label']+': '+str(r.get('path') or 'não localizado') for r in rows]
    return message('\n'.join(lines),'\n'.join(details))


def operation_message(tracking,seconds,error,result):
    sent=tracking['sent'];confirmed={file_id(r) for r in sent}
    pending=[r['label'] for r in tracking['planned'] if file_id(r) not in confirmed]
    lines=[f"{tracking['name']} · {tracking['period'][5:]}/{tracking['period'][:4]}"]
    if error:lines.append('Operação não concluída: '+error.splitlines()[0])
    elif result and 'cancelad' in str(result).casefold():lines.append('Operação cancelada.')
    else:lines.append('Operação concluída.')
    if tracking['words']:lines.append(f"Documentos verificados/atualizados: {tracking['words']}.")
    if tracking['planned']:
        lines.append(f'Envios confirmados: {len(sent)}/{len(tracking["planned"])}.')
        if pending:lines.append('Sem envio confirmado: '+', '.join(pending))
        lines.append('Confira as folhas antes de concluir o livro no Controle mensal.')
    elif not error:lines.append('Nenhum documento enviado à impressora.')
    details=lines+[f'Tempo da operação: {seconds:.1f} s']
    if sent:details.append('Enviados: '+', '.join(r['label'] for r in sent))
    if result:details.append(str(result))
    if error:details.append(error)
    return message('\n'.join(lines),'\n'.join(details))


def preview_message(name,month,year,target,docs):
    lines=[f'{name} · prévia para {month:02}/{year}', 'Nenhum documento alterado.']
    details=[f'Destino: {target}']
    for doc in docs:
        changes=list(dict.fromkeys((c.old,c.new,c.kind) for c in doc['changes'] if c.old!=c.new))
        kinds=list(dict.fromkeys(kind for _,_,kind in changes))
        lines.append(Path(doc['path']).name+': '+(', '.join(kinds) if kinds else 'já está atualizado')+'.')
        details.append(str(doc['path']))
        details.extend(f'{kind}: {old} → {new}' for old,new,kind in changes)
    return message('\n'.join(lines),'\n'.join(lines+['']+details))
