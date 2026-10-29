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
from central_service import DEFAULTS,LABELS,catalog,search,compare_reports,selected_plan,digest
from central_print import execute_plan
from obligations import check_obligations
from word_service import Word,discover
from central_update import prepare_closing,closing_condo,run_update
from print_service import available_printers
from book_history import BookHistory,file_id
from document_period import inspect_periods,period_summary


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


def settings_dialog(parent,path,on_saved=None):
    try:settings=load_settings(path)
    except Exception as exc:messagebox.showerror('Opções',str(exc),parent=parent);return
    dialog=tk.Toplevel(parent);dialog.title('AutoWord — opções');dialog.transient(parent.winfo_toplevel());dialog.grab_set()
    dialog.geometry(f'760x{min(650,dialog.winfo_screenheight()-100)}')
    shell=ttk.Frame(dialog,padding=16);shell.pack(fill='both',expand=True)
    tabs=ttk.Notebook(shell);tabs.pack(fill='both',expand=True)
    paths=ttk.Frame(tabs,padding=12);update=ttk.Frame(tabs,padding=12)
    tabs.add(paths,text='Pastas e impressoras');tabs.add(update,text='Atualização e responsáveis')
    values={}
    for field,label in [('root','Pasta principal dos condomínios'),('statements','Extratos (pasta acima dos anos)'),('reports','PDFs pessoais de obrigações'),('destination','Salvar Words em (vazio: pasta original)')]:
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
            for field,needle in [('main_printer','e50145'),('report_printer','l3150')]:
                if not values[field].get():values[field].set(next((n for n in names if needle in n.casefold()),''))
        except queue.Empty:dialog.after(100,poll)
    dialog.after(100,poll)
    include=tk.BooleanVar(value=settings['include_report'])
    ttk.Checkbutton(paths,text='Marcar obrigações para impressão por padrão',variable=include).pack(anchor='w',pady=12)
    ttk.Label(paths,text='Uma cópia, somente frente. PDFs usam o Adobe e as preferências da impressora.\nOrdem: capa, aprovação, anexo I, anexo II e extratos. Obrigações na outra impressora.',wraplength=650).pack(anchor='w')
    ttk.Label(update,text='Words a atualizar',style='Section.TLabel').pack(anchor='w',pady=(14,5))
    choices=ttk.Frame(update);choices.pack(fill='x')
    kinds=[tk.BooleanVar(value=k in settings.get('update_kinds',range(4))) for k in range(4)]
    for k,label in enumerate(('Aprovação','Capa','Anexo I','Anexo II')):
        ttk.Checkbutton(choices,text=label,variable=kinds[k]).pack(side='left',padx=5)
    subfolder=tk.BooleanVar(value=settings.get('create_subfolder',False))
    ttk.Checkbutton(update,text='Criar subpasta AAAA-MM para os Words',variable=subfolder).pack(anchor='w',pady=12)
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
    def updates():
        from launcher import configure_updates
        configure_updates(owner)
    ttk.Button(update,text='Atualizações do aplicativo…',command=lambda:call(updates)).pack(anchor='w',pady=10)
    def save():
        try:
            updated=dict(settings,**{k:v.get().strip() for k,v in values.items()},include_report=include.get(),
                         update_kinds=[k for k,v in enumerate(kinds) if v.get()],create_subfolder=subfolder.get())
            if not updated['root'] or not updated['statements']:raise ValueError('Informe as pastas principais de condomínios e extratos.')
            save_settings(path,updated);dismiss()
            if on_saved:on_saved()
        except Exception as exc:messagebox.showerror('Opções não salvas',str(exc),parent=dialog)
    footer=ttk.Frame(shell);footer.pack(fill='x',pady=(12,0))
    ttk.Button(footer,text='Salvar',style='Primary.TButton',command=save).pack(side='right')
    ttk.Button(footer,text='Cancelar',command=dismiss).pack(side='right',padx=8)
    dialog.protocol('WM_DELETE_WINDOW',dismiss)
    return dialog


