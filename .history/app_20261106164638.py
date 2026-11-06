import streamlit as st
import pymupdf as fitz  # PyMuPDF
from PIL import Image

# 1. 允许加载极大尺寸的图片（解除解压炸弹像素限制）
Image.MAX_IMAGE_PIXELS = None

# 2. 忽略解压警告
import warnings
warnings.simplefilter('ignore', Image.DecompressionBombWarning)

import io
import datetime

# ==================== 页面基础配置 ====================
st.set_page_config(
    page_title="PDF 纸样自动拼接工具",
    page_icon="✂️",
    layout="centered"
)

st.title("✂️ PDF 纸样自动拼接工具 (网页版)")
st.markdown("上传多页 PDF 纸样，工具将自动清除红网格、精准裁切、消除重影并乌黑加深，一键生成 1:1 高清大图！")

# ==================== 侧边栏参数设置 ====================
st.sidebar.header("⚙️ 拼接参数设置")
total_rows = st.sidebar.number_input("每列页数 (Rows)", min_value=1, max_value=10, value=4)
crop_margin = st.sidebar.number_input("白边裁切像素 (Margin)", min_value=0, max_value=100, value=46)
export_format = st.sidebar.selectbox("导出格式", ["PDF 文档", "JPG 图片"])

# ==================== 核心拼接逻辑 ====================
def generate_stitched_image(uploaded_file, rows, margin_px):
    # 用字节流读取上传的 PDF，避免文件路径问题
    pdf_bytes = uploaded_file.read()
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    num_pages = len(doc)
    
    total_cols = (num_pages + rows - 1) // rows
    is_column_first = True  # 列优先拼接

    images = []
    zoom = 3.0  # 3.0 倍超高清渲染
    mat = fitz.Matrix(zoom, zoom)

    for page in doc:
        # 1. 渲染高清页面并铺上纯白底色
        pix = page.get_pixmap(matrix=mat, alpha=False)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        
        # 2. 精准红网格清除
        pixels = img.load()
        w_px, h_px = img.size
        for y in range(h_px):
            for x in range(w_px):
                r, g, b = pixels[x, y]
                if r > 120 and g < 100 and b < 100:
                    pixels[x, y] = (255, 255, 255)

        # 3. 精准裁切白边
        scaled_crop = int(margin_px * (zoom / 2.0))
        crop_box = (scaled_crop, scaled_crop, w_px - scaled_crop, h_px - scaled_crop)
        cropped_img = img.crop(crop_box)
        
        # 4. 灰度平滑压黑（保护中文与虚线）
        img_gray = cropped_img.convert("L")
        table = []
        for i in range(256):
            if i > 225:
                table.append(255)
            elif i < 60:
                table.append(0)
            else:
                table.append(int(i * 0.4))
        bold_img = img_gray.point(table, 'L').convert("RGB")
        images.append(bold_img)

    # 尺寸统一对齐，防止边缘错位与重影
    max_w = max(im.width for im in images)
    max_h = max(im.height for im in images)
    
    uniform_images = []
    for im in images:
        if im.width != max_w or im.height != max_h:
            new_img = Image.new("RGB", (max_w, max_h), (255, 255, 255))
            new_img.paste(im, (0, 0))
            uniform_images.append(new_img)
        else:
            uniform_images.append(im)

    single_w, single_h = max_w, max_h
    outer_padding = 40
    scaled_outer_padding = int(outer_padding * (zoom / 2.0))
    
    canvas_w = single_w * total_cols + scaled_outer_padding * 2
    canvas_h = single_h * rows + scaled_outer_padding * 2
    
    canvas = Image.new("RGB", (canvas_w, canvas_h), (255, 255, 255))

    for idx, im in enumerate(uniform_images):
        if is_column_first:
            col = idx // rows
            row = idx % rows
        else:
            row = idx // total_cols
            col = idx // total_cols
            
        paste_x = scaled_outer_padding + col * single_w
        paste_y = scaled_outer_padding + row * single_h
        canvas.paste(im, (paste_x, paste_y))
        
    return canvas

# ==================== 主界面交互 ====================
uploaded_file = st.file_uploader("选择或拖拽要拼接的 PDF 纸样文件", type=["pdf"])

if uploaded_file is not None:
    st.success(f"已成功加载文件: {uploaded_file.name}")
    
    if st.button("🚀 开始拼接并生成预览", type="primary"):
        with st.spinner("正在处理大尺寸图纸，请稍候..."):
            try:
                stitched_img = generate_stitched_image(uploaded_file, total_rows, crop_margin)
                
                # 将无损大图保存到 session_state 中
                st.session_state['stitched_img'] = stitched_img
                st.session_state['file_name_base'] = uploaded_file.name.rsplit(".", 1)[0]
                st.success("拼接完成！请在下方查看效果并下载。")
            except Exception as e:
                st.error(f"处理过程中出错: {str(e)}")

# ==================== 预览与下载模块 ====================
if 'stitched_img' in st.session_state:
    st.markdown("---")
    st.subheader("👀 拼接效果预览")
    
    # 💡 关键修复：生成等比例缩略图并转为字节流，彻底解决超大图片在前端预览触发的 DecompressionBombError
    preview_img = st.session_state['stitched_img'].copy()
    preview_img.thumbnail((2000, 2000))
    
    img_byte_arr = io.BytesIO()
    preview_img.save(img_byte_arr, format='JPEG', quality=90)
    img_byte_arr.seek(0)
    
    # 渲染预览（使用最新的 width='stretch' 参数）
    st.image(img_byte_arr, caption="拼接后整体效果预览（网页显示已轻微压缩，下载文件为原图无损高清）", width='stretch')
    
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    
    if export_format == "PDF 文档":
        # 导出原图高清 PDF
        pdf_buffer = io.BytesIO()
        img_w, img_h = st.session_state['stitched_img'].size
        pdf_doc = fitz.open()
        page = pdf_doc.new_page(width=img_w, height=img_h)
        
        temp_img_bytes = io.BytesIO()
        st.session_state['stitched_img'].save(temp_img_bytes, format="PNG")
        page.insert_image(fitz.Rect(0, 0, img_w, img_h), stream=temp_img_bytes.getvalue())
        pdf_doc.save(pdf_buffer, garbage=4, deflate=True)
        pdf_doc.close()
        
        st.download_button(
            label="📥 点击下载无损高清 PDF 纸样",
            data=pdf_buffer.getvalue(),
            file_name=f"{st.session_state['file_name_base']}_{timestamp}_stitched.pdf",
            mime="application/pdf"
        )
    else:
        # 导出原图高清 JPG
        img_buffer = io.BytesIO()
        st.session_state['stitched_img'].save(img_buffer, format="JPEG", quality=98)
        
        st.download_button(
            label="📥 点击下载高清 JPG 纸样图片",
            data=img_buffer.getvalue(),
            file_name=f"{st.session_state['file_name_base']}_{timestamp}_stitched.jpg",
            mime="image/jpeg"
        )