"""Condomínio Fácil — aplicativo local para Windows e Microsoft Word."""
import copy
import json
import os
import queue
import re
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import ttk, filedialog, messagebox
from datetime import date
from engine import MONTHS, FILES, roster
from word_service import Word, discover, inspect_condo, generate, select_files, output_targets, digest
from responsible_sheet import SheetMonitor, read_table, sheet_names, key
from version import VERSION
from resignations import load_pdf,find_pdfs,file_hash,propose_signature
from theme import apply_theme, COLORS

DATA = Path(os.environ.get('LOCALAPPDATA', str(Path.home())))/'CondominioFacil'
CONFIG = DATA/'responsaveis.json'
MAPPINGS = DATA/'arquivos.json'

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.style = apply_theme(self)
        self.title(f'Condomínio Fácil — atualização de documentos • versão {VERSION}')
        height = min(860,self.winfo_screenheight()-40)
        self.geometry(f'{min(1180,self.winfo_screenwidth()-40)}x{height}')
        self.minsize(900,min(650,height))
        self.events = queue.Queue()
        self.cancel = threading.Event()
        self.busy = False
        self.preview = {}
        self.condos = []
        self.output = None
        self.config = {}
        self.mappings = {}
        self.sheet_monitor = None
        self.sheet_groups = {}
        self.sheet_mapping = {}
        self.sheet_polling = False
        self.sheet_error = None
        self.pending_sheet = None
        self.pending_regen = set()
        self.pending_updates = set()
        self.next_retry = {}
        self.last_jobs = {}
        self.generation_cache = {}
        self.state_dirty = False
        if MAPPINGS.exists():
            try:
                self.mappings = json.loads(MAPPINGS.read_text(encoding='utf-8'))
                if not isinstance(self.mappings, dict):
                    raise ValueError('Formato de seleção inválido')
            except Exception as exc:
                messagebox.showerror('Seleção de arquivos não carregada', str(exc)+f'\nRevise {MAPPINGS}.')
                self.destroy()
                return
        self.generation_cache = self.mappings.get('__cache__',{})
        self.source_models = self.mappings.get('__models__',{})
        self.resignations = self.mappings.get('__resignations__',{})
        self.pdf_stats = {}
        self.pending_updates = set(self.mappings.get('__pending_updates__',[]))
        if CONFIG.exists():
            try:
                self.config = json.loads(CONFIG.read_text(encoding='utf-8'))
                if not isinstance(self.config, dict):
                    raise ValueError('Cadastro inválido')
            except Exception as exc:
                messagebox.showerror('Cadastro não carregado', f'{exc}\nO arquivo não será sobrescrito. Revise responsaveis.json em {DATA}.')
                self.destroy()
                return
        self.folder = tk.StringVar()
        self.destination = tk.StringVar()
        self.create_subfolder = tk.BooleanVar(value=False)
        self.doc_choices = [tk.BooleanVar(value=True) for _ in FILES]
        self.sheet_status = tk.StringVar(value='Nenhuma planilha vinculada.')
        self.month = tk.StringVar(value=MONTHS[date.today().month-1].title())
        self.year = tk.StringVar(value=str(date.today().year))
        self.status = tk.StringVar(value='Escolha uma pasta para começar. A conferência é opcional.')
        self.controls = []
        self.build_interface()
        self.protocol('WM_DELETE_WINDOW', self.close)
        self.after(100, self.poll)
        self.after(3000, self.watch_sheet)

    def build_interface(self):
        top = ttk.Frame(self, padding=(20, 16))
        top.pack(fill='both', expand=True)
        top.columnconfigure(0, weight=1)
        top.rowconfigure(5, weight=1)
        header = ttk.Frame(top)
        header.grid(row=0, column=0, sticky='ew', pady=(0, 12))
        title = ttk.Frame(header)
        title.pack(side='left')
        ttk.Label(title, text='Documentos em dia', style='Title.TLabel').pack(anchor='w')
        ttk.Label(title, text='Condomínio Fácil  /  Atualização em lote',
                  style='Muted.TLabel').pack(anchor='w', pady=(3, 0))
        self.button(header, 'Opções', self.options_dialog).pack(side='right')

        card = ttk.Frame(top, style='Card.TFrame', padding=12)
        card.grid(row=1, column=0, sticky='ew')
        card.columnconfigure(1, weight=1)
        for index, (label, variable, command) in enumerate((
                ('Pasta de origem', self.folder, self.choose_root),
                ('Salvar em', self.destination, self.choose_output))):
            ttk.Label(card, text=label, style='Card.TLabel', width=16).grid(
                row=index, column=0, sticky='w', pady=3)
            entry = ttk.Entry(card, textvariable=variable,
                              state='normal' if variable is self.destination else 'readonly')
            entry.grid(row=index, column=1, sticky='ew', padx=(0, 12), pady=3)
            self.controls.append((entry, 'normal' if variable is self.destination else 'readonly'))
            self.button(card, 'Escolher…', command).grid(row=index, column=2, pady=3)
        self.destination_hint = tk.StringVar()
        ttk.Label(top, textvariable=self.destination_hint, style='Muted.TLabel').grid(
            row=2, column=0, sticky='w', pady=(6, 8))
        self.destination.trace_add('write', self.update_destination_hint)
        self.create_subfolder.trace_add('write', self.update_destination_hint)
        self.update_destination_hint()

        period = ttk.Frame(top)
        period.grid(row=3, column=0, sticky='ew', pady=(0, 8))
        ttk.Label(period, text='Competência', style='Section.TLabel').pack(side='left', padx=(0, 12))
        months = ttk.Combobox(period, textvariable=self.month,
                             values=[m.title() for m in MONTHS], state='readonly', width=14)
        months.pack(side='left', padx=(0, 8))
        months.bind('<<ComboboxSelected>>', self.invalidate)
        self.controls.append((months, 'readonly'))
        year = ttk.Spinbox(period, textvariable=self.year, from_=2000, to=2099, width=6)
        year.pack(side='left', padx=(0, 16))
        self.controls.append((year, 'normal'))
        self.year.trace_add('write', self.invalidate)
        subfolder = ttk.Checkbutton(period, text='Criar subpasta AAAA-MM', variable=self.create_subfolder)
        subfolder.pack(side='right')
        self.controls.append((subfolder, 'normal'))

        list_header = ttk.Frame(top)
        list_header.grid(row=4, column=0, sticky='ew', pady=(0, 6))
        self.selection_summary = tk.StringVar(value='Condomínios')
        ttk.Label(list_header, textvariable=self.selection_summary, style='Section.TLabel').pack(side='left')
        self.button(list_header, 'Selecionar todos', self.select_all).pack(side='right')
        self.list_area = ttk.Frame(top)
        self.list_area.grid(row=5, column=0, sticky='nsew')
        self.tree = ttk.Treeview(self.list_area, columns=('name', 'state'), show='headings',
                                 selectmode='extended', height=6)
        self.tree.heading('name', text='Condomínio')
        self.tree.heading('state', text='Situação')
        self.tree.column('name', width=280, minwidth=180)
        self.tree.column('state', width=650, minwidth=240)
        self.tree.pack(side='left', fill='both', expand=True)
        scroll = ttk.Scrollbar(self.list_area, command=self.tree.yview)
        scroll.pack(side='right', fill='y')
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.bind('<<TreeviewSelect>>', self.selection_changed)
        self.tree.bind('<Control-a>', self.select_all_shortcut)
        self.empty_state = ttk.Label(self.list_area, text='Escolha uma pasta para começar',
                                      style='Muted.TLabel')
        self.empty_state.place(relx=.5, rely=.5, anchor='center')

        actions = ttk.Frame(top)
        actions.grid(row=6, column=0, sticky='ew', pady=(10, 8))
        self.generate_button = self.button(actions, 'Atualizar documentos', self.run_generation)
        self.generate_button.configure(style='Primary.TButton')
        self.generate_button.pack(side='left')
        self.button(actions, 'Conferir (opcional)', self.inspect).pack(side='left', padx=8)
        self.cancel_button = ttk.Button(actions, text='Cancelar', command=self.cancel.set, state='disabled')
        self.cancel_button.pack(side='left')
        self.button(actions, 'Abrir saída', self.open_output).pack(side='right')

        self.progress = ttk.Progressbar(top, mode='indeterminate', maximum=100)
        self.progress.grid(row=7, column=0, sticky='ew', pady=(0, 6))
        footer = ttk.Frame(top)
        footer.grid(row=8, column=0, sticky='ew')
        self.status_label = ttk.Label(footer, textvariable=self.status, style='Muted.TLabel', wraplength=800)
        self.status_label.pack(side='left', fill='x', expand=True)
        footer.bind('<Configure>', lambda event: self.status_label.configure(wraplength=max(300, event.width-170)))
        self.details_button = ttk.Button(footer, text='Mostrar detalhes', command=self.toggle_details)
        self.details_button.pack(side='right', padx=(12, 0))
        self.details_open = False
        self.details_frame = ttk.Frame(top, padding=(0, 10, 0, 0))
        self.logbox = tk.Text(self.details_frame, height=3, wrap='word', font=('Consolas', 10),
                             background=COLORS['panel'], foreground=COLORS['text'],
                             insertbackground=COLORS['text'], selectbackground=COLORS['selected'],
                             selectforeground=COLORS['text'], relief='flat', padx=12, pady=10,
                             highlightthickness=1, highlightbackground=COLORS['border'], state='disabled')
        self.logbox.pack(side='left', fill='both', expand=True)
        log_scroll = ttk.Scrollbar(self.details_frame, command=self.logbox.yview)
        log_scroll.pack(side='right', fill='y')
        self.logbox.configure(yscrollcommand=log_scroll.set)
        self.bind('<Control-o>', lambda event: self.shortcut(self.choose_root))
        self.bind('<Control-Return>', lambda event: self.shortcut(self.run_generation))
        self.bind('<F1>', lambda event: self.shortcut(self.options_dialog))

    def shortcut(self, command):
        # Não atravessa janelas modais nem dispara ações durante uma geração.
        if not self.busy and self.grab_current() is None:
            command()
        return 'break'

    def select_all_shortcut(self, event=None):
        return self.shortcut(self.select_all)

    def selection_changed(self, *args):
        self.invalidate()
        self.selection_summary.set(f'Condomínios · {len(self.tree.selection())} de {len(self.condos)} selecionados')

    def update_destination_hint(self, *args):
        if self.create_subfolder.get():
            text = 'Salva em uma subpasta AAAA-MM no destino de cada condomínio.'
        elif self.destination.get().strip():
            text = 'Substitui somente os documentos escolhidos na pasta de destino.'
        else:
            text = 'Destino vazio: atualiza os documentos na própria pasta de cada condomínio.'
        self.destination_hint.set(text)

    def toggle_details(self, show=None):
        self.details_open = not self.details_open if show is None else show
        if self.details_open:
            self.details_frame.grid(row=9, column=0, sticky='ew')
        else:
            self.details_frame.grid_remove()
        self.details_button.configure(text='Ocultar detalhes' if self.details_open else 'Mostrar detalhes')

    def button(self, parent, text, command):
        b = ttk.Button(parent, text=text, command=command)
        self.controls.append((b, 'normal'))
        return b

    def log(self, text):
        if re.search(r'\b(ERRO|REVISAR|FALHOU)\b', text, re.IGNORECASE):
            self.toggle_details(True)
        self.logbox.configure(state='normal')
        self.logbox.insert('end', text+'\n')
        self.logbox.see('end')
        self.logbox.configure(state='disabled')

    def report_callback_exception(self, exception_type, value, traceback):
        self.log('ERRO: '+str(value))
        messagebox.showerror('Não foi possível concluir',str(value),parent=self)

    def invalidate(self, *args):
        self.preview = {}

    def choose_root(self):
        selected = filedialog.askdirectory(title='Pasta dos quatro documentos OU pasta principal dos condomínios')
        if not selected:
            return
        mappings = copy.deepcopy(self.mappings)
        def task():
            condos = discover(selected,mappings,progress=lambda name:self.events.put(('progress','Localizando: '+name)))
            self.events.put(('discovered',(selected,condos)))
        self.start(task,'Localizando os condomínios e seus documentos…')

    def apply_discovered(self,selected,condos):
        self.folder.set(selected)
        self.condos = condos
        self.invalidate()
        self.tree.delete(*self.tree.get_children())
        if condos:
            self.empty_state.place_forget()
        else:
            self.empty_state.place(relx=.5, rely=.5, anchor='center')
        for i, condo in enumerate(condos):
            self.tree.insert('', 'end', iid=str(i), values=(condo['name'], ' / '.join(condo['errors']) or '4 arquivos encontrados — pronto para atualizar'))
            if condo['errors']:
                self.log(f"\n{condo['name']}: {' / '.join(condo['errors'])}")
                self.log('  Arquivos Word encontrados: '+('; '.join(condo['found']) or 'nenhum'))
                self.log('  Use “Opções → Selecionar os 4 arquivos…” para indicar os nomes diferentes.')
        self.select_all()
        self.selection_changed()
        self.destination.set(condos[0]['folder'] if len(condos)==1 else '')
        self.status.set(f'{len(condos)} condomínio(s) encontrado(s). Escolha a competência e atualize.')
        self.last_jobs = {}
        for condo in condos:
            saved_job = self.mappings.get('__jobs__',{}).get(condo['folder'])
            if saved_job and saved_job.get('sources') == [str(p) if p else None for p in condo['files']]:
                self.last_jobs[condo['folder']] = {'condo':copy.deepcopy(condo),'target':Path(saved_job['target']),
                    'month':saved_job['month'],'year':saved_job['year'],'kinds':tuple(saved_job['kinds'])}
        saved = self.mappings.get('__planilha__')
        if saved:
            self.activate_sheet(saved['path'],saved['mapping'])
        elif self.sheet_monitor:
            self.activate_sheet(str(self.sheet_monitor.path),self.sheet_mapping)

    def map_files(self):
        selected = self.selected()
        if len(selected) != 1:
            messagebox.showinfo('Selecionar arquivos', 'Selecione apenas um condomínio na lista.')
            return
        condo = selected[0]
        dialog = tk.Toplevel(self)
        dialog.title('Selecionar os quatro arquivos — '+condo['name'])
        dialog.geometry('960x350')
        dialog.transient(self)
        dialog.grab_set()
        ttk.Label(dialog, text='Indique o documento de cada tipo. Não é necessário renomear nem converter os arquivos.', padding=12).pack(anchor='w')
        ttk.Label(dialog, text=condo['folder'], padding=12).pack(anchor='w')
        values = []
        for kind, label in enumerate(FILES):
            row = ttk.Frame(dialog, padding=6)
            row.pack(fill='x')
            ttk.Label(row, text=label, width=32).pack(side='left')
            value = tk.StringVar(value=str(condo['files'][kind]) if condo['files'][kind] else '')
            values.append(value)
            ttk.Entry(row, textvariable=value, state='readonly').pack(side='left', fill='x', expand=True, padx=5)
            def browse(v=value, title=label):
                path = filedialog.askopenfilename(parent=dialog, title='Selecione: '+title,
                    initialdir=condo['folder'], filetypes=[('Documentos Word', '*.doc *.docx')])
                if path:
                    v.set(path)
            ttk.Button(row, text='Escolher…', command=browse).pack(side='right')
        def save():
            try:
                if any(not v.get() for v in values):
                    raise ValueError('Escolha um arquivo para cada um dos quatro tipos.')
                updated = select_files(condo['folder'], [v.get() for v in values])
                updated['name'] = condo['name']
                candidate = copy.deepcopy(self.mappings)
                candidate[condo['folder']] = [str(p) for p in updated['files']]
                DATA.mkdir(parents=True, exist_ok=True)
                temporary = MAPPINGS.with_suffix('.tmp')
                temporary.write_text(json.dumps(candidate, ensure_ascii=False, indent=2), encoding='utf-8')
                temporary.replace(MAPPINGS)
                self.mappings = candidate
                index = self.condos.index(condo)
                self.condos[index] = updated
                self.tree.set(str(index), 'state', '4 arquivos selecionados — pronto para atualizar')
                self.invalidate()
                self.log(f"\nArquivos vinculados: {updated['name']}")
                for label, path in zip(FILES, updated['files']):
                    self.log(f'  {label} → {path.name}')
                dialog.destroy()
                self.status.set('Seleção salva. Clique em “Atualizar documentos”; a prévia é opcional.')
            except Exception as exc:
                messagebox.showerror('Seleção não salva', str(exc), parent=dialog)
        actions = ttk.Frame(dialog, padding=12)
        actions.pack(fill='x')
        ttk.Button(actions, text='Salvar seleção', command=save).pack(side='right')
        ttk.Button(actions, text='Cancelar', command=dialog.destroy).pack(side='right', padx=8)

    def choose_output(self):
        selected = filedialog.askdirectory(title='Pasta onde os documentos serão salvos ou substituídos')
        if selected:
            self.destination.set(selected)

    def options_dialog(self):
        dialog = tk.Toplevel(self)
        dialog.title('Opções')
        dialog.geometry(f'660x{min(590, self.winfo_screenheight()-90)}')
        dialog.transient(self)
        dialog.grab_set()
        content = ttk.Frame(dialog,padding=18)
        content.pack(fill='both',expand=True)
        ttk.Label(content,text='Documentos a atualizar',font=('Segoe UI',11,'bold')).pack(anchor='w',pady=(0,8))
        choices = ttk.Frame(content)
        choices.pack(fill='x')
        for value,label in zip(self.doc_choices,('Aprovação','Capa do livro','Anexo I','Anexo II')):
            ttk.Checkbutton(choices,text=label,variable=value,command=self.invalidate).pack(side='left',padx=5)
        def action(command):
            dialog.destroy()
            self.after(10,command)
        ttk.Button(content,text='Selecionar os 4 arquivos…',command=lambda:action(self.map_files)).pack(fill='x',pady=(18,5))
        ttk.Button(content,text='Editar responsáveis do selecionado…',command=lambda:action(self.edit_roster)).pack(fill='x',pady=5)
        ttk.Button(content,text='Importar planilha de responsáveis…',command=lambda:action(self.import_sheet)).pack(fill='x',pady=5)
        ttk.Button(content,text='Desvincular planilha',command=lambda:action(self.unlink_sheet)).pack(fill='x',pady=5)
        ttk.Button(content,text='Renúncias em PDF…',command=lambda:action(self.pdf_dialog)).pack(fill='x',pady=5)
        def updates():
            from launcher import configure_updates
            configure_updates(self)
        ttk.Button(content,text='Atualizações do aplicativo…',command=lambda:action(updates)).pack(fill='x',pady=5)
        ttk.Label(content,textvariable=self.sheet_status,wraplength=570).pack(anchor='w',pady=8)
        ttk.Label(content, text='Atalhos: Ctrl+O · abrir pasta    Ctrl+Enter · atualizar    F1 · opções',
                  style='Muted.TLabel').pack(anchor='w', pady=(4, 12))
        ttk.Button(content,text='Fechar',command=dialog.destroy).pack(anchor='e')

    def chosen_kinds(self):
        return tuple(i for i,v in enumerate(self.doc_choices) if v.get())

    def select_all(self):
        self.tree.selection_set(self.tree.get_children())

    def selected(self):
        return [self.condos[int(i)] for i in self.tree.selection()]

    def period(self):
        month, year = MONTHS.index(self.month.get().lower())+1, int(self.year.get())
        if not 2000 <= year <= 2099:
            raise ValueError('Informe um ano entre 2000 e 2099.')
        return month, year

    def start(self, task, status='Processando os documentos no Word…'):
        if self.busy:
            return
        self.busy = True
        self.progress.start(40)
        self.cancel.clear()
        for control, _ in self.controls:
            control.configure(state='disabled')
        self.tree.configure(selectmode='none')
        self.cancel_button.configure(state='normal')
        self.status.set(status)
        def worker():
            try:
                task()
            except Exception as exc:
                self.events.put(('error', str(exc)))
            finally:
                self.events.put(('done', None))
        threading.Thread(target=worker, daemon=False).start()

    def poll(self):
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == 'log':
                    self.log(value)
                elif kind == 'progress':
                    self.status.set(value)
                elif kind == 'discovered':
                    self.apply_discovered(*value)
                elif kind == 'row':
                    index, state = value
                    self.tree.set(str(index), 'state', state)
                elif kind == 'preview':
                    self.preview = value
                    self.toggle_details(True)
                elif kind == 'output':
                    self.output = value
                    self.log(f'Saída: {value}')
                elif kind == 'job':
                    folder, job = value
                    self.last_jobs[folder] = job
                    self.preview.pop(folder,None)
                    for index,condo in enumerate(self.condos):
                        if condo['folder']==folder:
                            self.tree.set(str(index),'state',f"Atualizado — {job['month']:02}/{job['year']}")
                    self.pending_regen.discard(folder)
                    self.pending_updates.discard(folder)
                    self.next_retry.pop(folder,None)
                    self.state_dirty = True
                elif kind == 'job_failed':
                    self.pending_updates.add(value)
                    self.pending_regen.add(value)
                    self.next_retry[value] = time.monotonic()+15
                    self.state_dirty = True
                elif kind == 'sheet_setup':
                    self.after(10,lambda v=value:self.sheet_dialog(*v))
                elif kind == 'pdf_setup':
                    self.after(10,lambda v=value:self.pdf_dialog(v))
                elif kind == 'sheet_update':
                    if self.busy:
                        self.pending_sheet = value
                    else:
                        self.accept_sheet_update(*value)
                elif kind == 'sheet_error':
                    monitor, error = value
                    if monitor is self.sheet_monitor and error != self.sheet_error:
                        self.log('Planilha: '+error)
                        self.sheet_error = error
                        self.sheet_status.set('Planilha aguardando revisão; geração suspensa até resolver.')
                elif kind == 'sheet_poll_done':
                    if value is self.sheet_monitor:
                        self.sheet_polling = False
                elif kind == 'roster':
                    condo, rows = value
                    self.after(10, lambda c=condo, r=rows: self.roster_dialog(c, r))
                elif kind == 'error':
                    self.toggle_details(True)
                    self.log('ERRO: '+value)
                    messagebox.showerror('Operação não concluída', value+'\nConfira se o Word está instalado e ativado.')
                elif kind == 'done':
                    self.busy = False
                    self.progress.stop()
                    self.progress.configure(value=0)
                    if self.cancel.is_set():
                        self.pending_regen.clear()
                        self.pending_updates.clear()
                        self.state_dirty = True
                    if self.state_dirty:
                        self.save_runtime_state()
                    for control, state in self.controls:
                        control.configure(state=state)
                    self.tree.configure(selectmode='extended')
                    self.cancel_button.configure(state='disabled')
                    self.status.set('Operação cancelada.' if self.cancel.is_set() else 'Operação finalizada. Consulte os detalhes para ver os resultados.')
                    if self.pending_sheet is not None:
                        update, self.pending_sheet = self.pending_sheet, None
                        self.after(10,lambda v=update:self.accept_sheet_update(*v))
        except queue.Empty:
            pass
        if self.winfo_exists():
            self.after(100, self.poll)

    def inspect(self):
        condos = self.selected()
        if not condos:
            messagebox.showinfo('Seleção', 'Selecione pelo menos um condomínio.')
            return
        try:
            month, year = self.period()
        except ValueError as exc:
            messagebox.showerror('Competência', str(exc))
            return
        self.preview = {}
        config = copy.deepcopy(self.config)
        kinds = self.chosen_kinds()
        if not kinds:
            messagebox.showinfo('Documentos','Marque pelo menos um documento para gerar.')
            return
        groups, mapping = copy.deepcopy(self.sheet_groups), copy.deepcopy(self.sheet_mapping)
        models = copy.deepcopy(self.source_models)
        resignations = copy.deepcopy(self.resignations)
        monitor = self.sheet_monitor
        if self.sheet_monitor and (self.sheet_polling or self.sheet_monitor.raw_hash is None or self.sheet_error):
            messagebox.showinfo('Planilha', 'Aguarde a leitura da planilha ou resolva o aviso antes de conferir.')
            return
        def task():
            preview = {}
            with Word() as word:
                if monitor:
                    monitor.require_current()
                for condo in condos:
                    if self.cancel.is_set():
                        break
                    try:
                        if monitor and condo['folder'] not in groups:
                            raise ValueError('Nenhuma linha da planilha associada a este condomínio.')
                        docs = inspect_condo(word, condo, month, year, config.get(condo['folder'], []), kinds,
                                             groups.get(condo['folder']), mapping, models=models,
                                             resignations=resignations.get(condo['folder'],[]))
                        preview[condo['folder']] = docs
                        self.events.put(('log', f"\n{condo['name']} — conferência aprovada"))
                        for d in docs:
                            for c in d['changes']:
                                self.events.put(('log', f"  {d['path'].name} | {c.kind}: {c.old} → {c.new}"))
                        state = 'Conferido — pronto para gerar'
                    except Exception as exc:
                        state = 'REVISAR: '+str(exc)
                        self.events.put(('log', f"{condo['name']}: {state}"))
                    self.events.put(('row', (self.condos.index(condo), state)))
            if monitor:
                monitor.require_current()
            self.events.put(('preview', preview))
            self.events.put(('log', f'\nConferência: {len(preview)} de {len(condos)} condomínios aprovados.'))
        self.start(task)

    def run_generation(self):
        condos = self.selected()
        if not condos:
            messagebox.showinfo('Seleção','Selecione um ou mais condomínios.')
            return
        try:
            month, year = self.period()
            root = Path(self.folder.get()).resolve()
            dest = self.destination.get() or None
            targets = output_targets(condos,month,year,dest,self.create_subfolder.get())
            kinds = self.chosen_kinds()
            if not kinds:
                raise ValueError('Marque pelo menos um documento em Opções.')
        except ValueError as exc:
            messagebox.showerror('Saída', str(exc))
            return
        preview = self.preview
        if self.sheet_monitor and (self.sheet_polling or self.sheet_error or self.sheet_monitor.raw_hash is None):
            messagebox.showinfo('Planilha','Aguarde a leitura ou resolva o aviso da planilha antes de gerar.')
            return
        monitor = self.sheet_monitor
        config = copy.deepcopy(self.config)
        groups,mapping = copy.deepcopy(self.sheet_groups),copy.deepcopy(self.sheet_mapping)
        resignations = copy.deepcopy(getattr(self,'resignations',{}))
        self.state_dirty = True
        def prepare(word,condo):
            if monitor and condo['folder'] not in groups:
                raise ValueError('Nenhuma linha da planilha associada a este condomínio.')
            return inspect_condo(word,condo,month,year,config.get(condo['folder'],[]),kinds,
                                 groups.get(condo['folder']),mapping,models=self.source_models,
                                 resignations=resignations.get(condo['folder'],[]))
        def task():
            with Word() as word:
                result = generate(word, condos, preview, root, month, year,
                    lambda message: self.events.put(('log', message)), self.cancel,
                    targets=targets,cache=self.generation_cache,overwrite_sources=True,models=self.source_models,
                    on_generated=lambda c,t,d:self.record_job(c,t,d,month,year),
                    validate=monitor.require_current if monitor else None,prepare=prepare,
                    progress=lambda i,total,name:self.events.put(('progress',f'Atualizando {i}/{total}: {name}')))
            self.events.put(('output', result))
        self.start(task)

    def record_job(self, condo, target, docs, month, year):
        self.events.put(('job',(condo['folder'], {'condo':copy.deepcopy(condo), 'target':target,
                        'month':month,'year':year,'kinds':tuple(d['kind'] for d in docs)})))

    def load_pdfs(self,paths,records):
        records={r['path']:r for r in records}
        selected=self.selected()
        default=selected[0]['folder'] if len(selected)==1 else ''
        def task():
            for index,path in enumerate(paths,1):
                if self.cancel.is_set():
                    break
                self.events.put(('progress',f'Lendo PDF {index}/{len(paths)}: {Path(path).name}'))
                try:
                    record=load_pdf(path,self.condos)
                except Exception as exc:
                    record={'path':str(Path(path).resolve()),'sha256':file_hash(path),'name':'','role':'','unit':'',
                            'since':'','confirmed':False,'mode':'manual','warning':str(exc),'date_candidates':[]}
                candidates=record.get('condo_candidates',[])
                record['folder']=candidates[0] if len(candidates)==1 else default
                records[record['path']]=record
            from contextlib import ExitStack
            with ExitStack() as stack:
                word=None
                texts={}
                for record in records.values():
                    condo=next((c for c in self.condos if c['folder']==record.get('folder')),None)
                    if not condo or not condo['files'][0] or record.get('confirmed'):
                        continue
                    try:
                        folder=condo['folder']
                        if folder not in texts:
                            source=condo['files'][0]
                            saved=self.source_models.get(str(source))
                            if saved and saved['current_hash']==digest(source):
                                texts[folder]=saved['text']
                            else:
                                word=word or stack.enter_context(Word())
                                texts[folder]=word.read(source)
                        original,warning=propose_signature(record.get('name',''),record.get('unit',''),roster(texts[folder]))
                        record['original_name']=original
                        if warning:
                            record['warning']+=' '+warning
                    except Exception:
                        record['warning']+=' Não foi possível ler as assinaturas; informe o nome exato que consta no Word.'
            self.events.put(('pdf_setup',list(records.values())))
        self.start(task,'Lendo os PDFs localmente…')

    def pdf_dialog(self,records=None):
        if not self.condos:
            messagebox.showinfo('Renúncias','Selecione primeiro a pasta dos condomínios.')
            return
        folders={c['folder'] for c in self.condos}
        if records is None:
            records=[dict(r,folder=folder) for folder,rows in self.resignations.items() if folder in folders for r in rows]
        dialog=tk.Toplevel(self)
        dialog.title('Renúncias em PDF — revisão inicial')
        dialog.geometry(f'{min(1200,self.winfo_screenwidth()-40)}x{min(680,self.winfo_screenheight()-60)}')
        dialog.transient(self)
        dialog.grab_set()
        ttk.Label(dialog,text='Confirme uma vez quem renunciou e quando os efeitos começaram. Depois, a assinatura é retirada automaticamente na competência aplicável.',
                  wraplength=1100,padding=12).pack(anchor='w')
        ttk.Label(dialog,text='Não há promoção automática de suplentes. Se a data depender de recebimento, informe a data do protocolo. OCR pode errar nomes e manuscritos.',
                  wraplength=1100,padding=8).pack(anchor='w')
        host=ttk.Frame(dialog,padding=8)
        host.pack(fill='both',expand=True)
        canvas=tk.Canvas(host,highlightthickness=0)
        scroll=ttk.Scrollbar(host,orient='vertical',command=canvas.yview)
        scroll.pack(side='right',fill='y')
        canvas.pack(side='top',fill='both',expand=True)
        horizontal=ttk.Scrollbar(host,orient='horizontal',command=canvas.xview)
        horizontal.pack(side='bottom',fill='x')
        canvas.configure(yscrollcommand=scroll.set,xscrollcommand=horizontal.set)
        grid=ttk.Frame(canvas)
        canvas.create_window((0,0),window=grid,anchor='nw')
        grid.bind('<Configure>',lambda e:canvas.configure(scrollregion=canvas.bbox('all')))
        labels=['PDF','Pasta do condomínio','Nome exato no Word','Cargo','Unidade','Efeitos desde AAAA-MM-DD','Conferido','Ignorar']
        for col,label in enumerate(labels):
            ttk.Label(grid,text=label).grid(row=0,column=col,padx=5,pady=5)
        variables=[]
        for i,record in enumerate(records,1):
            row=2*i-1
            ttk.Label(grid,text=Path(record['path']).name,wraplength=160).grid(row=row,column=0,sticky='w',padx=5)
            values={field:tk.StringVar(value=record.get(field,'')) for field in ('folder','role','unit','since')}
            values['original_name']=tk.StringVar(value=record.get('original_name') or record.get('name',''))
            values['confirmed']=tk.BooleanVar(value=record.get('confirmed',False))
            values['ignored']=tk.BooleanVar(value=record.get('ignored',False))
            ttk.Combobox(grid,textvariable=values['folder'],values=sorted(folders),state='readonly',width=26).grid(row=row,column=1,padx=4)
            for col,field,width in [(2,'original_name',27),(3,'role',23),(4,'unit',7),(5,'since',16)]:
                ttk.Entry(grid,textvariable=values[field],width=width).grid(row=row,column=col,padx=4,pady=6)
            ttk.Checkbutton(grid,variable=values['confirmed']).grid(row=row,column=6)
            ttk.Checkbutton(grid,variable=values['ignored']).grid(row=row,column=7)
            note='Nome lido no PDF: '+(record.get('name') or 'não reconhecido')+'. '+record.get('warning','')
            if record.get('date_candidates'):
                note+=' Datas lidas: '+', '.join(record['date_candidates'])+'.'
            ttk.Label(grid,text=note,wraplength=1080).grid(row=row+1,column=0,columnspan=8,sticky='w',padx=5,pady=(0,12))
            variables.append((record,values))
        if not records:
            ttk.Label(grid,text='Adicione os PDFs ou busque arquivos com “renúncia” no nome nas pastas do condomínio.').grid(row=1,column=0,columnspan=8,pady=20)
        def current_records():
            return [dict(record,**{k:v.get() for k,v in values.items()}) for record,values in variables]
        def add_files(search=False):
            paths=[]
            if search:
                for condo in self.selected():
                    paths.extend(map(str,find_pdfs(condo)))
                paths=sorted(set(paths))
            else:
                paths=list(filedialog.askopenfilenames(parent=dialog,title='Selecionar PDFs de renúncia',filetypes=[('PDF','*.pdf')]))
            if not paths:
                return
            current=current_records()
            dialog.destroy()
            self.load_pdfs(paths,current)
        def save():
            try:
                rows=current_records()
                for row in rows:
                    if row.get('folder') not in folders:
                        raise ValueError('Associe cada PDF ao condomínio correspondente.')
                    if not row.get('ignored'):
                        if not row.get('confirmed'):
                            continue
                        if not row['original_name'].strip() or not row['role'].strip():
                            raise ValueError('Preencha o nome exato no Word e o cargo dos registros conferidos.')
                        date.fromisoformat(row['since'])
                    if file_hash(row['path'])!=row['sha256']:
                        raise ValueError('O PDF mudou: use Adicionar/Reler PDFs para ler novamente.')
                candidate=copy.deepcopy(self.resignations)
                for folder in folders:
                    candidate[folder]=[]
                for row in rows:
                    row['original_name']=row['original_name'].strip()
                    candidate[row['folder']].append(row)
                changed={f for f in folders if self.resignations.get(f,[])!=candidate.get(f,[])}
                self.resignations=candidate
                self.state_dirty=True
                self.save_runtime_state()
                for folder in changed:
                    self.preview.pop(folder,None)
                    if folder in self.last_jobs:
                        self.pending_regen.add(folder)
                        self.pending_updates.add(folder)
                self.state_dirty=True
                self.save_runtime_state()
                dialog.destroy()
                self.log('Renúncias salvas. As confirmadas serão aplicadas a partir da data informada; pendências bloqueiam a aprovação até revisão.')
                self.after(20,self.auto_regenerate)
            except Exception as exc:
                messagebox.showerror('Renúncias não salvas',str(exc),parent=dialog)
        buttons=ttk.Frame(dialog,padding=12)
        buttons.pack(fill='x')
        ttk.Button(buttons,text='Adicionar / Reler PDFs…',command=add_files).pack(side='left')
        ttk.Button(buttons,text='Buscar nas pastas selecionadas',command=lambda:add_files(True)).pack(side='left',padx=8)
        ttk.Button(buttons,text='Salvar',command=save).pack(side='right')
        ttk.Button(buttons,text='Fechar',command=dialog.destroy).pack(side='right',padx=8)

    def check_pdf_sources(self):
        changed=False
        for folder,records in self.resignations.items():
            if folder not in {c['folder'] for c in self.condos}:
                continue
            for record in records:
                path=record['path']
                try:
                    stat=Path(path).stat()
                    current=(stat.st_mtime_ns,stat.st_size)
                except OSError:
                    current=('indisponivel',)
                before=self.pdf_stats.setdefault(path,current)
                if before!=current:
                    self.pdf_stats[path]=current
                    try:
                        if file_hash(path)==record['sha256']:
                            continue
                    except OSError:
                        pass
                    record['confirmed']=False
                    self.preview.pop(folder,None)
                    self.log('PDF alterado ou indisponível: '+Path(path).name+'. Releia e confirme em Opções → Renúncias em PDF.')
                    changed=True
        if changed:
            self.state_dirty=True
            self.save_runtime_state()

    def save_sheet_setting(self, setting):
        candidate = copy.deepcopy(self.mappings)
        if candidate.get('__planilha__') != setting:
            candidate.pop('__sheet_hashes__',None)
        if setting is None:
            candidate.pop('__planilha__',None)
            candidate.pop('__pending_updates__',None)
        else:
            candidate['__planilha__'] = setting
        DATA.mkdir(parents=True,exist_ok=True)
        temporary = MAPPINGS.with_suffix('.tmp')
        temporary.write_text(json.dumps(candidate,ensure_ascii=False,indent=2),encoding='utf-8')
        temporary.replace(MAPPINGS)
        self.mappings = candidate

    def save_runtime_state(self):
        # Reutiliza a configuração existente: nenhum manifesto acompanha os documentos.
        saved_jobs = dict(self.mappings.get('__jobs__',{}))
        saved_jobs.update({folder:{'target':str(job['target']), 'month':job['month'],
            'year':job['year'],'kinds':list(job['kinds']),
            'sources':[str(p) if p else None for p in job['condo']['files']]}
            for folder,job in self.last_jobs.items()})
        self.mappings['__jobs__'] = saved_jobs
        self.mappings['__cache__'] = self.generation_cache
        self.mappings['__models__'] = self.source_models
        self.mappings['__resignations__'] = self.resignations
        self.mappings['__pending_updates__'] = sorted(self.pending_updates)
        try:
            DATA.mkdir(parents=True,exist_ok=True)
            temporary = MAPPINGS.with_suffix('.tmp')
            temporary.write_text(json.dumps(self.mappings,ensure_ascii=False,indent=2),encoding='utf-8')
            temporary.replace(MAPPINGS)
            self.state_dirty = False
        except Exception as exc:
            self.log('Não foi possível salvar a retomada automática: '+str(exc))

    def import_sheet(self):
        if not self.condos:
            messagebox.showinfo('Planilha','Selecione primeiro a pasta dos condomínios.')
            return
        path = filedialog.askopenfilename(title='Planilha de responsáveis',filetypes=[('Planilhas','*.csv *.tsv *.xlsx *.xls')])
        if path:
            self.load_sheet_dialog(path)

    def load_sheet_dialog(self, path, sheet=''):
        def task():
            headers, records = read_table(path,sheet)
            names = sheet_names(path)
            self.events.put(('sheet_setup',(path,sheet,headers,records,names)))
        self.start(task)

    def sheet_dialog(self,path,sheet,headers,records,names):
        dialog = tk.Toplevel(self)
        dialog.title('Colunas da planilha — '+Path(path).name)
        dialog.geometry('900x590')
        dialog.transient(self)
        dialog.grab_set()
        ttk.Label(dialog,text='Selecione as colunas reais. Os cabeçalhos são preservados exatamente como na planilha.',padding=12).pack(anchor='w')
        ttk.Label(dialog,text='Modelos com marcadores aceitam qualquer coluna: {{CPF}}, {{Síndico|Nome completo}}.\nPara as assinaturas antigas, mapeie nome/cargo; use nome original se houver vários conselheiros.',padding=12).pack(anchor='w')
        aba = ttk.Frame(dialog,padding=8)
        aba.pack(fill='x')
        ttk.Label(aba,text='Aba (XLS: digite o nome ou deixe vazio para a primeira):').pack(side='left')
        tab = tk.StringVar(value=sheet or names[0])
        tab_entry = ttk.Combobox(aba,textvariable=tab,values=names,width=26)
        tab_entry.pack(side='left',padx=8)
        def reload_sheet():
            selected = tab.get()
            dialog.destroy()
            self.load_sheet_dialog(path,selected)
        ttk.Button(aba,text='Ler esta aba',command=reload_sheet).pack(side='left')
        labels = {'condo':'Condomínio (obrigatório)','name':'Nome do responsável (assinaturas)',
                  'role':'Cargo (assinaturas e seleção por cargo)','unit':'Apartamento (opcional)',
                  'old_name':'Nome no documento original (opcional)'}
        guesses = {'condo':['condominio','condomínio','edificio'], 'name':['nome','nome completo','responsavel'],
                   'role':['cargo','funcao'], 'unit':['apartamento','apto','unidade'], 'old_name':['nome original','nome no original']}
        variables = {}
        previous = self.sheet_mapping if self.sheet_monitor and str(self.sheet_monitor.path)==path else {}
        aliases = copy.deepcopy(previous.get('aliases',{}))
        for field,label in labels.items():
            row = ttk.Frame(dialog,padding=5)
            row.pack(fill='x')
            ttk.Label(row,text=label,width=43).pack(side='left')
            initial = previous.get(field,'')
            if initial not in headers:
                initial = next((h for h in headers if key(h) in guesses[field]),'')
            variables[field] = tk.StringVar(value=initial)
            ttk.Combobox(row,textvariable=variables[field],values=['']+headers,state='readonly',width=45).pack(side='left')
        def alias_dialog():
            column = variables['condo'].get()
            if not column:
                messagebox.showinfo('Coluna','Selecione primeiro a coluna de condomínio.',parent=dialog)
                return
            choices = sorted({r[column].strip() for _,r in records if r[column].strip()})
            popup = tk.Toplevel(dialog)
            popup.title('Associar nome/código da planilha a uma pasta')
            popup.transient(dialog)
            popup.grab_set()
            ttk.Label(popup,text='Valor exato da coluna de condomínio:').pack(padx=12,pady=6)
            source = tk.StringVar()
            ttk.Combobox(popup,textvariable=source,values=choices,state='readonly',width=75).pack(padx=12)
            ttk.Label(popup,text='Pasta correspondente:').pack(pady=6)
            target = tk.StringVar()
            ttk.Combobox(popup,textvariable=target,values=[c['folder'] for c in self.condos],state='readonly',width=75).pack(padx=12)
            def save_alias():
                if not source.get() or not target.get():
                    return
                aliases[source.get()] = target.get()
                popup.destroy()
                dialog.grab_set()
            ttk.Button(popup,text='Salvar associação',command=save_alias).pack(pady=12)
        ttk.Button(dialog,text='Associar um nome ou código diferente a uma pasta…',command=alias_dialog).pack(anchor='w',padx=12,pady=10)
        ttk.Label(dialog,text='Colunas disponíveis (nomes originais): '+', '.join(headers),wraplength=850,padding=12).pack(anchor='w')
        ttk.Label(dialog,text='Ao vincular, o aplicativo monitora o arquivo enquanto estiver aberto. Atualiza apenas os\ndados alterados e os documentos afetados da última geração de cada condomínio.',padding=12).pack(anchor='w')
        def save():
            mapping = {k:v.get() for k,v in variables.items()}
            if not mapping['condo']:
                messagebox.showerror('Coluna obrigatória','Escolha a coluna de condomínio.',parent=dialog)
                return
            mapping.update(sheet=sheet or names[0],aliases=aliases)
            try:
                self.save_sheet_setting({'path':str(Path(path).resolve()),'mapping':mapping})
            except Exception as exc:
                messagebox.showerror('Configuração não salva',str(exc),parent=dialog)
                return
            dialog.destroy()
            self.activate_sheet(path,mapping)
        ttk.Button(dialog,text='Vincular e monitorar',command=save).pack(side='right',padx=12,pady=8)

    def activate_sheet(self,path,mapping):
        folders = {c['folder'] for c in self.condos}
        previous = {f:h for f,h in self.mappings.get('__sheet_hashes__',{}).items() if f in folders}
        self.sheet_monitor = SheetMonitor(path,mapping,copy.deepcopy(self.condos),previous)
        self.sheet_mapping = copy.deepcopy(mapping)
        self.sheet_groups = {}
        self.sheet_polling = False
        self.sheet_error = None
        self.pending_sheet = None
        self.invalidate()
        self.sheet_status.set('Lendo '+Path(path).name+'…')
        self.poll_sheet()

    def unlink_sheet(self):
        try:
            self.save_sheet_setting(None)
        except Exception as exc:
            messagebox.showerror('Configuração',str(exc))
            return
        self.sheet_monitor = None
        self.sheet_polling = False
        self.sheet_groups = {}
        self.sheet_mapping = {}
        self.sheet_error = None
        self.pending_sheet = None
        self.pending_regen.clear()
        self.pending_updates.clear()
        self.mappings.pop('__pending_updates__',None)
        self.sheet_status.set('Nenhuma planilha vinculada.')
        self.invalidate()

    def watch_sheet(self):
        if not self.busy:
            self.check_pdf_sources()
            self.auto_regenerate()
            if not self.busy:
                self.poll_sheet()
        self.after(3000,self.watch_sheet)

    def poll_sheet(self):
        if self.busy or self.sheet_polling or self.sheet_monitor is None:
            return
        monitor = self.sheet_monitor
        self.sheet_polling = True
        def worker():
            try:
                groups,changed,warnings = monitor.poll()
                self.events.put(('sheet_update',(monitor,groups,changed,warnings)))
            except Exception as exc:
                self.events.put(('sheet_error',(monitor,str(exc))))
            finally:
                self.events.put(('sheet_poll_done',monitor))
        threading.Thread(target=worker,daemon=True).start()

    def accept_sheet_update(self,monitor,groups,changed,warnings):
        if monitor is not self.sheet_monitor:
            return
        self.sheet_error = None
        self.sheet_groups = groups
        folders = {c['folder'] for c in self.condos}
        fingerprints = {f:h for f,h in self.mappings.get('__sheet_hashes__',{}).items() if f not in folders}
        fingerprints.update(monitor.fingerprints)
        if changed or self.mappings.get('__sheet_hashes__') != fingerprints:
            self.mappings['__sheet_hashes__'] = fingerprints
            self.state_dirty = True
        self.sheet_status.set(f'{monitor.path.name}: {len(groups)} condomínio(s) associado(s). Monitoramento ativo.')
        for warning in warnings:
            self.log('Planilha — '+warning)
        if warnings:
            self.log('Use “Importar planilha” e “Associar um nome ou código diferente” para corrigir as associações.')
        for folder in changed:
            self.preview.pop(folder,None)
            for i,condo in enumerate(self.condos):
                if condo['folder']==folder:
                    self.tree.set(str(i),'state','Planilha alterada — aguardando atualização/conferência')
            self.log('Planilha: responsáveis alterados em '+Path(folder).name)
            if folder not in groups:
                self.log('Sem linhas associadas; documentos existentes preservados até revisão.')
            elif folder in self.last_jobs:
                self.pending_regen.add(folder)
                self.pending_updates.add(folder)
        self.pending_regen.update(f for f in self.pending_updates if f in groups and f in self.last_jobs)
        if changed:
            self.after(20,self.auto_regenerate)
        if self.state_dirty and not self.pending_regen:
            self.save_runtime_state()

    def auto_regenerate(self):
        if self.busy or self.sheet_polling or not self.pending_regen or self.sheet_error:
            return
        if self.sheet_monitor is not None and self.sheet_monitor.raw_hash is None:
            return
        folders = {f for f in self.pending_regen if time.monotonic()>=self.next_retry.get(f,0)}
        self.pending_regen.difference_update(folders)
        jobs = {f:copy.deepcopy(self.last_jobs[f]) for f in folders if f in self.last_jobs and (self.sheet_monitor is None or f in self.sheet_groups)}
        if not jobs:
            return
        groups, mapping, config = copy.deepcopy(self.sheet_groups),copy.deepcopy(self.sheet_mapping),copy.deepcopy(self.config)
        monitor = self.sheet_monitor
        def task():
            with Word() as word:
                for folder,job in jobs.items():
                    if self.cancel.is_set():
                        break
                    try:
                        success = []
                        if monitor:
                            monitor.require_current()
                        condo = job['condo']
                        docs = inspect_condo(word,condo,job['month'],job['year'],config.get(folder,[]),
                            job['kinds'],groups.get(folder),mapping,models=self.source_models,
                            resignations=self.resignations.get(folder,[]))
                        generate(word,[condo],{folder:docs},job['target'].parent,job['month'],job['year'],
                            lambda msg:self.events.put(('log','Atualização automática — '+msg)),self.cancel,
                            targets={folder:job['target']},cache=self.generation_cache,validate=monitor.require_current if monitor else None,automatic=True,
                            overwrite_sources=True,models=self.source_models,
                            on_generated=lambda c,t,d,m=job['month'],y=job['year']:(success.append(True),self.record_job(c,t,d,m,y)))
                        if not success:
                            self.events.put(('job_failed',folder))
                    except Exception as exc:
                        self.events.put(('log','Atualização automática: REVISAR — '+str(exc)))
                        self.events.put(('job_failed',folder))
        self.start(task)

    def edit_roster(self):
        selected = self.selected()
        if len(selected) != 1:
            messagebox.showinfo('Responsáveis', 'Selecione apenas um condomínio para editar seus responsáveis.')
            return
        condo = selected[0]
        if condo['folder'] in self.config:
            self.roster_dialog(condo, copy.deepcopy(self.config[condo['folder']]))
            return
        if not condo['files'][0]:
            messagebox.showerror('Arquivo ausente', 'A aprovação de contas não foi encontrada.')
            return
        def task():
            with Word() as word:
                source = condo['files'][0]
                saved = self.source_models.get(str(source))
                text = saved['text'] if saved and saved['current_hash']==digest(source) else word.read(source)
                rows = roster(text)
            self.events.put(('roster', (condo, rows)))
        self.start(task)

    def roster_dialog(self, condo, rows):
        dialog = tk.Toplevel(self)
        dialog.title('Responsáveis — '+condo['name'])
        dialog.geometry('1080x500')
        dialog.transient(self)
        dialog.grab_set()
        ttk.Label(dialog, text='Confira os dados importados. Preencha os novos nomes/apartamentos e o início de vigência (AAAA-MM).', padding=10).pack(anchor='w')
        ttk.Label(dialog, text='Os campos “No original” devem corresponder ao arquivo de origem. Uma regra por assinatura; o cargo serve para identificação.', padding=10).pack(anchor='w')
        host = ttk.Frame(dialog, padding=10)
        host.pack(fill='both', expand=True)
        canvas = tk.Canvas(host, highlightthickness=0)
        scroll = ttk.Scrollbar(host, orient='vertical', command=canvas.yview)
        scroll.pack(side='right', fill='y')
        canvas.pack(side='left', fill='both', expand=True)
        canvas.configure(yscrollcommand=scroll.set)
        grid = ttk.Frame(canvas)
        canvas.create_window((0,0), window=grid, anchor='nw')
        grid.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
        headers = ['Ativa','Cargo (identificação)','Nome no original','Apto original','Novo nome','Novo apto','Desde AAAA-MM']
        for col, label in enumerate(headers):
            ttk.Label(grid, text=label).grid(row=0, column=col, padx=5, pady=5)
        variables = []
        def add_row(row=None):
            row = row or {'role':'', 'old_name':'', 'old_unit':'', 'new_name':'', 'new_unit':'', 'since':f'{self.period()[1]}-{self.period()[0]:02}', 'enabled':True}
            values = {'enabled':tk.BooleanVar(value=row.get('enabled',True))}
            index = len(variables)+1
            ttk.Checkbutton(grid, variable=values['enabled']).grid(row=index, column=0)
            for col, field in enumerate(['role','old_name','old_unit','new_name','new_unit','since'],1):
                values[field] = tk.StringVar(value=row.get(field,''))
                ttk.Entry(grid, textvariable=values[field], width=23 if field in ('old_name','new_name') else 15 if field=='role' else 11).grid(row=index,column=col,padx=3,pady=5)
            variables.append(values)
        for row in rows:
            add_row(row)
        if not rows:
            ttk.Label(dialog, text='Nenhuma assinatura reconhecida automaticamente. Cadastre os nomes exatamente como aparecem no Word.').pack()
        def save():
            try:
                saved = [{k:v.get().strip() if isinstance(v.get(),str) else v.get() for k,v in row.items()} for row in variables]
                for row in saved:
                    if not row['enabled']:
                        continue
                    if not row['old_name'] or not row['new_name']:
                        raise ValueError('Preencha o nome original e o novo nome em todas as regras ativas.')
                    if not re.fullmatch(r'20\d{2}-(0[1-9]|1[0-2])', row['since']):
                        raise ValueError('Vigência deve ser AAAA-MM, entre 2000-01 e 2099-12.')
                    if not row['old_unit'] or not row['new_unit']:
                        raise ValueError('Preencha os apartamentos. Para assinaturas sem apartamento, mantenha o mesmo texto nos dois campos.')
                candidate = copy.deepcopy(self.config)
                candidate[condo['folder']] = saved
                DATA.mkdir(parents=True, exist_ok=True)
                temporary = CONFIG.with_suffix('.tmp')
                temporary.write_text(json.dumps(candidate, ensure_ascii=False, indent=2), encoding='utf-8')
                temporary.replace(CONFIG)
                self.config = candidate
                self.invalidate()
                dialog.destroy()
                self.log(f"Cadastro salvo: {condo['name']}. Você já pode atualizar os documentos; a prévia é opcional.")
            except Exception as exc:
                messagebox.showerror('Cadastro não salvo', str(exc), parent=dialog)
        actions = ttk.Frame(dialog,padding=10)
        actions.pack(fill='x')
        ttk.Button(actions,text='Adicionar assinatura',command=add_row).pack(side='left')
        ttk.Button(actions,text='Salvar cadastro',command=save).pack(side='right')
        ttk.Button(actions,text='Cancelar',command=dialog.destroy).pack(side='right',padx=8)

    def open_output(self):
        if self.output:
            os.startfile(str(self.output))
        else:
            messagebox.showinfo('Saída', 'Nenhum lote gerado nesta sessão.')

    def close(self):
        if self.sheet_polling:
            messagebox.showinfo('Aguarde','A leitura da planilha está em andamento. Aguarde terminar e feche novamente.')
            return
        if self.busy:
            self.cancel.set()
            messagebox.showinfo('Aguarde', 'Cancelamento solicitado. Aguarde o condomínio atual terminar e feche novamente.')
        else:
            if self.state_dirty:
                self.save_runtime_state()
            self.destroy()

if __name__ == '__main__':
    try:
        App().mainloop()
    except Exception as exc:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror('Erro ao abrir Condomínio Fácil',str(exc),parent=root)
        root.destroy()