class CentralView:
    def build(self,parent,path,embedded=False):
        self.embedded=embedded
        self.parent=parent;self.path=Path(path);self.settings=load_settings(path)
        self.history=BookHistory(self.path.with_name('livros.json'))
        self.operation=None;self.print_request=[];self.period_cache={}
        self.external_busy=False
        self.result=None;self.comparison=None;self.checked=set();self.busy=False;self.events=queue.Queue();self.cancel=parent.cancel
        if not embedded:
            self.title('AutoWord — atualizar e imprimir');self.geometry(f'1080x{min(740,self.winfo_screenheight()-100)}');self.minsize(900,600)
            self.transient(parent);self.grab_set()
        self.controls=[]
        self.name=tk.StringVar();self.month=parent.month;self.year=parent.year
        self.version=tk.StringVar(value='pdf');self.status=tk.StringVar(value='Carregando nomes dos condomínios…')
        body=ttk.Frame(self,padding=16);body.pack(fill='both',expand=True)
        body.columnconfigure(0,weight=1);body.rowconfigure(3,weight=1)
        header=ttk.Frame(body);header.grid(row=0,column=0,sticky='ew',pady=(0,10))
        ttk.Label(header,text='AutoWord',style='Title.TLabel').pack(side='left')
        self.action(header,'Opções',self.configure_paths).pack(side='right')
        self.action(header,'Controle mensal',self.monthly_control).pack(side='right',padx=8)
        self.action(header,'Atualização em lote',self.open_batch).pack(side='right',padx=8)
        row=ttk.Frame(body);row.grid(row=1,column=0,sticky='ew')
        ttk.Label(row,text='Condomínio').pack(side='left')
        self.names=ttk.Combobox(row,textvariable=self.name,state='readonly',width=38);self.names.pack(side='left',padx=8)
        from engine import MONTHS
        self.months=MONTHS
        self.month_box=ttk.Combobox(row,textvariable=self.month,values=[m.title() for m in MONTHS],state='readonly',width=13);self.month_box.pack(side='left',padx=5)
        self.year_box=ttk.Spinbox(row,textvariable=self.year,from_=2000,to=2099,width=6);self.year_box.pack(side='left')
        self.controls.extend([self.names,self.month_box,self.year_box])
        self.action(row,'Buscar arquivos',self.query).pack(side='left',padx=8)
        self.book_status=tk.StringVar(value='Pendente')
        legend=ttk.Frame(body);legend.grid(row=2,column=0,sticky='ew',pady=4)
        self.document_period=tk.StringVar(value='Competência dos Words: selecione um condomínio.')
        ttk.Label(legend,textvariable=self.document_period,style='Section.TLabel',wraplength=1000).pack(side='bottom',anchor='w',pady=(4,0))
        ttk.Label(legend,textvariable=self.book_status,style='Section.TLabel').pack(side='right')
        ttk.Label(legend,text='☐ Não imprimir    ☑ Imprimir  •  Clique na caixinha para escolher. Recentes aparecem primeiro na lista.',style='Muted.TLabel').pack(side='left')
        host=ttk.Frame(body);host.grid(row=3,column=0,sticky='nsew')
        self.tree=ttk.Treeview(host,columns=('check','group','file','printer'),show='headings',selectmode='browse')
        for key,title,width in [('check','Imprimir',85),('group','Documento / ordem',195),('file','Arquivo',460),('printer','Impressora',280)]:
            self.tree.heading(key,text=title);self.tree.column(key,width=width,minwidth=50,stretch=key in ('file','printer'))
        self.tree.column('check',anchor='center',stretch=False)
        self.tree.tag_configure('even',background='#FFFFFF')
        self.tree.tag_configure('odd',background='#F2F6F9')
        self.tree.tag_configure('missing',foreground='#8B4D23')
        self.tree.pack(side='left',fill='both',expand=True);scroll=ttk.Scrollbar(host,command=self.tree.yview);scroll.pack(side='right',fill='y');self.tree.configure(yscrollcommand=scroll.set)
        self.tree.bind('<Button-1>',self.click);self.tree.bind('<space>',self.toggle)
        row=ttk.Frame(body);row.grid(row=4,column=0,sticky='ew',pady=10)
        self.action(row,'Todos os extratos',lambda:self.check_statements(True)).pack(side='left')
        self.action(row,'Desmarcar extratos',lambda:self.check_statements(False)).pack(side='left',padx=6)
        self.action(row,'Abrir arquivo',self.open_file).pack(side='left',padx=6)
        self.action(row,'Vincular arquivo…',self.link).pack(side='left',padx=6)
        self.action(row,'Vincular Word Jurídico…',lambda:self.link(True)).pack(side='left')
        row=ttk.Frame(body);row.grid(row=5,column=0,sticky='ew',pady=4)
        self.action(row,'Comparar obrigações',self.compare).pack(side='left')
        self.action(row,'Abrir Word Jurídico',lambda:self.open_file(True)).pack(side='left',padx=6)
        self.action(row,'Conferi manualmente',self.manual_review).pack(side='left')
        self.pdf_radio=ttk.Radiobutton(row,text='Usar PDF pessoal',variable=self.version,value='pdf',command=self.redraw);self.pdf_radio.pack(side='left',padx=10)
        self.word_radio=ttk.Radiobutton(row,text='Usar Word atual',variable=self.version,value='word',command=self.redraw);self.word_radio.pack(side='left')
        self.controls.extend((self.pdf_radio,self.word_radio))
        self.details=tk.Text(body,height=5,wrap='word',state='disabled',font=('Segoe UI',10));self.details.grid(row=6,column=0,sticky='ew',pady=6)
        footer=ttk.Frame(body);footer.grid(row=7,column=0,sticky='ew')
        ttk.Label(footer,textvariable=self.status,wraplength=740).pack(side='left',fill='x',expand=True)
        actions=ttk.Frame(body);actions.grid(row=8,column=0,sticky='ew',pady=(8,0))
        self.update_print_button=self.action(actions,'Atualizar e imprimir',lambda:self.update_selected(True));self.update_print_button.configure(style='Primary.TButton');self.update_print_button.pack(side='left')
        self.action(actions,'Só atualizar',self.update_selected).pack(side='left',padx=8)
        self.print_button=self.action(actions,'Só imprimir',self.print_selected);self.print_button.pack(side='left')
        self.action(actions,'Conferir atualização (opcional)',self.preview_update).pack(side='right')
        self.cancel_button=ttk.Button(footer,text='Cancelar',command=self.cancel.set,state='disabled');self.cancel_button.pack(side='right',padx=8)
        if not embedded:self.protocol('WM_DELETE_WINDOW',self.close)
        self.names.bind('<<ComboboxSelected>>',lambda e:self.query())
        self.month_box.bind('<<ComboboxSelected>>',lambda e:self.invalidate())
        self.month_trace=self.month.trace_add('write',lambda *args:self.invalidate())
        self.year_trace=self.year.trace_add('write',lambda *args:self.invalidate())
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
        self.result=None;self.comparison=None;self.checked.clear();self.tree.delete(*self.tree.get_children());self.version.set('pdf')
        self.status.set('Clique em Buscar arquivos para a seleção atual.')
        self.document_period.set('Competência dos Words: busque os arquivos para consultar.')
        self.refresh_book_status()

    def configure_paths(self):
        if not self.busy and not self.parent.busy:
            settings_dialog(self,self.path,self.reload)

    def reload(self):
        self.settings=load_settings(self.path);self.invalidate()
        settings=copy.deepcopy(self.settings);mappings=copy.deepcopy(self.parent.mappings)
        def work():
            self.history.prepare_root(settings['root'])
            names=catalog(settings)
            if not self.embedded:return names
            condos=[c for c in discover(settings['root'],mappings) if c['name'] in names] if names else []
            return {'names':names,'condos':condos,'root':settings['root']}
        self.run(work,'workspace' if self.embedded else 'catalog')

    def context(self):
        return self.name.get(),self.months.index(self.month.get().lower())+1,int(self.year.get())

    def query(self):
        if self.busy or self.parent.busy:return
        try:
            name,month,year=self.context()
            if not name or not 2000<=year<=2099:raise ValueError('Selecione o condomínio e uma competência válida.')
        except Exception as exc:messagebox.showerror('Seleção',str(exc),parent=self);return
        self.invalidate()
        settings=copy.deepcopy(self.settings);mappings=copy.deepcopy(self.parent.mappings)
        names=tuple(self.names.cget('values'))
        self.document_period.set('Competência dos Words: consultando…')
        def work():
            result=search(settings,name,month,year,mappings,names=names)
            inspect_periods(result,self.period_cache,Word,self.cancel)
            return check_obligations(result,month,year)
        self.run(work,'search')

    def run(self,work,kind):
        if self.busy or self.parent.busy:return
        self.busy=True;self.parent.busy=True;self.cancel.clear()
        for widget in self.controls:widget.configure(state='disabled')
        self.cancel_button.configure(state='normal');self.status.set('Processando…')
        tracking=None
        if kind=='printed' and self.result:
            tracking=dict(root=self.settings['root'],name=self.result['name'],period=self.result['period'],words=0,sent=[],attempt=[],planned=list(self.print_request))
            self.operation=tracking
        def worker():
            started=time.monotonic();error='';result=None
            try:result=work()
            except Exception as exc:error=str(exc)
            if tracking is not None:
                seconds=time.monotonic()-started
                try:self.history.finish(tracking['root'],tracking['name'],tracking['period'],seconds,error)
                except Exception as exc:error+='\nNão foi possível salvar o controle: '+str(exc)
                confirmed={file_id(r) for r in tracking['sent']}
                pending=[r['label'] for r in tracking['planned'] if file_id(r) not in confirmed]
                lines=[f"{tracking['name']} — {tracking['period']}",f"Words verificados/atualizados: {tracking['words']}",f"Envios confirmados: {len(tracking['sent'])}",f"Tempo da operação: {seconds:.1f} s"]
                if tracking['sent']:lines.append('Enviados: '+', '.join(r['label'] for r in tracking['sent']))
                if pending:lines.append('Pendentes/sem confirmação: '+', '.join(pending))
                lines.append('Confira a saída física antes de concluir o livro no Controle mensal.')
                if error:lines.append(error)
                elif result:lines.append(str(result))
                result='\n'.join(lines)
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
                self.names.configure(state='readonly');self.month_box.configure(state='readonly')
        try:
            for _ in range(40):
                kind,value=self.events.get_nowait()
                if kind=='workspace':
                    self.parent.apply_discovered(value['root'],value['condos'])
                    self.names.configure(values=self.history.ordered_names(self.settings['root'],value['names']))
                    if self.name.get() not in value['names']:self.name.set('')
                    self.status.set('Selecione condomínio e competência para atualizar ou imprimir.')
                    if getattr(self,'query_after_reload',False) and self.name.get():
                        self.query_after_reload=False;self.after_idle(self.query)
                elif kind=='catalog':
                    self.names.configure(values=self.history.ordered_names(self.settings['root'],value))
                    current=self.parent.selected()
                    candidate=current[0]['name'] if len(current)==1 else self.name.get()
                    if candidate in value:self.name.set(candidate)
                    self.status.set('Selecione o nome do condomínio e busque os arquivos.')
                elif kind=='search':
                    self.history.touch(self.settings['root'],value['name'])
                    self.names.configure(values=self.history.ordered_names(self.settings['root'],self.names.cget('values')))
                    self.refresh_book_status()
                    self.result=value;self.show_period(value)
                    self.checked={i for i,row in enumerate(value['rows']) if row['checked']}
                    self.redraw();self.show_details('\n'.join(value['warnings']) or 'Arquivos localizados. Selecione o que deseja imprimir.')
                    self.status.set('Extratos: todos selecionados por padrão. Obrigações são opcionais e exigem conferência.')
                    if value.get('due_notice'):
                        self.status.set('Atenção: há obrigações nesta competência ou em meses anteriores.')
                        messagebox.showwarning('Revisar obrigações — '+value['name'],value['due_notice'],parent=self)
                elif kind=='duplicates':
                    text,answer,ready=value
                    answer.append(messagebox.askyesno('Possível impressão repetida',text,parent=self))
                    ready.set()
                elif kind=='comparison':
                    self.comparison=value;self.version.set('pdf' if value['equal'] else '');self.redraw();self.show_details(value['diff']);self.status.set('Textos equivalentes: será usado o PDF pessoal.' if value['equal'] else 'Há diferenças. Confira e escolha PDF pessoal ou Word atual antes de imprimir.')
                elif kind=='updated':
                    self.result=value;self.show_period(value);self.redraw()
                    self.show_details('\n'.join(value.get('warnings',[])))
                elif kind=='preview_update':
                    self.show_details(value);self.status.set('Conferência concluída. Nenhum documento alterado.')
                elif kind=='printed':self.status.set(value);self.show_details(value)
                elif kind=='log':self.status.set(value)
                elif kind=='error':
                    self.show_details(value);self.status.set('Não foi possível concluir. Confira os detalhes.');messagebox.showerror('Central de impressão',value,parent=self)
                elif kind=='done':
                    self.busy=False;self.parent.busy=False
                    for widget in self.controls:widget.configure(state='normal')
                    self.names.configure(state='readonly');self.month_box.configure(state='readonly');self.cancel_button.configure(state='disabled')
                    self.refresh_book_status()
                    self.parent.events.put(('central_done',None))
        except queue.Empty:pass
        if self.winfo_exists():self.poll_callback=self.after(100,self.poll)

    def show_period(self,result):
        summary=period_summary(result)
        self.document_period.set(summary.split('\n')[0]+(' Confira os detalhes abaixo.' if '\n' in summary else ''))
        if '\n' in summary:
            result['warnings']=[summary]+result.get('warnings',[])

    def redraw(self):
        if not self.result:return
        selected=self.tree.selection()
        focus=self.tree.focus()
        self.tree.delete(*self.tree.get_children())
        for i,row in enumerate(self.result['rows']):
            path=self.result['word'] if row['group']=='obligations' and self.version.get()=='word' else row['path']
            self.tree.insert('','end',iid=str(i),values=('☑' if i in self.checked else '☐',row['label'],Path(path).name if path else 'Arquivo não localizado — vincule ou desmarque',row['printer']),tags=(('even' if i%2==0 else 'odd'),)+(() if path else ('missing',)))
        if selected and self.tree.exists(selected[0]):self.tree.selection_set(selected[0])
        if focus and self.tree.exists(focus):self.tree.focus(focus)

    def click(self,event):
        if self.tree.identify_column(event.x)=='#1':
            row=self.tree.identify_row(event.y)
            if row:
                self.tree.selection_set(row);self.tree.focus(row)
                self.toggle(index=int(row))
                return 'break'

    def toggle(self,event=None,index=None):
        if self.busy or self.parent.busy or not self.result:return 'break'
        if index is None:
            selected=self.tree.selection()
            if not selected:return 'break'
            index=int(selected[0])
        if index in self.checked:self.checked.remove(index)
        else:self.checked.add(index)
        self.redraw();return 'break'

    def check_statements(self,include):
        if not self.result:return
        for i,row in enumerate(self.result['rows']):
            if row['group']=='statement':
                if include:self.checked.add(i)
                else:self.checked.discard(i)
        self.redraw()

    def show_details(self,text):
        self.details.configure(state='normal');self.details.delete('1.0','end');self.details.insert('end',text);self.details.configure(state='disabled')

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
        self.show_details(self.comparison['diff']+' Escolha PDF pessoal ou Word atual.')

    def open_file(self,word=False):
        if not self.result:return
        path=self.result['word'] if word else self.result['rows'][int(self.tree.selection()[0])]['path'] if self.tree.selection() else None
        if not word and self.tree.selection() and self.result['rows'][int(self.tree.selection()[0])]['group']=='obligations' and self.version.get()=='word':path=self.result['word']
        if path:
            try:os.startfile(str(path))
            except Exception as exc:messagebox.showerror('Abrir arquivo',str(exc),parent=self)

    def link(self,word=False):
        if not self.result:return
        if word:key='report_word';group='word'
        else:
            selected=self.tree.selection()
            if not selected:messagebox.showinfo('Vincular','Selecione a linha do documento na lista.',parent=self);return
            row=self.result['rows'][int(selected[0])];key=row['key'];group=row['group']
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
        except Exception as exc:messagebox.showerror('Conferência',str(exc),parent=self);return
        def work():
            with Word() as word:
                condo,docs,target=prepare_closing(word,result,settings,month,year,state)
            lines=[f"{condo['name']} — {month:02}/{year}",f'Destino: {target}']
            for doc in docs:
                lines.append(doc['path'].name)
                lines.extend(f'  {c.old} → {c.new}' for c in doc['changes'] if c.old!=c.new)
            return '\n'.join(lines)
        self.run(work,'preview_update')

    def update_selected(self,printing=False):
        if self.busy or self.parent.busy or not self.result:return
        try:
            month,year=self.context()[1:];state=self.update_state()
            result=copy.deepcopy(self.result);settings=copy.deepcopy(self.settings)
            kinds=settings.get('update_kinds',range(4))
            closing_condo(result,kinds)
            rows=selected_plan(result,self.checked,self.version.get(),self.comparison) if printing else None
            if rows is not None and any(r['group']=='closing' and int(r['key'].removeprefix('closing')) not in kinds for r in rows):
                raise ValueError('Marque para atualização todos os Words selecionados para impressão em Opções.')
            summary=f"{result['name']} — {month:02}/{year}\nAtualizar: "+', '.join(LABELS[k] for k in kinds)
            summary+='\nDestino: '+(settings.get('destination') or 'pasta original do fechamento')
            if settings.get('create_subfolder'):summary+=f' / {year}-{month:02}'
            if rows is not None:summary+='\n\nImprimir, nesta ordem:\n'+'\n'.join(f"{r['label']} → {r['printer']}" for r in rows)
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
        if not messagebox.askyesno('Confirmar impressão',summary+'\n\nUma cópia, somente frente. Enviar estes documentos?',parent=self):return
        self.print_request=rows
        def work():
            count=self.tracked_print(rows,self.cancel,lambda text:self.events.put(('log',text)),Word)
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
        names=list(self.names.cget('values'));root=self.settings['root']
        dialog=tk.Toplevel(self);dialog.title('Controle mensal — '+period);dialog.transient(self.winfo_toplevel());dialog.grab_set();dialog.geometry('780x530')
        body=ttk.Frame(dialog,padding=16);body.pack(fill='both',expand=True)
        total=tk.StringVar(master=dialog)
        ttk.Label(body,textvariable=total,style='Section.TLabel').pack(anchor='w',pady=(0,8))
        host=ttk.Frame(body);host.pack(fill='both',expand=True)
        tree=ttk.Treeview(host,columns=('name','status','words','sent'),show='headings',selectmode='browse')
        for key,label,width in [('name','Condomínio',270),('status','Situação',190),('words','Words',75),('sent','Envios confirmados',160)]:
            tree.heading(key,text=label);tree.column(key,width=width)
        tree.pack(side='left',fill='both',expand=True)
        scroll=ttk.Scrollbar(host,command=tree.yview);scroll.pack(side='right',fill='y');tree.configure(yscrollcommand=scroll.set)
        def redraw():
            selected=tree.selection();tree.delete(*tree.get_children())
            for i,name in enumerate(names):
                b=self.history.get(root,name,period)
                tree.insert('','end',iid=str(i),values=(name,self.history.status(b),len(b.get('updated',[])),sum(v['state']=='sent' for v in b.get('sent',{}).values())))
            if selected:tree.selection_set(selected)
            totals=self.history.totals(root,names,period)
            text=f"{totals['complete']}/{totals['total']} livros concluídos · Tempo das operações: {totals['seconds']/60:.1f} min"
            if totals['saving'] is not None:text+=f" · Economia estimada ({totals['saving_count']} livros): {totals['saving']/60:.1f} min"
            total.set(text)
        def chosen():
            return names[int(tree.selection()[0])] if tree.selection() else None
        def complete(value):
            name=chosen()
            if name and messagebox.askyesno('Concluir livro' if value else 'Reabrir livro',f'{name} — {period}\n'+('Você conferiu as folhas e terminou a montagem do livro?' if value else 'Retirar a confirmação de conclusão deste livro?'),parent=dialog):
                self.history.complete(root,name,period,value);redraw();self.refresh_book_status()
        def open_selected():
            name=chosen()
            if name:
                dialog.destroy();self.name.set(name);self.query()
        actions=ttk.Frame(body);actions.pack(fill='x',pady=10)
        ttk.Button(actions,text='Abrir condomínio',command=open_selected).pack(side='left')
        ttk.Button(actions,text='Concluir livro',command=lambda:complete(True)).pack(side='left',padx=8)
        ttk.Button(actions,text='Reabrir',command=lambda:complete(False)).pack(side='left')
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
        if hasattr(self,'poll_callback'):self.after_cancel(self.poll_callback)
        if hasattr(self,'year_trace'):self.year.trace_remove('write',self.year_trace)
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
