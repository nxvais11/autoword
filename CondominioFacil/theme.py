"""Tema claro com cantos arredondados, gerado em memória sem dependências."""
import tkinter as tk
from tkinter import ttk

COLORS = dict(bg='#F3F5F7', panel='#FFFFFF', field='#FFFFFF',
              text='#243447', muted='#586B7D', accent='#365F7D',
              border='#DCE3EA', selected='#E3EDF5')

def rounded_image(root, fill, outline=None, radius=10):
    """Pequeno bloco de nove regiões, redimensionado pelo próprio ttk."""
    size = radius*2+4
    image = tk.PhotoImage(master=root, width=size, height=size)
    def inside(x, y, inset=0):
        r = radius-inset
        cx = min(max(x, radius), size-radius-1)
        cy = min(max(y, radius), size-radius-1)
        return (x-cx)**2+(y-cy)**2 <= r*r
    for y in range(size):
        pixels = [x for x in range(size) if inside(x, y)]
        if pixels:
            colors = [outline if outline and not inside(x, y, 1) else fill for x in pixels]
            # Uma chamada por linha: evita milhares de chamadas Tcl na abertura.
            image.put('{'+ ' '.join(colors) +'}', (pixels[0], y))
    return image

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
    style.theme_use('clam')
    style.configure('.', background=c['bg'], foreground=c['text'],
                    font=('Segoe UI', 10), bordercolor=c['border'],
                    lightcolor=c['border'], darkcolor=c['border'])
    style.configure('TFrame', background=c['bg'])
    style.configure('Card.TFrame', background=c['panel'])
    style.configure('TLabel', background=c['bg'], foreground=c['text'])
    style.configure('Muted.TLabel', foreground=c['muted'])
    style.configure('Title.TLabel', font=('Segoe UI', 22, 'bold'))
    style.configure('Section.TLabel', font=('Segoe UI', 11, 'bold'))
    style.configure('Card.TLabel', background=c['panel'])
    style.configure('TButton', background=c['bg'], foreground=c['text'],
                    padding=(14, 8), relief='flat', focusthickness=1,
                    focuscolor=c['accent'])
    style.map('TButton', foreground=[('disabled', '#68798A')])
    style.configure('Primary.TButton', foreground='#FFFFFF',
                    font=('Segoe UI', 10, 'bold'), focuscolor='#FFFFFF')
    style.map('Primary.TButton', foreground=[('disabled', '#68798A'), ('!disabled', '#FFFFFF')])

    # Os widgets continuam sendo ttk.Button: teclado, foco e estados nativos.
    root._theme_images = []
    for name, colors in (
            ('Soft', ('#E7EDF2', '#DAE4EC', '#CDDAE4', '#E8ECEF')),
            ('Primary', (c['accent'], '#426E8D', '#2D506A', '#E8ECEF'))):
        images = [rounded_image(root, color) for color in colors]
        root._theme_images.extend(images)
        element = name+'.rounded'
        style.element_create(element, 'image', images[0],
                             ('disabled', images[3]), ('pressed', images[2]),
                             ('active', images[1]), border=11, padding=0, sticky='nsew')
        button_style = 'TButton' if name == 'Soft' else 'Primary.TButton'
        style.layout(button_style, [(element, dict(sticky='nsew', children=[
            ('Button.focus', dict(sticky='nsew', children=[
                ('Button.padding', dict(sticky='nsew', children=[
                    ('Button.label', dict(sticky='nsew'))]))]))]))])
    panel_image = rounded_image(root, c['panel'], c['border'], radius=12)
    root._theme_images.append(panel_image)
    style.element_create('Card.rounded', 'image', panel_image, border=13, padding=0, sticky='nsew')
    style.layout('Card.TFrame', [('Card.rounded', dict(sticky='nsew'))])

    for widget in ('TEntry', 'TCombobox', 'TSpinbox'):
        style.configure(widget, fieldbackground=c['field'], foreground=c['text'],
                        insertcolor=c['text'], padding=7, arrowcolor=c['muted'])
        style.map(widget, fieldbackground=[('readonly', c['field']), ('disabled', '#EDF1F4')],
                  foreground=[('disabled', c['muted']), ('readonly', c['text'])],
                  bordercolor=[('focus', c['accent'])],
                  selectbackground=[('!disabled', c['selected'])],
                  selectforeground=[('!disabled', c['text'])])
    style.configure('TCheckbutton', padding=4, indicatorbackground=c['field'])
    style.map('TCheckbutton', background=[('active', c['bg'])],
              foreground=[('disabled', c['muted'])],
              indicatorbackground=[('selected', c['accent'])])
    style.configure('Treeview', background=c['panel'], fieldbackground=c['panel'],
                    foreground=c['text'], rowheight=38, borderwidth=0)
    style.map('Treeview', background=[('selected', c['selected'])],
              foreground=[('selected', c['text'])])
    style.configure('Treeview.Heading', background='#EDF1F4', foreground=c['muted'],
                    padding=(10, 10), font=('Segoe UI', 10, 'bold'), relief='flat')
    style.map('Treeview.Heading', background=[('active', '#E7EDF2')])
    style.configure('Horizontal.TProgressbar', background=c['accent'],
                    troughcolor='#E6EBEF', borderwidth=0, thickness=4)
    style.configure('Vertical.TScrollbar', background='#DCE3EA',
                    troughcolor=c['bg'], arrowcolor=c['muted'])
    return style
