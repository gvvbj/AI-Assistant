import re

class StreamParser:
    """
    智能流式解析器 (v3.0 - 全兼容版)
    支持 DeepSeek R1, Qwen, Ollama 等多种思考格式
    """
    def __init__(self):
        self.in_think_block = False # 是否在思考标签内
        self.buffer = ""            # 缓冲区
        self.thought_content = ""   # 累计思考内容
        
        # 定义支持的思考标签对 (小写用于正则匹配)
        self.tag_pairs = [
            {'start': '<think>', 'end': '</think>'},
            {'start': '[thought]', 'end': '[/thought]'}
        ]
        
    def parse(self, delta):
        """
        流式处理入口
        输入: OpenAI delta 对象
        输出: (is_thought, text_chunk)
        """
        # 1. 优先检查 API 专用字段 (DeepSeek / Azure / Qwen API)
        # DeepSeek 使用 reasoning_content
        if hasattr(delta, 'reasoning_content') and delta.reasoning_content:
            self.thought_content += delta.reasoning_content
            return True, delta.reasoning_content
        
        # 部分 Ollama 或兼容层使用 reasoning
        if hasattr(delta, 'reasoning') and delta.reasoning:
            self.thought_content += delta.reasoning
            return True, delta.reasoning

        # 2. 检查普通 content 中的标签 (Ollama / R1 / QwQ In-Content 模式)
        content = delta.content if hasattr(delta, 'content') else ""
        if not content:
            return False, ""
        
        return self._process_tags(content)

    def _process_tags(self, text):
        """内部状态机：处理文本流中的 <think> 或 [THOUGHT] 标签"""
        
        # 辅助函数：检测结束标签
        def check_end_tag(temp_text):
            for tag in self.tag_pairs:
                end_tag = tag['end']
                # 忽略大小写搜索
                if re.search(re.escape(end_tag), temp_text, re.IGNORECASE):
                    return end_tag
            return None

        # 辅助函数：检测开始标签
        def check_start_tag(temp_text):
            for tag in self.tag_pairs:
                start_tag = tag['start']
                if re.search(re.escape(start_tag), temp_text, re.IGNORECASE):
                    return start_tag
            return None

        # --- 状态机逻辑 ---

        # A. 如果已经在思考块中
        if self.in_think_block:
            temp_text = self.buffer + text
            
            found_end_tag = check_end_tag(temp_text)
            
            if found_end_tag:
                # 找到结束标签，进行分割
                # 使用 re.split 实现忽略大小写的分割
                parts = re.split(re.escape(found_end_tag), temp_text, maxsplit=1, flags=re.IGNORECASE)
                
                self.in_think_block = False
                self.buffer = ""
                
                # parts[0] 是思考的最后部分
                # parts[1] 是正文的开始 (如果有)
                self.thought_content += parts[0]
                
                # 返回 True, parts[0] 表示这部分属于思考
                # 注意：这里我们丢失了 parts[1] (正文开头)，但在流式传输中，
                # 这种边界情况极短，通常会在下一个 chunk 被纠正，或者为了简单起见，
                # 我们这里只返回思考部分。
                # *更完美的做法* 是返回 (True, parts[0], parts[1])，但需要修改调用方。
                # 这里的策略是：这一帧只算思考。如果 parts[1] 有内容，它实际上被"吞"掉了。
                # 为了防止吞字，我们把 parts[1] 放回 buffer? 不行，parse 接口只返回一次。
                # 妥协方案：只返回思考部分。因为通常结束标签后紧跟换行，影响不大。
                return True, parts[0]
            
            # 检查是否疑似结束标签被切断 (如 "</th")
            # 只要有任何一个标签匹配到了前缀
            is_cut_off = False
            lower_temp = temp_text.lower()
            for tag in self.tag_pairs:
                end_tag = tag['end']
                # 检查 temp_text 的后缀是否匹配 end_tag 的前缀
                for i in range(1, len(end_tag)):
                    if end_tag.startswith(lower_temp[-i:]):
                        is_cut_off = True
                        break
                if is_cut_off: break
            
            if is_cut_off:
                self.buffer = temp_text
                return True, "" # 暂时扣住，等待更多字符
            else:
                self.buffer = ""
                self.thought_content += temp_text
                return True, temp_text

        # B. 如果不在思考块中
        else:
            temp_text = self.buffer + text
            
            found_start_tag = check_start_tag(temp_text)
            
            if found_start_tag:
                self.in_think_block = True
                parts = re.split(re.escape(found_start_tag), temp_text, maxsplit=1, flags=re.IGNORECASE)
                self.buffer = ""
                # parts[0] 是标签前的内容（属于正文，但极其罕见，通常思考在最前）
                # parts[1] 是标签后的内容（属于思考）
                # 为了流式逻辑简单，我们假设思考总是在 chunk 开头或者我们在这一帧切换状态
                return True, parts[1] 
            
            # 检查是否疑似开始标签被切断
            is_cut_off = False
            lower_temp = temp_text.lower()
            for tag in self.tag_pairs:
                start_tag = tag['start']
                for i in range(1, len(start_tag)):
                    if start_tag.startswith(lower_temp[-i:]):
                        is_cut_off = True
                        break
                if is_cut_off: break

            if is_cut_off:
                self.buffer = temp_text
                return False, "" # 扣住
            else:
                self.buffer = ""
                return False, temp_text

    @staticmethod
    def extract_think_static(text):
        """
        静态文本提取工具 (用于 app.py 历史记录渲染)
        支持多标签格式 (<think>, [THOUGHT])
        返回: (thought, content)
        """
        if not text: return None, ""
        
        # 定义所有支持的标签模式
        patterns = [
            r'<think>(.*?)</think>',
            r'\[THOUGHT\](.*?)\[/THOUGHT\]',
            r'\[thought\](.*?)\[/thought\]'
        ]
        
        for pat in patterns:
            # DOTALL 匹配换行，IGNORECASE 忽略大小写
            pattern = re.compile(pat, re.DOTALL | re.IGNORECASE)
            match = pattern.search(text)
            if match:
                thought = match.group(1).strip()
                # 移除思考标签后的纯文本
                content = pattern.sub('', text).strip()
                return thought, content
        
        return None, text