"""插件配置定义。

- 配置项统一带 ``remind_`` 前缀（NoneBot 官方建议），避免与其他插件的配置项重名冲突；
- 开启 ``coerce_numbers_to_str``：NoneBot 会对 .env 值做 JSON 解码，纯数字会变成 int，
  若不强制按文本读入，纯数字的配置值会让整个插件在加载期校验失败。
"""

from nonebot import get_plugin_config
from pydantic import BaseModel, ConfigDict, Field


class Config(BaseModel):
    model_config = ConfigDict(coerce_numbers_to_str=True)

    remind_private_list_all: bool = Field(
        default=True,
        description="私聊中是否列出私聊群聊全部提醒",
    )
    remind_keyword_error: bool = Field(
        default=True,
        description='触发"提醒"关键词时是否发送错误提示',
    )
    remind_llm_api_key: str = Field(
        default="",
        description="大模型 API Key（OpenAI 兼容接口；留空则禁用大模型兜底）",
    )
    remind_llm_base_url: str = Field(
        default="",
        description="大模型接口地址，如智谱 https://open.bigmodel.cn/api/paas/v4；留空使用 SDK 默认",
    )
    remind_llm_model: str = Field(
        default="",
        description="用于解析单次提醒的模型名称",
    )
    remind_llm_model_cron: str = Field(
        default="",
        description="用于解析循环提醒的模型名称",
    )


# 配置加载
plugin_config: Config = get_plugin_config(Config)
