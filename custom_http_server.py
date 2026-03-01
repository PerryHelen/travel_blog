"""
自定义HTTP服务器 - 基于Socket编程实现TCP连接和HTTP通信
本模块实现了从底层TCP Socket到HTTP协议解析的完整流程
"""

import socket
import threading
import time
from datetime import datetime
from urllib.parse import parse_qs, urlparse, quote, unquote
import io
import sys
from collections import defaultdict

class HTTPRequest:
    """HTTP请求解析类"""
    
    def __init__(self, raw_request):
        self.method = None
        self.path = None
        self.query_params = {}
        self.headers = {}
        self.body = b''
        self.content_length = 0
        self._parse(raw_request)
    
    def _parse(self, raw_request):
        """解析HTTP请求"""
        if not raw_request:
            return
        
        # 分离请求行、请求头和请求体
        parts = raw_request.split(b'\r\n\r\n', 1)
        header_part = parts[0]
        body_part = parts[1] if len(parts) > 1 else b''
        
        # 解析请求行和请求头
        lines = header_part.split(b'\r\n')
        if not lines:
            return
        
        # 解析请求行: METHOD PATH HTTP/VERSION
        request_line = lines[0].decode('utf-8', errors='ignore')
        request_parts = request_line.split(' ', 2)
        if len(request_parts) >= 2:
            self.method = request_parts[0]
            path_with_query = request_parts[1]
            
            # 解析路径和查询参数
            parsed_url = urlparse(path_with_query)
            self.path = parsed_url.path
            if parsed_url.query:
                self.query_params = parse_qs(parsed_url.query)
        
        # 解析请求头
        for line in lines[1:]:
            if b':' in line:
                key, value = line.split(b':', 1)
                key = key.strip().decode('utf-8', errors='ignore')
                value = value.strip().decode('utf-8', errors='ignore')
                self.headers[key.lower()] = value
        
        # 获取Content-Length
        if 'content-length' in self.headers:
            try:
                self.content_length = int(self.headers['content-length'])
            except ValueError:
                self.content_length = 0
        
        # 解析请求体
        if body_part:
            self.body = body_part[:self.content_length] if self.content_length > 0 else body_part


class HTTPResponse:
    """HTTP响应生成类"""
    
    def __init__(self, status_code=200, status_text="OK", headers=None, body=b''):
        self.status_code = status_code
        self.status_text = status_text
        self.headers = headers or {}
        self.body = body if isinstance(body, bytes) else body.encode('utf-8')
    
    def to_bytes(self):
        """将HTTP响应转换为字节流"""
        # 状态行
        status_line = f"HTTP/1.1 {self.status_code} {self.status_text}\r\n"
        
        # 添加默认头部
        if 'Content-Type' not in self.headers:
            self.headers['Content-Type'] = 'text/html; charset=utf-8'
        if 'Content-Length' not in self.headers:
            self.headers['Content-Length'] = str(len(self.body))
        self.headers['Connection'] = 'close'
        self.headers['Server'] = 'Custom-HTTP-Server/1.0'
        
        # 构建响应头
        # HTTP协议要求响应头必须使用latin-1编码
        header_lines = []
        for k, v in self.headers.items():
            # 确保键和值都是字符串
            key = str(k) if not isinstance(k, str) else k
            value = str(v) if not isinstance(v, str) else v
            
            # 确保可以编码为latin-1（HTTP头的要求）
            try:
                key.encode('latin-1')
                value.encode('latin-1')
                header_lines.append(f"{key}: {value}")
            except UnicodeEncodeError:
                # 如果包含非latin-1字符，尝试使用ASCII替换
                try:
                    safe_key = key.encode('ascii', errors='replace').decode('ascii')
                    safe_value = value.encode('ascii', errors='replace').decode('ascii')
                    header_lines.append(f"{safe_key}: {safe_value}")
                except:
                    # 如果还是失败，跳过这个头
                    pass
        
        headers_str = '\r\n'.join(header_lines)
        
        # 完整的HTTP响应
        # 响应头必须使用latin-1编码，响应体可以使用UTF-8
        response_header = f"{status_line}{headers_str}\r\n\r\n"
        return response_header.encode('latin-1') + self.body


