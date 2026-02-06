# core/__init__.py
from .config import (
    SMARTCTL_PATH, HDPARM_PATH, BADBLOCKS_PATH, F3PROBE_PATH,
    LOG_FILE, SMART_CACHE_TTL, REFRESH_RATE_MS,
    COLOR_BG_MAIN, COLOR_CARD_BG, COLOR_TEXT_LIGHT, COLOR_TEXT_GRAY,
    COLOR_GOOD, COLOR_WARN, COLOR_CRIT, COLOR_NA, COLOR_INFO
)

IGNORE_DEVICES = ['loop', 'sr0', 'dm-', 'zram']
IGNORE_MOUNTS = ['/boot/efi', '/sys', '/proc', '/dev/', '/run/user', 'snap']
IGNORE_FSTYPES = ['tmpfs', 'squashfs', 'devtmpfs', 'overlay']