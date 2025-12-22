import os
import fitz  # PyMuPDF
import patoolib
import shutil

class PDFProcessor:
    @staticmethod
    def extract_invoice_info(page):
        """
        提取发票信息
        返回: {"is_invoice": bool, "date": str, "number": str}
        """
        import re
        
        info = {"is_invoice": False, "date": "", "number": ""}
        text = page.get_text()
        
        if "发票" in text or "Invoice" in text:
            info["is_invoice"] = True
            
        # 提取日期 (支持 YYYY年MM月DD日 或 YYYY-MM-DD)
        # 增加年份限制 (2000-2099)，避免匹配到像 7384 这样的数字
        date_pattern = re.compile(r'(20\d{2}\s*[年-]\s*\d{1,2}\s*[月-]\s*\d{1,2})')
        # 优先寻找 "开票日期" 附近的日期
        lines = text.split('\n')
        for i, line in enumerate(lines):
            if "开票日期" in line:
                # 检查当前行
                m = date_pattern.search(line)
                if m:
                    info["date"] = m.group(1)
                    break
                # 检查下一行
                if i + 1 < len(lines):
                    m = date_pattern.search(lines[i+1])
                    if m:
                        info["date"] = m.group(1)
                        break
                # 如果下一行也没有，可能在同一行但被空格隔开了，或者是 OCR 分割问题
                # 尝试在后两行找
                if i + 2 < len(lines):
                    m = date_pattern.search(lines[i+2])
                    if m:
                        info["date"] = m.group(1)
                        break
        
        # 如果没找到特定的，就找全文第一个像日期的
        if not info["date"]:
            m = date_pattern.search(text)
            if m:
                info["date"] = m.group(1)

        # 提取发票号码
        # 策略1: 寻找 "发票号码" 附近的数字 (Keyword search)
        num_pattern = re.compile(r'\d{8,22}') # 扩宽到22位以防万一
        for i, line in enumerate(lines):
            if "发票号码" in line or "No." in line or "No " in line:
                m = num_pattern.search(line)
                if m:
                    info["number"] = m.group(0)
                    break
                if i + 1 < len(lines):
                    m = num_pattern.search(lines[i+1])
                    if m:
                        info["number"] = m.group(0)
                        break
        
        # 策略2: 如果没找到，扫描右上角的纯数字块 (Spatial search)
        if not info["number"]:
            try:
                blocks = page.get_text("blocks")
                page_w = page.rect.width
                page_h = page.rect.height
                
                # 定义右上角区域: x > 40%, y < 30%
                candidates = []
                for b in blocks:
                    # b: (x0, y0, x1, y1, text, block_no, block_type)
                    x0, y0, x1, y1, b_text, _, _ = b
                    
                    # 排除包含 "校验码"、"密码"、"代码" (发票代码) 的块
                    if any(k in b_text for k in ["校验码", "Check Code", "密码", "Password", "代码", "Code"]):
                        continue

                    if x0 > page_w * 0.4 and y1 < page_h * 0.3: #稍微放宽x范围
                        # 清理文本，去除空格换行
                        clean_text = re.sub(r'\s+', '', b_text)
                        # 查找长数字
                        matches = num_pattern.findall(clean_text)
                        for match in matches:
                            # 排除掉已经被识别为日期的数字 (如果日期也是纯数字)
                            if info["date"] and match in info["date"].replace("-", "").replace("年", "").replace("月", "").replace("日", ""):
                                continue
                            candidates.append((y0, match))
                
                # 如果找到多个候选
                if candidates:
                    # 优先选择位置靠上的 (y0 越小越靠上)
                    # 通常顺序：发票代码 -> 发票号码 -> 开票日期 -> 校验码
                    # 我们已经排除了代码和校验码，所以剩下的最上面的应该是号码
                    candidates.sort(key=lambda x: x[0])
                    info["number"] = candidates[0][1]
                    
            except Exception:
                pass

        return info

    @staticmethod
    def analyze_page(page):
        """
        分析页面内容，返回 (有效内容高度, 平均字号, 最大字号, 有效内容区域Rect)
        有效内容区域：排除了顶部和底部可能的干扰文本（如打印标记），并且尝试去除"棕色外框"。
        同时，计算水平方向的内容边界，以便去除左右的空白或边框。
        """
        try:
            text_dict = page.get_text("dict")
        except Exception:
            return 0, 0, 0, None
            
        blocks = text_dict.get("blocks", [])
        page_rect = page.rect
        page_h = page_rect.height
        page_w = page_rect.width
        
        # 定义忽略区域（顶部和底部各 50pt，约 1.7cm）
        IGNORE_TOP = 50
        IGNORE_BOTTOM = 50
        
        valid_blocks = []
        font_sizes = []
        
        # 1. 分析文本/图片块
        for b in blocks:
            bbox = b["bbox"] # (x0, y0, x1, y1)
            
            # 过滤掉顶部和底部的干扰内容 (仅针对文本)
            # 图片块(type=1)通常是重要的，保留
            if b["type"] == 0:
                if bbox[3] < IGNORE_TOP or bbox[1] > (page_h - IGNORE_BOTTOM):
                    continue
            
                # 收集字号信息
                for line in b["lines"]:
                    for span in line["spans"]:
                        font_sizes.append(span["size"])
        
            # 如果是图片，且不在极端边缘，也保留
            elif b["type"] == 1:
                # 图片通常不应该被忽略，除非它完全在忽略区
                 if bbox[3] < 10 or bbox[1] > (page_h - 10):
                    continue
        
            valid_blocks.append(b)
        
        # 2. 分析矢量绘图 (去除棕色外框，保留表格线)
        # 我们需要收集所有非棕色外框的绘图的边界
        valid_drawings_rects = []
        try:
            drawings = page.get_drawings()
            for path in drawings:
                # 判断是否为棕色外框
                # 棕色判定：R > G > B, 且 R > 0.3 (避免黑色/深灰误判)
                is_brown = False
                color = path.get("color") # stroke
                if color and len(color) == 3:
                    r, g, b = color
                    # 宽松的棕色/土色判定
                    if r > 0.3 and r > g and (g > b or b < 0.25): 
                        is_brown = True
                
                # 如果是棕色，且尺寸较大（认为是外框），则忽略
                # 假设外框通常比较长或宽
                path_rect = path["rect"]
                if is_brown and (path_rect.width > page_w * 0.4 or path_rect.height > page_h * 0.4):
                    continue # 忽略此棕色外框
                
                # 否则，认为是有效内容（如表格线），加入边界计算
                # 过滤掉极端边缘的线条（可能是打印裁切线）
                if path_rect.y1 < IGNORE_TOP or path_rect.y0 > (page_h - IGNORE_BOTTOM):
                    continue
                    
                valid_drawings_rects.append(path_rect)
        except Exception:
            pass # 忽略绘图分析错误

        if not valid_blocks and not valid_drawings_rects:
            # 如果过滤后没东西了，可能页面本身内容就在边缘，或者空白
            # 退化：使用所有块
            valid_blocks = blocks
        
        if not valid_blocks and not valid_drawings_rects:
            return 0, 0, 0, None
        
        # 计算有效内容的边界 (Text/Image + Drawings)
        x0_min = page_w
        y0_min = page_h
        x1_max = 0
        y1_max = 0
        
        # 合并 Text/Image 边界
        for b in valid_blocks:
            x0_min = min(x0_min, b["bbox"][0])
            y0_min = min(y0_min, b["bbox"][1])
            x1_max = max(x1_max, b["bbox"][2])
            y1_max = max(y1_max, b["bbox"][3])
            
        # 合并 Drawings 边界
        for r in valid_drawings_rects:
            x0_min = min(x0_min, r.x0)
            y0_min = min(y0_min, r.y0)
            x1_max = max(x1_max, r.x1)
            y1_max = max(y1_max, r.y1)

        # 修正初始值未更新的情况 (e.g. only drawings or only text)
        if x0_min > x1_max: # Should not happen if there is content
             x0_min, x1_max = 0, page_w
        if y0_min > y1_max:
             y0_min, y1_max = 0, page_h

        # 有效高度
        content_h = y1_max - y0_min
        
        # 构造有效内容区域
        # 使用计算出的水平边界，并给予一定的 Padding (左右各 10pt)
        # 上下也给 Padding (5pt)
        pad_x = 10
        pad_y = 5
        
        final_x0 = max(0, x0_min - pad_x)
        final_y0 = max(0, y0_min - pad_y)
        final_x1 = min(page_w, x1_max + pad_x)
        final_y1 = min(page_h, y1_max + pad_y)
        
        valid_rect = fitz.Rect(final_x0, final_y0, final_x1, final_y1)
        
        avg_font = sum(font_sizes)/len(font_sizes) if font_sizes else 0
        max_font = max(font_sizes) if font_sizes else 0
        
        return content_h, avg_font, max_font, valid_rect

    @staticmethod
    def merge_half_page_pdfs(input_items, output_path=None):
        """
        将多个PDF文件合并。
        input_items: List of (file_path, page_index) or file_paths (backward compatibility)
        
        智能逻辑：
        1. 排除页眉页脚干扰后，如果内容少于半页 -> 裁切掉干扰部分，拼接到半页。
        2. 如果内容多于半页且字号大 -> 逆时针旋转90度后缩放拼接到半页。
        3. 如果内容多于半页且字号正常 -> 独立一页，不截断。
        4. 如果是A5或横向页面 -> 视为半页内容，不做额外裁切。
        """
        src_docs = {} # cache open docs: path -> doc
        pages_to_process = []

        try:
            # 1. 解析输入
            for item in input_items:
                if isinstance(item, tuple):
                    path, page_idx = item
                    if path not in src_docs:
                        src_docs[path] = fitz.open(path)
                    pages_to_process.append(src_docs[path][page_idx])
                else:
                    # Backward compatibility for list of paths
                    path = item
                    if path not in src_docs:
                        src_docs[path] = fitz.open(path)
                    for page in src_docs[path]:
                        pages_to_process.append(page)

            if not pages_to_process:
                raise ValueError("No pages found to merge.")

            # 2. 创建输出文档
            doc_out = fitz.open()
            A4_WIDTH = 595
            A4_HEIGHT = 842
            HALF_HEIGHT = A4_HEIGHT / 2
            
            # Padding definitions (approx 7mm)
            PADDING_X = 20
            PADDING_Y = 20

            # 当前正在填充的输出页面
            current_out_page = None
            current_y_cursor = 0 
            
            # Helper to finalize page (draw cut line if needed)
            def finalize_page_line(page_obj):
                if page_obj:
                    # Draw line at the exact center
                    shape = page_obj.new_shape()
                    line_y = A4_HEIGHT / 2
                    
                    # Ensure the line is drawn across the entire width
                    shape.draw_line(fitz.Point(0, line_y), fitz.Point(A4_WIDTH, line_y))
                    
                    # Style: Dash-Dot, Light Gray (0.8, 0.8, 0.8), Width 1.0
                    # Pattern: Dash(15) - Gap(10) - Dot(2) - Gap(10)
                    # overlay=True ensures it is drawn on top of existing content
                    shape.finish(color=(0.8, 0.8, 0.8), dashes=[15, 10, 2, 10], width=1.0)
                    shape.commit(overlay=True)

            # 3. 逐页处理
            for page in pages_to_process:
                page_rect = page.rect
                page_w, page_h = page_rect.width, page_rect.height
                
                # 智能识别 A5 或 横向
                # A5: ~420x595. If height < 600, it's small.
                is_landscape = page_w > page_h
                is_small_page = page_h < 600
                
                # 分析页面 (获取内容高度)
                content_h, avg_font, max_font, valid_rect = PDFProcessor.analyze_page(page)
                
                if valid_rect is None:
                    valid_rect = page_rect
                    content_h = page_h

                # 策略判断
                # 1. 显式的半页内容 (内容高度小)
                # 2. 显式的 A5 页面 (页面高度小)
                # 3. 显式的 横向页面 (适合放入半页槽)
                is_half_page_content = (content_h <= (HALF_HEIGHT + 20)) or is_small_page or is_landscape
                
                strategy = "NORMAL_HALF"
                
                if not is_half_page_content:
                    if (avg_font > 12 or max_font > 18) and (page_h > page_w):
                        strategy = "ROTATE_AND_FIT"
                    else:
                        strategy = "FULL_PAGE"
                
                # 执行策略
                if strategy == "NORMAL_HALF":
                    req_h = HALF_HEIGHT
                    
                    if current_out_page is None or (current_y_cursor + req_h > A4_HEIGHT + 10):
                        # Finalize previous page before switching
                        finalize_page_line(current_out_page)
                        
                        current_out_page = doc_out.new_page(width=A4_WIDTH, height=A4_HEIGHT)
                        current_y_cursor = 0
                    
                    # 目标区域 (带 Padding)
                    target_rect = fitz.Rect(
                        PADDING_X, 
                        current_y_cursor + PADDING_Y, 
                        A4_WIDTH - PADDING_X, 
                        current_y_cursor + req_h - PADDING_Y
                    )
                    
                    # 裁剪与放置逻辑
                    if is_small_page or is_landscape:
                         current_out_page.show_pdf_page(target_rect, page.parent, page.number, clip=valid_rect, keep_proportion=True)
                    else:
                        # A4 纵向半页内容 -> 执行“去头去尾”的 Fit Width 裁剪
                        clip_w = valid_rect.width
                        clip_h = valid_rect.height
                        
                        if clip_w > 0:
                            # 目标最大宽高
                            max_dest_w = target_rect.width
                            max_dest_h = target_rect.height
                            
                            # 计算缩放比例 (Fit Width)
                            scale = max_dest_w / clip_w
                            dest_h = clip_h * scale
                            dest_w = max_dest_w # by definition of scale
                            
                            # 如果高度超出了，就按高度缩放
                            if dest_h > max_dest_h:
                                scale = max_dest_h / clip_h
                                dest_h = max_dest_h
                                dest_w = clip_w * scale
                                
                            # 居中放置
                            x_offset = target_rect.x0 + (max_dest_w - dest_w) / 2
                            y_offset = target_rect.y0 + (max_dest_h - dest_h) / 2
                            
                            real_target_rect = fitz.Rect(x_offset, y_offset, x_offset + dest_w, y_offset + dest_h)
                                 
                            current_out_page.show_pdf_page(real_target_rect, page.parent, page.number, clip=valid_rect)
                        else:
                            current_out_page.show_pdf_page(target_rect, page.parent, page.number)

                    current_y_cursor += req_h
                        
                elif strategy == "ROTATE_AND_FIT":
                    req_h = HALF_HEIGHT
                    if current_out_page is None or (current_y_cursor + req_h > A4_HEIGHT + 10):
                        finalize_page_line(current_out_page)
                        current_out_page = doc_out.new_page(width=A4_WIDTH, height=A4_HEIGHT)
                        current_y_cursor = 0
                        
                    target_rect = fitz.Rect(
                        PADDING_X, 
                        current_y_cursor + PADDING_Y, 
                        A4_WIDTH - PADDING_X, 
                        current_y_cursor + req_h - PADDING_Y
                    )
                    
                    # 旋转时也使用 valid_rect 裁剪以去除外框
                    current_out_page.show_pdf_page(target_rect, page.parent, page.number, clip=valid_rect, rotate=270, keep_proportion=True)
                    
                    current_y_cursor += req_h
                        
                else: # FULL_PAGE
                    if current_out_page is not None:
                         finalize_page_line(current_out_page)
                         current_out_page = None
                         current_y_cursor = 0
                    
                    new_p = doc_out.new_page(width=A4_WIDTH, height=A4_HEIGHT)
                    new_p.show_pdf_page(new_p.rect, page.parent, page.number)
                    
                    current_out_page = None
                    current_y_cursor = 0

            # Finalize last page
            finalize_page_line(current_out_page)

            # 4. 保存或返回
            if output_path:
                doc_out.save(output_path)
                doc_out.close()
                return output_path
            else:
                return doc_out
            
        finally:
            for doc in src_docs.values():
                doc.close()

