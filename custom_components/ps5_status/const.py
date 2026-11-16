"""Constants for PS5 Status."""
DOMAIN = "ps5_status"

CONF_PSN_ENTITY = "psn_entity"  # the media player the game comes from (any media player)
CONF_REGIST_KEY = "regist_key"  # from Remote Play linking: lets it turn the PS5 on
CONF_ACCOUNT_ID = "account_id"
CONF_PIN = "pin"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_OFF_AFTER = "off_after"
CONF_ACCOUNTS = "accounts"      # built-in PSN sign-ins: [{"name": "Jon", "npsso": "..."}]
CONF_NAME = "name"
CONF_NPSSO = "npsso"
CONF_FRIEND_OF = "friend_of"   # a friend is tracked through one of your signed-in accounts
CONF_PSN_INTERVAL = "psn_interval"

DEFAULT_SCAN_INTERVAL = 5   # seconds between status checks
DEFAULT_OFF_AFTER = 3       # missed answers in a row before the console counts as off
DEFAULT_PSN_INTERVAL = 30   # seconds between PSN checks while the console is on (PSN rate-limits hard)

POWER_ON = "on"
POWER_REST = "rest"
POWER_OFF = "off"
POWER_STATES = [POWER_ON, POWER_REST, POWER_OFF]