class NetworkMonitor:
    """网络性能监测类 - 实时显示延迟、吞吐量、RTT等参数"""
    
    def __init__(self):
        self.request_count = 0
        self.total_bytes_sent = 0
        self.total_bytes_received = 0
        self.request_times = []
        self.rtt_times = []  # Round Trip Time
        self.start_time = time.time()
        self.lock = threading.Lock()
    
    def record_request(self, bytes_received, bytes_sent, rtt):
        """记录请求统计信息"""
        with self.lock:
            self.request_count += 1
            self.total_bytes_received += bytes_received
            self.total_bytes_sent += bytes_sent
            self.rtt_times.append(rtt)
            self.request_times.append(time.time())
    
    def get_stats(self):
        """获取统计信息"""
        with self.lock:
            elapsed = time.time() - self.start_time
            if elapsed == 0:
                return {}
            
            # 计算平均RTT
            avg_rtt = sum(self.rtt_times) / len(self.rtt_times) if self.rtt_times else 0
            
            # 计算吞吐量 (bytes/second)
            throughput_sent = self.total_bytes_sent / elapsed if elapsed > 0 else 0
            throughput_received = self.total_bytes_received / elapsed if elapsed > 0 else 0
            
            # 计算请求速率
            requests_per_sec = self.request_count / elapsed if elapsed > 0 else 0
            
            return {
                'total_requests': self.request_count,
                'total_bytes_sent': self.total_bytes_sent,
                'total_bytes_received': self.total_bytes_received,
                'avg_rtt_ms': avg_rtt * 1000,  # 转换为毫秒
                'throughput_sent_kbps': throughput_sent * 8 / 1024,  # 转换为Kbps
                'throughput_received_kbps': throughput_received * 8 / 1024,
                'requests_per_sec': requests_per_sec,
                'uptime_seconds': elapsed
            }


# 全局变量：存储服务器实例，以便Flask应用访问
_global_server_instance = None

