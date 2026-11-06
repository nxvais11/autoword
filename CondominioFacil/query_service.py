"""Consultas de leitura isoladas: Word/rede presos não retêm a interface."""
import copy
import multiprocessing as mp
import sys
import time


class QueryInterrupted(ValueError):
    pass


def _entry(channel,target,args):
    try:channel.send(('result',target(channel.send,*args)))
    except BaseException as exc:
        try:channel.send(('error',str(exc)))
        except (OSError,EOFError):pass
    finally:channel.close()


def _word_handle(pid):
    if sys.platform!='win32':return None
    import win32api
    # Mantém o handle da instância exclusiva, sem procurar/encerrar outros Words.
    return win32api.OpenProcess(0x0001|0x00100000,False,pid)


def _stop_word(handle):
    if handle is None:return
    import win32api,win32event
    if win32event.WaitForSingleObject(handle,0)==258:win32api.TerminateProcess(handle,1)


def run_isolated(target,args=(),cancel=None,progress=None,*,timeout=45,total_timeout=180):
    context=mp.get_context('spawn')
    receiver,sender=context.Pipe(duplex=False)
    process=context.Process(target=_entry,args=(sender,target,args),daemon=True)
    handles=[];partial=None;stage='Iniciando consulta';started=time.monotonic();last=started
    try:
        process.start();sender.close()
        while True:
            if cancel is not None and cancel.is_set():raise QueryInterrupted('Consulta cancelada. Última etapa: '+stage)
            now=time.monotonic()
            if now-last>timeout or now-started>total_timeout:
                text='Consulta interrompida por tempo limite. Última etapa: '+stage+'. Confira o arquivo ou o acesso à rede e tente novamente.'
                if partial is None:raise QueryInterrupted(text)
                partial['query_incomplete']=text
                partial.setdefault('warnings',[]).append(text)
                return partial
            if receiver.poll(.05):
                try:kind,value=receiver.recv()
                except EOFError:raise QueryInterrupted('A consulta foi encerrada antes de concluir. Última etapa: '+stage) from None
                if kind=='progress':
                    stage=value;last=time.monotonic()
                    if progress:progress(value)
                elif kind=='partial':partial=value
                elif kind=='word':handles.append(_word_handle(value))
                elif kind=='result':return value
                elif kind=='error':raise QueryInterrupted('Não foi possível concluir a consulta: '+value+'\nÚltima etapa: '+stage)
            elif not process.is_alive():raise QueryInterrupted('A consulta foi encerrada antes de concluir. Última etapa: '+stage)
    finally:
        # Nenhuma espera por COM; o processo de leitura pode ser terminado mesmo
        # se uma chamada ao Word, PDF ou disco remoto não estiver retornando.
        if process.pid is not None:
            if process.is_alive():process.terminate()
            process.join(1)
            if process.is_alive():process.kill();process.join(1)
            process.close()
        for handle in handles:
            try:_stop_word(handle)
            except Exception:pass
            finally:handle.Close()
        sender.close();receiver.close()


def _query(send,settings,name,month,year,mappings,names,cache):
    from central_service import search
    from document_period import inspect_periods
    from obligations import check_obligations
    from word_service import Word
    def progress(text):send(('progress',text))
    def created(app):
        import win32process
        send(('word',win32process.GetWindowThreadProcessId(app.Hwnd)[1]))
    def factory():return Word(on_created=created)
    progress('Localizando arquivos de '+name)
    result=search(settings,name,month,year,mappings,names=names,progress=progress)
    send(('partial',result))
    inspect_periods(result,cache,factory,progress=progress)
    send(('partial',result))
    check_obligations(result,month,year,word_factory=factory,progress=progress)
    result['_period_cache']=cache
    return result


def consult(settings,name,month,year,mappings,names,cache,cancel,progress):
    value=run_isolated(_query,(settings,name,month,year,mappings,names,copy.deepcopy(cache)),cancel,progress)
    cache.update(value.pop('_period_cache',{}))
    return value


def smoke_query(send):
    send(('progress','Teste do processo de consulta'))
    return 'ok'
