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
    llm_api_key: str = Field(
        default="",
        description="大模型 API Key（OpenAI 兼容接口；留空则禁用大模型兜底）",
    )
    llm_base_url: str = Field(
        default="",
        description="大模型接口地址，如智谱 https://open.bigmodel.cn/api/paas/v4；留空使用 SDK 默认",
    )
    llm_model: str = Field(
        default="",
        description="用于解析单次提醒的模型名称",
    )
    llm_model_cron: str = Field(
        default="",
        description="用于解析循环提醒的模型名称",
    )


# 配置加载
plugin_config: Config = get_plugin_config(Config)
global_config = get_driver().config

# 全局名称
NICKNAME: str = next(iter(global_config.nickname), "")

# 兼容旧变量名
remind_config = plugin_config
