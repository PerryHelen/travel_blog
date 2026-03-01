"""
DeepSeek API 集成服务
用于生成文章摘要
"""
import requests
import os
from flask import current_app

def generate_summary(title, body, intro=""):
    """
    使用 DeepSeek API 生成文章摘要
    
    Args:
        title: 文章标题
        body: 文章正文
        intro: 文章简介（可选）
    
    Returns:
        str: 生成的摘要，如果失败返回 None
    """
    # 从环境变量或配置中获取 API Key
    api_key = os.getenv('DEEPSEEK_API_KEY', '').strip()
    
    # 如果环境变量中没有，尝试直接从文件读取
    if not api_key:
        try:
            # 尝试多个可能的路径
            possible_files = ['deekseek.env', '.env', 
                            os.path.join(os.path.dirname(os.path.dirname(__file__)), 'deekseek.env'),
                            os.path.join(os.getcwd(), 'deekseek.env')]
            
            for env_file in possible_files:
                if os.path.exists(env_file):
                    print(f"[DeepSeek] 尝试从文件读取: {env_file}")
                    with open(env_file, 'r', encoding='utf-8') as f:
                        for line in f:
                            line = line.strip()
                            if line.startswith('DEEPSEEK_API_KEY='):
                                api_key = line.split('=', 1)[1].strip()
                                # 移除可能的引号
                                api_key = api_key.strip('"').strip("'")
                                print(f"[DeepSeek] 从文件读取到 API Key (长度: {len(api_key)})")
                                break
                    if api_key:
                        break
        except Exception as e:
            print(f"[DeepSeek] 读取文件时出错: {e}")
    
    # 调试信息
    print(f"[DeepSeek] 尝试获取 API Key，结果: {'已找到' if api_key else '未找到'}")
    if api_key:
        print(f"[DeepSeek] API Key 长度: {len(api_key)}, 前10个字符: {api_key[:10]}...")
    
    if not api_key:
        # 如果没有配置 API Key，返回 None
        print("[DeepSeek] ✗ API Key 未配置，跳过摘要生成")
        print("[DeepSeek] 提示: 请检查 deekseek.env 或 .env 文件是否存在且包含 DEEPSEEK_API_KEY")
        print(f"[DeepSeek] 当前工作目录: {os.getcwd()}")
        return None
    
    # 构建文章内容
    content = f"标题：{title}\n\n"
    if intro:
        content += f"简介：{intro}\n\n"
    content += f"正文：{body[:2000]}"  # 限制长度避免超出token限制
    
    # 构建提示词
    prompt = f"""请为以下文章生成一个简洁的中文摘要，要求：
1. 摘要长度控制在100-200字
2. 突出文章的核心观点和主要内容
3. 语言简洁流畅

文章内容：
{content}

请直接输出摘要，不要包含其他说明文字。"""
    
    try:
        # 调用 DeepSeek API
        url = "https://api.deepseek.com/v1/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
        data = {
            "model": "deepseek-chat",
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "temperature": 0.7,
            "max_tokens": 300
        }
        
        response = requests.post(url, json=data, headers=headers, timeout=30)
        response.raise_for_status()
        
        result = response.json()
        summary = result.get('choices', [{}])[0].get('message', {}).get('content', '').strip()
        
        if summary:
            return summary
        else:
            print("[DeepSeek] API 返回空摘要")
            return None
            
    except requests.exceptions.RequestException as e:
        print(f"[DeepSeek] API 请求失败: {str(e)}")
        return None
    except Exception as e:
        print(f"[DeepSeek] 生成摘要时出错: {str(e)}")
        return None

