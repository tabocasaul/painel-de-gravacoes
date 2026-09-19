"""Coordinate recording starts, preserving captures after the first release."""
import math
import threading
import time


class RecordingStartGroup:
    def __init__(self, serials, check_cancel, allow_partial=True):
        self._serials=set(serials)
        self._arrivals={0:set(),1:set()}
        self._condition=threading.Condition()
        self._allow_partial=allow_partial
        self._first_released=False
        self._broken=None
        self.check_cancel=check_cancel

    def active(self):
        with self._condition:
            return set(self._serials)

    def drop(self, serial):
        with self._condition:
            if serial in self._serials and not self._allow_partial and not self._first_released:
                self._broken='Gravação não iniciada: um celular falhou antes do início em grupo: '+serial
            self._serials.discard(serial)
            self._condition.notify_all()

    def wait(self, serial, phase, timeout=90):
        if phase not in self._arrivals:
            raise ValueError('Fase de sincronização inválida.')
        timeout=float(timeout)
        if not math.isfinite(timeout) or timeout<0:
            raise ValueError('Prazo de sincronização inválido.')
        deadline=time.monotonic()+timeout
        with self._condition:
            self.check_cancel()
            if self._broken:raise RuntimeError(self._broken)
            if serial not in self._serials:
                raise RuntimeError('Celular removido do início sincronizado: '+serial)
            self._arrivals[phase].add(serial)
            self._condition.notify_all()
            while True:
                self.check_cancel()
                if self._broken:raise RuntimeError(self._broken)
                if serial not in self._serials:
                    raise RuntimeError('Celular removido do início sincronizado: '+serial)
                if self._serials<=self._arrivals[phase]:
                    # Phase 0 releases the record buttons. Beyond this point,
                    # failures must let the other captures finish and save.
                    if phase==0:self._first_released=True
                    return
                remaining=deadline-time.monotonic()
                if remaining<=0:
                    if not self._allow_partial and not self._first_released:
                        self._broken='Gravação não iniciada: nem todos os celulares ficaram prontos dentro do prazo.'
                        self._condition.notify_all()
                        raise RuntimeError(self._broken)
                    # The phones already ready may proceed. Exclude only
                    # those that have not reached this phase by the deadline.
                    self._serials.intersection_update(self._arrivals[phase])
                    self._condition.notify_all()
                    return
                self._condition.wait(min(.2,remaining))
