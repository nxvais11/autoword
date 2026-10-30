"""Resumos da Central; detalhes completos continuam disponíveis para conferência."""
from pathlib import Path
from document_period import period_summary
from book_history import file_id
from textwrap import shorten


def message(summary,details):
    return {'summary':summary,'details':details}


def scoped_warnings(result):
    """Compatibilidade com resultados antigos: exclui ambiguidades de terceiros."""
    import re
    from central_service import identity
    warnings=[]
    for warning in dict.fromkeys(result.get('warnings',[])):
        match=re.search(r'amb[íi]gu[oa] entre (.+?)\. (?:Vincule|Confira)',warning,re.I)
        if match and identity(result['name']) not in {identity(n) for n in match[1].split(', ')}:continue
        if ': identificação pendente — ' in warning:continue
        warnings.append(warning)
    return warnings


def short_path(path):
    from pathlib import PureWindowsPath
    text=str(path)
    return PureWindowsPath(text).name if '\\' in text else Path(text).name


def search_message(result,selected):
    rows=result['rows'];warnings=scoped_warnings(result)
    closing=[r for r in rows if r['group']=='closing']
    statements=[r for r in rows if r['group']=='statement' and r.get('path')]
    report_selected=any(i in selected and r['group']=='obligations' for i,r in enumerate(rows))
    competence=f"{result['period'][5:]}/{result['period'][:4]}"
    lines=[f"{result['name']} · competência selecionada: {competence}",
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
    due=result.get('due_obligations',[]);issues=result.get('obligation_issues',[])
    if due:attention.append(f'Obrigações pendentes: {len(due)} com data anterior à competência. Solicite a correção do relatório.')
    if issues and result.get('word'):attention.append(f'Obrigações: {len(issues)} inconsistência(s) ou dado(s) a corrigir. Veja os serviços em Ver detalhes.')
    other=[]
    for warning in warnings:
        if warning in issues or warning==result.get('due_notice') or warning==period:continue
        if warning.startswith(('PDF pessoal:','Word do Jurídico:')):
            if ': 0 candidatos.' in warning:continue
            label='Relatório PDF' if warning.startswith('PDF pessoal:') else 'Word do Jurídico'
            if ' candidatos.' in warning:warning=label+': há mais de um arquivo. Vincule o correto.'
            if not report_selected:continue
        if 'Próxima realização' in warning or warning.startswith('Word original não localizado'):
            warning='Não foi possível conferir as obrigações. Vincule ou revise o Word do Jurídico.'
        other.append(warning)
    attention+=other;attention=list(dict.fromkeys(attention))
    if attention:lines=lines[:1]+['Atenção:']+[shorten(' '.join(v.split()),width=200,placeholder='… Veja detalhes.') for v in attention[:5]]+['']+lines[1:]
    else:lines.append('Pronto para a ação escolhida. Confira a seleção na lista acima.')
    if len(attention)>5:lines.append('Há outros avisos deste condomínio em Ver detalhes.')
    details=[f"Condomínio: {result['name']}",f'Competência selecionada: {competence}',period]
    if attention:details+=['','O que precisa de atenção:']+list(dict.fromkeys(attention))
    if due:details+=['',f'Obrigações vencidas antes de {competence}:']+due
    if issues:details+=['','Serviços/dados que precisam de correção ou conferência:']+issues
    checks=result.get('obligation_checks',[])
    if checks:
        compatible=sum(row['status']=='prazo compatível' for row in checks)
        automatic=sum(row['status']=='renovação automática' for row in checks)
        undated=sum(row['status']=='sem data' for row in checks)
        details+=['',f'Conferência de obrigações: {compatible} prazo(s) compatível(is); {automatic} renovação(ões) automática(s).']
        if undated:details.append(f'{undated} serviço(s) sem datas suficientes para conferir o vencimento.')
    details+=['','Arquivos deste condomínio:']
    for row in rows:
        label='Relatório PDF de obrigações' if row['group']=='obligations' else row['label']
        details.append(label+': '+(short_path(row['path']) if row.get('path') else 'não localizado'))
    details.append('Word do Jurídico (fonte da conferência): '+(short_path(result['word']) if result.get('word') else 'não localizado'))
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
