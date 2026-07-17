"""Seed a short-video campaign evaluation dataset for every workspace.

Usage:
    python server/scripts/seed_short_video_evaluation.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("RUN_JOB_QUEUE_BACKEND", "thread")

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from sqlalchemy import select  # noqa: E402

from server.src import main as api  # noqa: E402
from server.src.models import EvaluationDatasetPayload, WorkflowPayload  # noqa: E402
from server.src.orm import DbUser, DbWorkspace, DbWorkspaceMember  # noqa: E402


WORKFLOW_NAME = "评测目标：短视频口播与配图生成"
DATASET_NAME = "短视频口播与配图生成模板评测集"


CASES = [
    (
        "为咖啡店新品燕麦拿铁生成一套抖音短视频素材：包含 20 秒口播、封面配图提示词和发布文案，语气温暖，面向上班族。",
        ["燕麦拿铁", "上班族", "口播", "图片", "发布"],
    ),
    (
        "为智能保温杯做一套小红书种草素材，突出 12 小时保温、通勤便携和极简外观，语气真实克制。",
        ["保温杯", "通勤", "口播", "图片", "小红书"],
    ),
    (
        "为夏季防晒衣生成视频号短视频素材，目标用户是户外亲子家庭，强调轻薄透气和防晒等级。",
        ["防晒衣", "亲子", "轻薄", "口播", "发布"],
    ),
    (
        "为本地健身房 7 天体验课做一套短视频素材，目标是附近白领，语气积极但不要夸张承诺。",
        ["健身房", "体验课", "白领", "口播", "图片"],
    ),
    (
        "为宠物自动喂食器做抖音口播和封面图提示词，突出定时喂食、远程查看和上班族养宠场景。",
        ["宠物", "喂食器", "上班族", "口播", "图片"],
    ),
    (
        "为儿童编程体验营生成短视频素材，面向 8-12 岁孩子家长，语气专业可信，避免制造焦虑。",
        ["儿童编程", "家长", "体验营", "口播", "发布"],
    ),
    (
        "为城市露营装备套餐做一套小红书视频素材，突出周末轻露营、易收纳、适合新手。",
        ["露营", "新手", "收纳", "图片", "发布"],
    ),
    (
        "为低糖酸奶新品生成 15 秒短视频素材，面向控糖人群和办公室零食场景，语气清爽。",
        ["低糖酸奶", "控糖", "办公室", "口播", "图片"],
    ),
    (
        "为家用洗地机生成直播预热视频素材，突出拖洗一体、宠物家庭和省时清洁。",
        ["洗地机", "宠物家庭", "清洁", "口播", "发布"],
    ),
    (
        "为线上英语口语课生成短视频素材，目标用户是准备面试的职场新人，强调实战练习。",
        ["英语口语", "面试", "职场新人", "口播", "图片"],
    ),
    (
        "为国风香薰礼盒生成节日送礼短视频素材，语气雅致，平台是小红书。",
        ["香薰礼盒", "送礼", "国风", "小红书", "发布"],
    ),
    (
        "为社区烘焙课生成短视频素材，面向亲子家庭，突出周末活动和成品可带走。",
        ["烘焙课", "亲子", "周末", "口播", "图片"],
    ),
    (
        "为二手书循环市集生成公益向短视频素材，语气温和，强调环保、分享和周末活动。",
        ["二手书", "环保", "市集", "口播", "发布"],
    ),
    (
        "为高端商务双肩包生成短视频素材，面向频繁出差人群，突出电脑保护、分区收纳和耐磨。",
        ["双肩包", "出差", "收纳", "口播", "图片"],
    ),
    (
        "为 AI 会议纪要工具生成 B 站短视频素材，面向产品经理和创业团队，强调转写、摘要、待办。",
        ["AI", "会议纪要", "产品经理", "口播", "B站"],
    ),
    (
        "为新能源汽车试驾活动生成短视频素材，突出预约试驾、城市通勤和智能座舱，不要夸大续航。",
        ["新能源", "试驾", "通勤", "口播", "发布"],
    ),
    (
        "为鲜花订阅服务生成短视频素材，面向租房独居女生，语气治愈，突出每周上新和桌面布置。",
        ["鲜花订阅", "独居", "治愈", "图片", "发布"],
    ),
    (
        "为本地牙科洗牙套餐生成短视频素材，面向第一次洗牙用户，语气专业安心，避免医疗效果承诺。",
        ["洗牙", "专业", "安心", "口播", "发布"],
    ),
    (
        "为户外运动手表生成短视频素材，强调 GPS、心率监测和越野跑场景，语气硬朗。",
        ["运动手表", "GPS", "越野跑", "口播", "图片"],
    ),
    (
        "为企业知识库 SaaS 生成短视频素材，面向客服主管，强调内部知识沉淀、权限和检索效率。",
        ["知识库", "客服主管", "权限", "检索", "口播"],
    ),
    (
        "为秋冬羊毛围巾生成小红书短视频素材，面向送礼人群，语气温暖高级。",
        ["羊毛围巾", "送礼", "温暖", "小红书", "图片"],
    ),
    (
        "为校园摄影毕业季套餐生成短视频素材，面向大学毕业生，突出自然抓拍、多人合照和交付周期。",
        ["毕业季", "摄影", "合照", "口播", "发布"],
    ),
    (
        "为无糖气泡水生成抖音短视频素材，面向运动后补水场景，语气轻快，突出无糖和清爽。",
        ["气泡水", "无糖", "运动", "口播", "图片"],
    ),
    (
        "为民宿周末套餐生成短视频素材，面向情侣短途游，突出山景、早餐和可预约。",
        ["民宿", "情侣", "短途游", "早餐", "发布"],
    ),
]


def workflow_payload() -> WorkflowPayload:
    return WorkflowPayload(
        name=WORKFLOW_NAME,
        version="0.1.0",
        nodes=[
            {
                "id": "input-1",
                "position": {"x": 40, "y": 180},
                "data": {
                    "kind": "input",
                    "label": "素材需求",
                    "description": "输入产品、受众、语气、投放平台和期望素材类型。",
                    "sampleInput": CASES[0][0],
                    "outputKey": "campaign_request",
                },
            },
            {
                "id": "llm-json",
                "position": {"x": 380, "y": 180},
                "data": {
                    "kind": "llm",
                    "label": "生成素材 JSON",
                    "description": "把用户需求整理成标题、口播、图片提示词、发布文案和清单。",
                    "model": "deepseek-v4-flash",
                    "temperature": 0.5,
                    "maxOutputTokens": 900,
                    "timeoutSeconds": 60,
                    "systemPrompt": "你是中文短视频营销策划助手。只输出合法 JSON，不要 Markdown，不要解释，不要代码块。",
                    "prompt": (
                        "根据需求输出严格 JSON，字段必须包含 title、script、image_prompt、caption、publish_checklist。"
                        "script 必须是 105 到 115 个汉字的连续口播正文，按正常语速朗读约 18 到 22 秒，适合直接 TTS 朗读；"
                        "image_prompt 要适合中文商品营销海报或短视频封面；"
                        "publish_checklist 是 3 条字符串数组。\n\n"
                        'JSON 示例：{"title":"标题","script":"口播文案","image_prompt":"图片生成提示词",'
                        '"caption":"发布文案","publish_checklist":["检查口播节奏","确认图片不含违规元素","发布前补充商品链接"]}'
                        "\n\n需求：{{campaign_request}}"
                    ),
                    "outputKey": "content_json",
                    "failurePolicy": "continue",
                    "retryCount": 1,
                },
            },
            {
                "id": "json-title",
                "position": {"x": 720, "y": 70},
                "data": {
                    "kind": "json",
                    "label": "提取标题",
                    "jsonSource": "{{content_json}}",
                    "jsonPath": "title",
                    "outputKey": "title",
                    "failurePolicy": "continue",
                    "retryCount": 0,
                },
            },
            {
                "id": "json-script",
                "position": {"x": 720, "y": 220},
                "data": {
                    "kind": "json",
                    "label": "提取口播",
                    "jsonSource": "{{content_json}}",
                    "jsonPath": "script",
                    "outputKey": "script",
                    "failurePolicy": "continue",
                    "retryCount": 0,
                },
            },
            {
                "id": "json-image",
                "position": {"x": 720, "y": 370},
                "data": {
                    "kind": "json",
                    "label": "提取图片提示词",
                    "jsonSource": "{{content_json}}",
                    "jsonPath": "image_prompt",
                    "outputKey": "image_prompt",
                    "failurePolicy": "continue",
                    "retryCount": 0,
                },
            },
            {
                "id": "json-caption",
                "position": {"x": 720, "y": 520},
                "data": {
                    "kind": "json",
                    "label": "提取发布文案",
                    "jsonSource": "{{content_json}}",
                    "jsonPath": "caption",
                    "outputKey": "caption",
                    "failurePolicy": "continue",
                    "retryCount": 0,
                },
            },
            {
                "id": "tts-1",
                "position": {"x": 1060, "y": 220},
                "data": {
                    "kind": "tts",
                    "label": "生成口播音频",
                    "description": "把提取出的口播文案交给阿里云 TTS 合成音频。",
                    "ttsText": "{{script}}",
                    "ttsModel": "cosyvoice-v2",
                    "ttsVoice": "longxiaochun_v2",
                    "audioFormat": "mp3",
                    "speechRate": 1,
                    "outputKey": "audio_url",
                    "failurePolicy": "continue",
                    "retryCount": 0,
                },
            },
            {
                "id": "image-1",
                "position": {"x": 1060, "y": 370},
                "data": {
                    "kind": "image",
                    "label": "生成营销配图",
                    "description": "把图片提示词交给阿里云通义万相生成封面或配图。",
                    "imagePrompt": "{{image_prompt}}",
                    "imageModel": "wanx2.1-t2i-turbo",
                    "imageSize": "1024*1024",
                    "imageCount": 1,
                    "outputKey": "image_urls",
                    "failurePolicy": "continue",
                    "retryCount": 0,
                },
            },
            {
                "id": "aggregate-1",
                "position": {"x": 1400, "y": 300},
                "data": {
                    "kind": "aggregate",
                    "label": "汇总素材包",
                    "description": "把标题、口播、音频地址、图片地址和发布文案汇总成最终结果。",
                    "aggregateVariables": "title\nscript\naudio_url\nimage_prompt\nimage_urls\ncaption",
                    "aggregateSeparator": "\n\n",
                    "outputKey": "content_package",
                },
            },
            {
                "id": "output-1",
                "position": {"x": 1720, "y": 300},
                "data": {
                    "kind": "output",
                    "label": "素材包输出",
                    "description": "返回可用于短视频发布的素材包。",
                    "prompt": "{{content_package}}",
                    "outputKey": "answer",
                },
            },
        ],
        edges=[
            {"id": "e-input-llm", "source": "input-1", "target": "llm-json"},
            {"id": "e-llm-title", "source": "llm-json", "target": "json-title"},
            {"id": "e-llm-script", "source": "llm-json", "target": "json-script"},
            {"id": "e-llm-image", "source": "llm-json", "target": "json-image"},
            {"id": "e-llm-caption", "source": "llm-json", "target": "json-caption"},
            {"id": "e-script-tts", "source": "json-script", "target": "tts-1"},
            {"id": "e-image-gen", "source": "json-image", "target": "image-1"},
            {"id": "e-title-agg", "source": "json-title", "target": "aggregate-1"},
            {"id": "e-tts-agg", "source": "tts-1", "target": "aggregate-1"},
            {"id": "e-image-agg", "source": "image-1", "target": "aggregate-1"},
            {"id": "e-caption-agg", "source": "json-caption", "target": "aggregate-1"},
            {"id": "e-agg-output", "source": "aggregate-1", "target": "output-1"},
        ],
    )


def dataset_payload() -> EvaluationDatasetPayload:
    return EvaluationDatasetPayload(
        name=DATASET_NAME,
        description=(
            "用于测试“短视频口播与配图生成”模板的评测功能；覆盖多行业、多平台、不同受众、"
            "不同语气和合规边界。期望输出至少包含口播、图片/封面提示、发布文案等素材包要素。"
        ),
        cases=[
            {
                "input_text": input_text,
                "expected_output": "应生成完整短视频素材包，覆盖标题、口播、图片提示词、发布文案和发布检查项。",
                "expected_keywords": keywords,
            }
            for input_text, keywords in CASES
        ],
    )


def workspace_targets() -> list[tuple[str, str, str, str]]:
    with api.store._connect() as session:
        rows = session.execute(
            select(DbWorkspace.id, DbWorkspace.name, DbUser.id, DbUser.username)
            .join(DbWorkspaceMember, DbWorkspaceMember.workspace_id == DbWorkspace.id)
            .join(DbUser, DbUser.id == DbWorkspaceMember.user_id)
            .where(DbWorkspaceMember.role == "owner")
            .order_by(DbWorkspace.created_at.asc(), DbUser.created_at.asc())
        ).all()
    return [(str(workspace_id), str(workspace_name), str(user_id), str(username)) for workspace_id, workspace_name, user_id, username in rows]


def upsert_workflow(user_id: str, workspace_id: str):
    payload = workflow_payload()
    existing = next(
        (workflow for workflow in api.store.list_workflows(user_id, workspace_id) if workflow.name == WORKFLOW_NAME),
        None,
    )
    if existing:
        updated = api.store.update_workflow(existing.id, payload, user_id, workspace_id)
        if updated is None:
            raise RuntimeError(f"Failed to update workflow in workspace {workspace_id}")
        return updated
    return api.store.create_workflow(payload, user_id, workspace_id)


def upsert_dataset(user_id: str, workspace_id: str):
    payload = dataset_payload()
    existing = next(
        (
            dataset
            for dataset in (api.store.list_evaluation_datasets(user_id, workspace_id) or [])
            if dataset.name == DATASET_NAME
        ),
        None,
    )
    if existing:
        updated = api.store.update_evaluation_dataset(existing.id, payload, user_id, workspace_id)
        if updated is None:
            raise RuntimeError(f"Failed to update dataset in workspace {workspace_id}")
        return updated
    created = api.store.create_evaluation_dataset(payload, user_id, workspace_id)
    if created is None:
        raise RuntimeError(f"Failed to create dataset in workspace {workspace_id}")
    return created


def main() -> None:
    targets = workspace_targets()
    if not targets:
        raise RuntimeError("No workspace owner found. Register and log in once, then run this script again.")

    print(f"Seeding {len(CASES)} short-video evaluation cases into {len(targets)} workspace(s).")
    for workspace_id, workspace_name, user_id, username in targets:
        workflow = upsert_workflow(user_id, workspace_id)
        dataset = upsert_dataset(user_id, workspace_id)
        print(
            f"- {username} / {workspace_name}: workflow={workflow.id}, dataset={dataset.id}, cases={dataset.case_count}"
        )


if __name__ == "__main__":
    main()
