"""桌面界面多语言支持（中文 / English）。

语言偏好保存在用户主目录的 ``.clash-node-filter.json``；
没有保存过的偏好时，按操作系统界面语言自动选择。
"""

from __future__ import annotations

import ctypes
import json
import os
import sys
from pathlib import Path

PREF_FILE = Path.home() / ".clash-node-filter.json"

STRINGS: dict[str, dict[str, str]] = {
    "zh": {
        "app.title": "Clash 节点筛选器",
        "app.subtitle": "网页可用性 · 延迟 · 下载速度",
        "app.tagline": "本地测试工具",
        "app.language_toggle": "English",
        "source.title": "订阅来源",
        "source.hint": "支持订阅 URL、Clash/Mihomo YAML、Base64 节点列表；多个来源用英文逗号分隔",
        "source.choose_file": "选择 YAML",
        "source.fetch": "获取节点",
        "footer.privacy": "所有请求仅在本机执行，不上传节点配置",
        "controls.title": "测试设置",
        "controls.hint": "通过真实网页请求判定节点，不发送 ICMP ping",
        "controls.server": "网页测速服务",
        "controls.server_hint": "末尾是否带 / 不影响访问，程序会自动规范化。",
        "controls.mode": "测试模式",
        "controls.targets": "国外网页目标",
        "mode.both": "网页可用性 + 速度",
        "mode.unlock_only": "仅网页可用性",
        "mode.speed_only": "仅速度",
        "cat.streaming": "流媒体",
        "cat.video": "视频",
        "cat.ai": "AI 服务",
        "cat.music": "音乐",
        "cat.region": "区域内容",
        "field.concurrent": "并发数",
        "field.timeout": "超时（秒）",
        "field.max_latency": "最大延迟（毫秒）",
        "field.download": "下载样本（MB）",
        "field.upload": "上传样本（MB）",
        "field_name.concurrent": "并发数",
        "field_name.timeout": "超时",
        "field_name.max_latency": "最大延迟",
        "field_name.download": "下载样本",
        "field_name.upload": "上传样本",
        "button.start": "开始批量测试",
        "button.stop": "停止当前测试",
        "tips.title": "筛选建议",
        "tips.body": "先获取节点确认订阅可解析，再开始测试。网页可用性通过目标平台的 HTTPS 请求检测；测速使用 Cloudflare 下载/上传接口。",
        "results.title": "节点结果",
        "col.name": "节点",
        "col.type": "协议",
        "col.server": "服务器",
        "col.latency": "延迟",
        "col.download": "下载速度",
        "col.web": "网页可用",
        "col.status": "状态",
        "button.export_json": "导出 JSON",
        "button.export_csv": "导出 CSV",
        "button.clear": "清空结果",
        "dialog.choose_config": "选择 Clash/Mihomo 配置",
        "file.yaml": "YAML 文件",
        "file.all": "所有文件",
        "dialog.export_title": "导出测试结果",
        "dialog.warn_source_title": "缺少订阅来源",
        "dialog.warn_source_fetch": "请粘贴订阅链接或选择一个 Clash/Mihomo YAML 文件。",
        "dialog.warn_source_test": "请先输入订阅链接或选择本地配置。",
        "dialog.invalid_title": "设置有误",
        "dialog.no_results_title": "没有结果",
        "dialog.no_results": "请先完成一次测试，再导出结果。",
        "dialog.error_title": "操作失败",
        "dialog.export_error_title": "导出失败",
        "status.ready": "准备就绪 · 尚未加载订阅",
        "status.core_connected": "本地测试核心已连接 · 可以获取订阅",
        "status.core_missing": "未找到测试核心，请先运行 build.ps1 构建",
        "status.core_start_failed": "测试核心启动失败：{error}",
        "status.core_timeout": "测试核心启动超时，请检查 backend/logs",
        "status.fetching": "正在读取订阅并解析节点……",
        "status.fetched": "已解析 {count} 个节点 · 可以开始测试",
        "status.testing": "测试中……",
        "status.test_started": "已启动网页测试 · 正在逐个验证节点",
        "status.testing_node": "正在测试：{name} · {status}",
        "status.test_done": "测试完成 · 已返回 {count} 条结果",
        "status.test_stopped": "已停止当前测试；未完成任务不会继续显示",
        "status.test_cancelled": "测试已停止 · 保留 {count} 条结果（完成 {done}/{total}）",
        "status.cleared": "已清空测试结果",
        "status.exported": "已导出 {name}",
        "status.results_count": "{count} 条结果",
        "summary.nodes": "{count} 个节点",
        "summary.results": "{count} 条测试结果",
        "error.parse": "节点解析失败",
        "error.fetch": "获取节点失败：{error}",
        "error.task_create": "测试任务创建失败",
        "error.not_number": "「{name}」请填写整数",
        "error.range": "{name}需在 {minimum}～{maximum} 之间",
        "error.ws_deadline": "实时测试超过整批任务保护时限，已自动结束等待",
        "error.ws_fallback": "实时通道不可用，改用同步测试：{error}",
        "error.ws_abnormal": "实时测试未正常结束：{error}",
        "error.test": "测试失败",
        "error.test_with": "测试失败：{error}",
        "net.refused": "订阅服务器拒绝了连接。请确认链接仍有效、端口可访问，或稍后重试；这通常是订阅服务端问题，不是节点测速失败。",
        "net.timeout": "订阅服务器响应超时。请检查网络、代理/VPN 状态，或稍后重试。",
        "net.unreachable": "无法连接订阅地址，请检查链接是否完整、是否需要登录，以及当前网络是否能访问该域名。",
        "net.unknown": "未知错误",
        "node.pending": "待测试",
        "node.alive": "可用",
        "node.failed": "失败",
        "node.timeout": "超时",
        "targets.selected": "已选择 {count} 个目标：{names}",
        "targets.none": "未选择任何目标（将跳过网页解锁检测）",
    },
    "en": {
        "app.title": "Clash Node Filter",
        "app.subtitle": "Web availability · Latency · Download speed",
        "app.tagline": "Local testing tool",
        "app.language_toggle": "中文",
        "source.title": "Subscription",
        "source.hint": "Subscription URLs, Clash/Mihomo YAML, or Base64 node lists; separate multiple sources with commas",
        "source.choose_file": "Choose YAML",
        "source.fetch": "Fetch nodes",
        "footer.privacy": "All requests run locally — node configs are never uploaded",
        "controls.title": "Test settings",
        "controls.hint": "Nodes are judged via real web requests — no ICMP ping",
        "controls.server": "Speed test service",
        "controls.server_hint": "A trailing slash is fine — it is normalized automatically.",
        "controls.mode": "Test mode",
        "controls.targets": "Web targets",
        "mode.both": "Web availability + speed",
        "mode.unlock_only": "Web availability only",
        "mode.speed_only": "Speed only",
        "cat.streaming": "Streaming",
        "cat.video": "Video",
        "cat.ai": "AI services",
        "cat.music": "Music",
        "cat.region": "Regional",
        "field.concurrent": "Concurrency",
        "field.timeout": "Timeout (s)",
        "field.max_latency": "Max latency (ms)",
        "field.download": "Download size (MB)",
        "field.upload": "Upload size (MB)",
        "field_name.concurrent": "Concurrency",
        "field_name.timeout": "Timeout",
        "field_name.max_latency": "Max latency",
        "field_name.download": "Download size",
        "field_name.upload": "Upload size",
        "button.start": "Start batch test",
        "button.stop": "Stop current test",
        "tips.title": "Tips",
        "tips.body": "Fetch nodes first to confirm the subscription parses, then run the test. Web availability is checked with HTTPS requests to each target platform; speed tests use the Cloudflare download/upload endpoints.",
        "results.title": "Node results",
        "col.name": "Node",
        "col.type": "Type",
        "col.server": "Server",
        "col.latency": "Latency",
        "col.download": "Download",
        "col.web": "Web",
        "col.status": "Status",
        "button.export_json": "Export JSON",
        "button.export_csv": "Export CSV",
        "button.clear": "Clear results",
        "dialog.choose_config": "Choose Clash/Mihomo config",
        "file.yaml": "YAML files",
        "file.all": "All files",
        "dialog.export_title": "Export test results",
        "dialog.warn_source_title": "Subscription required",
        "dialog.warn_source_fetch": "Paste a subscription link or choose a Clash/Mihomo YAML file first.",
        "dialog.warn_source_test": "Enter a subscription link or choose a local config file first.",
        "dialog.invalid_title": "Invalid settings",
        "dialog.no_results_title": "No results",
        "dialog.no_results": "Run a test first, then export the results.",
        "dialog.error_title": "Operation failed",
        "dialog.export_error_title": "Export failed",
        "status.ready": "Ready · no subscription loaded",
        "status.core_connected": "Local test core connected · ready to fetch subscriptions",
        "status.core_missing": "Test core not found — run build.ps1 first",
        "status.core_start_failed": "Failed to start test core: {error}",
        "status.core_timeout": "Test core startup timed out — check backend/logs",
        "status.fetching": "Reading subscription and parsing nodes…",
        "status.fetched": "Parsed {count} nodes · ready to test",
        "status.testing": "Testing…",
        "status.test_started": "Web test started · verifying nodes one by one",
        "status.testing_node": "Testing: {name} · {status}",
        "status.test_done": "Test finished · {count} results returned",
        "status.test_stopped": "Test stopped — unfinished nodes are discarded",
        "status.test_cancelled": "Test stopped · kept {count} results ({done}/{total} completed)",
        "status.cleared": "Results cleared",
        "status.exported": "Exported {name}",
        "status.results_count": "{count} results",
        "summary.nodes": "{count} nodes",
        "summary.results": "{count} test results",
        "error.parse": "Failed to parse nodes",
        "error.fetch": "Failed to fetch nodes: {error}",
        "error.task_create": "Failed to create test task",
        "error.not_number": "{name} must be a whole number",
        "error.range": "{name} must be between {minimum} and {maximum}",
        "error.ws_deadline": "Realtime test exceeded the batch deadline — stopped waiting",
        "error.ws_fallback": "Realtime channel unavailable, using sync test: {error}",
        "error.ws_abnormal": "Realtime test did not finish normally: {error}",
        "error.test": "Test failed",
        "error.test_with": "Test failed: {error}",
        "net.refused": "The subscription server refused the connection. Make sure the link is still valid and the port is reachable, then retry — this is usually a server-side issue, not a node failure.",
        "net.timeout": "The subscription server timed out. Check your network and proxy/VPN status, then retry.",
        "net.unreachable": "Cannot reach the subscription URL. Check that the link is complete, whether it requires login, and that the domain is reachable from your network.",
        "net.unknown": "Unknown error",
        "node.pending": "Pending",
        "node.alive": "Alive",
        "node.failed": "Failed",
        "node.timeout": "Timed out",
        "targets.selected": "{count} target(s) selected: {names}",
        "targets.none": "No targets selected (web unlock checks will be skipped)",
    },
}

