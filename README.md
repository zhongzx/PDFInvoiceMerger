# PDF Invoice Merger (PDF 发票合并工具)

[English Version Below](#pdf-invoice-merger)

一个功能强大且易于使用的 Windows 工具，用于将半页的 PDF 发票和行程单合并到单张 A4 纸上，从而减少纸张浪费。采用 PyQt6 构建，界面简洁现代。

## 功能特点

*   **智能合并**：自动检测半页内容（如电子发票、行程单），并将两页合并到一张 A4 纸上。
*   **智能处理**：
    *   自动识别并保留 A5 大小和横向页面。
    *   如果需要，自动旋转内容以适应页面。
    *   自动去除电子发票周围烦人的三边棕色外框。
    *   在合并的上下部分之间绘制清晰的裁切线。
*   **信息提取**：自动扫描并提取发票号码和日期，便于核对。
*   **拖拽支持**：支持直接将文件和文件夹拖入应用。
    *   **多层压缩包支持**：自动解压嵌套的 ZIP/RAR/7z 文件（支持多达 3 层递归），查找其中的 PDF。
*   **查重功能**：自动检测重复的发票号码并用红色高亮显示，防止重复报销。
*   **实时预览**：在打印或保存之前实时预览合并效果。
*   **双语界面**：一键切换中文和英文界面。

## 安装说明

1.  确保已安装 Python 3.8 或更高版本。
2.  安装依赖库：
    ```bash
    pip install -r requirements.txt
    ```
    *(注意：需要 `PyQt6`, `pymupdf`, `patool`)*

## 使用指南

1.  **启动应用**：运行 `run_merger.bat` 或 `python main.py`。
2.  **添加文件**：将 PDF 或 ZIP 文件拖入列表，或使用“添加文件”按钮。
3.  **管理页面**：
    *   使用复选框选择或取消选择特定页面。
    *   拖动项目调整顺序。
    *   按 `Space`（空格键）切换页面的选择状态。
    *   重复发票会显示为 **红色**；已解决的重复项（只选中了一个）会显示为 **蓝色**。
4.  **合并**：点击“合并”按钮生成结果。
5.  **预览与输出**：
    *   在右侧预览窗格查看结果。
    *   点击“保存 PDF”导出文件。
    *   点击“打印”直接打印。

## 快捷键

*   **空格键 (Space)**：切换页面选中状态。
*   **上/下箭头 (Up/Down)**：在列表中导航（自动跳过文件头，只在页面间切换）。
*   **Delete**：移除选中的文件。

## 许可证

MIT

---

# PDF Invoice Merger

A powerful, user-friendly tool to merge half-page PDF invoices and itineraries into single A4 pages to reduce paper waste. Designed for Windows with a clean PyQt6 interface.

## Features

*   **Smart Merging**: Automatically detects half-page content (e.g., invoices, itineraries) and merges two onto a single A4 page.
*   **Intelligent Processing**:
    *   Preserves A5 and Landscape pages.
    *   Auto-rotates content if needed.
    *   Removes unwanted 3-sided brown frames from electronic invoices.
    *   Draws a clear cut-line between merged sections.
*   **Data Extraction**: Automatically scans and extracts Invoice Numbers and Dates for easy organization.
*   **Drag & Drop**: Supports dragging files and folders directly into the app.
    *   **Recursive Archive Support**: Automatically unpacks nested ZIP/RAR/7z files (up to 3 levels deep) to find PDFs.
*   **Duplicate Detection**: Highlights duplicate invoice numbers in red to prevent errors.
*   **Real-time Preview**: Preview the merged result before printing or saving.
*   **Bilingual Interface**: One-click switch between Chinese and English.

## Installation

1.  Ensure you have Python 3.8+ installed.
2.  Install dependencies:
    ```bash
    pip install -r requirements.txt
    ```
    *(Note: Requires `PyQt6`, `pymupdf`, `patool`)*

## Usage

1.  **Launch the App**: Run `run_merger.bat` or `python main.py`.
2.  **Add Files**: Drag PDF or ZIP files into the list, or use the "Add Files" button.
3.  **Manage Pages**:
    *   Use checkboxes to select/deselect specific pages.
    *   Drag items to reorder.
    *   Press `Space` to toggle page selection.
    *   Duplicates are highlighted in **Red**; resolved duplicates (single selection) are **Blue**.
4.  **Merge**: Click "Merge" to generate the output.
5.  **Preview & Output**:
    *   Check the preview pane.
    *   Click "Save PDF" to export.
    *   Click "Print" to print directly.

## Shortcuts

*   **Space**: Toggle page selection.
*   **Up/Down**: Navigate list (skips file headers).
*   **Del**: Remove selected file.

## Acknowledgments (鸣谢)

> **Dedicated to my dear wife Merin. This work was inspired by her professional needs and made possible by her constant encouragement.**
>
> **仅以此软件献给我亲爱的妻子美林 (Merin)，正是因为她在工作中的需求和不断的鼓励才有了这么一个作品。**

## License

MIT
