from pydantic import BaseModel
from nonebot import get_plugin_config


class Config(BaseModel):
    private_list_all: bool = True
    remind_keyword_error: bool = True
    glm_4_model: str = ""
    glm_4_model_cron: str = ""
    glm_api_key: str = ""


remind_config = get_plugin_config(Config)