_language = "zh"


def init() -> str:
    """加载已保存的语言偏好；没有则按系统语言检测。返回当前语言。"""
    global _language
    _language = _load_preference() or _detect_system_language()
    return _language


def get_language() -> str:
    return _language


def set_language(language: str) -> None:
    """切换界面语言并写入偏好文件；非法取值保持原语言。"""
    global _language
    if language not in STRINGS:
        return
    _language = language
    try:
        PREF_FILE.write_text(json.dumps({"language": _language}, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def tr(key: str, **kwargs: object) -> str:
    """按当前语言取文案；支持 {name} 占位符，缺失时回退中文再回退键名。"""
    text = STRINGS.get(_language, {}).get(key) or STRINGS["zh"].get(key) or key
    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, IndexError, ValueError):
            return text
    return text


def _load_preference() -> str | None:
    try:
        data = json.loads(PREF_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    language = data.get("language") if isinstance(data, dict) else None
    return language if language in STRINGS else None


def _detect_system_language() -> str:
    if sys.platform == "win32":
        try:
            # LANGID 低 10 位是主语言 ID，0x0004 表示中文。
            if ctypes.windll.user32.GetUserDefaultUILanguage() & 0x3FF == 0x0004:
                return "zh"
            return "en"
        except Exception:  # noqa: BLE001
            pass
    for name in ("LC_ALL", "LC_MESSAGES", "LANG"):
        value = os.environ.get(name, "")
        if value.lower().startswith("zh"):
            return "zh"
        if value:
            return "en"
    return "zh"
