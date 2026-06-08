#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
FANSAI - 全平台内容发布工具
"""

__version__ = "1.2.0"
__author__ = "FANSAI"
__email__ = ""
__logo__ = r"""
 ______        _   _  _____          _____
|  ____|/\    | \ | |/ ____|   /\   |_   _|
| |__  /  \   |  \| | (___    /  \    | |
|  __|/ /\ \  | . ` |\___ \  / /\ \   | |
| |  / ____ \ | |\  |____) |/ ____ \ _| |_
|_| /_/    \_\|_| \_|_____//_/    \_\_____|
"""

from spreado.core.uploader import BaseUploader
from spreado.core.base_publisher import BasePublisher
from spreado.plugin_loader import PluginLoader, get_plugin_loader
from spreado.account_manager import AccountManager
from spreado.models.task import Task

__all__ = [
    "BaseUploader",
    "BasePublisher",
    "PluginLoader",
    "get_plugin_loader",
    "AccountManager",
    "Task",
    "__version__",
    "__logo__",
]
