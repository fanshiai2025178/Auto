"""豆包 Seed 2.0 Lite 视频内容分析。"""

from __future__ import annotations

import base64
import json
import mimetypes
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from spreado.conf import (
    DOUBAO_ARK_BASE_URL,
    DOUBAO_VIDEO_MAX_INLINE_MB,
    DOUBAO_VIDEO_MODEL,
)

ANALYSIS_PROMPT = """你是一名专业的短视频内容分析师。请观看这段视频，为在抖音、小红书、快手等中文社交平台发布该视频生成配套文案。

请概括视频核心内容，输出：
1. title：吸引人的标题，10-15字，贴合视频内容
2. description：视频描述/正文，70-95字，口语化、有感染力
3. tags：最多4个相关标签，不带#号，适合社交平台

请严格以 JSON 格式回复，不要包含 markdown 代码块或其他说明文字：
{"title": "标题", "description": "描述正文", "tags": ["标签1", "标签2", "标签3", "标签4"]}"""


@dataclass
class VideoAnalysisResult:
    title: str
    description: str
    tags: List[str]


class DoubaoVideoAnalyzer:
    def __init__(self, api_key: str, model: str = DOUBAO_VIDEO_MODEL):
        self.api_key = api_key.strip()
        self.model = model.strip() or DOUBAO_VIDEO_MODEL
        if not self.api_key:
            raise ValueError("API Key 不能为空")

    def test_connection(self) -> str:
        """测试 API Key 是否可用，返回模型回复摘要。"""
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": "请只回复：连接成功"}],
            "max_tokens": 32,
            "temperature": 0,
        }
        data = self._post_json(f"{DOUBAO_ARK_BASE_URL}/chat/completions", payload)
        return self._extract_message_content(data)

    def analyze_video(self, video_path: str | Path) -> VideoAnalysisResult:
        path = Path(video_path)
        if not path.exists():
            raise FileNotFoundError(f"视频文件不存在: {path}")

        size_mb = path.stat().st_size / (1024 * 1024)
        if size_mb > DOUBAO_VIDEO_MAX_INLINE_MB:
            video_ref = self._upload_video_file(path)
        else:
            video_ref = self._video_to_data_uri(path)

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "video_url",
                            "video_url": {"url": video_ref, "fps": 1},
                        },
                        {"type": "text", "text": ANALYSIS_PROMPT},
                    ],
                }
            ],
            "temperature": 0.3,
            "max_tokens": 1024,
        }
        data = self._post_json(f"{DOUBAO_ARK_BASE_URL}/chat/completions", payload)
        raw = self._extract_message_content(data)
        parsed = self._parse_analysis_json(raw)
        return VideoAnalysisResult(
            title=parsed.get("title", "").strip(),
            description=parsed.get("description", "").strip(),
            tags=[
                str(t).strip().lstrip("#")
                for t in parsed.get("tags", [])[:4]
                if str(t).strip()
            ],
        )

    def _video_to_data_uri(self, path: Path) -> str:
        mime, _ = mimetypes.guess_type(path.name)
        mime = mime or "video/mp4"
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        return f"data:{mime};base64,{encoded}"

    def _upload_video_file(self, path: Path) -> str:
        boundary = f"----SpreadoBoundary{uuid.uuid4().hex}"
        mime, _ = mimetypes.guess_type(path.name)
        mime = mime or "video/mp4"
        file_bytes = path.read_bytes()

        parts: List[bytes] = []
        parts.append(
            self._multipart_field(boundary, "purpose", "user_data")
        )
        parts.append(
            self._multipart_file(boundary, "file", path.name, mime, file_bytes)
        )
        parts.append(
            self._multipart_field(boundary, "preprocess_configs[video][fps]", "1")
        )
        parts.append(f"--{boundary}--\r\n".encode("utf-8"))
        body = b"".join(parts)

        req = Request(
            f"{DOUBAO_ARK_BASE_URL}/files",
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": f"multipart/form-data; boundary={boundary}",
            },
        )
        data = self._read_json_response(urlopen(req, timeout=300))
        file_id = data.get("id")
        if not file_id:
            raise RuntimeError(f"视频上传失败，未返回 file_id: {data}")
        return f"file_id://{file_id}"

    @staticmethod
    def _multipart_field(boundary: str, name: str, value: str) -> bytes:
        return (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
            f"{value}\r\n"
        ).encode("utf-8")

    @staticmethod
    def _multipart_file(
        boundary: str, name: str, filename: str, mime: str, content: bytes
    ) -> bytes:
        header = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'
            f"Content-Type: {mime}\r\n\r\n"
        ).encode("utf-8")
        return header + content + b"\r\n"

    def _post_json(self, url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = Request(
            url,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )
        return self._read_json_response(urlopen(req, timeout=300))

    @staticmethod
    def _read_json_response(resp) -> Dict[str, Any]:
        try:
            raw = resp.read().decode("utf-8")
            return json.loads(raw)
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"API 请求失败 ({exc.code}): {detail}") from exc
        except URLError as exc:
            raise RuntimeError(f"网络请求失败: {exc.reason}") from exc
        finally:
            resp.close()

    @staticmethod
    def _extract_message_content(data: Dict[str, Any]) -> str:
        try:
            return data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, AttributeError) as exc:
            raise RuntimeError(f"API 响应格式异常: {data}") from exc

    @staticmethod
    def _parse_analysis_json(text: str) -> Dict[str, Any]:
        cleaned = text.strip()
        fence = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned)
        if fence:
            cleaned = fence.group(1).strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            match = re.search(r"\{[\s\S]*\}", cleaned)
            if not match:
                raise ValueError(f"无法解析模型返回的 JSON:\n{text[:500]}")
            return json.loads(match.group(0))
