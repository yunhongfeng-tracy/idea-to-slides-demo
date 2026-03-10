# -*- coding: utf-8 -*-
"""
通用图片生成脚本 - 基于 Nano Banana Pro API
用法：python -X utf8 py/generate_image.py --prompt "你的提示词"
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
from typing import Dict, Optional, Tuple

sys.stdout.reconfigure(encoding='utf-8')

try:
    import requests
except ImportError:
    print("缺少依赖：requests，请运行 pip install requests")
    raise

import urllib3
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

DEFAULT_BASE_URL = "https://api.grsai.com"
DEFAULT_MODEL = "nano-banana-pro"
DEFAULT_ASPECT_RATIO = "3:4"


def _create_session(verify_ssl: bool) -> requests.Session:
    """创建带自动重试的 requests Session，应对临时性网络/SSL 错误"""
    session = requests.Session()
    retry_strategy = Retry(
        total=5,
        backoff_factor=2,
        status_forcelist=[502, 503, 504],
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.verify = verify_ssl
    return session


def _read_api_key(api_file: Optional[Path]) -> Tuple[str, str]:
    """
    从 api 文件读取 API key。
    兼容两种格式：
    1. 纯 key（文件只有一行 key）
    2. key=value 格式（GRSAI_API_KEY=xxx）
    """
    # 优先从环境变量读取
    env_key = os.getenv("GRSAI_API_KEY")
    env_url = os.getenv("GRSAI_BASE_URL")
    if env_key:
        return env_key, (env_url or DEFAULT_BASE_URL).rstrip("/")

    if not api_file or not api_file.exists():
        raise SystemExit("找不到 api 文件，请在项目目录放置 api.md 或设置 GRSAI_API_KEY 环境变量")

    # 读取文件内容
    content = api_file.read_text(encoding="utf-8").strip()
    if not content:
        raise SystemExit("api 文件为空")

    config: Dict[str, str] = {}
    resolved_key = None

    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            # key=value 格式
            key, value = line.split("=", 1)
            config[key.strip()] = value.strip().strip("'\"")
        elif not resolved_key:
            # 纯 key 格式（取第一个非空行）
            resolved_key = line

    # 按优先级取 key
    resolved_key = resolved_key or config.get("GRSAI_API_KEY") or config.get("API_KEY")
    if not resolved_key:
        raise SystemExit("api 文件中未找到有效的 API key")

    resolved_url = config.get("GRSAI_BASE_URL") or DEFAULT_BASE_URL
    return resolved_key, resolved_url.rstrip("/")


def _find_api_file(start: Path) -> Optional[Path]:
    """向上搜索 api.md 或 api 文件"""
    for base in [start, *start.parents]:
        for name in ["api.md", "api"]:
            candidate = base / name
            if candidate.exists():
                return candidate
    return None


def _submit_task(
    session: requests.Session,
    base_url: str,
    api_key: str,
    prompt: str,
    aspect_ratio: str,
    image_size: Optional[str],
    model: str,
    timeout_s: int,
) -> str:
    """提交绘图任务，返回 task_id"""
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
    payload = {
        "model": model,
        "prompt": prompt,
        "aspectRatio": aspect_ratio,
        "webHook": "-1",
    }
    if image_size:
        payload["imageSize"] = image_size

    response = session.post(
        f"{base_url}/v1/draw/nano-banana",
        headers=headers,
        json=payload,
        timeout=timeout_s,
    )
    response.raise_for_status()
    result = response.json()

    if result.get("code") != 0:
        raise RuntimeError(f"任务提交失败：{result.get('msg', '未知错误')}")

    task_id = result.get("data", {}).get("id")
    if not task_id:
        raise RuntimeError("任务提交成功但未返回 task_id")
    return task_id


def _poll_result(
    session: requests.Session,
    base_url: str,
    api_key: str,
    task_id: str,
    timeout_s: int,
    poll_interval_s: int,
    max_wait_s: int,
) -> str:
    """轮询任务结果，返回图片 URL"""
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
    attempts = max(1, int(max_wait_s / poll_interval_s))

    for attempt in range(1, attempts + 1):
        time.sleep(poll_interval_s)
        response = session.post(
            f"{base_url}/v1/draw/result",
            headers=headers,
            json={"id": task_id},
            timeout=timeout_s,
        )
        response.raise_for_status()
        result = response.json()

        if result.get("code") != 0:
            raise RuntimeError(f"轮询失败：{result.get('msg', '未知错误')}")

        task = result.get("data", {})
        progress = task.get("progress", 0)
        status = task.get("status", "")
        print(f"  进度：{progress}%（{attempt}/{attempts}）")

        if progress == 100 and status == "succeeded":
            results = task.get("results", [])
            if results and results[0].get("url"):
                return results[0]["url"]
            raise RuntimeError("任务完成但未返回图片 URL")

        if status == "failed":
            reason = task.get("failure_reason", "未知原因")
            detail = task.get("error") or ""
            suffix = f"：{detail}" if detail else ""
            raise RuntimeError(f"任务失败：{reason}{suffix}")

    raise RuntimeError("等待超时，图片未生成完成")


def _download_image(session: requests.Session, url: str, output_path: Path, timeout_s: int) -> None:
    """下载图片并保存到本地，使用分块流式下载应对大文件和不稳定连接"""
    for attempt in range(1, 4):
        try:
            response = session.get(url, timeout=timeout_s, stream=True)
            response.raise_for_status()
            output_path.parent.mkdir(parents=True, exist_ok=True)
            chunks = []
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    chunks.append(chunk)
            output_path.write_bytes(b"".join(chunks))
            return
        except Exception as exc:
            if attempt >= 3:
                raise
            print(f"  下载重试 {attempt}/3：{type(exc).__name__}")
            time.sleep(attempt * 2)


def main() -> int:
    parser = argparse.ArgumentParser(description="Nano Banana Pro 图片生成")
    parser.add_argument("--prompt", help="提示词文本")
    parser.add_argument("--prompt-file", help="提示词文件路径")
    parser.add_argument("--output", default="output.png", help="输出图片路径（默认 output.png）")
    parser.add_argument(
        "--aspect-ratio", default=DEFAULT_ASPECT_RATIO,
        help="宽高比（默认 3:4，可选 auto/1:1/16:9/9:16/4:3/3:4/3:2/2:3/5:4/4:5/21:9）",
    )
    parser.add_argument("--image-size", help="输出尺寸（1K/2K/4K，模型相关）")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="模型名（默认 nano-banana-pro）")
    parser.add_argument("--api-file", help="api 文件路径（默认自动向上搜索）")
    parser.add_argument("--poll-interval", type=int, default=5, help="轮询间隔秒数（默认 5）")
    parser.add_argument("--max-wait", type=int, default=300, help="最长等待秒数（默认 300）")
    parser.add_argument("--timeout", type=int, default=30, help="HTTP 超时秒数（默认 30）")
    parser.add_argument("--verify-ssl", action="store_true", help="启用 SSL 校验（默认关闭）")
    args = parser.parse_args()

    # 读取提示词
    prompt = args.prompt
    if not prompt and args.prompt_file:
        prompt_path = Path(args.prompt_file)
        if not prompt_path.exists():
            raise SystemExit(f"提示词文件不存在：{args.prompt_file}")
        prompt = prompt_path.read_text(encoding="utf-8").strip()
    if not prompt:
        raise SystemExit("请通过 --prompt 或 --prompt-file 提供提示词")

    # 读取 API 配置
    api_file = Path(args.api_file) if args.api_file else _find_api_file(Path.cwd())
    api_key, base_url = _read_api_key(api_file)

    if not args.verify_ssl:
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    # 创建带重试的 HTTP 会话
    session = _create_session(verify_ssl=args.verify_ssl)

    # 打印配置
    print(f"模型：{args.model}")
    print(f"宽高比：{args.aspect_ratio}")
    if args.image_size:
        print(f"输出尺寸：{args.image_size}")
    print(f"API 地址：{base_url}")
    print(f"提示词长度：{len(prompt)} 字符")
    print()

    # 提交任务
    output_path = Path(args.output)
    max_wait_s = min(args.max_wait, 300)

    print("正在提交绘图任务...")
    task_id = _submit_task(
        session=session,
        base_url=base_url,
        api_key=api_key,
        prompt=prompt,
        aspect_ratio=args.aspect_ratio,
        image_size=args.image_size,
        model=args.model,
        timeout_s=args.timeout,
    )
    print(f"任务已提交，task_id：{task_id}")
    print("等待生成中...")

    # 轮询结果
    image_url = _poll_result(
        session=session,
        base_url=base_url,
        api_key=api_key,
        task_id=task_id,
        timeout_s=args.timeout,
        poll_interval_s=args.poll_interval,
        max_wait_s=max_wait_s,
    )
    print(f"\n图片 URL：{image_url}")

    # 下载图片
    print("正在下载图片...")
    _download_image(session, image_url, output_path, timeout_s=args.timeout)
    print(f"图片已保存：{output_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
