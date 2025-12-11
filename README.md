# AI Assistant Pro (Local Agent Framework)

🤖 一个基于 Streamlit 的现代化 AI 智能助手，集成了 RAG（知识库）、MCP（模型上下文协议）与 Docker 代码沙箱。

> **Note / 说明**: 
> This is a personal learning project exploring the integration of LLMs with local tools. 
> 这是一个探索 LLM 与本地工具集成的个人学习项目，适合作为 Python/AI 爱好者的参考 Demo。

## ✨ Features (核心功能)

- **🧠 Multi-Model Support**: 支持 Ollama (本地) 和 OpenAI API (云端) 混合调用。
- **🔄 Plan-and-Solve Agent**: 内置 ReAct 与规划模式，支持复杂任务拆解与执行。
- **🔌 MCP Integration**: 支持 [Model Context Protocol](https://modelcontextprotocol.io/)，可无缝扩展外部工具（如 SQLite, Google Maps 等）。
- **🛡️ Docker Sandbox**: Python 代码解释器运行在 Docker 容器中，安全隔离，支持文件生成与绘图。
- **📚 RAG Knowledge Base**: 支持 PDF/Excel/Txt 等多格式文档索引与检索。
- **🔍 Web Search**: 集成联网搜索能力。

## 🛠️ Installation (安装指南)

### Prerequisites (前置要求)
- Python 3.10+
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (用于代码沙箱)
- [Ollama](https://ollama.com/) (可选，用于本地模型)
- Node.js (可选，用于部分 MCP 服务)
- uvx(可选，用于部分 MCP 服务)

### Setup (配置)

1. Clone the repository:
   ```bash
   
   cd AI-Assistant-Pro
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Build the Docker Sandbox (Required for Code Interpreter):
   (构建 Docker 沙箱环境，代码解释器功能必选)
   ```bash
   docker build -t ai-sandbox:latest .
   ```
4. 解压models里面压缩包

5. Run the application:
   ```bash
   streamlit run app.py
   ```

## 🚀 Usage (使用说明)

1. **Config**: 在侧边栏 "⚙️ 设置" 中配置你的 API Key 或 Ollama 地址。
2. **Tools**: 在 "🛠️ 能力扩展" 中开启需要的工具（如 Docker 解释器、MCP 服务）。
3. **Chat**: 在对话框中直接输入任务，例如："帮我读取 data.xlsx 并画一个饼图"。

## 📝 Disclaimer (免责声明)

此项目主要用于学习与演示。虽然包含加密与沙箱机制，但在生产环境使用前请进行更严格的安全审计。

---

*Built with ❤️ by a Python Learner & AI*
