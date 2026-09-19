"""Daily task/video sequence; failures and manual stops never advance it."""
DAILY_PLAN = (
    {'task': 'Lavar Louça na Pia', 'video': 'Lavando louça .MOV'},
    {'task': 'Arrancar ervas daninhas à mão / com garfo de mão', 'video': 'Arrancando ervas .mov'},
    {'task': 'Manutenção completa do jardim', 'video': 'Arrancando ervas .mov'},
)


def continuous_daily_plan(run_once, check_cancel, stopped, pause, today, update, retry_preparation=True):
    """Retry preparation only; a capture/save failure must preserve pending work."""
    while not stopped():
        check_cancel()
        day = today()
        try:
            run_once()
        except RuntimeError as exc:
            if not retry_preparation or not str(exc).startswith('Gravação não iniciada:'):
                raise
            update(message='Falha antes de gravar; nova tentativa em 30 segundos: '+str(exc),
                   level='warn', planRetrying=True)
            for _ in range(30):
                check_cancel()
                if stopped(): return
                pause(1)
            update(planRetrying=False)
            continue
        if stopped(): return
        update(message='Limites de hoje concluídos. Loop aguardando o próximo dia.',
               planWaitingNextDay=True)
        while today() == day:
            check_cancel()
            if stopped(): return
            pause(1)
        update(planWaitingNextDay=False, planCompleted=False)


def run_daily_plan(targets, usage, preflight, activate, run_task, check_cancel, stopped, update):
    # Validate every source before touching any emulator.
    for video in dict.fromkeys(row['video'] for row in DAILY_PLAN):
        preflight(video)
    for index, row in enumerate(DAILY_PLAN, 1):
        check_cancel()
        if stopped():
            return
        task, video = row['task'], row['video']
        eligible = {n: p for n, p in targets.items() if 7200 - usage(n, task) >= 90}
        update(planStep=index, planTask=task, planVideo=video,
               message=f'Plano diário {index}/3: {task}')
        if not eligible:
            continue
        activate(eligible, video)
        check_cancel()
        if stopped():
            return
        run_task(eligible, task)
        check_cancel()
        if stopped():
            return
        if any(7200 - usage(n, task) >= 90 for n in targets):
            raise RuntimeError('A etapa não concluiu o saldo diário de todos os celulares: '+task)
    update(message='Plano diário concluído nas três tarefas para todos os celulares.', planCompleted=True)
