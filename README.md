# Markdown 实时预览工具 (MdViewer)

一个轻量级的 Markdown 文件实时预览桌面应用，窗口始终置顶，适合写作时随时查看渲染效果。

## 功能

- 可视化渲染 Markdown 文件（支持表格、代码块、目录、换行等）
- 文件修改后自动刷新显示
- 窗口始终置顶，不会被其他窗口遮挡
- 窗口大小可调，菜单提供多种预设分辨率
- 支持拖拽文件到窗口中打开
- 支持命令行参数直接打开文件

## 使用方式

### 直接运行（需要 Python 环境）

```bash
# 双击启动
start.bat

# 或指定文件
start.bat readme.md
```

### 使用打包后的 exe

双击 `dist/MdViewer.exe` 运行，无需 Python 环境。

## 快捷键

| 快捷键 | 功能 |
|--------|------|
| Ctrl+O | 打开文件 |
| F5 | 手动刷新 |

## 菜单

- **文件 → 打开** — 选择 Markdown 文件
- **文件 → 刷新** — 手动刷新渲染
- **窗口** — 选择预设分辨率调整窗口大小

## 构建发布包

```bash
release.bat
```

输出：`dist/MdViewer.exe`

## 依赖

- Python 3.8+
- PySide6
- markdown
