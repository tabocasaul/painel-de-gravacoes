"""TikTok device diagnostics; never starts a public broadcast automatically."""
import re

PACKAGES = ('com.zhiliaoapp.musically', 'com.ss.android.ugc.trill')


class TikTokLive:
    def __init__(self, adb, devices):
        self.adb = adb
        self.devices = devices

    def validate(self, serial):
        if serial not in {value[0] for value in self.devices().values()} or not re.fullmatch(r'emulator-\d+', serial):
            raise ValueError('Selecione um celular cadastrado no painel.')
        result = self.adb(serial, 'get-state', timeout=8)
        if result.returncode or result.stdout.strip() != 'device':
            raise ValueError('Ligue o celular selecionado antes de conectar o TikTok.')

    def inspect(self, serial):
        self.validate(serial)
        package = None
        for name in PACKAGES:
            result = self.adb(serial, 'shell', 'pm', 'path', name, timeout=15)
            if result.returncode == 0 and 'package:' in result.stdout:
                package = name
                break
        mic = self.adb(serial, 'emu', 'avd', 'hostmicon', timeout=8)
        return dict(serial=serial, installed=bool(package), package=package,
                    microphone=mic.stdout.strip(), liveVerified=False,
                    message='TikTok instalado. Abra o aplicativo para entrar na conta e conferir o acesso ao LIVE.' if package else 'TikTok não instalado. Instale pela Play Store neste celular.')

    def open(self, serial):
        info = self.inspect(serial)
        if not info['installed']:
            raise ValueError(info['message'])
        result = self.adb(serial, 'shell', 'monkey', '-p', info['package'], '-c', 'android.intent.category.LAUNCHER', '1', timeout=20)
        if result.returncode or 'Events injected: 1' not in result.stdout:
            raise RuntimeError('Não foi possível abrir o TikTok neste celular.')
        return info

    def microphone(self, serial, enabled):
        self.validate(serial)
        result = self.adb(serial, 'emu', 'avd', 'hostmicon', 'on' if enabled else 'off', timeout=10)
        if result.returncode or 'KO:' in result.stdout or 'OK' not in result.stdout:
            raise RuntimeError('O emulador não confirmou o microfone. Confira Controles estendidos > Microfone.')
        return dict(serial=serial, hostMicrophone=enabled,
                    message='Microfone do PC habilitado no emulador. Confira a entrada padrão de gravação do Windows.' if enabled else 'Microfone do PC desabilitado no emulador.')

    def store(self, serial):
        self.validate(serial)
        result = self.adb(serial, 'shell', 'am', 'start', '-a', 'android.intent.action.VIEW',
                          '-d', 'market://details?id=' + PACKAGES[0], '-p', 'com.android.vending', timeout=20)
        if result.returncode or 'Error' in result.stdout or 'Error' in (result.stderr or ''):
            raise RuntimeError('Não foi possível abrir a Play Store neste celular.')
        return dict(serial=serial, message='Play Store aberta. Conclua a instalação do TikTok no celular.')
