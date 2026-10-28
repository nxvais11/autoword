"""Fluxos de interface reais, sem abrir Word ou acessar os arquivos do usuário."""
import sys
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import App


class Interface(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            root = tk.Tk()
            root.destroy()
        except tk.TclError:
            if sys.platform == 'win32':
                raise  # O ambiente de publicação deve validar a interface.
            raise unittest.SkipTest('Interface exige um servidor gráfico; validada no CI Windows.')

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.patches = [patch('app.DATA', root), patch('app.CONFIG', root/'responsaveis.json'),
                        patch('app.MAPPINGS', root/'arquivos.json')]
        for item in self.patches:
            item.start()
        with patch('tkinter.PhotoImage', side_effect=AssertionError('Interface simples não deve gerar imagens')):
            self.app = App()
        self.app.geometry('1000x760')
        self.app.update()

    def tearDown(self):
        # Cancela callbacks para não deixar trabalho pendente entre janelas.
        for callback in self.app.tk.splitlist(self.app.tk.call('after', 'info')):
            self.app.after_cancel(callback)
        self.app.destroy()
        for item in reversed(self.patches):
            item.stop()
        self.tmp.cleanup()

    def test_details_open_for_preview_and_errors_but_not_routine_logs(self):
        self.app.log('Condomínio exemplo: pronto para atualizar')
        self.assertFalse(self.app.details_open)
        self.app.events.put(('preview', {}))
        self.app.poll()
        self.assertTrue(self.app.details_open)
        self.app.toggle_details(False)
        self.app.log('Condomínio exemplo: REVISAR arquivo ausente')
        self.assertTrue(self.app.details_open)
        self.assertIn('arquivo ausente', self.app.logbox.get('1.0', 'end'))

    def test_discovery_selects_entire_batch_and_keeps_destination_behavior(self):
        condos = [dict(name=name, folder=str(Path(self.tmp.name)/name), errors=[],
                       found=[], files=[None]*4) for name in ('Edifício A', 'Edifício B')]
        self.app.apply_discovered(self.tmp.name, condos)
        self.app.update()
        self.assertEqual(len(self.app.selected()), 2)
        self.assertEqual(self.app.destination.get(), '')
        self.assertFalse(self.app.create_subfolder.get())
        self.assertIn('2 de 2', self.app.selection_summary.get())
        self.assertFalse(self.app.empty_state.winfo_ismapped())
        self.app.tree.selection_set('1')
        self.app.update()
        self.assertEqual(self.app.selected()[0]['name'], 'Edifício B')

    def test_shortcuts_do_not_run_while_busy_or_through_a_modal(self):
        called = []
        action = lambda: called.append(True)
        self.app.busy = True
        self.app.shortcut(action)
        self.assertFalse(called)
        self.app.busy = False
        dialog = tk.Toplevel(self.app)
        dialog.update()
        dialog.grab_set()
        self.app.shortcut(action)
        self.assertFalse(called)
        dialog.destroy()
        self.app.shortcut(action)
        self.assertEqual(called, [True])

    def test_background_task_disables_inputs_and_restores_them_on_completion(self):
        import threading
        started, finish = threading.Event(), threading.Event()
        def task():
            started.set()
            finish.wait(3)
        try:
            self.app.start(task)
            self.assertTrue(started.wait(1))
            self.assertTrue(self.app.busy)
            self.assertTrue(all(str(control.cget('state')) == 'disabled'
                                for control, _ in self.app.controls))
            finish.set()
            # Aguarda apenas a fila da tarefa, sem executar o Word.
            while True:
                event = self.app.events.get(timeout=3)
                if event[0] == 'done':
                    self.app.events.put(event)
                    break
            self.app.poll()
            self.assertFalse(self.app.busy)
            self.assertTrue(all(str(control.cget('state')) == state
                                for control, state in self.app.controls))
            self.assertEqual(str(self.app.cancel_button.cget('state')), 'disabled')
        finally:
            finish.set()

    def test_primary_action_remains_visible_at_minimum_window_size(self):
        self.app.geometry('900x650')
        self.app.toggle_details(True)
        self.app.update()
        button = self.app.generate_button
        bottom = button.winfo_rooty()-self.app.winfo_rooty()+button.winfo_height()
        self.assertTrue(button.winfo_ismapped())
        self.assertLessEqual(bottom, self.app.winfo_height())
        self.assertGreater(self.app.tree.winfo_height(), 30)

    def test_subfolder_is_opt_in_and_explained_at_destination(self):
        self.app.destination.set('Z:/Condomínios/Edifício A')
        self.assertIn('Substitui somente', self.app.destination_hint.get())
        self.app.create_subfolder.set(True)
        self.assertIn('AAAA-MM', self.app.destination_hint.get())
        self.app.create_subfolder.set(False)
        self.app.destination.set('')
        self.assertIn('própria pasta', self.app.destination_hint.get())


    def test_print_button_only_enabled_for_completed_individual_and_resets_on_edit(self):
        condos = [dict(name=name, folder=str(Path(self.tmp.name)/name), errors=[],
                       found=[], files=[None]*4) for name in ('Edifício A', 'Edifício B')]
        self.app.apply_discovered(self.tmp.name, condos)
        self.app.update()
        self.assertEqual(str(self.app.print_button.cget('state')), 'disabled')
        self.app.tree.selection_set('0')
        self.app.update()
        self.app.events.put(('print_ready', dict(folder=condos[0]['folder'], files=[])))
        self.app.events.put(('done', None))
        self.app.poll()
        self.assertEqual(str(self.app.print_button.cget('state')), 'normal')
        self.app.tree.selection_set('1')
        self.app.update()
        self.assertEqual(str(self.app.print_button.cget('state')), 'disabled')
        self.app.tree.selection_set('0')
        self.app.update()
        self.assertEqual(str(self.app.print_button.cget('state')), 'disabled')

    def test_pdf_option_removed_and_buttons_use_standard_widgets(self):
        from tkinter import ttk
        self.app.options_dialog()
        def labels(widget):
            values = []
            for child in widget.winfo_children():
                if isinstance(child, ttk.Button):
                    values.append(str(child.cget('text')))
                values.extend(labels(child))
            return values
        self.assertFalse(any('PDF' in text for text in labels(self.app)))
        self.assertTrue(any('planilha' in text for text in labels(self.app)))
        self.assertIsInstance(self.app.print_button, ttk.Button)
        self.assertNotIn('rounded', str(self.app.style.layout('Primary.TButton')))

    def test_print_existing_enabled_after_folder_selection_without_generation(self):
        from engine import FILES
        folder = Path(self.tmp.name)/'Condomínio existente'
        folder.mkdir()
        files = []
        for name in FILES:
            path = folder/(name+'.doc')
            path.write_bytes(b'documento existente sem atualizar')
            files.append(path)
        condo = dict(name=folder.name,folder=str(folder),files=files,errors=[],found=[])
        self.app.apply_discovered(str(folder),[condo])
        self.app.update()
        self.assertIsNone(self.app.print_job)
        self.assertEqual(str(self.app.print_button.cget('state')),'normal')
        with patch('app.available_printers',return_value=(['Teste'],'Teste')),patch('app.Word') as word:
            self.app.print_dialog()
            word.assert_not_called()
        for child in self.app.winfo_children():
            if isinstance(child,tk.Toplevel):
                child.destroy()
        self.app.doc_choices[0].set(False)
        self.app.invalidate()
        self.assertEqual(str(self.app.print_button.cget('state')),'normal')
        for choice in self.app.doc_choices:
            choice.set(False)
        self.app.invalidate()
        self.assertEqual(str(self.app.print_button.cget('state')),'disabled')
        self.assertTrue(all(path.read_bytes()==b'documento existente sem atualizar' for path in files))

    def test_central_selects_all_statements_and_can_exclude_obligations(self):
        import time
        from central_ui import CentralDialog,save_settings
        from central_service import DEFAULTS
        path=Path(self.tmp.name)/'central.json'
        save_settings(path,dict(DEFAULTS,root=self.tmp.name))
        rows=[dict(group=group,label=group,key=group,path=None,checked=group!='obligations',printer='TEST') for group in ('closing','statement','statement','obligations')]
        result=dict(name='CONDOMINIO TESTE',period='2026-09',rows=rows,word=None,warnings=[])
        def wait(window):
            until=time.monotonic()+5
            while window.busy and time.monotonic()<until:
                window.update();time.sleep(.01)
            self.assertFalse(window.busy)
        with patch('central_ui.catalog',return_value=['CONDOMINIO TESTE']),patch('central_ui.search',return_value=result):
            window=CentralDialog(self.app,path)
            wait(window)
            window.name.set('CONDOMINIO TESTE');window.query();wait(window)
            window.geometry('900x600');window.update()
            bottom=window.print_button.winfo_rooty()-window.winfo_rooty()+window.print_button.winfo_height()
            self.assertLessEqual(bottom,window.winfo_height())
            self.assertEqual(window.checked,{0,1,2})
            self.assertEqual(window.tree.set('1','check'),'☑')
            self.assertEqual(window.tree.set('3','check'),'☐')
            window.tree.selection_set('1');window.tree.focus('1')
            window.toggle(index=1)
            self.assertEqual(window.tree.set('1','check'),'☐')
            self.assertEqual(window.tree.selection(),('1',))
            self.assertEqual(window.tree.focus(),'1')
            window.toggle(index=1)
            window.check_statements(False);self.assertEqual(window.checked,{0})
            window.check_statements(True);self.assertEqual(window.checked,{0,1,2})
            window.toggle(index=3);self.assertEqual(window.checked,{0,1,2,3})
            window.month.set('Setembro');window.invalidate();self.assertIsNone(window.result)
            window.destroy()
        self.assertFalse(self.app.busy)

    def test_simple_theme_has_no_custom_images_or_layout_elements(self):
        from theme import COLORS
        self.assertFalse(hasattr(self.app, '_theme_images'))
        self.assertFalse(hasattr(self.app, '_rounded_image_cache'))
        for style in ('TButton','Primary.TButton','Card.TFrame'):
            self.assertNotIn('rounded', str(self.app.style.layout(style)))
        self.assertEqual(self.app.style.layout('Primary.TButton'), self.app.style.layout('TButton'))
        self.assertEqual(self.app.style.lookup('TFrame','background'), COLORS['bg'])
        self.assertEqual(self.app.style.lookup('Primary.TButton','background'), COLORS['accent'])
        self.assertEqual(self.app.style.lookup('Treeview','fieldbackground'), COLORS['panel'])

    def test_options_reopen_reuses_standard_widgets_without_visual_allocations(self):
        import time
        from theme import apply_theme
        first = self.app.options_dialog()
        children = tuple(first.winfo_children())
        self.app.tk.call(first.protocol('WM_DELETE_WINDOW'))
        self.app.update()
        self.assertEqual(first.state(), 'withdrawn')
        self.app.doc_choices[0].set(False)
        started = time.perf_counter()
        second = self.app.options_dialog()
        elapsed = time.perf_counter()-started
        self.assertIs(first, second)
        self.assertEqual(children, tuple(second.winfo_children()))
        self.assertFalse(self.app.doc_choices[0].get())
        with patch('tkinter.PhotoImage') as create_image:
            apply_theme(self.app)
        create_image.assert_not_called()
        print(f'AUTOWORD_OPTIONS_REOPEN_SECONDS={elapsed:.4f}')

    def test_log_burst_yields_to_ui_and_appends_text_once_per_tick(self):
        for index in range(500):
            self.app.events.put(('log', f'Linha {index}'))
        with patch.object(self.app.logbox, 'insert', wraps=self.app.logbox.insert) as insert:
            self.app.poll()
        self.assertGreaterEqual(self.app.events.qsize(), 420)
        self.assertLess(self.app.events.qsize(), 500)
        self.assertEqual(insert.call_count, 1)
        self.assertIn('Linha 0\n', self.app.logbox.get('1.0','end'))

    @unittest.skipUnless(sys.platform=='win32', 'Captura de interface usa Windows')
    def test_visual_snapshot_main_and_options(self):
        import os
        import subprocess
        if not os.environ.get('CI'):
            self.skipTest('Captura disponível no ambiente de validação')
        def capture(widget, label):
            widget.lift()
            widget.update()
            x,y = widget.winfo_rootx(),widget.winfo_rooty()
            w,h = widget.winfo_width(),widget.winfo_height()
            script = (
                "$ErrorActionPreference='Stop'; Add-Type -AssemblyName System.Drawing;"
                f"$b=New-Object System.Drawing.Bitmap({w},{h});"
                "$g=[System.Drawing.Graphics]::FromImage($b);"
                f"$g.CopyFromScreen({x},{y},0,0,$b.Size);"
                "$m=New-Object System.IO.MemoryStream;"
                "$b.Save($m,[System.Drawing.Imaging.ImageFormat]::Png);"
                "[Convert]::ToBase64String($m.ToArray());"
                "$g.Dispose();$b.Dispose();$m.Dispose()")
            result = subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',script],
                                    capture_output=True,text=True,timeout=30,
                                    creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            self.assertEqual(result.returncode,0,result.stderr)
            encoded = result.stdout.strip()
            self.assertTrue(encoded.startswith('iVBOR'))
            print('AUTOWORD_VISUAL_'+label+':'+encoded)
        self.app.geometry('1000x650+20+20')
        capture(self.app,'MAIN')
        dialog = self.app.options_dialog()
        capture(dialog,'OPTIONS')

if __name__ == '__main__':
    unittest.main()
