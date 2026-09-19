#!/system/bin/sh
# The camera provider needs explicit access to the Magisk-mounted video file.
magiskpolicy --live "allow hal_camera_default system_file file { getattr open read map }"
