"""Constants for PS5 Status."""
DOMAIN = "ps5_status"

CONF_PSN_ENTITY = "psn_entity"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_OFF_AFTER = "off_after"

DEFAULT_SCAN_INTERVAL = 5   # seconds between status checks
DEFAULT_OFF_AFTER = 3       # missed answers in a row before the console counts as off

POWER_ON = "on"
POWER_REST = "rest"
POWER_OFF = "off"
POWER_STATES = [POWER_ON, POWER_REST, POWER_OFF]
