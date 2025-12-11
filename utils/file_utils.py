import base64
import os
import mimetypes

def get_image_base64(file_path):
    """读取图片并转换为 Base64 编码字符串"""
    if not os.path.exists(file_path):
        return None
        
    mime_type, _ = mimetypes.guess_type(file_path)
    if not mime_type or not mime_type.startswith('image'):
        return None
        
    with open(file_path, "rb") as image_file:
        encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
        
    return f"data:{mime_type};base64,{encoded_string}"

def is_image_file(file_path):
    """判断是否为图片文件"""
    if not file_path: return False
    mime_type, _ = mimetypes.guess_type(file_path)
    return mime_type and mime_type.startswith('image')