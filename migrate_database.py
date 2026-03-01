# -*- coding: utf-8 -*-
"""
数据库迁移脚本：添加新功能所需的字段和表
运行此脚本以添加：
1. blog_posts.summary 字段（AI生成的摘要）
2. blog_reposts 表（转发功能）
3. blog_messages 表（私信功能）
4. blog_stats.reposts_total 字段（转发统计）
"""
import sqlite3
import os
import sys
from app.config import Config

# 设置控制台输出编码（Windows 兼容）
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

def migrate_database():
    """执行数据库迁移"""
    # 获取数据库路径
    db_path = os.path.join(os.path.dirname(__file__), 'instance', 'admin.db')
    
    if not os.path.exists(db_path):
        print(f"错误：数据库文件不存在: {db_path}")
        print("请先运行应用程序以创建数据库。")
        return False
    
    conn = None
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        print("=" * 60)
        print("开始数据库迁移...")
        print("=" * 60)
        
        # 1. 检查并添加 blog_posts.summary 字段
        cursor.execute("PRAGMA table_info(blog_posts)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'summary' not in columns:
            print("\n[1/4] 添加 blog_posts.summary 字段...")
            cursor.execute("""
                ALTER TABLE blog_posts 
                ADD COLUMN summary TEXT
            """)
            print("    [OK] summary 字段添加成功")
        else:
            print("\n[1/4] blog_posts.summary 字段已存在，跳过")
        
        # 2. 检查并创建 blog_reposts 表
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='blog_reposts'
        """)
        if not cursor.fetchone():
            print("\n[2/4] 创建 blog_reposts 表...")
            cursor.execute("""
                CREATE TABLE blog_reposts (
                    id INTEGER NOT NULL PRIMARY KEY,
                    date_submitted DATETIME,
                    post_id INTEGER,
                    user_id INTEGER,
                    target_user_id INTEGER,
                    comment VARCHAR(500),
                    FOREIGN KEY(post_id) REFERENCES blog_posts (id),
                    FOREIGN KEY(user_id) REFERENCES blog_user (id),
                    FOREIGN KEY(target_user_id) REFERENCES blog_user (id)
                )
            """)
            print("    [OK] blog_reposts 表创建成功")
        else:
            # 检查是否需要添加 target_user_id 字段
            cursor.execute("PRAGMA table_info(blog_reposts)")
            repost_columns = [column[1] for column in cursor.fetchall()]
            
            if 'target_user_id' not in repost_columns:
                print("\n[2/4] blog_reposts 表已存在，添加 target_user_id 字段...")
                cursor.execute("""
                    ALTER TABLE blog_reposts 
                    ADD COLUMN target_user_id INTEGER
                """)
                # 添加外键约束（SQLite 不支持 ALTER TABLE ADD FOREIGN KEY，但字段已添加）
                print("    [OK] target_user_id 字段添加成功")
            else:
                print("\n[2/4] blog_reposts 表已存在且包含 target_user_id 字段，跳过")
        
        # 3. 检查并创建 blog_messages 表
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='blog_messages'
        """)
        if not cursor.fetchone():
            print("\n[3/4] 创建 blog_messages 表...")
            cursor.execute("""
                CREATE TABLE blog_messages (
                    id INTEGER NOT NULL PRIMARY KEY,
                    date_submitted DATETIME,
                    sender_id INTEGER,
                    receiver_id INTEGER,
                    content TEXT NOT NULL,
                    read VARCHAR(5),
                    FOREIGN KEY(sender_id) REFERENCES blog_user (id),
                    FOREIGN KEY(receiver_id) REFERENCES blog_user (id)
                )
            """)
            print("    [OK] blog_messages 表创建成功")
        else:
            print("\n[3/4] blog_messages 表已存在，跳过")
        
        # 4. 检查并添加 blog_stats.reposts_total 字段
        cursor.execute("PRAGMA table_info(blog_stats)")
        stats_columns = [column[1] for column in cursor.fetchall()]
        
        if 'reposts_total' not in stats_columns:
            print("\n[4/4] 添加 blog_stats.reposts_total 字段...")
            cursor.execute("""
                ALTER TABLE blog_stats 
                ADD COLUMN reposts_total INTEGER DEFAULT 0
            """)
            # 为现有记录设置默认值
            cursor.execute("""
                UPDATE blog_stats 
                SET reposts_total = 0 
                WHERE reposts_total IS NULL
            """)
            print("    [OK] reposts_total 字段添加成功")
        else:
            print("\n[4/4] blog_stats.reposts_total 字段已存在，跳过")
        
        # 提交更改
        conn.commit()
        
        print("\n" + "=" * 60)
        print("[OK] 数据库迁移完成！")
        print("=" * 60)
        
        conn.close()
        return True
        
    except sqlite3.Error as e:
        print(f"\n[ERROR] 数据库错误: {e}")
        if conn:
            conn.rollback()
            conn.close()
        return False
    except Exception as e:
        print(f"\n[ERROR] 发生错误: {e}")
        import traceback
        traceback.print_exc()
        if conn:
            conn.close()
        return False

if __name__ == "__main__":
    print("\n数据库迁移工具")
    print("此脚本将添加新功能所需的数据库字段和表\n")
    
    if migrate_database():
        print("\n迁移成功！您现在可以正常使用新功能了。")
        print("\n提示：")
        print("1. 如需使用 DeepSeek AI 摘要功能，请在 .env 文件中配置 DEEPSEEK_API_KEY")
        print("2. 重新启动应用程序以应用更改")
    else:
        print("\n迁移失败！请检查错误信息。")

