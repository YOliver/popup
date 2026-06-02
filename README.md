# Popup - Markdown 实时预览工具

> 当前版本：v1.4.1

一个轻量级的 Markdown 文件实时预览桌面应用，窗口始终置顶，适合写作时随时查看渲染效果。

## 功能

- 可视化渲染 Markdown 文件（支持表格、代码块、目录、换行等）
- 左侧目录边栏，自动提取标题，点击跳转
- 文件修改后自动刷新显示
- 窗口始终置顶，不会被其他窗口遮挡
- 窗口大小可调，菜单提供多种预设分辨率
- 支持拖拽文件到窗口中打开
- 支持命令行参数直接打开文件
- 轻量渲染引擎，快速启动

## 使用方式

### 直接运行（需要 Python 环境）

```bash
start.bat
start.bat readme.md
```

### 使用安装包

运行 `installer/Popup_Setup.exe` 安装，支持开始菜单和桌面快捷方式。

### 使用打包后的 exe

双击 `dist/Popup.exe` 运行，无需 Python 环境。

## 快捷键

| 快捷键 | 功能 |
|--------|------|
| Ctrl+O | 打开文件 |
| F5 | 手动刷新 |
| Ctrl+B | 显示/隐藏目录边栏 |

## 菜单

- **文件 → 打开** — 选择 Markdown 文件
- **文件 → 刷新** — 手动刷新渲染
- **窗口** — 选择预设分辨率调整窗口大小
- **日志 → 打开日志目录** — 查看运行日志

## 构建发布包

```bash
release.bat
```

输出：
- `dist/Popup.exe` — 单文件可执行程序
- `installer/Popup_Setup.exe` — Windows 安装包

## 依赖

- Python 3.8+
- PySide6
- markdown

## 文档

- [欢迎](helpdocs/welcome.md) — 开发者信息与联系方式
- [关于](helpdocs/about.md) — 版本信息与运行环境
- [使用手册](helpdocs/使用手册.md) — 完整使用说明
