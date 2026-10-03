"""插件配置测试：前缀命名与数字值文本化。"""


def test_all_config_fields_have_prefix():
    """全部配置项带 remind_ 前缀（防跨插件重名）。"""
    from nonebot_plugin_remind.config import Config

    for name in Config.model_fields:
        assert name.startswith("remind_"), f"配置项缺少 remind_ 前缀: {name}"


def test_numeric_config_value_coerced_to_str():
    """纯数字配置值按文本读入（NoneBot 对 .env 值做 JSON 解码，原会变 int）。"""
    from nonebot_plugin_remind.config import Config

    cfg = Config.model_validate({"remind_llm_api_key": 12345678})
    assert cfg.remind_llm_api_key == "12345678"
