from hummingbot.client.config.config_var import ConfigVar
from hummingbot.client.settings import KeysContext

grvt_perpetual_config_map = {
    "grvt_perpetual_api_key": ConfigVar(
        prompt="Enter your GRVT API key: ",
        is_secure=True,
        is_connect_key=True,
        requirement=KeysContext
    ),
    "grvt_perpetual_api_secret": ConfigVar(
        prompt="Enter your GRVT API secret: ",
        is_secure=True,
        is_connect_key=True,
        requirement=KeysContext
    ),
}
