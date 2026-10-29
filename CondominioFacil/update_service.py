"""Verificação e download em segundo plano; a interface controla os intervalos."""
import copy
import threading
from executable_update import find_update,download_update

CHECK_INTERVAL_MS=30*60*1000


class UpdateService:
    def __init__(self,data,repository,current,emit):
        self.data=data;self.repository=repository;self.current=current;self.emit=emit
        self.lock=threading.Lock();self.stopped=threading.Event()
        self.checking=False;self.downloading=False;self.ready=False;self.offer=None

    def _emit(self,kind,value):
        if not self.stopped.is_set():self.emit((kind,value))

    def check(self):
        with self.lock:
            if self.stopped.is_set() or self.checking or self.downloading or self.ready:return False
            self.checking=True
        def work():
            try:
                offer=find_update(self.repository,self.current)
                with self.lock:
                    if self.downloading or self.ready:return
                    self.offer=offer
                    current=copy.deepcopy(self.offer)
                self._emit('update_available' if current else 'update_current',current)
            except Exception as exc:self._emit('update_check_error',str(exc))
            finally:
                with self.lock:self.checking=False
        try:threading.Thread(target=work,daemon=True).start()
        except Exception as exc:
            with self.lock:self.checking=False
            self._emit('update_check_error',str(exc));return False
        return True

    def download(self):
        with self.lock:
            if self.stopped.is_set() or self.downloading or self.ready or not self.offer:return False
            self.downloading=True;offer=copy.deepcopy(self.offer)
        self._emit('update_downloading',offer['version'])
        def work():
            try:
                receipt=download_update(self.data,self.repository,offer)
                with self.lock:self.ready=True
                self._emit('installer_ready',receipt)
            except Exception as exc:self._emit('update_download_error',str(exc))
            finally:
                with self.lock:self.downloading=False
        try:threading.Thread(target=work,daemon=True).start()
        except Exception as exc:
            with self.lock:self.downloading=False
            self._emit('update_download_error',str(exc));return False
        return True

    def stop(self):self.stopped.set()

    def retry_install(self):
        with self.lock:self.ready=False
