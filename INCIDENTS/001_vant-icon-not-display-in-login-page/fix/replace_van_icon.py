#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把 wxml 中的 <van-icon name="..."> 替换为 <text class="vi">真实 unicode 字符</text>

用途：解决 vant-icon 组件在某些 wxss 环境下不渲染的问题（INCIDENTS/001）

使用方法：
1. 修改 WXML_PATH 为目标 wxml 路径
2. 运行脚本：python replace_van_icon.py
3. 确保目标 wxml 中 <text class="vi"> 有对应的 wxss 样式

注意：必须用真实 unicode 字符（UTF-8），不能用 HTML 实体（wxml 不解析）
"""

import re

WXSS_PATH = r"E:\MyPrj\zhxt\zhpt-new\frontend\components\vant-icon\index.wxss"
WXML_PATH = r"E:\MyPrj\zhxt\zhpt-new\frontend\pages\login\login.wxml"


def load_icon_mapping(wxss_path):
    """从 vant-icon.wxss 解析 name -> unicode 字符映射"""
    with open(wxss_path, 'r', encoding='utf-8') as f:
        wxss = f.read()

    # 匹配 .van-icon-name:before{content:"\eXXX"}
    pattern = re.compile(r'\.van-icon-([a-z0-9-]+):before\{content:"\\([a-f0-9]+)"\}')
    name_to_unicode = {}
    for m in pattern.finditer(wxss):
        name = m.group(1)
        code = int(m.group(2), 16)
        name_to_unicode[name] = chr(code)

    return name_to_unicode


def replace_van_icons(wxml_path, name_to_unicode):
    """把 <van-icon name="..."> 替换为 <text class="vi">unicode字符</text>"""
    with open(wxml_path, 'r', encoding='utf-8') as f:
        wxml = f.read()

    icon_pattern = re.compile(
        r'<van-icon\s+name="([^"]+)"'
        r'(?:\s+size="([^"]+)")?'
        r'(?:\s+color="([^"]+)")?'
        r'(?:\s+class="([^"]+)")?'
        r'\s*/>'
    )

    def replace_icon(m):
        name = m.group(1)
        size = m.group(2) or '1em'
        color = m.group(3) or 'inherit'
        classes = m.group(4) or ''

        if name not in name_to_unicode:
            print(f"⚠️ 未知图标: {name}")
            return m.group(0)

        char = name_to_unicode[name]
        extra = (' ' + classes) if classes else ''
        return (
            f'<text class="vi{extra}" '
            f'style="font-family:vant-icon,sans-serif;'
            f'font-size:{size};color:{color};">'
            f'{char}</text>'
        )

    new_wxml = icon_pattern.sub(replace_icon, wxml)
    count = len(icon_pattern.findall(wxml))

    with open(wxml_path, 'w', encoding='utf-8') as f:
        f.write(new_wxml)

    return count


def main():
    print("=" * 60)
    print("vant-icon → text 批量替换工具")
    print("=" * 60)

    name_to_unicode = load_icon_mapping(WXSS_PATH)
    print(f"✅ 加载 {len(name_to_unicode)} 个图标映射")

    if 'phone-o' in name_to_unicode:
        print(f"   phone-o -> U+{ord(name_to_unicode['phone-o']):04X}")
    if 'shield-o' in name_to_unicode:
        print(f"   shield-o -> U+{ord(name_to_unicode['shield-o']):04X}")
    if 'user-o' in name_to_unicode:
        print(f"   user-o -> U+{ord(name_to_unicode['user-o']):04X}")

    print()
    count = replace_van_icons(WXML_PATH, name_to_unicode)
    print(f"✅ 替换了 {count} 个 <van-icon> 标签")
    print(f"📁 输出: {WXML_PATH}")


if __name__ == '__main__':
    main()