class CustomHTTPServer:
    """
    自定义HTTP服务器 - 基于Socket编程
    实现TCP连接和HTTP协议解析
    """
    
    def __init__(self, host='127.0.0.1', port=5000, wsgi_app=None):
        global _global_server_instance
        self.host = host
        self.port = port
        self.wsgi_app = wsgi_app
        self.socket = None
        self.running = False
        self.monitor = NetworkMonitor()
        self.request_handlers = {}
        # 保存全局实例
        _global_server_instance = self
    
    def start(self):
        """启动HTTP服务器"""
        # 创建TCP Socket
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        try:
            # 绑定地址和端口
            self.socket.bind((self.host, self.port))
            # 开始监听，最大连接数为128
            self.socket.listen(128)
            self.running = True
            
            print(f"[TCP Server] 服务器启动成功")
            print(f"[TCP Server] 监听地址: {self.host}:{self.port}")
            print(f"[TCP Server] 使用Socket编程实现TCP连接")
            print(f"[TCP Server] HTTP协议解析已启用")
            print("-" * 60)
            
            # 启动监控线程
            monitor_thread = threading.Thread(target=self._monitor_stats, daemon=True)
            monitor_thread.start()
            
            # 主循环：接受连接
            while self.running:
                try:
                    # 设置socket为非阻塞模式，以便可以检查running状态
                    self.socket.settimeout(1.0)  # 1秒超时，用于检查running状态
                    try:
                        # 接受TCP连接
                        client_socket, client_address = self.socket.accept()
                        # 减少日志输出，只在调试时显示
                        # print(f"[TCP Connection] 新连接来自: {client_address[0]}:{client_address[1]}")
                        
                        # 为每个连接创建新线程处理
                        client_thread = threading.Thread(
                            target=self._handle_client,
                            args=(client_socket, client_address),
                            daemon=True
                        )
                        client_thread.start()
                    except socket.timeout:
                        # 超时是正常的，继续循环检查running状态
                        continue
                except OSError as e:
                    # 如果服务器正在运行，检查是否是socket关闭导致的错误
                    if self.running:
                        # 检查是否是socket关闭导致的错误（这是正常的停止流程）
                        # Windows上错误码10038表示"在一个非套接字上尝试了一个操作"
                        # 这通常发生在socket被关闭后
                        error_code = getattr(e, 'winerror', None) or getattr(e, 'errno', None)
                        if error_code == 10038 or error_code == 9:  # Windows 10038 或 Linux EBADF
                            # Socket已关闭，正常退出循环
                            break
                        try:
                            if self.socket.fileno() == -1:
                                # Socket已关闭，正常退出循环
                                break
                        except:
                            # Socket已关闭，正常退出循环
                            break
                        # 其他OSError异常，重新抛出
                        raise
                    else:
                        # 服务器已停止，正常退出循环
                        break
        except Exception as e:
            print(f"[Error] 服务器启动失败: {e}")
            import traceback
            traceback.print_exc()
            self.running = False
            if self.socket:
                try:
                    self.socket.close()
                except:
                    pass
            raise
    
    def _handle_client(self, client_socket, client_address):
        """处理客户端连接"""
        request_start_time = time.time()
        bytes_received = 0
        bytes_sent = 0
        
        try:
            # 接收HTTP请求数据
            request_data = b''
            client_socket.settimeout(30)  # 30秒超时
            
            # 读取请求数据
            while True:
                chunk = client_socket.recv(4096)
                if not chunk:
                    break
                request_data += chunk
                bytes_received += len(chunk)
                
                # 检查是否接收完整（简单检查：包含\r\n\r\n表示头部结束）
                if b'\r\n\r\n' in request_data:
                    # 如果有Content-Length，继续读取body
                    if b'Content-Length:' in request_data:
                        try:
                            # 提取Content-Length值
                            header_end = request_data.find(b'\r\n\r\n')
                            headers = request_data[:header_end].decode('utf-8', errors='ignore')
                            for line in headers.split('\r\n'):
                                if line.lower().startswith('content-length:'):
                                    content_length = int(line.split(':')[1].strip())
                                    body_start = header_end + 4
                                    body_received = len(request_data) - body_start
                                    if body_received < content_length:
                                        # 继续接收body
                                        remaining = content_length - body_received
                                        while remaining > 0:
                                            chunk = client_socket.recv(min(remaining, 4096))
                                            if not chunk:
                                                break
                                            request_data += chunk
                                            bytes_received += len(chunk)
                                            remaining -= len(chunk)
                                    break
                        except (ValueError, IndexError):
                            pass
                    break
            
            if not request_data:
                return
            
            # 解析HTTP请求
            request = HTTPRequest(request_data)
            
            # 减少日志输出，只在调试时显示
            # print(f"[HTTP Request] {request.method} {request.path} from {client_address[0]}")
            
            # 处理请求并生成响应
            response = self._process_request(request, client_address)
            
            # 发送HTTP响应
            response_bytes = response.to_bytes()
            client_socket.sendall(response_bytes)
            bytes_sent = len(response_bytes)
            
            # 计算RTT (Round Trip Time)
            rtt = time.time() - request_start_time
            
            # 记录统计信息
            self.monitor.record_request(bytes_received, bytes_sent, rtt)
            
        except socket.timeout:
            print(f"[Timeout] 客户端 {client_address} 连接超时")
        except Exception as e:
            print(f"[Error] 处理客户端 {client_address} 请求时出错: {e}")
            try:
                error_response = HTTPResponse(
                    status_code=500,
                    status_text="Internal Server Error",
                    body="<h1>500 Internal Server Error</h1>"
                )
                client_socket.sendall(error_response.to_bytes())
            except:
                pass
        finally:
            # 关闭TCP连接
            client_socket.close()
            # 减少日志输出
            # print(f"[TCP Connection] 连接已关闭: {client_address[0]}:{client_address[1]}")
    
    def _process_request(self, request, client_address):
        """处理HTTP请求并生成响应"""
        # 如果有WSGI应用，使用WSGI接口处理
        if self.wsgi_app:
            return self._handle_wsgi_request(request, client_address)
        
        # 否则返回默认响应
        return HTTPResponse(
            status_code=200,
            status_text="OK",
            body="<h1>Custom HTTP Server</h1><p>TCP Socket based HTTP server is running.</p>"
        )
    
    def _handle_wsgi_request(self, request, client_address):
        """通过WSGI接口处理请求"""
        # 创建WSGI环境变量
        # 处理查询字符串，确保中文字符正确编码
        query_string_parts = []
        for k, v in request.query_params.items():
            # URL编码键和值
            encoded_key = quote(str(k), safe='')
            if isinstance(v, list) and len(v) > 0:
                encoded_value = quote(str(v[0]), safe='')
            else:
                encoded_value = quote(str(v), safe='')
            query_string_parts.append(f"{encoded_key}={encoded_value}")
        query_string = '&'.join(query_string_parts)
        
        environ = {
            'REQUEST_METHOD': request.method,
            'PATH_INFO': request.path,
            'QUERY_STRING': query_string,
            'SERVER_NAME': self.host,
            'SERVER_PORT': str(self.port),
            'SERVER_PROTOCOL': 'HTTP/1.1',
            'wsgi.version': (1, 0),
            'wsgi.url_scheme': 'http',
            'wsgi.input': io.BytesIO(request.body),
            'wsgi.errors': sys.stderr,
            'wsgi.multithread': True,
            'wsgi.multiprocess': False,
            'wsgi.run_once': False,
            'REMOTE_ADDR': client_address[0],
            'REMOTE_PORT': str(client_address[1]),
        }
        
        # 添加Content-Type和Content-Length（对POST请求很重要）
        if 'content-type' in request.headers:
            environ['CONTENT_TYPE'] = request.headers['content-type']
        if 'content-length' in request.headers:
            environ['CONTENT_LENGTH'] = request.headers['content-length']
        
        # 添加HTTP请求头到环境变量
        for key, value in request.headers.items():
            key = key.replace('-', '_').upper()
            # 跳过已经单独处理的Content-Type和Content-Length
            if key not in ['CONTENT_TYPE', 'CONTENT_LENGTH']:
                environ[f'HTTP_{key}'] = value
        
        # 调用WSGI应用
        response_body = []
        status_code = 200
        status_text = "OK"
        headers = {}
        
        def start_response(status, response_headers):
            nonlocal status_code, status_text, headers
            # 解析状态码和状态文本
            parts = status.split(' ', 1)
            status_code = int(parts[0])
            status_text = parts[1] if len(parts) > 1 else "OK"
            # 确保响应头值都是字符串，并且可以正确编码为latin-1
            # HTTP协议要求响应头必须使用latin-1编码
            headers = {}
            for key, value in response_headers:
                # 确保值是字符串类型
                if not isinstance(value, str):
                    value = str(value)
                # HTTP响应头必须使用latin-1编码
                # 如果值包含非latin-1字符，需要进行编码处理
                try:
                    # 尝试编码为latin-1，如果成功则直接使用
                    value.encode('latin-1')
                    headers[key] = value
                except UnicodeEncodeError:
                    # 如果包含非latin-1字符，使用RFC 2047编码（MIME编码）
                    # 或者使用URL编码，但更安全的方式是使用ASCII替换
                    # 对于某些头（如Content-Disposition），可以使用RFC 2231编码
                    # 这里我们使用一个更安全的方法：将非ASCII字符替换为ASCII等价字符
                    try:
                        # 尝试使用ASCII编码，替换无法编码的字符
                        safe_value = value.encode('ascii', errors='replace').decode('ascii')
                        headers[key] = safe_value
                    except:
                        # 如果还是失败，使用空字符串或默认值
                        headers[key] = ''
            return response_body.append
        
        try:
            # 调用WSGI应用
            result = self.wsgi_app(environ, start_response)
            
            # 收集响应体
            for chunk in result:
                if isinstance(chunk, bytes):
                    response_body.append(chunk)
                else:
                    response_body.append(chunk.encode('utf-8'))
            
            # 如果有close方法，调用它
            if hasattr(result, 'close'):
                result.close()
            
            # 构建响应
            body = b''.join(response_body)
            return HTTPResponse(
                status_code=status_code,
                status_text=status_text,
                headers=headers,
                body=body
            )
        except Exception as e:
            print(f"[WSGI Error] 处理WSGI请求时出错: {e}")
            return HTTPResponse(
                status_code=500,
                status_text="Internal Server Error",
                body=f"<h1>500 Internal Server Error</h1><p>{str(e)}</p>"
            )
    
    def _monitor_stats(self):
        """监控线程：定期输出网络性能统计（可选，默认关闭以减少输出）"""
        while self.running:
            time.sleep(30)  # 改为每30秒输出一次，减少输出频率
            if self.running and self.monitor.request_count > 0:  # 只在有请求时输出
                stats = self.monitor.get_stats()
                if stats and stats.get('total_requests', 0) > 0:
                    print("\n[网络性能监测] 总请求数: {}, 平均RTT: {:.2f}ms, 请求速率: {:.2f}req/s".format(
                        stats['total_requests'], 
                        stats['avg_rtt_ms'], 
                        stats['requests_per_sec']
                    ))
    
    def stop(self):
        """停止服务器"""
        global _global_server_instance
        self.running = False
        if self.socket:
            try:
                self.socket.close()
                print("[TCP Server] 服务器已停止")
            except:
                pass
        _global_server_instance = None
    
    @staticmethod
    def get_instance():
        """获取全局服务器实例"""
        return _global_server_instance

