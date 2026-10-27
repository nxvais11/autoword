"""Tema claro com cantos arredondados, gerado em memória sem dependências."""
import tkinter as tk
from tkinter import ttk

COLORS = dict(bg='#F3F5F7', panel='#FFFFFF', field='#FFFFFF',
              text='#243447', muted='#586B7D', accent='#365F7D',
              border='#DCE3EA', selected='#E3EDF5')

def rounded_image(root, fill, outline=None, radius=10, background=None):
    """Imagem PNG pequena em uma chamada Tcl, com cantos antisserrilhados."""
    import base64
    import struct
    import zlib
    background = background or COLORS['bg']
    size = radius*2+4
    def rgb(value):
        return tuple(int(value[i:i+2], 16) for i in (1, 3, 5))
    face, edge, back = rgb(fill), rgb(outline or fill), rgb(background)
    def inside(x, y, inset=0):
        cx = min(max(x, radius), size-radius)
        cy = min(max(y, radius), size-radius)
        return (x-cx)**2+(y-cy)**2 <= (radius-inset)**2
    rows = bytearray()
    for y in range(size):
        rows.append(0)  # Filtro PNG: sem transformação.
        for x in range(size):
            samples = []
            for dx,dy in ((.25,.25),(.75,.25),(.25,.75),(.75,.75)):
                px,py = x+dx,y+dy
                samples.append(back if not inside(px,py) else
                               edge if outline and not inside(px,py,1.5) else face)
            rows.extend(round(sum(p[i] for p in samples)/4) for i in range(3))
    def chunk(kind, data):
        return struct.pack('!I',len(data))+kind+data+struct.pack('!I',zlib.crc32(kind+data)&0xffffffff)
    png = (bytes((137,80,78,71,13,10,26,10))
           +chunk(b'IHDR',struct.pack('!2I5B',size,size,8,2,0,0,0))
           +chunk(b'IDAT',zlib.compress(bytes(rows)))
           +chunk(b'IEND',b''))
    return tk.PhotoImage(master=root, data=base64.b64encode(png).decode('ascii'), format='png')

def apply_theme(root):
    if hasattr(root, '_autoword_style'):
        return root._autoword_style
    c = COLORS
    root.configure(background=c['bg'])
    # Uma opção global *Font sobrepunha títulos e pesos definidos nos estilos.
    from tkinter import font
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
                    font=('Segoe UI', 10), bordercolor=c['border'],
                    lightcolor=c['border'], darkcolor=c['border'])
    style.configure('TFrame', background=c['bg'])
    style.configure('Card.TFrame', background=c['bg'])
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

    # Nenhum Button.focus/border nativo: ele pintava um retângulo sobre a imagem.
    # Cada superfície mantém a mesma cor de fundo em todos os estados.
    root._theme_images = []
    cache = {}
    def image_for(fill, parent, outline=None, radius=10):
        key = fill,parent,outline,radius
        if key not in cache:
            cache[key] = rounded_image(root,fill,outline,radius,parent)
            root._theme_images.append(cache[key])
        return cache[key]
    for name, parent, colors in (
            ('Soft', c['bg'], ('#E7EDF2', '#DAE4EC', '#CDDAE4', '#E8ECEF')),
            ('Primary', c['bg'], (c['accent'], '#426E8D', '#2D506A', '#E8ECEF')),
            ('CardButton', c['panel'], ('#E7EDF2', '#DAE4EC', '#CDDAE4', '#E8ECEF'))):
        images = [image_for(color,parent) for color in colors]
        focus = image_for(colors[0],parent, '#203F59' if name=='Primary' else c['accent'])
        element = name+'.rounded'
        style.element_create(element, 'image', images[0],
                             ('disabled', images[3]), ('pressed', images[2]),
                             ('focus', focus), ('active', images[1]),
                             border=11, padding=0, sticky='nsew')
        button_style = {'Soft':'TButton','Primary':'Primary.TButton','CardButton':'Card.TButton'}[name]
        style.configure(button_style, background=parent)
        style.map(button_style, background=[('disabled',parent), ('active',parent), ('!disabled',parent)])
        style.layout(button_style, [(element, dict(sticky='nsew', children=[
            ('Button.padding', dict(sticky='nsew', children=[
                ('Button.label', dict(sticky='nsew'))]))]))])
    panel_image = image_for(c['panel'], c['bg'], c['border'], radius=12)
    style.element_create('Card.rounded', 'image', panel_image, border=13, padding=0, sticky='nsew')
    style.layout('Card.TFrame', [('Card.rounded', dict(sticky='nsew'))])
    root._rounded_image_cache = cache

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
    root._autoword_style = style
    return style
