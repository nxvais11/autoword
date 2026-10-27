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

    def test_pdf_option_removed_and_buttons_remain_native_and_rounded(self):
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
        self.assertIn('rounded', str(self.app.style.layout('Primary.TButton')))

if __name__ == '__main__':
    unittest.main()
