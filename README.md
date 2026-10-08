# local_ollama_harness

一个运行在本地的命令行代码助手：通过本地 Ollama 模型，在终端里用自然语言完成 Python 文件的创建、查看、修改与运行。

## 环境要求

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- [Ollama](https://ollama.com) 已安装并在运行
- 本地已具备模型 `qwen2.5-coder-3b:latest`（可用 `ollama list` 确认）

## 安装

```bash
git clone https://github.com/LinuxLinking/local_ollama_harness.git
cd local_ollama_harness
uv sync
```

## 运行

```bash
uv run python main.py
```

启动后出现 `>>>` 提示符即可输入任务，例如：

- `写个 fizzbuzz 存到 fizz.py 然后跑一下`
- `sandbox 里有个 broken.py 跑不通，帮我修好并验证`

任务结束后会打印 `=== Final Answer ===`。

## REPL 命令

| 命令 | 作用 |
|---|---|
| `/exit`、`/quit` | 退出程序 |
| `/reset` | 清空当前对话历史，重新开始 |
| `/quiet` | 切换输出详略：每步过程 / 仅最终答案 |
| `/tools` | 列出可用工具及参数格式 |

## 文件操作范围

程序对文件的读写和执行都限定在项目内的 `sandbox/` 目录中，目录之外的路径会被拒绝。仓库自带两个示例文件：

- `sandbox/fizz.py`
- `sandbox/broken.py`

## 模型与服务地址

默认连接本机 Ollama 服务（`http://localhost:11434`），默认模型为 `qwen2.5-coder-3b:latest`。如需修改，调整 `pypilot/config.py` 中的 `OLLAMA_BASE_URL` 与 `MODEL_NAME`。

## Windows 终端中文显示

若终端输出中文出现乱码，可在启动前设置：

```bat
set PYTHONIOENCODING=utf-8
uv run python main.py
```
