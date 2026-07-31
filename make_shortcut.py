#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""在桌面建立「即時翻譯」捷徑（pythonw，無主控台）。

為什麼不用 .bat 直接做：cmd.exe 是以系統 OEM 編碼逐位元組讀批次檔，
批次檔裡一旦有中文（或用 chcp 65001 硬轉），續行符號與含中文的 %~dp0
都會被打斷。所以 .bat 只留純 ASCII 當薄殼，實際工作交給 Python。
"""
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
BASE = os.path.dirname(os.path.abspath(__file__))
NAME = "即時翻譯"


def main():
    try:
        import win32com.client
    except ImportError:
        print("  缺少 pywin32，請先執行： python -m pip install pywin32")
        return 1

    pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    if not os.path.exists(pyw):
        pyw = sys.executable          # 沒有 pythonw 就退回 python（會有主控台）
        print("  找不到 pythonw.exe，改用 python.exe（啟動時會有主控台視窗）")

    shell = win32com.client.Dispatch("WScript.Shell")
    lnk = os.path.join(shell.SpecialFolders("Desktop"), NAME + ".lnk")
    s = shell.CreateShortCut(lnk)
    s.TargetPath = pyw
    s.Arguments = '"hover_translate.py"'
    s.WorkingDirectory = BASE
    icon = os.path.join(BASE, "icon.ico")
    if os.path.exists(icon):
        s.IconLocation = icon + ",0"
    s.Description = "滑鼠指到英文即時發音 + 繁中釋義（離線）"
    s.WindowStyle = 7                 # 最小化執行，不閃視窗
    try:
        s.save()
    except AttributeError:
        s.Save()

    if os.path.exists(lnk):
        print(f"  已建立桌面捷徑：{lnk}")
        return 0
    print("  捷徑建立失敗。仍可用「啟動.bat」執行程式。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
