from app import create_app
from app.extensions import db
from custom_http_server import CustomHTTPServer
import os
from dotenv import load_dotenv

# 在应用启动时确保加载环境变量
# 优先加载 deekseek.env，然后才是 .env
current_dir = os.getcwd()
script_dir = os.path.dirname(os.path.abspath(__file__))

# 优先查找 deekseek.env
env_files = [
    os.path.join(current_dir, 'deekseek.env'),
    os.path.join(script_dir, 'deekseek.env'),
    os.path.join(current_dir, '.env'),
    os.path.join(script_dir, '.env'),
]

loaded = False
for env_file in env_files:
    if os.path.exists(env_file):
        print(f"[Run] 从 {env_file} 加载环境变量")
        load_dotenv(env_file, override=True)
        api_key = os.getenv('DEEPSEEK_API_KEY', '').strip()
        if api_key:
            print(f"[Run] ✓ DEEPSEEK_API_KEY 已加载 (长度: {len(api_key)}, 前10字符: {api_key[:10]}...)")
            loaded = True
        elif 'deekseek.env' in env_file:
            # 如果加载了 deekseek.env 但没有找到 API Key，尝试直接读取
            try:
                with open(env_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith('DEEPSEEK_API_KEY='):
                            api_key = line.split('=', 1)[1].strip().strip('"').strip("'")
                            os.environ['DEEPSEEK_API_KEY'] = api_key
                            print(f"[Run] ✓ 从文件直接读取 DEEPSEEK_API_KEY (长度: {len(api_key)})")
                            loaded = True
                            break
            except Exception as e:
                print(f"[Run] 读取文件失败: {e}")
        
        # 如果找到了 deekseek.env 就停止，即使没有 API Key
        if 'deekseek.env' in env_file:
            break

app = create_app()

# 添加网络性能监测面板路由
@app.route('/network_monitor')
def network_monitor():
    """网络性能监测面板 - 实时显示延迟、吞吐量、RTT等参数"""
    from flask import render_template
    from flask_login import current_user
    return render_template('website/network_monitor.html', logged_in=current_user.is_authenticated)

@app.route('/api/network_stats')
def api_network_stats():
    """API端点：返回网络性能统计数据（JSON格式）"""
    from flask import jsonify
    from custom_http_server import CustomHTTPServer
    
    server = CustomHTTPServer.get_instance()
    if server and server.monitor:
        stats = server.monitor.get_stats()
        return jsonify(stats)
    else:
        return jsonify({
            'total_requests': 0,
            'avg_rtt_ms': 0,
            'throughput_sent_kbps': 0,
            'throughput_received_kbps': 0,
            'requests_per_sec': 0,
            'total_bytes_sent': 0,
            'total_bytes_received': 0,
            'uptime_seconds': 0
        })
    
if __name__ == '__main__':
    # 使用自定义HTTP服务器（基于Socket编程）
    print("=" * 60)
    print("启动基于TCP Socket和HTTP协议的博客系统")
    print("=" * 60)
    
    
    # 创建自定义HTTP服务器实例
    server = CustomHTTPServer(host='127.0.0.1', port=5000, wsgi_app=app.wsgi_app)
    
    try:
        # 启动服务器（这是阻塞调用，会一直运行直到停止）
        server.start()
    except KeyboardInterrupt:
        print("\n[Server] 收到停止信号，正在关闭服务器...")
        server.stop()
        print("[Server] 服务器已停止")
    except Exception as e:
        print(f"\n[Server] 服务器运行出错: {e}")
        import traceback
        traceback.print_exc()
        server.stop()