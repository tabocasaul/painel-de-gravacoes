"""Read task cards through the Minute UI without opening a task."""
import json
import os
import time


def read_catalog(path):
    try:
        with open(path, encoding='utf-8') as stream: return json.load(stream)
    except (OSError, ValueError): return {'tasks': []}


def collect_catalog(automation, serial, path, update):
    if automation.e._camera_pronta(serial) is not None:
        raise RuntimeError('Salve ou encerre a câmera antes de atualizar o catálogo.')
    automation.launch_minute(serial)
    automation.wait_minute_ready(serial)
    # task_list preserves pending review screens.
    automation.task_list(serial)
    automation.set_query(serial, '')
    found = {}
    previous = None
    stable = 0
    for _ in range(200):
        automation.check_cancel()
        nodes = list(automation.xml(serial).iter('node'))
        cards = [n for n in nodes if n.get('resource-id','').startswith('task-card-')]
        signature = tuple((n.get('resource-id'), n.get('bounds')) for n in cards)
        for card in cards:
            name = card.get('content-desc','').split(',')[0].strip()
            if name: found[card.get('resource-id')] = name
        stable = stable+1 if signature and signature==previous else 0
        previous = signature
        update(message=f'Lendo tarefas do Minute: {len(found)} encontradas...')
        if stable >= 2:
            result = {'tasks': sorted(set(found.values()),key=str.casefold),
                      'serial':serial,'updatedAt':time.strftime('%Y-%m-%d %H:%M:%S')}
            if not found: raise RuntimeError('O Minute não exibiu tarefas; catálogo anterior preservado.')
            with open(path+'.tmp','w',encoding='utf-8') as stream: json.dump(result,stream,ensure_ascii=False)
            os.replace(path+'.tmp',path)
            update(message=f'Catálogo atualizado: {len(result["tasks"])} tarefas do Minute.',level='ok',busy=False)
            return
        automation.scroll_tasks(serial)
    raise RuntimeError('Não foi possível confirmar o final da lista; catálogo anterior preservado.')
