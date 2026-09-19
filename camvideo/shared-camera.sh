#!/system/bin/sh
# Bind a read-only shared camera disk supplied by the host emulator launcher.
MOD=/data/adb/modules/videocam
[ -f "$MOD/shared-camera.conf" ] || exit 0
read SIZE DIGEST < "$MOD/shared-camera.conf"
case "$SIZE" in ''|*[!0-9]*) exit 1;; esac
DEVICE=
for SYS in /sys/class/block/vd*; do
    [ -f "$SYS/partition" ] && continue
    CANDIDATE=/dev/block/${SYS##*/}
    # Android mksh arithmetic can overflow at 2 GiB; compare decimal strings.
    BYTES=$(blockdev --getsize64 "$CANDIDATE" 2>/dev/null)
    [ "$BYTES" = "$SIZE" ] || continue
    HASH=$(dd if="$CANDIDATE" bs=4096 count=1 2>/dev/null | sha256sum)
    [ "${HASH%% *}" = "$DIGEST" ] || continue
    DEVICE=$CANDIDATE
    break
done
[ -n "$DEVICE" ] || exit 2
blockdev --setro "$DEVICE" || exit 3
chcon u:object_r:system_file:s0 "$DEVICE"
chmod 644 "$DEVICE"
magiskpolicy --live 'allow hal_camera_default system_file blk_file { getattr open read ioctl }'
/data/adb/magisk/busybox mount -o bind "$DEVICE" /vendor/etc/config/emu_camera_video.i420 || exit 4
printf '%s\n' "$SIZE" > "$MOD/shared-camera.ready"
