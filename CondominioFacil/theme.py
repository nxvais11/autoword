"""Tema nativo leve: sem imagens, fontes externas ou dependências."""
from tkinter import ttk

COLORS = dict(bg='#0B1220', panel='#121E32', field='#1B2C46',
              text='#E8EEF7', muted='#A5B4C9', accent='#F0A064',
              border='#30435D', selected='#29496D')

def apply_theme(root):
    c = COLORS
    root.configure(background=c['bg'])
    root.option_add('*Font', ('Segoe UI', 10))
    root.option_add('*Toplevel.background', c['bg'])
    root.option_add('*Canvas.background', c['bg'])
    root.option_add('*Listbox.background', c['field'])
    root.option_add('*Listbox.foreground', c['text'])
    root.option_add('*Listbox.selectBackground', c['selected'])
    root.option_add('*Listbox.selectForeground', c['text'])
    style = ttk.Style(root)
    style.theme_use('clam')  # Cores consistentes também no Windows.
    style.configure('.', background=c['bg'], foreground=c['text'],
                    font=('Segoe UI', 10), bordercolor=c['border'],
                    lightcolor=c['border'], darkcolor=c['border'])
    style.configure('TFrame', background=c['bg'])
    style.configure('Card.TFrame', background=c['panel'])
    style.configure('TLabel', background=c['bg'], foreground=c['text'])
    style.configure('Muted.TLabel', foreground=c['muted'])
    style.configure('Title.TLabel', font=('Segoe UI', 23, 'bold'))
    style.configure('Section.TLabel', font=('Segoe UI', 12, 'bold'))
    style.configure('Card.TLabel', background=c['panel'])
    style.configure('TButton', background=c['field'], foreground=c['text'],
                    padding=(12, 8), relief='flat', focusthickness=2,
                    focuscolor=c['text'])
    style.map('TButton', background=[('disabled', c['panel']), ('pressed', c['selected']),
                                    ('active', c['selected'])],
              foreground=[('disabled', c['muted'])])
    style.configure('Primary.TButton', background=c['accent'], foreground=c['bg'],
                    font=('Segoe UI', 10, 'bold'), focuscolor=c['bg'])
    style.map('Primary.TButton', background=[('disabled', c['field']),
                ('pressed', '#D8884D'), ('active', '#FFB67E')],
              foreground=[('disabled', c['muted']), ('!disabled', c['bg'])])
    for widget in ('TEntry', 'TCombobox', 'TSpinbox'):
        style.configure(widget, fieldbackground=c['field'], foreground=c['text'],
                        insertcolor=c['text'], padding=7, arrowcolor=c['text'])
        style.map(widget, fieldbackground=[('readonly', c['field']), ('disabled', c['panel'])],
                  foreground=[('disabled', c['muted']), ('readonly', c['text'])],
                  bordercolor=[('focus', c['accent'])],
                  selectbackground=[('!disabled', c['selected'])],
                  selectforeground=[('!disabled', c['text'])])
    style.configure('TCheckbutton', padding=4, indicatorbackground=c['field'])
    style.map('TCheckbutton', background=[('active', c['bg'])],
              foreground=[('disabled', c['muted'])],
              indicatorbackground=[('selected', c['accent'])])
    style.configure('Treeview', background=c['panel'], fieldbackground=c['panel'],
                    foreground=c['text'], rowheight=36, borderwidth=0)
    style.map('Treeview', background=[('selected', c['selected'])],
              foreground=[('selected', c['text'])])
    style.configure('Treeview.Heading', background=c['field'], foreground=c['muted'],
                    padding=(10, 10), font=('Segoe UI', 10, 'bold'), relief='flat')
    style.map('Treeview.Heading', background=[('active', c['field'])])
    style.configure('Horizontal.TProgressbar', background=c['accent'],
                    troughcolor=c['panel'], borderwidth=0)
    style.configure('Vertical.TScrollbar', background=c['field'],
                    troughcolor=c['panel'], arrowcolor=c['muted'])
    return style
