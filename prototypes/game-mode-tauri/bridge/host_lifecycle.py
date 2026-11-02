"""One request lane, independent cancellation, and safe EOF/shutdown draining."""
import json
import threading


def serve(stream, handle, send, allowed, cancel_all):
    stopping = threading.Event()
    lane = threading.Lock()
    workers = []

    def work(request):
        with lane:
            if stopping.is_set():
                send({'id': request.get('id'), 'error': 'The application is closing. Review again after reopening.'})
                return
            handle(request)

    try:
        for line in stream:
            request = None
            try:
                if len(line) > 4 * 1024 * 1024:
                    raise ValueError('Engine request exceeded its size limit.')
                request = json.loads(line)
                if not isinstance(request, dict) or request.get('method') not in allowed:
                    raise ValueError('Unsupported engine method.')
                if request['method'] in ('cancel', 'cancel_routes'):
                    handle(request)
                    continue
                workers = [worker for worker in workers if worker.is_alive()]
                if len(workers) >= 32:
                    raise ValueError('The engine is busy. Wait for the current operation.')
                worker = threading.Thread(target=work, args=(request,), daemon=False)
                worker.start()
                workers.append(worker)
            except (ValueError, TypeError) as error:
                send({'id': request.get('id') if isinstance(request, dict) else None, 'error': str(error)})
    finally:
        stopping.set()
        cancel_all()
        # Never terminate a transaction midway through its original-file write.
        for worker in workers:
            worker.join()
        cancel_all()  # Discard reviews created just before EOF was observed.
