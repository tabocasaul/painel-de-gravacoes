# Patch da Camera HAL

`emulated-camera-video.patch` registra a alteração aplicada sobre
`platform/hardware/google/camera` do Android 13. Ela troca a cena sintética por
quadros I420 640×360 quando o módulo Magisk fornece
`/vendor/etc/config/emu_camera_video.i420`.

A biblioteca resultante já está versionada no módulo `magisk/videocam`; este
patch existe para auditoria e futuras recompilações.
