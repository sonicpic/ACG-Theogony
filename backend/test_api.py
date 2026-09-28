"""测试 DeepSeek API 连接"""
import os
from pathlib import Path

# 加载 .env
env_file = Path(__file__).parent.parent / ".env"
if env_file.exists():
    with open(env_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ[key.strip()] = value.strip()

from openai import OpenAI

print("测试 DeepSeek API 连接...")
print(f"API Key: {os.getenv('DEEPSEEK_API_KEY', '')[:20]}...")

client = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com",
)

try:
    print("\n发送测试请求...")
    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[{"role": "user", "content": "你好，请用一句话介绍亚瑟王"}],
        max_tokens=100,
        timeout=30.0,
    )
    
    result = response.choices[0].message.content
    print(f"\n✓ API 连接成功!")
    print(f"响应: {result}")
    
except Exception as e:
    print(f"\n✗ API 调用失败: {e}")
    print(f"错误类型: {type(e).__name__}")
