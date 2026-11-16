"""ae_io: executa ExtendScript no After Effects pela ponte de arquivos (%TEMP%\ae_bridge\task.json -> result.json)."""
import os, json, time, tempfile, uuid

def run_ae(code, timeout=60):
    d = os.path.join(tempfile.gettempdir(), 'ae_bridge'); os.makedirs(d, exist_ok=True)
    tid = '%d_%s' % (int(time.time() * 1000), uuid.uuid4().hex[:6])
    res = os.path.join(d, 'result.json')
    if os.path.exists(res):
        try: os.remove(res)
        except OSError: pass
    json.dump({'id': tid, 'code': code}, open(os.path.join(d, 'task.json'), 'w', encoding='utf-8'))
    t0 = time.time()
    while time.time() - t0 < timeout:
        if os.path.exists(res):
            try:
                r = json.loads(open(res, encoding='utf-8').read() or 'null')
            except Exception:
                r = None
            if r and r.get('id') == tid:
                try: os.remove(res)
                except OSError: pass
                if not r.get('success'):
                    raise RuntimeError('After Effects: %s' % r.get('error'))
                return r.get('data')
        time.sleep(0.05)
    raise TimeoutError('After Effects nao respondeu em %ss (painel da ponte aberto? Window > Extensions)' % timeout)

if __name__ == '__main__':
    print(run_ae('return {v: app.version, n: app.project.numItems};'))
