import os
import shutil
from cryptography.fernet import Fernet
from utils.logger import logger

class SecurityManager:
    _key = None
    KEY_FILE = '.secret.key'

    @classmethod
    def get_key(cls):
        """获取加密密钥，包含自愈机制"""
        if cls._key:
            return cls._key

        # 1. 尝试读取
        if os.path.exists(cls.KEY_FILE):
            try:
                with open(cls.KEY_FILE, 'rb') as f:
                    file_content = f.read()
                
                # 校验密钥格式是否有效
                Fernet(file_content)
                cls._key = file_content
                return cls._key
            except Exception as e:
                logger.error(f"[Security] 密钥文件损坏或格式错误: {e}，正在重置...")
                # 备份错误的密钥
                shutil.copy(cls.KEY_FILE, cls.KEY_FILE + ".bak")

        # 2. 生成新密钥 (Fernet.generate_key() 返回的是 URL-safe base64-encoded bytes)
        cls._key = Fernet.generate_key()
        with open(cls.KEY_FILE, 'wb') as f:
            f.write(cls._key)
        
        logger.info("[Security] 已生成新的加密密钥")
        return cls._key

    @classmethod
    def encrypt(cls, text):
        if not text: return ""
        try:
            f = Fernet(cls.get_key())
            return f.encrypt(text.encode('utf-8')).decode('utf-8')
        except Exception as e:
            logger.error(f"加密失败: {e}")
            return text

    @classmethod
    def decrypt(cls, text):
        if not text: return ""
        try:
            f = Fernet(cls.get_key())
            return f.decrypt(text.encode('utf-8')).decode('utf-8')
        except Exception as e:
            # 如果解密失败（可能是密钥重置了），返回原文或空
            logger.error(f"解密失败 (可能密钥已变更): {e}")
            return text

    @staticmethod
    def is_safe_path(path):
        """防止路径遍历攻击"""
        try:
            base_dir = os.path.abspath(os.getcwd())
            resolved_path = os.path.abspath(path)
            return resolved_path.startswith(base_dir)
        except:
            return False

    @staticmethod
    def sanitize_path(path):
        clean_path = str(path).strip().replace('"', '').replace("'", "")
        if not SecurityManager.is_safe_path(clean_path):
            raise ValueError(f"访问被拒绝: 非法路径 {clean_path}")
        return clean_path