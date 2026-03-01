import os
from dotenv import load_dotenv, find_dotenv  # getting .env variables
from datetime import timedelta

# 获取项目根目录路径（多种方法尝试）
# 方法1: 从当前文件位置计算
BASE_DIR_1 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 方法2: 从工作目录
BASE_DIR_2 = os.getcwd()
# 方法3: 使用find_dotenv查找
env_file_found = find_dotenv('deekseek.env') or find_dotenv('.env')

# 优先查找 deekseek.env，然后才是 .env
# 先检查 deekseek.env，如果存在就只加载它
deekseek_env = None
env_file = None

# 优先查找 deekseek.env
possible_deekseek_paths = []
if BASE_DIR_1:
    possible_deekseek_paths.append(os.path.join(BASE_DIR_1, 'deekseek.env'))
if BASE_DIR_2 and BASE_DIR_2 != BASE_DIR_1:
    possible_deekseek_paths.append(os.path.join(BASE_DIR_2, 'deekseek.env'))
if env_file_found and 'deekseek.env' in env_file_found:
    possible_deekseek_paths.insert(0, env_file_found)

for path in possible_deekseek_paths:
    if os.path.exists(path):
        deekseek_env = path
        print(f"[Config] 找到 deekseek.env: {path}")
        break

# 如果找到了 deekseek.env，就只加载它
if deekseek_env:
    env_file = deekseek_env
else:
    # 否则尝试加载 .env
    possible_env_paths = []
    if BASE_DIR_1:
        possible_env_paths.append(os.path.join(BASE_DIR_1, '.env'))
    if BASE_DIR_2 and BASE_DIR_2 != BASE_DIR_1:
        possible_env_paths.append(os.path.join(BASE_DIR_2, '.env'))
    if env_file_found and '.env' in env_file_found and 'deekseek.env' not in env_file_found:
        possible_env_paths.insert(0, env_file_found)
    
    for path in possible_env_paths:
        if os.path.exists(path):
            env_file = path
            print(f"[Config] 找到 .env: {path}")
            break

if env_file:
    print(f"[Config] 加载环境变量文件: {env_file}")
    load_dotenv(env_file, override=True)  # override=True 确保覆盖现有环境变量
    
    # 验证 API Key 是否加载成功
    api_key = os.getenv('DEEPSEEK_API_KEY', '').strip()
    
    # 如果环境变量中没有，尝试直接从文件读取（特别是 deekseek.env）
    if not api_key and 'deekseek.env' in env_file:
        try:
            with open(env_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        if 'DEEPSEEK_API_KEY' in line:
                            # 处理各种格式：DEEPSEEK_API_KEY=xxx 或 DEEPSEEK_API_KEY = xxx
                            if '=' in line:
                                api_key = line.split('=', 1)[1].strip()
                                # 移除可能的引号
                                api_key = api_key.strip('"').strip("'")
                                # 设置到环境变量
                                os.environ['DEEPSEEK_API_KEY'] = api_key
                                print(f"[Config] ✓ 从文件直接读取 DEEPSEEK_API_KEY")
                                break
        except Exception as e:
            print(f"[Config] 读取文件失败: {e}")
    
    if api_key:
        print(f"[Config] ✓ DEEPSEEK_API_KEY 已加载 (长度: {len(api_key)}, 前10字符: {api_key[:10]}...)")
    else:
        print("[Config] ✗ 警告: DEEPSEEK_API_KEY 未找到")
        # 尝试直接读取文件内容用于调试
        try:
            with open(env_file, 'r', encoding='utf-8') as f:
                content = f.read()
                print(f"[Config] 文件内容预览: {repr(content[:200])}")
        except Exception as e:
            print(f"[Config] 读取文件失败: {e}")
else:
    print("[Config] ✗ 警告: 未找到 .env 或 deekseek.env 文件")
    print(f"[Config] 尝试的路径: {[p[1] for p in possible_paths]}")
    load_dotenv()  # 默认尝试加载 .env

class Config:
    SECRET_KEY = "myFlaskApp4Fun"  # needed for login with wtforms
    SQLALCHEMY_DATABASE_URI = 'sqlite:///admin.db' 
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    TEMPLATES_AUTO_RELOAD = True
    ABSOLUTE_PATH = os.path.dirname(__file__)
    RELATIVE_PATH = "static/Pictures_Users"
    BLOG_PICTURES_PATH = "static/Pictures_Posts"
    PROFILE_IMG_FOLDER = os.path.join(ABSOLUTE_PATH, RELATIVE_PATH)
    BLOG_IMG_FOLDER = os.path.join(ABSOLUTE_PATH, BLOG_PICTURES_PATH)
    STATIC_FOLDER = os.path.join(ABSOLUTE_PATH, "static")
    ALLOWED_IMG_EXTENSIONS = ['PNG', 'JPG', 'JPEG', 'png', 'jpg', 'jpeg']  # 支持大小写
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024

