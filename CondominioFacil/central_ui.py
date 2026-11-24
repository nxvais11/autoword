"""Central simples por condomínio, com trabalho de rede e Word fora da interface."""
import copy
import json
import os
import queue
import tempfile
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import ttk,filedialog,messagebox
from central_service import DEFAULTS,LABELS,catalog,search,compare_reports,selected_plan,digest,validate_statement_aliases
from central_print import execute_plan
from obligations import check_obligations
from query_service import consult,QueryInterrupted
from word_service import Word,discover
from central_update import prepare_closing,closing_condo,run_update
from print_service import available_printers
from book_history import BookHistory,file_id
from document_period import inspect_periods,period_summary
from console_messages import search_message,operation_message,preview_message,message
from workspace_cache import load_cache,save_cache,cache_key
from central_service import alphabetical_names,matching_names,norm,check_workspace
from theme import COLORS


def load_settings(path):
    value=copy.deepcopy(DEFAULTS)
    if Path(path).exists():
        saved=json.loads(Path(path).read_text(encoding='utf-8'))
        if not isinstance(saved,dict):raise ValueError('Configuração da central inválida.')
        value.update(saved)
    return value


def save_settings(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8');os.replace(tmp,path)


def settings_dialog(parent,path,on_saved=None,*,setup=False):
    try:settings=load_settings(path)
    except Exception as exc:messagebox.showerror('Opções',str(exc),parent=parent);return
    dialog=tk.Toplevel(parent)
    dialog.title('Configurar AutoWord' if setup else 'AutoWord — opções')
    dialog.transient(parent.winfo_toplevel());dialog.grab_set()
    dialog.geometry(f'760x{min(650,dialog.winfo_screenheight()-100)}')
    shell=ttk.Frame(dialog,padding=16);shell.pack(fill='both',expand=True)
    if setup:
        ttk.Label(shell,text='Configuração inicial',style='Title.TLabel').pack(anchor='w')
        ttk.Label(shell,text='Escolha a pasta dos condomínios. Adicione extratos, relatórios e impressoras conforme o seu fluxo.',
                  style='Muted.TLabel',wraplength=680).pack(anchor='w',pady=(3,12))
    tabs=ttk.Notebook(shell);tabs.pack(fill='both',expand=True)
    paths=ttk.Frame(tabs,padding=12);update=ttk.Frame(tabs,padding=12)
    tabs.add(paths,text='Pastas e impressoras');tabs.add(update,text='Atualização e responsáveis')
    aliases_tab=ttk.Frame(tabs,padding=12);tabs.add(aliases_tab,text='Nomes de extratos')
    aliases=copy.deepcopy(settings.get('statement_aliases',{}))
    owner=getattr(parent,'parent',parent)
    known=list(parent.catalog_names) if hasattr(parent,'catalog_names') else [c['name'] for c in getattr(owner,'condos',[])]
    alias_names=sorted(set(known)|set(aliases))
    alias_name=tk.StringVar(value=parent.name.get() if hasattr(parent,'name') and parent.name.get() in alias_names else (alias_names[0] if alias_names else ''))
    ttk.Label(aliases_tab,text='Condomínio',style='Section.TLabel').pack(anchor='w')
    alias_combo=ttk.Combobox(aliases_tab,textvariable=alias_name,values=alias_names,state='readonly');alias_combo.pack(fill='x',pady=(4,12))
    ttk.Label(aliases_tab,text='Nomes alternativos dos extratos — um por linha').pack(anchor='w')
    alias_text=tk.Text(aliases_tab,height=9,wrap='word',font=('Segoe UI',10));alias_text.pack(fill='both',expand=True,pady=6)
    ttk.Label(aliases_tab,text='Informe nomes ou apelidos específicos, sem o mês e o ano. Ex.: nome antigo do condomínio.\nO nome da pasta continua sendo reconhecido. Evite nomes genéricos como Extrato Mensal.\nAs alterações serão gravadas ao clicar em Salvar.',wraplength=650,style='Muted.TLabel').pack(anchor='w')
    alias_current=[alias_name.get()]
    def store_aliases():
        name=alias_current[0]
        if name:
            entries=list(dict.fromkeys(v.strip() for v in alias_text.get('1.0','end').splitlines() if v.strip()))
            if entries:aliases[name]=entries
            else:aliases.pop(name,None)
    def change_aliases(event=None):
        store_aliases();alias_current[0]=alias_name.get()
        alias_text.delete('1.0','end');alias_text.insert('1.0','\n'.join(aliases.get(alias_name.get(),[])))
    alias_text.insert('1.0','\n'.join(aliases.get(alias_name.get(),[])))
    alias_combo.bind('<<ComboboxSelected>>',change_aliases)
    if not alias_names:
        alias_text.configure(state='disabled')
        ttk.Label(aliases_tab,text='Carregue os condomínios na Central para cadastrar os nomes.').pack(anchor='w')
    dialog.alias_combo=alias_combo;dialog.alias_text=alias_text
    refresh_target=[parent if hasattr(parent,'reload') else getattr(owner,'central_panel',None)]
    def refresh_choices(error=''):
        if not dialog.winfo_exists():return
        refresh_button.configure(state='normal',text='Atualizar lista')
        if error:
            messagebox.showerror('Lista não atualizada',error,parent=dialog);return
        target=refresh_target[0]
        store_aliases()
        alias_names[:]=alphabetical_names(set(target.catalog_names)|set(aliases))
        alias_combo.configure(values=alias_names)
        alias_text.configure(state='normal' if alias_names else 'disabled')
        if alias_name.get() not in alias_names:
            alias_name.set(alias_names[0] if alias_names else '');change_aliases()
    def register_refresh(target):
        refresh_target[0]=target;target.catalog_dialog=dialog;target.catalog_dialog_refresh=refresh_choices
    def refresh_catalog():
        target=refresh_target[0]
        if target is None:
            owner.open_central();target=getattr(owner,'central_panel',None)
        if target is None:return
        register_refresh(target)
        refresh_button.configure(state='disabled',text='Atualizando…');target.reload()
    refresh_button=ttk.Button(aliases_tab,text='Atualizar lista',command=refresh_catalog)
    refresh_button.pack(anchor='w',pady=(8,0))
    ttk.Label(aliases_tab,text='Busca novamente os condomínios nas pastas. Não altera os nomes digitados.',style='Muted.TLabel',wraplength=650).pack(anchor='w',pady=4)
    if refresh_target[0] is not None:register_refresh(refresh_target[0])
    def release_refresh(event):
        if event.widget is not dialog:return
        target=refresh_target[0]
        if target is not None and getattr(target,'catalog_dialog',None) is dialog:
            target.catalog_dialog=None;target.catalog_dialog_refresh=None
    dialog.bind('<Destroy>',release_refresh,add='+')
    dialog.refresh_button=refresh_button
    values={}
    for field,label in [('root','Pasta principal dos condomínios'),('statements','Extratos (opcional, pasta acima dos anos)'),('reports','PDFs pessoais de obrigações (opcional)'),('destination','Pasta de saída (opcional, organiza por condomínio e competência)')]:
        host=update if field=='destination' else paths
        ttk.Label(host,text=label).pack(anchor='w',pady=(8,3));row=ttk.Frame(host);row.pack(fill='x')
        value=tk.StringVar(value=settings.get(field,''));values[field]=value
        ttk.Entry(row,textvariable=value).pack(side='left',fill='x',expand=True)
        def browse(v=value):
            chosen=filedialog.askdirectory(parent=dialog)
            if chosen:v.set(chosen)
        ttk.Button(row,text='Escolher…',command=browse).pack(side='right',padx=5)
    combos=[]
    for field,label in [('main_printer','Fechamento e extratos'),('report_printer','Relatório de obrigações')]:
        ttk.Label(paths,text='Impressora — '+label).pack(anchor='w',pady=(10,3))
        value=tk.StringVar(value=settings[field]);values[field]=value
        combo=ttk.Combobox(paths,textvariable=value);combo.pack(fill='x');combos.append(combo)
    errors=queue.Queue()
    def printers():
        try:errors.put(available_printers()[0])
        except Exception:errors.put([])
    threading.Thread(target=printers,daemon=True).start()
    def poll():
        if not dialog.winfo_exists():return
        try:
            names=errors.get_nowait()
            for combo in combos:combo.configure(values=names)
        except queue.Empty:dialog.after(100,poll)
    dialog.after(100,poll)
    include=tk.BooleanVar(value=settings['include_report'])
    ttk.Checkbutton(paths,text='Marcar obrigações para impressão por padrão',variable=include).pack(anchor='w',pady=12)
    ttk.Label(paths,text='Escolha as impressoras para habilitar o envio. PDFs usam o Adobe e as preferências da impressora.',
              style='Muted.TLabel',wraplength=650).pack(anchor='w')
    ttk.Label(update,text='Words a atualizar',style='Section.TLabel').pack(anchor='w',pady=(14,5))
    choices=ttk.Frame(update);choices.pack(fill='x')
    kinds=[tk.BooleanVar(value=k in settings.get('update_kinds',range(4))) for k in range(4)]
    for k,label in enumerate(('Aprovação','Capa','Anexo I','Anexo II')):
        ttk.Checkbutton(choices,text=label,variable=kinds[k]).pack(side='left',padx=5)
    subfolder=tk.BooleanVar(value=settings.get('create_subfolder',False))
    ttk.Checkbutton(update,text='Criar subpasta AAAA-MM ao salvar na pasta original',variable=subfolder).pack(anchor='w',pady=12)
    owner=getattr(parent,'parent',parent)
    def dismiss():
        dialog.destroy()
        if isinstance(parent,tk.Toplevel):parent.grab_set()
    def call(command):
        dismiss();parent.after_idle(command)
    actions=ttk.Frame(update);actions.pack(fill='x',pady=10)
    ttk.Button(actions,text='Responsáveis do condomínio…',command=lambda:call(parent.manage_roster if hasattr(parent,'manage_roster') else owner.edit_roster)).pack(anchor='w',pady=4)
    ttk.Button(actions,text='Importar planilha de responsáveis…',command=lambda:call(owner.import_sheet)).pack(anchor='w',pady=4)
    ttk.Button(actions,text='Desvincular planilha',command=lambda:call(owner.unlink_sheet)).pack(anchor='w',pady=4)
    ttk.Label(update,textvariable=owner.sheet_status,wraplength=650).pack(anchor='w')
    def candidate():
        store_aliases()
        validate_statement_aliases(aliases,alias_names)
        return dict(settings,**{k:v.get().strip() for k,v in values.items()},statement_aliases=aliases,
                    include_report=include.get(),update_kinds=[k for k,v in enumerate(kinds) if v.get()],
                    create_subfolder=subfolder.get())

    def persist(updated):
        try:
            if not updated['root']:raise ValueError('Informe a pasta principal dos condomínios.')
            save_settings(path,updated)
        except Exception as exc:
            messagebox.showerror('Opções não salvas',str(exc),parent=dialog)
            return
        dismiss()
        if on_saved:on_saved()

    def verify(save_after=False):
        try:updated=candidate()
        except ValueError as exc:
            messagebox.showerror('Configuração',str(exc),parent=dialog);return
        mailbox=queue.Queue()
        verify_button.configure(state='disabled')
        save_button.configure(state='disabled')
        check_status.set('Verificando acesso às pastas e filas de impressão…')
        threading.Thread(target=lambda:mailbox.put(check_workspace(updated,available_printers)),daemon=True).start()

        def show_checks():
            if not dialog.winfo_exists():return
            try:checks=mailbox.get_nowait()
            except queue.Empty:
                dialog.after(100,show_checks)
                return
            verify_button.configure(state='normal')
            save_button.configure(state='normal')
            if any(updated[k]!=v.get().strip() for k,v in values.items()):
                check_status.set('Os campos mudaram. Verifique a configuração atual.')
                return
            errors=[label for label,ok,_ in checks if not ok]
            check_status.set('Revise: '+', '.join(errors)+'.' if errors else 'Acesso confirmado para os itens configurados.')
            if save_after and not errors:
                save()
            else:
                text='\n'.join(f'{label} · {note}' for label,_,note in checks)
                notice=messagebox.showwarning if errors else messagebox.showinfo
                notice('Verificação da configuração',text,parent=dialog)
        dialog.after(100,show_checks)

    def save():
        try:updated=candidate()
        except ValueError as exc:
            messagebox.showerror('Opções não salvas',str(exc),parent=dialog);return
        persist(updated)

    footer=ttk.Frame(shell);footer.pack(fill='x',pady=(12,0))
    check_status=tk.StringVar()
    ttk.Label(shell,textvariable=check_status,style='Muted.TLabel',wraplength=680).pack(anchor='w',pady=(5,0))
    verify_button=ttk.Button(footer,text='Testar configuração',command=verify)
    verify_button.pack(side='left')
    save_button=ttk.Button(footer,text='Salvar',style='Primary.TButton',command=lambda:verify(True) if setup else save())
    save_button.pack(side='right')
    ttk.Button(footer,text='Cancelar',command=dismiss).pack(side='right',padx=8)
    dialog.protocol('WM_DELETE_WINDOW',dismiss)
    return dialog


class CentralView:
    def build(self,parent,path,embedded=False):
        self.embedded=embedded
        self.parent=parent;self.path=Path(path);self.settings=load_settings(path)
        self.history=BookHistory(self.path.with_name('livros.json'))
        if self.history.recovery_notice:
            self.after(0,lambda:messagebox.showinfo('Controle mensal recuperado',self.history.recovery_notice,parent=self))
        self.operation=None;self.print_request=[];self.period_cache={}
        self.catalog_loading=False;self.workspace_loaded=False;self.catalog_cancel=threading.Event()
        self.loaded_key=None;self.batch_revision=0
        self.catalog_names=()
        self.external_busy=False
        self.result=None;self.comparison=None;self.checked=set();self.busy=False;self.events=queue.Queue();self.cancel=parent.cancel
        if not embedded:
            self.title('AutoWord — atualizar e imprimir');self.geometry(f'1080x{min(740,self.winfo_screenheight()-100)}');self.minsize(900,600)
            self.transient(parent);self.grab_set()
        self.controls=[]
        self.update_kinds=set()
        self.period_callback=None
        self.name=tk.StringVar();self.month=parent.month;self.year=parent.year
        self.version=tk.StringVar(value='pdf');self.status=tk.StringVar(value='Carregando nomes dos condomínios…')
        body=ttk.Frame(self,padding=(18,14));body.pack(fill='both',expand=True)
        body.columnconfigure(0,weight=1);body.rowconfigure(3,weight=1)
        header=ttk.Frame(body);header.grid(row=0,column=0,sticky='ew',pady=(0,12))
        title=ttk.Frame(header);title.pack(side='left')
        ttk.Label(title,text='Central de fechamento',style='Title.TLabel').pack(anchor='w')
        self.book_status=tk.StringVar()
        ttk.Label(title,textvariable=self.book_status,style='Muted.TLabel').pack(anchor='w')
        self.action(header,'Opções',self.configure_paths).pack(side='right')
        self.action(header,'Controle mensal',self.monthly_control).pack(side='right',padx=8)
        self.action(header,'Atualização em lote',self.open_batch).pack(side='right')

        context=ttk.Frame(body,style='Card.TFrame',padding=(12,9))
        context.grid(row=1,column=0,sticky='ew',pady=(0,10))
        selection=ttk.Frame(context,style='Card.TFrame');selection.pack(fill='x')
        condo=ttk.Frame(selection,style='Card.TFrame');condo.pack(side='left',padx=(0,14))
        ttk.Label(condo,text='Condomínio',style='Card.TLabel').pack(anchor='w')
        self.names=ttk.Combobox(condo,textvariable=self.name,state='normal',width=34)
        self.names.pack(fill='x',pady=(3,0))
        from engine import MONTHS
        self.months=MONTHS
        period=ttk.Frame(selection,style='Card.TFrame');period.pack(side='left',padx=(0,10))
        ttk.Label(period,text='Competência para atualização',style='Card.TLabel').grid(row=0,columnspan=2,sticky='w')
        self.month_box=ttk.Combobox(period,textvariable=self.month,values=[m.title() for m in MONTHS],state='readonly',width=12)
        self.month_box.grid(row=1,column=0,pady=(3,0))
        self.year_box=ttk.Spinbox(period,textvariable=self.year,from_=2000,to=2099,width=6)
        self.year_box.grid(row=1,column=1,padx=(5,0),pady=(3,0))
        self.controls.extend([self.names,self.month_box,self.year_box])
        self.action(selection,'Buscar arquivos',self.query).pack(side='left',anchor='s')
        self.setup_button=self.action(selection,'Configurar AutoWord',self.configure_paths)
        self.document_period=tk.StringVar(value='Competência dos Words: selecione um condomínio.')
        ttk.Label(context,textvariable=self.document_period,style='Card.TLabel',wraplength=790).pack(anchor='w',pady=(8,0))

        legend=ttk.Frame(body);legend.grid(row=2,column=0,sticky='ew',pady=(0,5))
        ttk.Label(legend,text='Documentos',style='Section.TLabel').pack(side='left')
        self.clear_all_button=self.action(legend,'Limpar seleção de impressão',lambda:self.check_all(False))
        self.clear_all_button.pack(side='right')
        self.select_all_button=self.action(legend,'Marcar disponíveis',lambda:self.check_all(True))
        self.select_all_button.pack(side='right',padx=6)
        host=ttk.Frame(body);host.grid(row=3,column=0,sticky='nsew')
        self.tree=ttk.Treeview(host,columns=('update','check','file','state','action'),show='tree headings',selectmode='browse')
        self.tree.heading('#0',text='Documento')
        self.tree.column('#0',width=190,minwidth=150)
        for key,title,width in [('update','Atualizar',86),('check','Imprimir',84),('file','Arquivo',235),
                                ('state','Situação',145),('action','Ação',135)]:
            self.tree.heading(key,text=title)
            self.tree.column(key,width=width,minwidth=width if key in ('update','check') else 105,stretch=key in ('file','#0'))
        for key in ('update','check'):self.tree.column(key,anchor='center')
        self.tree.tag_configure('group',background=COLORS['section'],foreground=COLORS['text'],font=('Segoe UI',10,'bold'))
        self.tree.tag_configure('even',background=COLORS['panel'])
        self.tree.tag_configure('odd',background=COLORS['alternate'])
        self.tree.tag_configure('attention',foreground=COLORS['attention'])
        self.tree.pack(side='left',fill='both',expand=True)
        scroll=ttk.Scrollbar(host,command=self.tree.yview);scroll.pack(side='right',fill='y')
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.bind('<Button-1>',self.click)
        self.tree.bind('<space>',self.toggle)
        self.tree.bind('<Key-u>',lambda event:self.toggle(update=True))
        self.tree.bind('<Return>',lambda event:self.handle_row_action())
        self.tree.bind('<<TreeviewSelect>>',lambda event:self.refresh_row_actions())

        row=ttk.Frame(body);row.grid(row=4,column=0,sticky='ew',pady=(7,4))
        self.row_button=self.action(row,'Selecionar um documento',self.handle_row_action)
        self.row_button.pack(side='left')
        self.link_button=self.action(row,'Trocar vínculo…',self.link)
        self.link_button.pack(side='left',padx=6)
        self.report_menu=ttk.Menubutton(row,text='Obrigações')
        self.report_menu.pack(side='right')
        self.controls.append(self.report_menu)
        report_menu=self.report_actions=tk.Menu(self.report_menu,tearoff=False)
        self.report_menu.configure(menu=report_menu)
        report_menu.add_command(label='Comparar relatórios',command=self.compare)
        report_menu.add_command(label='Abrir Word do Jurídico',command=lambda:self.open_file(True))
        report_menu.add_command(label='Vincular Word do Jurídico…',command=lambda:self.link(True))
        report_menu.add_command(label='Vincular PDF pessoal…',command=lambda:self.link(report_pdf=True))
        report_menu.add_command(label='Confirmar conferência manual',command=self.manual_review)
        report_menu.add_separator()
        report_menu.add_radiobutton(label='Imprimir PDF pessoal',variable=self.version,value='pdf',command=self.redraw)
        report_menu.add_radiobutton(label='Imprimir Word atual',variable=self.version,value='word',command=self.redraw)

        summary=ttk.Frame(body);summary.grid(row=6,column=0,sticky='ew',pady=(3,6))
        toolbar=ttk.Frame(summary);toolbar.pack(fill='x')
        ttk.Label(toolbar,text='Resumo',style='Section.TLabel').pack(side='left')
        self.action(toolbar,'Ver detalhes',self.open_details).pack(side='right')
        host=ttk.Frame(summary);host.pack(fill='both',expand=True,pady=(4,0))
        self.details=tk.Text(host,height=4,wrap='word',state='disabled',font=('Segoe UI',10),
                             background=COLORS['panel'],foreground=COLORS['text'],relief='flat',padx=8,pady=5)
        self.details.pack(side='left',fill='both',expand=True)
        scroll=ttk.Scrollbar(host,command=self.details.yview);scroll.pack(side='right',fill='y')
        self.details.configure(yscrollcommand=scroll.set)
        self.technical_details='';self.operation_log=[]
        footer=ttk.Frame(body);footer.grid(row=7,column=0,sticky='ew')
        ttk.Label(footer,textvariable=self.status,style='Muted.TLabel',wraplength=740).pack(side='left',fill='x',expand=True)
        self.cancel_button=ttk.Button(footer,text='Cancelar',command=self.cancel.set,state='disabled')
        self.cancel_button.pack(side='right',padx=(8,0))
        actions=ttk.Frame(body);actions.grid(row=8,column=0,sticky='ew',pady=(8,0))
        self.update_print_button=self.action(actions,'Atualizar e imprimir',lambda:self.update_selected(True))
        self.update_print_button.configure(style='Primary.TButton');self.update_print_button.pack(side='left')
        self.update_button=self.action(actions,'Só atualizar',self.update_selected)
        self.update_button.pack(side='left',padx=8)
        self.print_button=self.action(actions,'Só imprimir',self.print_selected)
        self.print_button.pack(side='left')
        self.preview_button=self.action(actions,'Conferir atualização',self.preview_update)
        self.preview_button.pack(side='right')
        if not embedded:self.protocol('WM_DELETE_WINDOW',self.close)
        self.names.bind('<<ComboboxSelected>>',lambda event:self.query())
        self.names.bind('<Return>',self.choose_typed_name)
        self.names.bind('<Escape>',lambda event:self.name.set(''))
        self.name_trace=self.name.trace_add('write',self.filter_names)
        self.month_trace=self.month.trace_add('write',self.schedule_period_query)
        self.year_trace=self.year.trace_add('write',self.schedule_period_query)
        self.poll_callback=self.after(100,self.poll)
        self.reload()

    def open_batch(self):
        if not self.busy and not self.parent.busy:
            if self.embedded:self.parent.show_batch()
            else:self.destroy()

    def action(self,parent,text,command):
        button=ttk.Button(parent,text=text,command=command);self.controls.append(button);return button

    def invalidate(self):
        if self.busy or self.parent.busy:return
        self.result=None;self.comparison=None;self.checked.clear();self.update_kinds.clear()
        self.tree.delete(*self.tree.get_children());self.version.set('pdf')
        self.refresh_actions()
        self.status.set('Clique em Buscar arquivos para a seleção atual.')
        self.document_period.set('Competência dos Words: busque os arquivos para consultar.')
        self.show_details('Busque os arquivos para consultar o resumo desta seleção.')
        self.refresh_book_status()

    def configure_paths(self):
        if not self.busy and not self.parent.busy:
            settings_dialog(self,self.path,self.reload,setup=not bool(self.settings['root']))

    def reload(self):
        self.catalog_cancel.set();self.catalog_cancel=threading.Event()
        self.settings=load_settings(self.path);self.invalidate()
        settings=copy.deepcopy(self.settings);mappings=copy.deepcopy(self.parent.mappings)
        self.loaded_key=cache_key(settings['root'],mappings)
        if not settings['root']:
            self.catalog_loading=False
            self.workspace_loaded=False
            self.set_names(())
            self.setup_button.pack(side='left',anchor='s',padx=8)
            self.status.set('Configure a pasta dos condomínios para começar.')
            self.document_period.set('Competência dos Words: aguardando a configuração.')
            self.show_details('Use Configurar AutoWord para verificar pastas e impressoras.')
            return
        self.setup_button.pack_forget()
        cached=load_cache(self.path.with_name('workspace_cache.json'),settings['root'],mappings) if self.embedded else None
        if cached:
            self.apply_workspace(cached,cached=True)
            self.status.set('Lista carregada. Conferindo as pastas em segundo plano…')
        else:self.status.set('Localizando condomínios em segundo plano… Você pode trocar de tela ou fechar.')
        self.catalog_loading=True;cancel=self.catalog_cancel
        def work():
            try:
                self.history.prepare_root(settings['root'])
                names=catalog(settings)
                if cancel.is_set():return
                if self.embedded:
                    condos=[c for c in discover(settings['root'],mappings) if c['name'] in names] if names else []
                    value={'names':names,'condos':condos,'root':settings['root']}
                    if cancel.is_set():return
                    try:save_cache(self.path.with_name('workspace_cache.json'),settings['root'],mappings,value)
                    except OSError:pass  # Falha de cache não impede a consulta real.
                else:value=names
                if not cancel.is_set():self.events.put(('catalog_ready',(cancel,value,'')))
            except Exception as exc:
                if not cancel.is_set():self.events.put(('catalog_ready',(cancel,None,str(exc))))
        threading.Thread(target=work,daemon=True).start()

    def apply_workspace(self,value,cached=False):
        if self.parent.condos!=value['condos'] or self.parent.folder.get()!=value['root']:
            selected={c['folder'] for c in self.parent.selected()}
            self.parent.apply_discovered(value['root'],value['condos'])
            keep=[str(i) for i,c in enumerate(value['condos']) if c['folder'] in selected]
            if keep:self.parent.tree.selection_set(keep);self.parent.selection_changed()
        names=value['names'];self.set_names(names)
        if self.result and self.result['name'] not in names:self.invalidate()
        if self.name.get() and not matching_names(names,self.name.get()):self.name.set('');self.invalidate()
        self.workspace_loaded=True

    def set_names(self,names):
        self.catalog_names=alphabetical_names(names)
        text=self.name.get()
        self.names.configure(values=self.catalog_names if text in self.catalog_names else matching_names(self.catalog_names,text))

    def filter_names(self,*args):
        if self.busy or self.parent.busy:return
        self.invalidate()
        matches=matching_names(self.catalog_names,self.name.get())
        self.names.configure(values=matches)
        if self.name.get() and self.name.get() not in self.catalog_names:
            self.status.set(f'{len(matches)} condomínio(s) encontrado(s). Selecione na lista ou pressione Enter.' if matches else 'Nenhum condomínio encontrado. Confira o nome digitado.')

    def choose_typed_name(self,event=None):
        self.query();return 'break'

    def resume(self):
        settings=load_settings(self.path)
        if settings!=self.settings or cache_key(settings['root'],self.parent.mappings)!=self.loaded_key:
            self.reload();return
        if getattr(self.parent,'document_revision',0)!=self.batch_revision:
            self.invalidate()
        if self.result is None and self.name.get() in self.catalog_names:self.after_idle(self.run_period_query)

    def schedule_period_query(self,*args):
        self.invalidate()
        self.cancel_period_query()
        if self.name.get() in self.catalog_names:
            self.period_callback=self.after(350,self.run_period_query)

    def cancel_period_query(self):
        if self.period_callback is not None:
            self.after_cancel(self.period_callback)
            self.period_callback=None

    def run_period_query(self):
        self.period_callback=None
        if not self.winfo_ismapped() or self.name.get() not in self.catalog_names:return
        grab=str(self.tk.call('grab','current',self._w))
        if grab and grab!=str(self):return
        try:_,_,year=self.context()
        except ValueError:return
        if 2000<=year<=2099:self.query()

    def context(self):
        return self.name.get(),self.months.index(self.month.get().lower())+1,int(self.year.get())

    def query(self):
        self.cancel_period_query()
        if self.busy or self.parent.busy:return
        if not self.settings['root']:
            self.configure_paths()
            return
        try:
            name,month,year=self.context()
            if not name or not 2000<=year<=2099:raise ValueError('Selecione o condomínio e uma competência válida.')
            if name not in self.catalog_names:
                exact=[n for n in self.catalog_names if norm(n)==norm(name)]
                matches=exact or matching_names(self.catalog_names,name)
                if len(matches)!=1:raise ValueError('Selecione um condomínio na lista de resultados.' if matches else 'Nenhum condomínio encontrado com esse nome.')
                name=matches[0];self.name.set(name)
        except Exception as exc:messagebox.showerror('Seleção',str(exc),parent=self);return
        self.invalidate()
        settings=copy.deepcopy(self.settings);mappings=copy.deepcopy(self.parent.mappings)
        names=self.catalog_names
        self.document_period.set('Competência dos Words: consultando…')
        hint=None
        if self.parent.folder.get()==settings['root']:
            known=next((c for c in self.parent.condos if c['name']==name),None)
            if known:hint=dict(name=name,folder=known['folder'],root=settings['root'])
        def work():
            return consult(settings,name,month,year,mappings,names,self.period_cache,self.cancel,
                           lambda text:self.events.put(('log',text)),closing_hint=hint)
        self.run(work,'search')

    def run(self,work,kind):
        if self.busy or self.parent.busy:return
        self.busy=True;self.parent.busy=True;self.cancel.clear();self.operation_log=[]
        for widget in self.controls:widget.configure(state='disabled')
        self.cancel_button.configure(state='normal');self.status.set('Processando…')
        tracking=None
        if kind=='printed' and self.result:
            tracking=dict(root=self.settings['root'],name=self.result['name'],period=self.result['period'],words=0,sent=[],attempt=[],planned=list(self.print_request))
            self.operation=tracking
        def worker():
            started=time.monotonic();error='';result=None;stopped=False
            try:result=work()
            except QueryInterrupted as exc:
                stopped=True
                self.events.put(('query_stopped',str(exc)))
            except Exception as exc:error=str(exc)
            if tracking is not None:
                seconds=time.monotonic()-started
                try:self.history.finish(tracking['root'],tracking['name'],tracking['period'],seconds,error)
                except Exception as exc:error+='\nNão foi possível salvar o controle: '+str(exc)
                result=operation_message(tracking,seconds,error,result)
            if not stopped:
                self.events.put(('error' if error else kind,result if tracking is not None else error if error else result))
            self.events.put(('done',None))
        threading.Thread(target=worker,daemon=False).start()

    def poll(self):
        external=self.parent.busy and not self.busy
        if external!=self.external_busy:
            self.external_busy=external
            self.cancel_button.configure(state='normal' if external else 'disabled')
            if external:self.status.set('Atualizando dados em segundo plano…')
            for widget in self.controls:widget.configure(state='disabled' if external else 'normal')
            if not external:
                self.names.configure(state='normal');self.month_box.configure(state='readonly')
                self.refresh_actions()
        try:
            for _ in range(40):
                kind,value=self.events.get_nowait()
                if kind=='catalog_ready':
                    cancel,result,error=value
                    if cancel is not self.catalog_cancel or cancel.is_set():continue
                    grab=str(self.tk.call('grab','current',self._w))
                    if self.busy or self.parent.busy or (grab and grab not in (str(self),str(getattr(self,'catalog_dialog',None)))):
                        self.events.put((kind,value));break
                    self.catalog_loading=False
                    if error:
                        self.status.set('Pastas indisponíveis. '+('Lista anterior mantida; confira o acesso à rede.' if self.workspace_loaded else 'Confira as pastas e tente novamente em Opções.'))
                        self.show_details(message('Não foi possível atualizar a lista de condomínios.\nConfira o acesso às pastas configuradas em Opções.',error))
                    else:
                        if self.embedded:self.apply_workspace(result)
                        else:
                            self.set_names(result);self.workspace_loaded=True
                        if not self.result:self.status.set('Selecione condomínio e competência para atualizar ou imprimir.')
                        if getattr(self,'query_after_reload',False) and self.name.get():
                            self.query_after_reload=False;self.after_idle(self.query)
                    refresh=getattr(self,'catalog_dialog_refresh',None)
                    if refresh:refresh(error)
                elif kind=='workspace':
                    self.parent.apply_discovered(value['root'],value['condos'])
                    self.set_names(value['names'])
                    if self.name.get() not in value['names']:self.name.set('')
                    self.status.set('Selecione condomínio e competência para atualizar ou imprimir.')
                    if getattr(self,'query_after_reload',False) and self.name.get():
                        self.query_after_reload=False;self.after_idle(self.query)
                elif kind=='catalog':
                    self.set_names(value)
                    current=self.parent.selected()
                    candidate=current[0]['name'] if len(current)==1 else self.name.get()
                    if candidate in value:self.name.set(candidate)
                    self.status.set('Selecione o nome do condomínio e busque os arquivos.')
                elif kind=='search':
                    if value.get('discarded_closing_bindings'):
                        try:
                            current=load_settings(self.path);bindings=current.get('overrides',{}).get(value['name'],{});changed=False
                            for key,old in value['discarded_closing_bindings'].items():
                                if bindings.get(key)==old:bindings.pop(key);changed=True
                            if changed:save_settings(self.path,current);self.settings=current
                        except Exception as exc:value['warnings'].append('Arquivos identificados, mas não foi possível remover o vínculo antigo: '+str(exc))
                    self.history.touch(self.settings['root'],value['name'])
                    self.set_names(self.catalog_names)
                    self.refresh_book_status()
                    self.result=value;self.show_period(value)
                    self.update_kinds=set(self.settings.get('update_kinds',range(4)))
                    self.checked={i for i,row in enumerate(value['rows']) if row['checked'] and row['path']}
                    self.redraw();self.show_details(search_message(value,self.checked))
                    self.status.set('Consulta incompleta. Veja a etapa interrompida nos detalhes.' if value.get('query_incomplete') else 'Consulta concluída. Confira o resumo e a seleção dos documentos.')
                    notice=value.get('obligation_notice') or value.get('due_notice')
                    if notice:
                        self.status.set('Revise as obrigações: há pendências anteriores ou inconsistências a corrigir.')
                        messagebox.showwarning('Corrigir relatório de obrigações — '+value['name'],notice,parent=self)
                elif kind=='query_stopped':
                    self.document_period.set('Competência dos Words: consulta interrompida.')
                    self.status.set(value);self.show_details(value)
                elif kind=='duplicates':
                    text,answer,ready=value
                    answer.append(messagebox.askyesno('Possível impressão repetida',text,parent=self))
                    ready.set()
                elif kind=='comparison':
                    self.comparison=value;self.version.set('pdf' if value['equal'] else '');self.redraw()
                    summary='Relatórios com textos equivalentes. Será usado o PDF pessoal.\nA aparência de impressão e as assinaturas gráficas não foram comparadas.' if value['equal'] else 'Há diferenças entre os relatórios.\nAbra Ver detalhes, confira as alterações e escolha PDF pessoal ou Word atual antes de imprimir.'
                    self.show_details(message(summary,value['diff']));self.status.set('Comparação concluída. Confira o resumo.')
                elif kind=='updated':
                    self.result=value;self.show_period(value);self.redraw()
                    self.show_details(search_message(value,self.checked))
                elif kind=='preview_update':
                    self.show_details(value);self.status.set('Conferência concluída. Nenhum documento alterado.')
                elif kind=='printed':self.status.set('Operação finalizada. Confira o resumo.');self.show_details(value)
                elif kind=='log':self.operation_log.append(str(value));self.status.set(str(value).splitlines()[0] if value else 'Processando…')
                elif kind=='error':
                    self.show_details(value);self.status.set('Não foi possível concluir. Confira o resumo.');messagebox.showerror('Central de impressão',value['summary'] if isinstance(value,dict) else value,parent=self)
                elif kind=='done':
                    self.busy=False;self.parent.busy=False
                    for widget in self.controls:widget.configure(state='normal')
                    self.names.configure(state='normal');self.month_box.configure(state='readonly');self.cancel_button.configure(state='disabled')
                    self.refresh_actions()
                    self.set_names(self.catalog_names)
                    self.refresh_book_status()
                    self.parent.events.put(('central_done',None))
                    if getattr(self.parent,'close_pending',False):self.parent.after_idle(self.parent.close)
        except queue.Empty:pass
        if self.winfo_exists():self.poll_callback=self.after(100,self.poll)

    def show_period(self,result):
        summary=period_summary(result)
        self.document_period.set(summary.split('\n')[0]+(' Confira os detalhes abaixo.' if '\n' in summary else ''))

    def row_path(self,row):
        if row['group']=='obligations' and self.version.get()=='word':
            return self.result['word']
        return row['path']

    def row_state(self,row):
        if not self.row_path(row):return 'Arquivo ausente'
        if row['group']=='obligations' and (not self.comparison or not self.version.get()):
            return 'Requer conferência'
        if not row['printer']:return 'Sem impressora'
        return 'Pronto'

    def selected_row(self):
        selected=self.tree.selection()
        if selected and selected[0].isdigit() and self.result:
            return self.result['rows'][int(selected[0])]
        return None

    def row_action_label(self,row):
        if not self.row_path(row):return 'Vincular extrato' if row['group']=='statement' else 'Vincular arquivo'
        if row['group']=='obligations':
            if not self.comparison:return 'Conferir relatório'
            if not self.version.get():return 'Escolher versão'
        if not row['printer']:return 'Configurar impressora'
        return 'Abrir arquivo'

    def refresh_row_actions(self):
        if self.busy or self.parent.busy:return
        row=self.selected_row()
        self.row_button.configure(text=self.row_action_label(row) if row else 'Selecionar um documento',
                                  state='normal' if row else 'disabled')
        self.link_button.configure(state='normal' if row and self.row_path(row) else 'disabled')

    def refresh_actions(self):
        if self.busy or self.parent.busy:return
        rows=self.result['rows'] if self.result else ()
        keys={f'closing{kind}' for kind in self.update_kinds}
        updates=[row for row in rows if row['group']=='closing' and row['key'] in keys]
        prints=[row for i,row in enumerate(rows) if i in self.checked]
        available=any(self.row_path(row) for row in rows)
        can_update=bool(updates) and all(row.get('source_path',row['path']) for row in updates)
        can_print=bool(prints) and all(self.row_state(row)=='Pronto' for row in prints)
        can_combine=can_update and can_print and all(row in updates for row in prints if row['group']=='closing')
        primary=self.update_print_button if can_combine else self.update_button if can_update else self.print_button if can_print else None
        for button in (self.update_print_button,self.update_button,self.print_button):
            button.configure(style='Primary.TButton' if button is primary else 'TButton')
        self.update_button.configure(state='normal' if can_update else 'disabled')
        self.preview_button.configure(state='normal' if can_update else 'disabled')
        self.print_button.configure(state='normal' if can_print else 'disabled',
                                    text=f'Imprimir {len(prints)} disponíveis' if prints and self.missing_print_files() else 'Só imprimir')
        self.update_print_button.configure(state='normal' if can_combine else 'disabled',
            text=f'Atualizar {len(updates)} e enviar {len(prints)} à fila' if updates and prints else 'Atualizar e imprimir')
        self.select_all_button.configure(state='normal' if available else 'disabled')
        self.clear_all_button.configure(state='normal' if prints else 'disabled')
        self.report_menu.configure(state='normal' if rows else 'disabled')
        self.refresh_row_actions()

    def redraw(self):
        if not self.result:return
        selected=self.tree.selection()
        focus=self.tree.focus()
        expanded={iid for iid in self.tree.get_children() if self.tree.item(iid,'open')}
        first_draw=not self.tree.get_children()
        self.tree.delete(*self.tree.get_children())
        groups=(('closing','Fechamento'),('statement','Extratos'),('obligations','Obrigações'))
        for group,label in groups:
            rows=[(i,row) for i,row in enumerate(self.result['rows']) if row['group']==group]
            if not rows:continue
            self.tree.insert('','end',iid=group,text=label,open=first_draw or group in expanded,tags=('group',))
            for i,row in rows:
                path=self.row_path(row)
                if group=='closing':
                    kind=int(row['key'].removeprefix('closing'))
                    update='☑' if kind in self.update_kinds else '☐'
                else:update='—'
                state=self.row_state(row)
                tags=('even' if i%2==0 else 'odd',)+(() if state=='Pronto' else ('attention',))
                label='Extrato' if group=='statement' else row['label']
                self.tree.insert(group,'end',iid=str(i),text=label,values=(update,'☑' if i in self.checked else '☐',
                                 Path(path).name if path else '—',state,self.row_action_label(row)),tags=tags)
        if selected and self.tree.exists(selected[0]):self.tree.selection_set(selected[0])
        if focus and self.tree.exists(focus):self.tree.focus(focus)
        self.refresh_actions()

    def click(self,event):
        column=self.tree.identify_column(event.x)
        item=self.tree.identify_row(event.y)
        if item.isdigit() and column in ('#1','#2','#5'):
            self.tree.selection_set(item);self.tree.focus(item)
            if column=='#5':self.handle_row_action()
            else:self.toggle(index=int(item),update=column=='#1')
            return 'break'

    def toggle(self,event=None,index=None,*,update=False):
        if self.busy or self.parent.busy or not self.result:return 'break'
        if index is None:
            selected=self.tree.selection()
            if not selected or not selected[0].isdigit():return 'break'
            index=int(selected[0])
        row=self.result['rows'][index]
        if update and row['group']=='closing':
            kind=int(row['key'].removeprefix('closing'))
            self.update_kinds.symmetric_difference_update({kind})
        elif not update and self.row_path(row):
            self.checked.symmetric_difference_update({index})
        self.redraw()
        self.show_details(search_message(self.result,self.checked))
        return 'break'

    def check_all(self,include):
        if self.busy or self.parent.busy or not self.result:return
        self.checked={i for i,row in enumerate(self.result['rows']) if self.row_path(row)} if include else set()
        self.redraw();self.show_details(search_message(self.result,self.checked))

    def missing_print_files(self):
        if not self.result:return []
        return [row['label'] for row in self.result['rows'] if row['group'] in ('closing','statement')
                and not self.row_path(row)]

    def handle_row_action(self):
        if self.busy or self.parent.busy:return 'break'
        row=self.selected_row()
        if row:
            if not self.row_path(row):self.link()
            elif row['group']=='obligations' and (not self.comparison or not self.version.get()):
                if not self.result['word']:self.link(True)
                elif self.comparison and not self.version.get():
                    self.report_actions.tk_popup(self.report_menu.winfo_rootx(),
                                                 self.report_menu.winfo_rooty()+self.report_menu.winfo_height())
                else:self.compare()
            elif not row['printer']:self.configure_paths()
            else:self.open_file()
        return 'break'

    def show_details(self,text):
        self.technical_details=text['details'] if isinstance(text,dict) else str(text)
        if isinstance(text,dict) and self.operation_log:self.technical_details+='\n\nRegistro da operação:\n'+'\n'.join(self.operation_log)
        if isinstance(text,dict) and self.comparison and self.comparison['diff'] not in self.technical_details:
            self.technical_details+='\n\nComparação dos relatórios:\n'+self.comparison['diff']
        text=text['summary'] if isinstance(text,dict) else str(text)
        self.details.configure(state='normal');self.details.delete('1.0','end');self.details.insert('end',text);self.details.configure(state='disabled')

    def open_details(self):
        dialog=tk.Toplevel(self);dialog.title('Detalhes — '+self.result['name'] if self.result else 'Detalhes da operação');dialog.transient(self.winfo_toplevel());dialog.geometry('850x500')
        host=ttk.Frame(dialog,padding=12);host.pack(fill='both',expand=True)
        text=tk.Text(host,wrap='word',font=('Segoe UI',10));text.pack(side='left',fill='both',expand=True)
        scroll=ttk.Scrollbar(host,command=text.yview);scroll.pack(side='right',fill='y');text.configure(yscrollcommand=scroll.set)
        text.insert('1.0',self.technical_details or 'Nenhuma consulta realizada.');text.configure(state='disabled')

    def report_paths(self):
        if not self.result:raise ValueError('Busque os arquivos primeiro.')
        pdf=next(r['path'] for r in self.result['rows'] if r['group']=='obligations')
        word=self.result['word']
        if not pdf or not word:raise ValueError('Vincule o PDF pessoal e o Word do Jurídico antes de conferir.')
        return pdf,word

    def compare(self):
        try:pdf,word=self.report_paths()
        except Exception as exc:messagebox.showinfo('Comparação',str(exc),parent=self);return
        self.comparison=None
        def work():
            with tempfile.TemporaryDirectory(prefix='autoword_comparacao_') as folder:
                with Word() as service:return compare_reports(service,pdf,word,folder)
        self.run(work,'comparison')

    def manual_review(self):
        try:pdf,word=self.report_paths()
        except Exception as exc:messagebox.showinfo('Conferência',str(exc),parent=self);return
        if not messagebox.askyesno('Conferência manual','Você abriu e conferiu os dois relatórios? Esta confirmação permite imprimir mesmo sem comparação automática completa.',parent=self):return
        self.comparison={'equal':False,'hashes':{str(p):digest(Path(p)) for p in (pdf,word)},'diff':'Conferência manual confirmada pelo usuário.'}
        self.version.set('')
        self.redraw()
        self.show_details(self.comparison['diff']+' Escolha PDF pessoal ou Word atual em Obrigações.')

    def open_file(self,word=False):
        if not self.result:return
        row=self.selected_row()
        path=self.result['word'] if word else self.row_path(row) if row else None
        if path:
            try:os.startfile(str(path))
            except Exception as exc:messagebox.showerror('Abrir arquivo',str(exc),parent=self)

    def link(self,word=False,*,report_pdf=False):
        if not self.result:return
        if word:key='report_word';group='word'
        elif report_pdf:key='report_pdf';group='obligations'
        else:
            row=self.selected_row()
            if not row:messagebox.showinfo('Vincular','Selecione a linha do documento na lista.',parent=self);return
            key=row['key'];group=row['group']
        pdf=group in ('statement','obligations')
        if group=='statement':paths=filedialog.askopenfilenames(parent=self,title='Selecione os extratos deste condomínio e competência',filetypes=[('PDF','*.pdf')])
        else:
            chosen=filedialog.askopenfilename(parent=self,title='Vincular arquivo',filetypes=[('PDF','*.pdf')] if pdf else [('Word','*.doc *.docx')]);paths=[chosen] if chosen else []
        if not paths:return
        try:
            self.settings.setdefault('overrides',{}).setdefault(self.result['name'],{})[key]=list(paths) if group=='statement' else paths[0]
            save_settings(self.path,self.settings);self.query()
        except Exception as exc:messagebox.showerror('Associação não salva',str(exc),parent=self)

    def update_state(self):
        parent=self.parent
        if parent.sheet_monitor and (parent.sheet_polling or parent.sheet_error or parent.sheet_monitor.raw_hash is None):
            raise ValueError('Aguarde a leitura da planilha ou resolva o aviso antes de atualizar.')
        return {'config':copy.deepcopy(parent.config),'sheet_groups':copy.deepcopy(parent.sheet_groups),
                'sheet_mapping':copy.deepcopy(parent.sheet_mapping),'sheet_monitor':parent.sheet_monitor,
                'source_models':parent.source_models,'generation_cache':parent.generation_cache}

    def preview_update(self):
        if self.busy or self.parent.busy or not self.result:return
        try:
            month,year=self.context()[1:];state=self.update_state()
            result=copy.deepcopy(self.result);settings=copy.deepcopy(self.settings)
            settings['update_kinds']=sorted(self.update_kinds)
        except Exception as exc:messagebox.showerror('Conferência',str(exc),parent=self);return
        def work():
            with Word() as word:
                condo,docs,target=prepare_closing(word,result,settings,month,year,state)
            return preview_message(condo['name'],month,year,target,docs)
        self.run(work,'preview_update')

    def update_selected(self,printing=False):
        if self.busy or self.parent.busy or not self.result:return
        try:
            month,year=self.context()[1:];state=self.update_state()
            result=copy.deepcopy(self.result);settings=copy.deepcopy(self.settings)
            settings['update_kinds']=sorted(self.update_kinds)
            kinds=settings.get('update_kinds',range(4))
            closing_condo(result,kinds)
            rows=selected_plan(result,self.checked,self.version.get(),self.comparison) if printing else None
            if rows is not None and any(r['group']=='closing' and int(r['key'].removeprefix('closing')) not in kinds for r in rows):
                raise ValueError('Marque para atualização todos os Words selecionados para impressão em Opções.')
            summary=f"{result['name']} — {month:02}/{year}\nAtualizar: "+', '.join(LABELS[k] for k in kinds)
            summary+='\nDestino: '+(settings.get('destination') or 'pasta original do fechamento')
            if settings.get('destination'):summary+=f" / {result['name']} / {year}-{month:02}"
            elif settings.get('create_subfolder'):summary+=f' / {year}-{month:02}'
            if rows is not None:
                summary+='\n\nImprimir, nesta ordem:\n'+'\n'.join(f"{r['label']} → {r['printer']}" for r in rows)
                if self.missing_print_files():summary+='\n\nFicarão de fora: '+', '.join(self.missing_print_files())+'.'
        except Exception as exc:messagebox.showerror('Atualização',str(exc),parent=self);return
        if not messagebox.askyesno('Atualizar e imprimir' if printing else 'Só atualizar',summary+'\n\nContinuar?',parent=self):return
        self.parent.state_dirty=True
        self.print_request=rows or []
        def work():
            def generated(c,t,d):self.parent.record_job(c,t,d,month,year)
            def updated(value):
                self.history.updated(settings['root'],result['name'],result['period'],value['updated_kinds'])
                if self.operation is not None:self.operation['words']=len(value['updated_kinds'])
                try:inspect_periods(value,self.period_cache,Word,self.cancel)
                except Exception as exc:
                    value['document_periods']=[]
                    value.setdefault('warnings',[]).append('Competência não consultada: '+str(exc))
                self.events.put(('updated',value));self.parent.events.put(('output',Path(value['output'])))
            value,count=run_update(result,settings,month,year,state,self.cancel,
                lambda text:self.events.put(('log',text)),print_rows=rows,on_generated=generated,on_updated=updated,word_factory=Word,printer=self.tracked_print)
            if self.cancel.is_set():return 'Operação cancelada. Nenhum reenvio automático de impressão.'
            return (f'Atualização concluída. {count}/{len(rows)} documento(s) enviado(s) à impressão.' if rows is not None else
                    'Atualização concluída. Nenhum documento enviado à impressora.')
        self.run(work,'printed')

    def select_parent_condo(self):
        if not self.result:raise ValueError('Selecione um condomínio e busque os arquivos primeiro.')
        condo=closing_condo(self.result,(0,))
        for i,current in enumerate(self.parent.condos):
            if current['folder']==condo['folder']:
                self.parent.condos[i]=dict(current,files=condo['files'])
                self.parent.tree.selection_set(str(i));return
        raise ValueError('Carregue a pasta principal dos condomínios em Opções antes de editar os responsáveis.')

    def manage_roster(self):
        try:self.select_parent_condo()
        except Exception as exc:messagebox.showinfo('Responsáveis',str(exc),parent=self);return
        self.parent.edit_roster()

    def print_selected(self):
        if self.busy or self.parent.busy or not self.result:return
        try:
            rows=selected_plan(self.result,self.checked,self.version.get(),self.comparison)
            summary='\n'.join(f"{i+1}. {row['label']} ({Path(row['path']).name}) → {row['printer']}" for i,row in enumerate(rows))
        except Exception as exc:messagebox.showerror('Impressão',str(exc),parent=self);return
        missing=self.missing_print_files()
        if missing:summary+='\n\nFicarão de fora: '+', '.join(missing)+'.'
        if not messagebox.askyesno('Confirmar impressão',summary+'\n\nUma cópia, somente frente. Enviar estes documentos?',parent=self):return
        self.print_request=rows
        def work():
            count=self.tracked_print(rows,self.cancel,lambda text:self.events.put(('log',text)),Word)
            if self.cancel.is_set():return 'Envio cancelado. Confira os documentos já recebidos pela fila.'
            return f'{count}/{len(rows)} documento(s) enviado(s). Confira a fila das impressoras; não há repetição automática em caso de falha.'
        self.run(work,'printed')

    def refresh_book_status(self):
        try:
            name,month,year=self.context()
            if not name:
                self.book_status.set('');return
            if not self.history.root_ready(self.settings['root']):
                self.book_status.set('Carregando…');return
            book=self.history.get(self.settings['root'],name,f'{year}-{month:02}')
            self.book_status.set(self.history.status(book))
        except (ValueError,AttributeError):pass

    def tracked_print(self,rows,cancel,log,word_factory):
        tracking=self.operation
        if tracking is None:raise ValueError('Controle da operação não inicializado.')
        tracking['planned']=rows
        duplicates=self.history.duplicates(tracking['root'],tracking['name'],tracking['period'],rows)
        if duplicates:
            ready=threading.Event();answer=[]
            text='Estes arquivos já foram enviados ou tiveram envio sem confirmação nesta competência:\n\n'+'\n'.join(r['label'] for r in duplicates)+'\n\nConfira a fila e as folhas. Deseja enviar novamente?'
            self.events.put(('duplicates',(text,answer,ready)))
            while not ready.wait(.1):
                if cancel.is_set():return 0
            if not answer or not answer[0]:return 0
        def event(kind,row):
            self.history.print_event(tracking['root'],tracking['name'],tracking['period'],kind,row)
            tracking['sent' if kind=='sent' else 'attempt'].append(copy.deepcopy(row))
        return execute_plan(rows,cancel,log,word_factory,on_event=event)

    def monthly_control(self):
        if self.busy or self.parent.busy:return
        try:
            _,month,year=self.context();period=f'{year}-{month:02}'
        except ValueError:return
        names=list(self.catalog_names);root=self.settings['root']
        dialog=tk.Toplevel(self);dialog.title('Controle mensal — '+period);dialog.transient(self.winfo_toplevel());dialog.grab_set();dialog.geometry('780x530')
        body=ttk.Frame(dialog,padding=16);body.pack(fill='both',expand=True)
        total=tk.StringVar(master=dialog)
        toolbar=ttk.Frame(body);toolbar.pack(fill='x',pady=(0,8))
        ttk.Label(toolbar,textvariable=total,style='Section.TLabel',wraplength=560).pack(side='left')
        only_pending=tk.BooleanVar(master=dialog)
        ttk.Checkbutton(toolbar,text='Só pendências',variable=only_pending,command=lambda:redraw()).pack(side='right')
        host=ttk.Frame(body);host.pack(fill='both',expand=True)
        tree=ttk.Treeview(host,columns=('name','status','words','sent'),show='headings',selectmode='browse')
        for key,label,width in [('name','Condomínio',270),('status','Situação',190),('words','Words',75),('sent','Envios confirmados',160)]:
            tree.heading(key,text=label);tree.column(key,width=width)
        tree.pack(side='left',fill='both',expand=True)
        scroll=ttk.Scrollbar(host,command=tree.yview);scroll.pack(side='right',fill='y');tree.configure(yscrollcommand=scroll.set)
        def redraw():
            selected=tree.selection();tree.delete(*tree.get_children())
            snapshot=self.history.month(root,names,period) if names else {}
            for i,name in enumerate(names):
                book=snapshot[name]
                if only_pending.get() and book.get('complete'):continue
                tree.insert('','end',iid=str(i),values=(name,self.history.status(book),len(book.get('updated',[])),
                            sum(v['state']=='sent' for v in book.get('sent',{}).values())))
            if selected and tree.exists(selected[0]):tree.selection_set(selected)
            totals=self.history.totals(root,names,period,snapshot=snapshot)
            text=f"{totals['complete']}/{totals['total']} livros concluídos · Tempo das operações: {totals['seconds']/60:.1f} min"
            if totals['saving'] is not None:text+=f" · Economia estimada ({totals['saving_count']} livros): {totals['saving']/60:.1f} min"
            if only_pending.get():text+=f' · {len(tree.get_children())} pendentes'
            total.set(text)
        def chosen():
            return names[int(tree.selection()[0])] if tree.selection() else None
        def complete(value):
            name=chosen()
            if name and messagebox.askyesno('Concluir livro' if value else 'Reabrir livro',f'{name} — {period}\n'+('Você conferiu as folhas e terminou a montagem do livro?' if value else 'Retirar a confirmação de conclusão deste livro?'),parent=dialog):
                self.history.complete(root,name,period,value);redraw();self.refresh_book_status()
        def open_selected(event=None):
            if event and event.type==tk.EventType.ButtonPress:
                item=tree.identify_row(event.y)
                if not item:return
                tree.selection_set(item)
            name=chosen()
            if name:
                dialog.destroy();self.name.set(name);self.query()
        tree.bind('<Double-1>',open_selected)
        tree.bind('<Return>',open_selected)
        actions=ttk.Frame(body);actions.pack(fill='x',pady=10)
        ttk.Button(actions,text='Abrir condomínio',command=open_selected).pack(side='left')
        ttk.Button(actions,text='Concluir livro',command=lambda:complete(True)).pack(side='left',padx=8)
        ttk.Button(actions,text='Reabrir',command=lambda:complete(False)).pack(side='left')
        def restore():
            try:options=self.history.recovery_options(period)
            except Exception as exc:
                messagebox.showerror('Restaurar controle',str(exc),parent=dialog);return
            if not options:
                messagebox.showinfo('Restaurar controle','Não há registros salvos ou backup para esta competência. Não é possível reconstruir envios anteriores com segurança.',parent=dialog);return
            recovery=tk.Toplevel(dialog);recovery.title('Restaurar controle — '+period);recovery.transient(dialog);recovery.grab_set()
            shell=ttk.Frame(recovery,padding=16);shell.pack(fill='both',expand=True)
            ttk.Label(shell,text='Escolha o histórico que pertence a esta pasta de condomínios.',wraplength=650).pack(anchor='w')
            labels=[('Backup anterior' if Path(o['path'])==self.history.previous_backup else 'Backup recente' if Path(o['path'])==self.history.backup else 'Histórico salvo')+f" · {o['count']} registros · {o['root']}" for o in options]
            choice=ttk.Combobox(shell,values=labels,state='readonly',width=85);choice.pack(fill='x',pady=12);choice.current(0)
            ttk.Label(shell,text='Recupera somente '+period+' e os condomínios da lista atual.\nOs registros atuais serão preservados; nenhum documento será alterado.',wraplength=650).pack(anchor='w')
            def dismiss():recovery.destroy();dialog.grab_set()
            def apply():
                if not messagebox.askyesno('Confirmar recuperação',f'Restaurar os registros selecionados para {period}?\nConfira a pasta de origem:\n'+options[choice.current()]['root'],parent=recovery):return
                try:
                    count=self.history.restore_month(options[choice.current()],root,period,names)
                    dismiss();redraw();self.refresh_book_status()
                    messagebox.showinfo('Controle restaurado',f'{count} registro(s) recuperado(s). Confira os status e os envios.',parent=dialog)
                except Exception as exc:messagebox.showerror('Controle não restaurado',str(exc),parent=recovery)
            buttons=ttk.Frame(shell);buttons.pack(fill='x',pady=(12,0))
            ttk.Button(buttons,text='Restaurar',command=apply).pack(side='right')
            ttk.Button(buttons,text='Cancelar',command=dismiss).pack(side='right',padx=8)
            recovery.protocol('WM_DELETE_WINDOW',dismiss)
        ttk.Button(actions,text='Restaurar controle',command=restore).pack(side='right')
        row=ttk.Frame(body);row.pack(fill='x')
        ttk.Label(row,text='Seu tempo manual por livro (min):').pack(side='left')
        baseline=tk.StringVar(master=dialog,value='' if self.history.data.get('manual_minutes') is None else str(self.history.data['manual_minutes']))
        ttk.Entry(row,textvariable=baseline,width=8).pack(side='left',padx=6)
        def save_baseline():
            try:self.history.set_baseline(float(baseline.get().replace(',','.')) if baseline.get().strip() else None);redraw()
            except ValueError as exc:messagebox.showerror('Tempo manual',str(exc),parent=dialog)
        ttk.Button(row,text='Salvar referência',command=save_baseline).pack(side='left')
        ttk.Label(body,text='Economia é uma estimativa dos livros concluídos, usando sua referência manual.\nTempo da operação não mede exatamente sua atenção. Envio à fila não confirma impressão física.',style='Muted.TLabel',wraplength=730).pack(anchor='w',pady=8)
        redraw()

    def destroy(self):
        self.catalog_cancel.set()
        self.cancel_period_query()
        if hasattr(self,'poll_callback'):self.after_cancel(self.poll_callback)
        if hasattr(self,'year_trace'):self.year.trace_remove('write',self.year_trace)
        if hasattr(self,'name_trace'):self.name.trace_remove('write',self.name_trace)
        if hasattr(self,'month_trace'):self.month.trace_remove('write',self.month_trace)
        super().destroy()

    def close(self):
        if self.busy:
            self.cancel.set();messagebox.showinfo('Aguarde','Cancelamento solicitado. Aguarde a operação atual terminar.',parent=self);return
        self.destroy()


class CentralDialog(CentralView,tk.Toplevel):
    def __init__(self,parent,path):
        tk.Toplevel.__init__(self,parent)
        self.build(parent,path)


class CentralPanel(CentralView,ttk.Frame):
    def __init__(self,parent,path):
        ttk.Frame.__init__(self,parent)
        self.build(parent,path,embedded=True)


