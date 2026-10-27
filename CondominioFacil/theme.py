"""Controles padrão do Tk: somente cores e fontes, sem imagens ou desenhos próprios."""
from tkinter import font, ttk

COLORS = dict(bg='#F3F5F7', panel='#FFFFFF', field='#FFFFFF',
              text='#243447', muted='#586B7D', accent='#365F7D',
              border='#DCE3EA', selected='#E3EDF5')

def apply_theme(root):
    if hasattr(root, '_autoword_style'):
        return root._autoword_style
    c = COLORS
    root.configure(background=c['bg'])
    for name in ('TkDefaultFont','TkTextFont','TkMenuFont','TkHeadingFont'):
        font.nametofont(name,root=root).configure(family='Segoe UI',size=10)
    root.option_add('*Toplevel.background', c['bg'])
    root.option_add('*Canvas.background', c['bg'])
    root.option_add('*Listbox.background', c['field'])
    root.option_add('*Listbox.foreground', c['text'])
    root.option_add('*Listbox.selectBackground', c['selected'])
    root.option_add('*Listbox.selectForeground', c['text'])
    style = ttk.Style(root)
    style.theme_use('clam')
    style.configure('.', background=c['bg'], foreground=c['text'],
                    font=('Segoe UI',10), bordercolor=c['border'],
                    lightcolor=c['border'], darkcolor=c['border'])
    style.configure('TFrame', background=c['bg'])
    style.configure('Card.TFrame', background=c['panel'])
    style.configure('TLabel', background=c['bg'], foreground=c['text'])
    style.configure('Muted.TLabel', foreground=c['muted'])
    style.configure('Title.TLabel', font=('Segoe UI',18,'bold'))
    style.configure('Section.TLabel', font=('Segoe UI',11,'bold'))
    style.configure('Card.TLabel', background=c['panel'])

    # Usa os elementos e layouts originais do tema; não cria PhotoImage,
    # elementos ttk, contornos, recortes, transições ou callbacks visuais.
    style.configure('TButton', background='#E7EDF2', foreground=c['text'],
                    padding=(10,5), relief='raised', borderwidth=1)
    style.map('TButton', background=[('disabled','#EDF1F4'), ('pressed','#CDDAE4'), ('active','#DAE4EC')],
              foreground=[('disabled','#68798A')])
    style.configure('Primary.TButton', background=c['accent'], foreground='#FFFFFF',
                    font=('Segoe UI',10,'bold'))
    style.map('Primary.TButton', background=[('disabled','#EDF1F4'), ('pressed','#2D506A'), ('active','#426E8D')],
              foreground=[('disabled','#68798A'), ('!disabled','#FFFFFF')])
    for widget in ('TEntry','TCombobox','TSpinbox'):
        style.configure(widget, fieldbackground=c['field'], foreground=c['text'],
                        insertcolor=c['text'], padding=4, arrowcolor=c['muted'])
        style.map(widget, fieldbackground=[('readonly',c['field']), ('disabled','#EDF1F4')],
                  foreground=[('disabled',c['muted']), ('readonly',c['text'])],
                  selectbackground=[('!disabled',c['selected'])],
                  selectforeground=[('!disabled',c['text'])])
    style.configure('TCheckbutton', padding=3, indicatorbackground=c['field'])
    style.map('TCheckbutton', background=[('active',c['bg'])],
              foreground=[('disabled',c['muted'])],
              indicatorbackground=[('selected',c['accent'])])
    style.configure('Treeview', background=c['panel'], fieldbackground=c['panel'],
                    foreground=c['text'], rowheight=28)
    style.map('Treeview', background=[('selected',c['selected'])],
              foreground=[('selected',c['text'])])
    style.configure('Treeview.Heading', background='#EDF1F4', foreground=c['muted'],
                    padding=(8,6), font=('Segoe UI',10,'bold'))
    style.map('Treeview.Heading', background=[('active','#E7EDF2')])
    style.configure('Horizontal.TProgressbar', background=c['accent'],
                    troughcolor='#E6EBEF', borderwidth=0, thickness=4)
    style.configure('Vertical.TScrollbar', background='#DCE3EA',
                    troughcolor=c['bg'], arrowcolor=c['muted'])
    root._autoword_style = style
    return style
