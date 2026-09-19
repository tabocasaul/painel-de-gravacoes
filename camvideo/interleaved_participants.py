"""Keep unavailable phones out of a round without losing their pending captures."""


class InterleavedParticipants:
    def __init__(self, targets, status, start, pending, recover, check_cancel, update,release=None):
        self.targets, self.status, self.start = targets, status, start
        self.pending, self.recover = pending, recover
        self.check_cancel, self.update = check_cancel, update
        self.release=release
        self.deferred, self.attempted = {}, {}
        for name, (serial, _) in targets.items():
            if serial in pending():
                self.deferred[name] = 'Gravação pendente preservada; tentando concluir antes de voltar.'
        self.publish()

    def publish(self):
        self.update(planDeferredPhones=[dict(name=name,serial=self.targets[name][0],reason=reason)
                                       for name,reason in self.deferred.items()])

    def defer(self, name, reason):
        self.deferred[name] = str(reason) or 'Aguardando a próxima oportunidade para entrar com o grupo.'
        self.publish()

    def admit(self, candidates, limit, cycle):
        states={}
        for name,(serial,_) in self.targets.items():
            try:states[name]=self.status(serial)
            except Exception:states[name]='unavailable'
        for name,(serial,_) in self.targets.items():
            if serial in self.pending() and name not in self.deferred:
                self.defer(name,'Gravação pendente preservada; os demais continuam.')
        live=sum(state!='off' for state in states.values())
        for name, (serial, port) in candidates.items():
            self.check_cancel()
            if name in self.deferred or serial in self.pending():
                if self.attempted.get(name) == cycle:
                    continue
                self.attempted[name] = cycle
                try:
                    state = states[name]
                    if state == 'off':
                        if live>=limit and self.release:
                            replacement=next((other for other in reversed(list(candidates))
                                if other not in self.deferred and states[other]=='online'
                                and self.targets[other][0] not in self.pending()),None)
                            if replacement is not None:
                                try:
                                    self.release(self.targets[replacement][0])
                                    states[replacement]='off'
                                    live-=1
                                except InterruptedError:raise
                                except Exception as exc:
                                    self.defer(replacement,exc)
                                    self.attempted[replacement]=cycle
                        if live>=limit:
                            self.defer(name,'Aguardando uma vaga para ligar sem ultrapassar a quantidade escolhida.')
                            continue
                        self.start(name,serial,port)
                        states[name]='booting'
                        live+=1
                        self.defer(name,'Ligando; entrará com um próximo grupo quando estiver pronto.')
                        continue
                    if state != 'online':
                        self.defer(name,'Celular iniciando; os demais continuam.')
                        continue
                    if serial in self.pending() and not self.recover(serial):
                        self.defer(name,'Gravação pendente preservada; os demais continuam na próxima tarefa.')
                        continue
                    if serial in self.pending():
                        self.defer(name,'Aguardando confirmação do salvamento antes de entrar novamente.')
                        continue
                    self.deferred.pop(name,None)
                except InterruptedError:
                    raise
                except Exception as exc:
                    self.defer(name,exc)
                    continue
        protected=sum(states[name]!='off' for name in self.deferred)
        slots=max(0,limit-protected)
        admitted=dict((name,pair) for name,pair in candidates.items() if name not in self.deferred)
        admitted=dict(list(admitted.items())[:slots])
        self.publish()
        return admitted

    def failed(self, names, rows):
        for name in names:
            if name in self.targets:
                self.defer(name,rows.get(self.targets[name][0],{}).get('error','Aguardando próxima rodada.'))
