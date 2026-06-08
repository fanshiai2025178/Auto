"""小红书视频上传器。"""

from __future__ import annotations

import re
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from playwright.async_api import Error, Page

from spreado.core.base_publisher import BasePublisher


class XiaoHongShuUploader(BasePublisher):
    """小红书视频上传器。"""

    @property
    def platform_name(self) -> str:
        return "xiaohongshu"

    @property
    def display_name(self) -> str:
        return "小红书"

    @property
    def login_url(self) -> str:
        return "https://creator.xiaohongshu.com/"

    @property
    def publish_url(self) -> str:
        return "https://creator.xiaohongshu.com/publish/publish"

    @property
    def _video_upload_url(self) -> str:
        return f"{self.publish_url}?from=homepage&target=video"

    @property
    def _login_selectors(self) -> List[str]:
        return [
            'text="短信登录"',
            'text="扫码登录"',
            'button:has-text("登")',
            ".login-btn",
        ]

    @property
    def _authed_selectors(self) -> List[str]:
        # 上传页才会渲染的元素：视频上传 input + 顶部的"上传视频"按钮
        return ["input.upload-input", 'button:has-text("上传视频")']

    # ---------------------------------------------------------------- 主流程

    async def _upload_video(
        self,
        page: Page,
        file_path: str | Path,
        title: str = "",
        content: str = "",
        tags: List[str] = None,
        publish_date: Optional[datetime] = None,
        thumbnail_path: Optional[str | Path] = None,
    ) -> bool:
        try:
            with self.logger.step("upload_video", title=title, file=str(file_path)):
                with self.logger.step("goto_upload_page"):
                    await page.goto(self._video_upload_url)
                    try:
                        await page.wait_for_url(self._video_upload_url, timeout=5000)
                    except Error:
                        pass

                with self.logger.step("upload_video_file", file=str(file_path)):
                    if not await self._upload_video_file(page, file_path):
                        return False

                with self.logger.step("wait_for_upload_complete"):
                    if not await self._wait_for_upload_complete(page):
                        return False

                with self.logger.step("fill_video_info", title=title):
                    if not await self._fill_video_info(page, title, content, tags):
                        return False

                with self.logger.step("set_thumbnail", path=str(thumbnail_path or "")):
                    if not await self._set_thumbnail(page, thumbnail_path):
                        self.logger.warning("封面设置未完成，继续发布流程")

                if publish_date:
                    with self.logger.step(
                        "set_schedule_time", at=publish_date.isoformat()
                    ):
                        if not await self._set_schedule_time(page, publish_date):
                            return False

                with self.logger.step("publish_video"):
                    if not await self._publish_video(page):
                        return False
            return True
        except Exception as e:
            self.logger.error("upload_video 异常", reason=str(e)[:200])
            return False

    # ---------------------------------------------------------------- 子步骤

    async def _upload_video_file(self, page: Page, file_path: str | Path) -> bool:
        try:
            inp = page.locator("input.upload-input")
            await inp.wait_for(state="attached", timeout=10000)
            await inp.set_input_files(file_path)
            return True
        except Exception as e:
            self.logger.error("视频文件注入失败", reason=str(e)[:200])
            return False

    async def _wait_for_upload_complete(self, page: Page) -> bool:
        """轮询直到编辑页完全可发布。

        小红书会先渲染发布组件，再继续处理视频和封面。过早点击发布会没有
        任何反馈；但页面也可能长期保留“封面上传中/遇到问题”等非阻塞文案。
        这里在发布组件出现后保守等待一段固定缓冲时间。
        """
        stable_since: Optional[float] = None

        async def check() -> bool:
            nonlocal stable_since

            publish_host = page.locator("xhs-publish-btn").first
            publish_ready = (
                await publish_host.count() > 0 and await publish_host.is_visible()
            )

            if publish_ready:
                now = time.monotonic()
                if stable_since is None:
                    stable_since = now
                    self.logger.info("发布组件已出现，等待页面处理稳定")
                    return False
                return now - stable_since >= 60.0

            stable_since = None
            return False

        return await self._wait_for_condition(
            check, timeout=360.0, interval=2.0, desc="upload_complete"
        )

    async def _fill_video_info(
        self,
        page: Page,
        title: str = "",
        content: str = "",
        tags: List[str] = None,
    ) -> bool:
        try:
            await page.wait_for_selector(
                "input[placeholder*='填写标题'], .notranslate",
                state="visible",
                timeout=10000,
            )

            title_container = page.locator("input[placeholder*='填写标题']")
            if await title_container.count() > 0:
                await title_container.fill(title[:20])
            else:
                fallback = page.locator(".notranslate")
                await fallback.click()
                await page.keyboard.press("Backspace")
                await page.keyboard.press("Control+KeyA")
                await page.keyboard.press("Delete")
                await page.keyboard.type(title[:20])

            desc = page.locator("div.tiptap-container div[contenteditable]")
            await desc.click()
            await desc.fill(content)

            added = 0
            for tag in tags or []:
                clean_tag = tag.lstrip("#")
                try:
                    await desc.focus()
                    await page.keyboard.press("End")
                    await page.wait_for_timeout(800)
                    await desc.type(" ")
                    await page.wait_for_timeout(800)
                    await desc.type("#")
                    await page.wait_for_timeout(500)
                    await desc.type(clean_tag)
                    await page.wait_for_timeout(1000)
                    await page.keyboard.press("Enter")
                    added += 1
                except Exception as e:
                    self.logger.warning(
                        "标签添加失败，回退到纯文本",
                        tag=clean_tag,
                        reason=str(e)[:100],
                    )
                    try:
                        await desc.focus()
                        await page.keyboard.press("End")
                        await desc.type(f" #{clean_tag} ")
                        added += 1
                    except Exception as e2:
                        self.logger.error(
                            "标签直接追加也失败",
                            tag=clean_tag,
                            reason=str(e2)[:100],
                        )
                await desc.focus()
                await page.keyboard.press("End")
                await page.wait_for_timeout(800)

            self.logger.info("标题与标签已填充", added=added, total=len(tags or []))
            return True
        except Exception as e:
            self.logger.error("填写视频信息失败", reason=str(e)[:200])
            return False

    async def _set_thumbnail(
        self, page: Page, thumbnail_path: Optional[str | Path]
    ) -> bool:
        if not thumbnail_path:
            self.logger.info("无封面，跳过")
            return True
        if not Path(thumbnail_path).exists():
            self.logger.warning("封面文件不存在，跳过", path=str(thumbnail_path))
            return True

        try:
            # 1) 打开封面编辑弹窗（点击封面预览本身）
            cover_trigger_selectors = [
                ".publish-page-content-cover .cover-container",
                ".publish-page-content-cover-content",
                ".publish-page-content-cover",
                ".cover-plugin-preview .cover .default.row",
                ".cover-plugin-preview .cover",
                'div[class*="cover"]:has-text("设置封面")',
                'text="封面"',
            ]
            if not await self._click_first_visible(
                page, cover_trigger_selectors, force=True
            ):
                self.logger.error("未找到封面入口")
                return False

            modal_selectors = [
                ".d-modal:has-text('设置封面')",
                ".d-modal:has-text('封面')",
                ".el-dialog:has-text('封面')",
                "[role='dialog']:has-text('封面')",
                "[class*='modal']:has-text('封面')",
                "[class*='dialog']:has-text('封面')",
            ]
            modal = await self._find_first_element(
                page, modal_selectors, timeout=5000, state="visible"
            )
            if modal is None:
                self.logger.warning("封面弹窗未出现，跳过自定义封面")
                return False

            # 2) 弹窗内 file input 是异步挂载的，先等再注入
            upload_input_selectors = [
                '.d-modal .cover-container input[type="file"][accept*="image"]',
                '.d-modal input[type="file"][accept*="image"]',
                '.el-dialog input[type="file"][accept*="image"]',
                '[role="dialog"] input[type="file"][accept*="image"]',
                '[class*="modal"] input[type="file"][accept*="image"]',
                '[class*="dialog"] input[type="file"][accept*="image"]',
                'input.upload-input[type="file"][accept*="image"]',
            ]
            if not await self._upload_file_to_first(
                page, upload_input_selectors, thumbnail_path, timeout=10000
            ):
                self.logger.warning("未找到封面图片上传 input")
                return False

            await page.wait_for_timeout(2000)

            # 3) 确认
            if not await self._click_first_visible(
                page,
                [
                    '.d-modal button:has-text("确定")',
                    '.d-modal button:has-text("确认")',
                    'button:has-text("确定")',
                ],
                force=True,
            ):
                self.logger.error("未找到确定按钮")
                return False

            try:
                await page.wait_for_selector(
                    ".d-modal:has-text('设置封面')",
                    state="hidden",
                    timeout=10000,
                )
            except Error:
                pass

            return True
        except Exception as e:
            self.logger.error("封面设置失败", reason=str(e)[:200])
            return False

    async def _set_schedule_time(self, page: Page, publish_date: datetime) -> bool:
        try:
            publish_date_str = publish_date.strftime("%Y-%m-%d %H:%M")

            # 1) 开启定时发布开关
            switch_container = page.locator(
                ".post-time-switch-container:has-text('定时发布')"
            )
            switch = switch_container.locator(".d-switch").first
            if await switch.count() == 0:
                switch = page.locator("div:has-text('定时发布') >> .d-switch").first

            if await switch.count() > 0:
                await switch.scroll_into_view_if_needed()
                checked = await switch.locator("input").evaluate("el => el.checked")
                if not checked:
                    await switch.locator(".d-switch-simulator").click(force=True)
                    await page.wait_for_timeout(1000)
            else:
                self.logger.warning("未找到定时发布开关")

            # 2) 等日期选择器渲染
            try:
                await page.wait_for_selector(
                    ".date-picker-container", state="visible", timeout=5000
                )
            except Error:
                self.logger.warning("date-picker-container 未出现")

            # 3) 设置时间
            datetime_elem = page.locator(
                ".date-picker-container .d-text, .d-datepicker-input-filter input,"
                " .d-datepicker-input-filter"
            ).first
            if await datetime_elem.count() == 0:
                self.logger.error("未找到日期输入框")
                return False
            await datetime_elem.wait_for(state="visible", timeout=5000)
            target_input = (
                datetime_elem
                if await datetime_elem.evaluate("el => el.tagName === 'INPUT'")
                else datetime_elem.locator("input").first
            )
            await target_input.click(force=True)
            await target_input.fill(publish_date_str)
            await page.keyboard.press("Enter")
            await page.wait_for_timeout(500)
            return True
        except Exception as e:
            self.logger.error("定时发布设置失败", reason=str(e)[:200])
            return False

    async def _publish_video(self, page: Page) -> bool:
        try:
            publish_host = page.locator("xhs-publish-btn").first
            if await publish_host.count() > 0:
                await publish_host.scroll_into_view_if_needed()
                await publish_host.wait_for(state="visible", timeout=10000)

                # xhs-publish-btn 是无子节点的自定义组件，内部按钮无法用 DOM
                # 选择器定位。红色“发布”按钮位于宿主组件右侧区域。
                for attempt, ratio in enumerate((0.62, 0.72, 0.5), start=1):
                    box = await publish_host.bounding_box()
                    if box is None:
                        self.logger.error("发布组件不可点击")
                        return False
                    self.logger.info("点击发布组件", attempt=attempt, ratio=ratio)
                    await page.mouse.click(
                        box["x"] + box["width"] * ratio,
                        box["y"] + box["height"] * 0.5,
                    )
                    if await self._wait_for_publish_result(page, timeout=20.0):
                        return True
                    if await page.locator("xhs-publish-btn").count() == 0:
                        return await self._wait_for_publish_result(page, timeout=40.0)
                    await page.wait_for_timeout(1500)
                return False

            button = page.get_by_role("button", name=re.compile("发布|定时发布")).first
            if await button.count() == 0:
                button = page.locator(
                    'button:has-text("发布"), div:has-text("发布")'
                ).last
            if await button.count() == 0:
                self.logger.error("未找到发布按钮或发布组件")
                return False
            await button.scroll_into_view_if_needed()
            await button.wait_for(state="visible", timeout=10000)
            await button.click(force=True)
            return await self._wait_for_publish_result(page)
        except Exception as e:
            self.logger.error("发布异常", reason=str(e)[:200])
            return False

    async def _wait_for_publish_result(
        self, page: Page, *, timeout: float = 60.0
    ) -> bool:
        """等待发布后的成功反馈或成功页跳转。"""
        success_url = re.compile(r"/success|published=true|publish/success")

        try:
            await page.wait_for_url(
                success_url,
                wait_until="domcontentloaded",
                timeout=int(min(timeout, 15.0) * 1000),
            )
            self.logger.info("发布成功", url=page.url)
            return True
        except Error:
            if success_url.search(page.url):
                self.logger.info("发布成功", url=page.url)
                return True

        success_texts = [
            "发布成功",
            "提交成功",
            "发布完成",
            "审核中",
            "作品已发布",
        ]
        error_texts = ["发布失败", "上传失败", "请完善", "不能为空", "错误"]

        async def check() -> bool:
            if success_url.search(page.url):
                self.logger.info("发布成功", url=page.url)
                return True
            for text in success_texts:
                success = page.locator(f"text={text}").first
                if await success.count() > 0 and await success.is_visible():
                    self.logger.info("发布成功", method="text", text=text)
                    return True
            for text in error_texts:
                err = page.locator(f"text={text}").first
                if await err.count() > 0 and await err.is_visible():
                    message = await err.inner_text()
                    raise RuntimeError(f"发布失败提示: {message[:80]}")
            return False

        return await self._wait_for_condition(
            check, timeout=timeout, interval=0.5, desc="publish_result"
        )
