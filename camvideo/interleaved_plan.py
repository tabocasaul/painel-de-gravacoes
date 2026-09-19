"""One saved pair per task turn; shuffle fair rounds of eligible tasks."""
import random
from automation import task_key
from participant_selection import validate_simultaneous
from interleaved_video_rotation import InterleavedVideoRotation


def validate_plan(rows):
    if not isinstance(rows, list) or not rows:
        raise ValueError('Adicione pelo menos uma tarefa e seu vídeo.')
    result, seen = [], set()
    for row in rows:
        if not isinstance(row, dict): raise ValueError('Tarefa inválida.')
        task = str(row.get('task', '')).strip()
        if not task or len(task) > 160: raise ValueError('Informe o nome completo de cada tarefa, até 160 caracteres.')
        videos = row['videos'] if 'videos' in row else [row.get('video', '')]
        if not isinstance(videos, list) or not videos:
            raise ValueError('Adicione pelo menos um vídeo da biblioteca para cada tarefa.')
        normalized = []
        for video in videos:
            if not isinstance(video, str):
                raise ValueError('Selecione vídeos válidos da biblioteca para cada tarefa.')
            video = video.strip()
            if (not video or video in {'.', '..'} or any(c in video for c in '<>:"/\\|?*')
                    or any(ord(c) < 32 for c in video)):
                raise ValueError('Selecione vídeos da biblioteca, sem caminhos ou nomes inválidos.')
            normalized.append(video)
        key = task_key(task)
        if key in seen: raise ValueError('Não repita a mesma tarefa na lista: '+task)
        seen.add(key); result.append(dict(task=task, videos=normalized))
    return result


def run_interleaved_plan(rows, targets, usage, preflight, activate, record_pair,
                         check_cancel, stopped, update, shuffle=random.shuffle, simultaneous=2, rotation=None,
                         continue_after_failure=False,admit=None,pause=None):
    rows = validate_plan(rows)
    validate_simultaneous(simultaneous)
    if simultaneous is None:
        raise ValueError('Informe a quantidade simultânea do plano intercalado.')
    for video in dict.fromkeys(video for row in rows for video in row['videos']): preflight(video)
    rotation = rotation if rotation is not None else InterleavedVideoRotation()
    # Validate every saved position before touching an emulator as well.
    for row in rows:
        rotation.position(row['task'], row['videos'])
    previous = None
    turn = 0
    cycle = 0
    opportunity = 0
    while True:
        cycle += 1
        completed = 0
        check_cancel()
        if stopped(): return
        choices = [row for row in rows if any(7200-usage(n,row['task']) >= 90 for n in targets)]
        if not choices:
            update(planCompleted=True, message='Limites diários do plano intercalado concluídos.')
            return
        shuffle(choices)
        if len(choices)>1 and choices[0]['task']==previous:
            choices[0], choices[1] = choices[1], choices[0]
        for row in choices:
            check_cancel()
            if stopped(): return
            task = row['task']
            eligible = [n for n in targets if 7200-usage(n,task) >= 90]
            # Preserve the usage priority, but randomize phones tied at the
            # same usage so every new round does not always start by name.
            shuffle(eligible)
            eligible.sort(key=lambda n: usage(n,task))
            candidates = {n:targets[n] for n in eligible}
            opportunity += 1
            pair = admit(candidates,simultaneous,opportunity) if admit else dict(list(candidates.items())[:simultaneous])
            if not pair: continue
            index = rotation.position(task, row['videos'])
            video = row['videos'][index]
            turn += 1
            update(planMode='interleaved', planStep=turn, planTask=task, planVideo=video,
                   planVideoIndex=index + 1, planVideoCount=len(row['videos']),
                   message=f'Plano intercalado • rodada {turn}: {task} • vídeo {index + 1} de {len(row["videos"])}')
            activated=activate(pair,video)
            if continue_after_failure and isinstance(activated,dict):pair=activated
            if not pair:continue
            check_cancel()
            if stopped(): return
            # This call must finish and confirm saving before changing the source.
            rotation.begin_round(task, row['videos'], index, pair,allow_partial=continue_after_failure)
            outcome=record_pair(pair,task)
            consumed=bool(outcome.get('saved')) if isinstance(outcome,dict) else outcome is not False
            if not consumed:
                if stopped(): return
                if continue_after_failure:continue
                raise RuntimeError('A rodada não foi totalmente salva. A sequência de vídeos não avançou.')
            rotation.advance(task, row['videos'], index)
            previous = task
            completed += 1
        if continue_after_failure and not completed:
            update(message='Aguardando aparelhos disponíveis; gravações pendentes permanecem preservadas.')
            if pause:
                for _ in range(5):
                    check_cancel()
                    if stopped():return
                    pause(1)
