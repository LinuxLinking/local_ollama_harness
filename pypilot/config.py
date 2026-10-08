"""配置项。"""
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

SANDBOX_DIR = PROJECT_ROOT / "sandbox"
SANDBOX_DIR.mkdir(exist_ok=True)

OLLAMA_BASE_URL = "http://localhost:11434"
MODEL_NAME = "qwen2.5-coder-3b:latest"

TEMPERATURE = 0.7
NUM_CTX = 8192
STOP_SEQUENCES = ["<|im_start|>", "<|im_end|>", "<|endoftext|>", "Observation:"]

MAX_ITERATIONS = 8
RUN_TIMEOUT = 30

RECURSION_LIMIT = 4 * MAX_ITERATIONS + 10
RESERVED_COMPLETION_TOKENS = 3500
CJK_CHARS_PER_TOKEN = 1.6
INCLUDE_AI_CONTEXT = False
ENABLE_SUMMARY = False
