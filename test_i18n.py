"""i18n 冒烟测试：验证双语键完整性、tr 格式化与真实窗口的语言切换。"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import i18n
from desktop_app import MODES, PLATFORMS, ClashFilterApp
from tkinter import Tk


def backup_pref() -> Path | None:
    if i18n.PREF_FILE.exists():
        backup = i18n.PREF_FILE.with_suffix(".bak")
        shutil.copy2(i18n.PREF_FILE, backup)
        return backup
    return None


def restore_pref(backup: Path | None) -> None:
    i18n.PREF_FILE.unlink(missing_ok=True)
    if backup is not None:
        shutil.move(str(backup), i18n.PREF_FILE)


def test_key_parity() -> None:
    zh, en = i18n.STRINGS["zh"], i18n.STRINGS["en"]
    missing_en = zh.keys() - en.keys()
    missing_zh = en.keys() - zh.keys()
    assert not missing_en, f"en 缺少键: {missing_en}"
    assert not missing_zh, f"zh 多余键: {missing_zh}"
    for key, text in en.items():
        assert isinstance(text, str) and text, f"en 空文案: {key}"


def test_tr_formatting() -> None:
    i18n._language = "zh"
    assert i18n.tr("summary.nodes", count=3) == "3 个节点"
    assert i18n.tr("error.range", name="超时", minimum=1, maximum=300) == "超时需在 1～300 之间"
    i18n._language = "en"
    assert i18n.tr("summary.nodes", count=3) == "3 nodes"
    assert i18n.tr("nonexistent.key") == "nonexistent.key"


def test_ui_toggle() -> None:
    i18n._language = "zh"
    root = Tk()
    root.withdraw()
    app = ClashFilterApp(root)
    root.update()

    assert app.fetch_button.cget("text") == "获取节点"
    assert app.tree.heading("name")["text"] == "节点"
    assert app.platform_buttons["Netflix"].cget("text") == "√ Netflix  ·  流媒体"
    assert app.platform_buttons["Bilibili"].cget("text") == "□ Bilibili  ·  区域内容"

    app.source_var.set("https://example.com/sub")
    app.timeout_var.set("12")
    app.platform_vars["Netflix"].set(True)
    app.platform_vars["YouTube"].set(True)

    app._toggle_language()
    root.update()
    assert i18n.get_language() == "en"
    assert app.fetch_button.cget("text") == "Fetch nodes"
    assert app.tree.heading("name")["text"] == "Node"
    assert app.platform_buttons["Netflix"].cget("text") == "√ Netflix  ·  Streaming"
    assert app.platform_buttons["Bilibili"].cget("text") == "□ Bilibili  ·  Regional"
    assert app.source_var.get() == "https://example.com/sub"
    assert app.timeout_var.get() == "12"
    assert app.mode_var.get() == "Web availability + speed"
    assert app._mode_id() == "both"
    assert "Netflix, YouTube" in app.platform_status_var.get()
    saved = json.loads(i18n.PREF_FILE.read_text(encoding="utf-8"))
    assert saved == {"language": "en"}

    app._toggle_language()
    root.update()
    assert i18n.get_language() == "zh"
    assert app.fetch_button.cget("text") == "获取节点"
    assert app.source_var.get() == "https://example.com/sub"
    assert app.mode_var.get() == "网页可用性 + 速度"
    saved = json.loads(i18n.PREF_FILE.read_text(encoding="utf-8"))
    assert saved == {"language": "zh"}

    # 模式映射在两种语言下都应得到相同后端值
    app.mode_var.set(i18n.tr("mode.speed_only"))
    assert app._mode_id() == "speed_only"
    app.mode_var.set(i18n.tr("mode.both"))

    app.close()


def test_platforms_reference_valid_keys() -> None:
    for _name, category, _enabled in PLATFORMS:
        assert category in i18n.STRINGS["zh"], f"未知平台分类键: {category}"
    for _mode_id, key in MODES:
        assert key in i18n.STRINGS["zh"], f"未知模式键: {key}"


def main() -> None:
    backup = backup_pref()
    try:
        test_key_parity()
        test_tr_formatting()
        test_platforms_reference_valid_keys()
        test_ui_toggle()
        print("ALL I18N SMOKE TESTS PASSED")
    finally:
        restore_pref(backup)


if __name__ == "__main__":
    main()
