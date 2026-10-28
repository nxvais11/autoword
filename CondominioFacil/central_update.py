"""Atualização individual da Central usando o mesmo motor da atualização em lote."""
import copy
from pathlib import Path
from central_service import LABELS,verify_plan
from word_service import inspect_condo,generate,output_targets,digest


def closing_condo(result,kinds):
    if not kinds or any(k not in range(4) for k in kinds):
        raise ValueError('Escolha os Words a atualizar em Opções.')
    files=[None]*4
    for row in result['rows']:
        if row['group']=='closing':files[int(row['key'].removeprefix('closing'))]=row.get('source_path',row['path'])
    chosen=[Path(files[k]).resolve() for k in kinds if files[k]]
    if len(chosen)!=len(kinds):raise ValueError('Word de fechamento ausente. Vincule os arquivos antes de atualizar.')
    if len(set(chosen))!=len(chosen):raise ValueError('O mesmo Word está vinculado a dois tipos de documento.')
    parents={p.parent for p in chosen}
    if len(parents)!=1:raise ValueError('Os Words a atualizar devem estar na mesma pasta de fechamento.')
    return {'name':result['name'],'folder':str(chosen[0].parent),'files':[Path(p).resolve() if p else None for p in files]}


def prepare_closing(word,result,settings,month,year,state):
    if result['period']!=f'{year}-{month:02}':raise ValueError('A competência mudou. Busque os arquivos novamente.')
    kinds=tuple(settings.get('update_kinds',range(4)))
    condo=closing_condo(result,kinds)
    monitor=state.get('sheet_monitor')
    if monitor:
        monitor.require_current()
        if condo['folder'] not in state['sheet_groups']:
            raise ValueError('Nenhuma linha da planilha associada a este condomínio. Revise as associações em Opções.')
    docs=inspect_condo(word,condo,month,year,state['config'].get(condo['folder'],[]),kinds,
                       state['sheet_groups'].get(condo['folder']),state['sheet_mapping'],
                       models=state['source_models'],check_resignations=False)
    target=output_targets([condo],month,year,settings.get('destination') or None,settings.get('create_subfolder',False))[condo['folder']]
    return condo,docs,target


def update_closing(word,result,settings,month,year,state,cancel,log,on_generated=None):
    condo,docs,target=prepare_closing(word,result,settings,month,year,state)
    completed=[];messages=[]
    def record(c,t,d):
        completed.append(True)
        if on_generated:on_generated(c,t,d)
    def report(text):messages.append(text);log(text)
    monitor=state.get('sheet_monitor')
    generate(word,[condo],{condo['folder']:docs},Path(condo['folder']),month,year,report,cancel,
             targets={condo['folder']:target},cache=state['generation_cache'],models=state['source_models'],
             overwrite_sources=True,validate=monitor.require_current if monitor else None,on_generated=record)
    if not completed:
        raise ValueError('Atualização não concluída; nenhum documento foi enviado à impressora.\n'+'\n'.join(messages))
    updated=copy.deepcopy(result)
    for row in updated['rows']:
        if row['group']=='closing' and int(row['key'].removeprefix('closing')) in settings.get('update_kinds',range(4)):
            row.setdefault('source_path',row['path'])
            row['path']=Path(target)/Path(row['source_path']).name
    updated['updated_kinds']=list(settings.get('update_kinds',range(4)))
    updated['output']=str(target)
    return updated


def updated_print_plan(original_plan,updated):
    """Revalida PDFs/relatórios; somente os Words atualizados recebem novo hash."""
    rows=copy.deepcopy(original_plan)
    paths={r['key']:r['path'] for r in updated['rows'] if r['group']=='closing'}
    for row in rows:
        if row['group']=='closing':
            kind=int(row['key'].removeprefix('closing'))
            if kind not in updated['updated_kinds']:
                raise ValueError(LABELS[kind]+': marque este Word para atualização antes de atualizar e imprimir.')
            row['path']=paths[row['key']];row['hash']=digest(Path(row['path']))
    verify_plan(rows)
    return rows


def run_update(result,settings,month,year,state,cancel,log,*,print_rows=None,on_generated=None,on_updated=None,word_factory=None,printer=None):
    from word_service import Word
    from central_print import execute_plan
    if print_rows is not None:
        for row in print_rows:
            if row['group']=='closing' and int(row['key'].removeprefix('closing')) not in settings.get('update_kinds',range(4)):
                raise ValueError('Marque para atualização todos os Words selecionados para impressão em Opções.')
        verify_plan(print_rows)
    with (word_factory or Word)() as word:
        updated=update_closing(word,result,settings,month,year,state,cancel,log,on_generated)
    if on_updated:on_updated(updated)
    count=0
    if print_rows is not None and not cancel.is_set():
        rows=updated_print_plan(print_rows,updated)
        count=(printer or execute_plan)(rows,cancel,log,word_factory or Word)
    return updated,count