class ArchiveExtractor:
    @staticmethod
    def extract_and_find_pdfs(archive_path, temp_root_dir, max_depth=3, current_depth=1):
        """
        递归解压压缩包到临时目录，并返回找到的所有PDF路径。
        支持嵌套压缩包（套娃），默认最大递归深度为3层。
        """
        found_pdfs = []
        
        # 为该压缩包创建一个独立的子目录 (避免文件名冲突)
        # 使用随机后缀或者简单的计数可能更好，这里直接用文件名+深度
        folder_name = f"{os.path.splitext(os.path.basename(archive_path))[0]}_d{current_depth}_extracted"
        extract_dir = os.path.join(temp_root_dir, folder_name)
        
        # 如果目录已存在（可能同名文件），尝试加个随机数或时间戳，这里简化处理：
        counter = 1
        original_extract_dir = extract_dir
        while os.path.exists(extract_dir):
            extract_dir = f"{original_extract_dir}_{counter}"
            counter += 1
            
        os.makedirs(extract_dir, exist_ok=True)
        
        # 解压
        try:
            # verbosity=-1 静默模式
            patoolib.extract_archive(archive_path, outdir=extract_dir, verbosity=-1)
        except Exception as e:
            # 如果解压失败，记录错误但不要中断整个流程，返回空列表即可
            print(f"Failed to extract {os.path.basename(archive_path)}: {str(e)}")
            return []
        
        # 遍历解压后的目录
        for root, dirs, files in os.walk(extract_dir):
            for file in files:
                file_path = os.path.join(root, file)
                ext = os.path.splitext(file)[1].lower()
                
                if ext == '.pdf':
                    found_pdfs.append(file_path)
                
                elif ext in ['.zip', '.rar', '.7z'] and current_depth < max_depth:
                    # 发现嵌套压缩包，且未达最大深度 -> 递归调用
                    print(f"Found nested archive: {file}, digging deeper (Level {current_depth+1})...")
                    nested_pdfs = ArchiveExtractor.extract_and_find_pdfs(
                        file_path, 
                        extract_dir, # 在当前解压目录下继续创建子目录
                        max_depth=max_depth, 
                        current_depth=current_depth + 1
                    )
                    found_pdfs.extend(nested_pdfs)
        
        # 排序
        found_pdfs.sort()
        return found_pdfs