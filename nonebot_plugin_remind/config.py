from nonebot import get_driver, get_plugin_config
from pydantic import BaseModel, Field


class Config(BaseModel):
    private_list_all: bool = Field(
        default=True,
        description="私聊中是否列出私聊群聊全部提醒",
    )
    remind_keyword_error: bool = Field(
        default=True,
        description='触发"提醒"关键词时是否发送错误提示',
    )
    glm_4_model: str = Field(
        default="",
        description="用于解析单次提醒的 GLM-4 系列大模型名称",
    )
    glm_4_model_cron: str = Field(
        default="",
        description="用于解析循环提醒的 GLM-4 系列大模型名称",
    )
    glm_api_key: str = Field(
        default="",
        description="GLM-4 系列大模型的 API_KEY",
    )


# 配置加载
plugin_config: Config = get_plugin_config(Config)
global_config = get_driver().config

# 全局名称
NICKNAME: str = next(iter(global_config.nickname), "")

# 兼容旧变量名
remind_config = plugin_config
