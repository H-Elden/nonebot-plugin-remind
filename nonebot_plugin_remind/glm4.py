import asyncio
from datetime import datetime
from zhipuai import ZhipuAI

from nonebot.log import logger

from .config import remind_config


GLM_4_MODEL = remind_config.glm_4_model
GLM_4_MODEL_CRON = remind_config.glm_4_model_cron
GLM_API_KEY = remind_config.glm_api_key


async def parsed_datetime_glm4(time_text: str):
    """异步调用GLM-4的API解析时间"""
    if time_text == "":
        return "None"
    if GLM_4_MODEL == "" or GLM_API_KEY == "":
        logger.warning("未配置GLM模型或API_KEY")
        return "None"
    client = ZhipuAI(api_key=GLM_API_KEY)  # 请填写您自己的APIKey
    response = client.chat.asyncCompletions.create(
        model=GLM_4_MODEL,  # 请填写您要调用的模型名称
        messages=[
            {
                "role": "system",
                "content": f'当前时间是{datetime.now().strftime("%Y-%m-%d %H:%M")}（24小时制时间），我提供一个关于时间的表述，请你以当前时间为基准，仅回复我一个未来最符合该表述的时间，采用"YYYY-MM-DD HH:MM"的格式回复24小时制时间（提示：晚上12点或者24点都应回复为第二天的0点）；如果表述中不能明确是上午或是下午则默认按上午来回复。特殊情况：如果符合的时间早于当前 或者 如果我提供的表述无法表示正确的时间则回复"None"。',
            },
            {
                "role": "user",
                "content": time_text,
            },
        ],
        temperature=0.25,
        max_tokens=20,
    )
    logger.debug(response)

    task_id = response.id
    task_status = ""
    get_cnt = 0  # 限制查询10次

    while task_status != "SUCCESS" and task_status != "FAILED" and get_cnt <= 10:
        result_response = client.chat.asyncCompletions.retrieve_completion_result(
            id=task_id
        )
        logger.debug(result_response)
        task_status = result_response.task_status
        if task_status == "FAILED":
            logger.error(f"基于{GLM_4_MODEL}模型的解析失败！")
            return "Failed"
        if task_status == "SUCCESS":
            logger.success(
                f"基于{GLM_4_MODEL}模型的解析结果：{result_response.choices[0].message.content}"
            )
            return result_response.choices[0].message.content

        # 每隔1秒查询一次结果
        await asyncio.sleep(1)
        get_cnt += 1

    logger.warning("GLM API查询超时")
    return "Timeout"


async def parsed_cron_time_glm4(time_text: str) -> str:
    """异步调用GLM-4的API解析CronTrigger()的参数"""
    if time_text == "":
        return "None"
    if GLM_4_MODEL_CRON == "" or GLM_API_KEY == "":
        logger.warning("未配置GLM模型或API_KEY")
        return "None"
    client = ZhipuAI(api_key=GLM_API_KEY)  # 请填写您自己的APIKey
    response = client.chat.asyncCompletions.create(
        model=GLM_4_MODEL_CRON,  # 请填写您要调用的模型名称
        messages=[
            {
                "role": "system",
                "content": "我提供一个时间的文本表述用于创建python中的CronTrigger()实例来实现定时，请你仅回复一个参数字典（不要用makedown的代码块包裹），用于向CronTrigger()中传递参数。",
            },
            {
                "role": "user",
                "content": time_text,
            },
        ],
        temperature=0.75,
        max_tokens=40,
    )
    logger.debug(response)

    task_id = response.id
    task_status = ""
    get_cnt = 0  # 限制查询10次

    while task_status != "SUCCESS" and task_status != "FAILED" and get_cnt <= 10:
        result_response = client.chat.asyncCompletions.retrieve_completion_result(
            id=task_id
        )
        logger.debug(result_response)
        task_status = result_response.task_status
        if task_status == "FAILED":
            logger.error(f"基于{GLM_4_MODEL_CRON}模型的解析失败！")
            return "Failed"
        if task_status == "SUCCESS":
            logger.success(
                f"基于{GLM_4_MODEL_CRON}模型的解析结果：{result_response.choices[0].message.content}"
            )
            return result_response.choices[0].message.content

        # 每隔1秒查询一次结果
        await asyncio.sleep(1)
        get_cnt += 1

    return "Timeout"


async def main():
    time_text = input("输入要解析的时间文本：")
    result = await parsed_datetime_glm4(time_text)
    print("解析结果为：", result)


if __name__ == "__main__":
    # 运行主函数
    asyncio.run(main())
