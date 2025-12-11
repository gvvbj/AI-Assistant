class AppError(Exception):
    def __init__(self, message, details=None):
        self.message = message
        self.details = details or {}
        super().__init__(self.message)

class ToolError(AppError): pass
class SecurityError(AppError): pass
class ConfigError(AppError): pass

def safe_execute(error_msg="操作失败"):
    def decorator(func):
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                # Streamlit 的控制流异常直接抛出
                if type(e).__name__ in ["StopException", "RerunException"]: raise e
                print(f"[ERROR] {error_msg}: {e}")
                raise AppError(f"{error_msg}: {str(e)}") from e
        return wrapper
    return decorator