from flask import Blueprint, render_template, request, jsonify, make_response, redirect, flash, url_for
from app.extensions import db
from app.models.themes import Blog_Theme
from app.models.posts import Blog_Posts
from app.models.user import Blog_User
from app.models.likes import Blog_Likes
from app.models.bookmarks import Blog_Bookmarks
from app.models.reposts import Blog_Reposts
from app.models.messages import Blog_Messages
from app.models.comments import Blog_Comments, Blog_Replies
from app.models.follows import Blog_Follows
from app.models.helpers import update_likes, update_bookmarks, update_reposts, delete_comment, delete_reply
from flask_login import current_user, login_required
from datetime import datetime
from sqlalchemy import desc, or_
import re

website = Blueprint('website', __name__,
                    static_folder="../static", template_folder="../template")

@website.route("/")
def home():
    # 查询数据库获取主题及对应的图片路径
    posts_themes = [(u.theme, u.picture, u.id)
                    for u in db.session.query(Blog_Theme).all()]
    theme_list = [t[2] for t in posts_themes]
    
    # 查询每个主题的最新3篇文章
    # 重要说明：如果增加主题数量，以下代码的可维护性会变差，但目前我自身无法实现更优的方案
    # 该部分代码需要后续优化
    # 代码同时会提取第四个主题的文章ID，因为这些文章在首页中是单独展示的
    posts_all = []
    forth_theme_post_ids = []
    for num_themes in theme_list:
        query = db.session.query(Blog_Posts).filter(
            Blog_Posts.admin_approved == "TRUE",
            Blog_Posts.date_to_post <= datetime.utcnow(),
            Blog_Posts.theme_id == num_themes
        ).order_by(desc(Blog_Posts.date_to_post)).limit(3)
        theme_posts = query.all()
        posts_all.append(theme_posts)
        if num_themes == 4:
            for post in theme_posts:
                forth_theme_post_ids.append(post.id)
    posts_all = posts_all[0] + posts_all[1] + posts_all[2] + posts_all[3]

    return render_template('website/index.html', posts_all=posts_all, posts_themes=posts_themes, logged_in=current_user.is_authenticated, forth_theme_post_ids=forth_theme_post_ids)

# 路由：全部文章页面或指定主题的文章页面
@website.route("/all/<int:index>")
def all(index):
    index = int(index)
    all_blog_posts = None
    chosen_theme = ""
    intros = []
    if index != 0:
        chosen_theme = db.session.query(
            Blog_Theme).filter(Blog_Theme.id == index).first().theme
        all_blog_posts = db.session.query(Blog_Posts).filter(Blog_Posts.theme_id == index,
            Blog_Posts.admin_approved == "TRUE", Blog_Posts.date_to_post <= datetime.utcnow(),
        ).order_by(desc(Blog_Posts.date_to_post)).limit(25)
    else:
        all_blog_posts = db.session.query(Blog_Posts).filter(
            Blog_Posts.admin_approved == "TRUE", Blog_Posts.date_to_post <= datetime.utcnow(),
            ).order_by(desc(Blog_Posts.date_to_post)).limit(25)
    for post in all_blog_posts:
        # 如果 intro 为空或只有空白字符，从 body 中提取文本
        intro_text = post.intro if post.intro and post.intro.strip() else ""
        if not intro_text and post.body:
            # 从 body 中提取纯文本（去除HTML标签）
            body_text = re.sub(r'<[^>]+>', '', post.body)
            body_text = body_text.strip()
            if body_text:
                intro_text = body_text[:300] + "..." if len(body_text) > 300 else body_text
            else:
                intro_text = ""
        
        if intro_text and len(intro_text) > 300:
            cut_intro_if_too_long = f"{intro_text[:300]}..."
            intros.append(cut_intro_if_too_long)
        else:
            intros.append(intro_text if intro_text else "")

    return render_template('website/all_posts.html', all_blog_posts=all_blog_posts, chosen_theme=chosen_theme, intros=intros, logged_in=current_user.is_authenticated)

@website.route("/about/")
def about():
    authors_all = db.session.query(Blog_User).filter(
        Blog_User.blocked == "FALSE", Blog_User.type == "author",
        ).order_by(desc(Blog_User.id)).limit(25)
    
    # 获取每个作者的关注数和粉丝数
    authors_with_stats = []
    for author in authors_all:
        followers_count = Blog_Follows.query.filter_by(following_id=author.id).count()
        following_count = Blog_Follows.query.filter_by(follower_id=author.id).count()
        is_following = False
        if current_user.is_authenticated:
            is_following = Blog_Follows.query.filter_by(
                follower_id=current_user.id,
                following_id=author.id
            ).first() is not None
        authors_with_stats.append({
            'author': author,
            'followers_count': followers_count,
            'following_count': following_count,
            'is_following': is_following
        })
    
    return render_template('website/about.html', 
                         authors_with_stats=authors_with_stats,
                         logged_in=current_user.is_authenticated)

@website.route("/post/<int:index>", methods=["GET", "POST"])
def blog_post(index):
    # 获取文章
    blog_post = db.session.query(Blog_Posts).filter(Blog_Posts.id == index,
                                                    Blog_Posts.admin_approved == "TRUE", Blog_Posts.date_to_post <= datetime.utcnow(),
                                                    ).order_by(Blog_Posts.date_submitted.desc()).first()
    # 获取点赞数
    post_likes = db.session.query(Blog_Likes).filter(
        Blog_Likes.post_id == index).all()

    # 检查用户是否登录，以及是否已点赞、收藏或转发该文章
    user_liked = False
    user_bookmarked = False
    user_reposted = False
    is_following_author = False
    author_followers_count = 0
    if current_user.is_authenticated:
        like = db.session.query(Blog_Likes).filter(
            Blog_Likes.user_id == current_user.id, Blog_Likes.post_id == index).first()
        bookmark = db.session.query(Blog_Bookmarks).filter(
            Blog_Bookmarks.user_id == current_user.id, Blog_Bookmarks.post_id == index).first()
        repost = db.session.query(Blog_Reposts).filter(
            Blog_Reposts.user_id == current_user.id, Blog_Reposts.post_id == index).first()
        # 检查是否关注了作者
        if blog_post and blog_post.author_id != current_user.id:
            follow = Blog_Follows.query.filter_by(
                follower_id=current_user.id,
                following_id=blog_post.author_id
            ).first()
            is_following_author = follow is not None
    else:
        like = False
        bookmark = False
        repost = False
    
    if like:
        user_liked = True
    if bookmark:
        user_bookmarked = True
    if repost:
        user_reposted = True
    
    # 获取转发数
    post_reposts = db.session.query(Blog_Reposts).filter(
        Blog_Reposts.post_id == index).all()
    
    # 获取作者的粉丝数
    if blog_post:
        author_followers_count = Blog_Follows.query.filter_by(following_id=blog_post.author_id).count()
    
    # 获取评论
    comments = db.session.query(Blog_Comments).filter(
        Blog_Comments.post_id == index).order_by(Blog_Comments.date_submitted.desc()).limit(25)
    # 获取回复
    replies = db.session.query(Blog_Replies).filter(Blog_Replies.post_id == index,
                                                    ).order_by(Blog_Replies.date_submitted.asc()).limit(100)
    return render_template('website/post.html', 
                         blog_posts=blog_post, 
                         logged_in=current_user.is_authenticated, 
                         comments=comments, 
                         replies=replies, 
                         post_likes=post_likes,
                         post_reposts=post_reposts,
                         user_liked=user_liked, 
                         user_bookmarked=user_bookmarked,
                         user_reposted=user_reposted,
                         is_following_author=is_following_author,
                         author_followers_count=author_followers_count)

# 对文章发表评论或回复
@website.route("/comment_post/<int:index>", methods=["POST"])
def post_comment(index):
    data = request.get_json()
    content_type = request.headers.get('Content-Type')
    if (content_type == 'application/json'):
        data = request.get_json()
        if not data.get('comment') and not data.get('reply'):
            return make_response(jsonify({"message": "评论内容不能为空"}), 400)
        if data.get('reply') and not data.get('comment'):
            # 添加回复
            reply = Blog_Replies(
                text=data.get('reply'), post_id=index, user_id=current_user.id, comment_id=int(data.get('commentId')))
            db.session.add(reply)
            db.session.commit()
            return make_response(jsonify({"message": "回复添加成功"}), 200)
        elif data.get('comment') and not data.get('reply'):
            # 添加评论
            comment = Blog_Comments(
                text=data.get('comment'), post_id=index, user_id=current_user.id)
            db.session.add(comment)
            db.session.commit()
            return make_response(jsonify({"message": "评论添加成功"}), 200)
        else:
            return make_response(jsonify({"message": "只能选择发表评论或回复其中一项"}), 400)
    else:
        return make_response(jsonify({"message": "不支持的内容类型"}), 412)

# 删除评论或回复
@website.route("/delete_comment_or_reply/<int:index>", methods=["POST"])
def post_delete_comment(index):
    data = request.get_json()
    content_type = request.headers.get('Content-Type')
    if (content_type == 'application/json'):
        data = request.get_json()
        if not data.get('commentId') and not data.get('replyId'):
            return make_response(jsonify({"message": "没有需要删除的内容"}), 400)
        if data.get('replyId') and not data.get('commentId'):
            # 删除回复
            res = delete_reply(int(data.get('replyId')))
            if res == "success":
                return make_response(jsonify({"message": "删除成功"}), 200)
            else:
                return make_response(jsonify({"message": "回复不存在"}), 404)
        elif data.get('commentId') and not data.get('replyId'):
            # 删除评论
            res = delete_comment(int(data.get('commentId')))
            if res == "success":
                return make_response(jsonify({"message": "删除成功"}), 200)
            else:
                return make_response(jsonify({"message": "评论不存在"}), 404)
        else:
            return make_response(jsonify({"message": "只能选择评论ID或回复ID其中一项"}), 400)
    else:
        return make_response(jsonify({"message": "不支持的内容类型"}), 412)

# 点赞文章（由JavaScript发起请求）
@website.route("/like_post/<int:index>", methods=["POST"])
def post_like(index):
    # 检查文章是否存在
    post = db.session.query(Blog_Posts).filter_by(id=index).first()
    if not post:
        return jsonify({"error": "文章不存在"}, 400)
    
    # 检查用户是否已点赞该文章
    like = db.session.query(Blog_Likes).filter(
        Blog_Likes.user_id == current_user.id, Blog_Likes.post_id == index).first()
    if like:
        db.session.delete(like)
        db.session.commit()
        update_likes(-1)
        has_liked = "false"
    else:
        like = Blog_Likes(user_id=current_user.id, post_id=index)
        db.session.add(like)
        db.session.commit()
        update_likes(1)
        has_liked = "true"
    
    # 操作后重新查询点赞数，确保返回正确的值
    post_likes = db.session.query(Blog_Likes).filter(
        Blog_Likes.post_id == index).all()
    return jsonify({"likes": len(post_likes), "user_liked": has_liked})

# 收藏文章（由JavaScript发起请求）
@website.route("/bookmark_post/<int:index>", methods=["POST"])
def post_bookmark(index):
    # 检查文章是否存在
    post = db.session.query(Blog_Posts).filter_by(id=index).first()
    if not post:
        return jsonify({"error": "文章不存在"}, 400)

    # 检查用户是否已收藏该文章，以决定添加或取消收藏
    bookmark = db.session.query(Blog_Bookmarks).filter(
        Blog_Bookmarks.user_id == current_user.id, Blog_Bookmarks.post_id == index).first()
    if bookmark:
        db.session.delete(bookmark)
        db.session.commit()
        update_bookmarks(-1)
        has_bookmarked = "false"
    else:
        bookmark = Blog_Bookmarks(user_id=current_user.id, post_id=index)
        db.session.add(bookmark)
        db.session.commit()
        update_bookmarks(1)
        has_bookmarked = "true"
    return jsonify({"user_bookmarked": has_bookmarked})

# 获取所有用户列表（用于转发时选择）
@website.route("/api/users", methods=["GET"])
@login_required
def get_users():
    """获取所有用户列表（用于转发时选择）"""
    users = db.session.query(Blog_User).filter(
        Blog_User.blocked == "FALSE",
        Blog_User.id != current_user.id  # 不包括自己
    ).order_by(Blog_User.name).all()
    
    users_list = [{
        "id": user.id,
        "name": user.name,
        "picture": user.picture
    } for user in users]
    
    return jsonify({"users": users_list})

# 转发文章（由JavaScript发起请求）
@website.route("/repost_post/<int:index>", methods=["POST"])
@login_required
def post_repost(index):
    """转发文章"""
    # 检查文章是否存在
    post = db.session.query(Blog_Posts).filter_by(id=index).first()
    if not post:
        return jsonify({"error": "文章不存在"}, 400)
    
    data = request.get_json()
    comment = data.get('comment', '') if data else ''
    target_user_id = data.get('target_user_id', None) if data else None
    
    # 如果指定了目标用户，验证用户是否存在
    if target_user_id:
        target_user = db.session.query(Blog_User).filter_by(id=target_user_id).first()
        if not target_user:
            return jsonify({"error": "目标用户不存在"}, 400)
        if target_user.blocked == "TRUE":
            return jsonify({"error": "目标用户已被封禁"}, 400)
    
    # 检查用户是否已转发该文章（如果指定了目标用户，检查是否转发给同一人）
    if target_user_id:
        repost = db.session.query(Blog_Reposts).filter(
            Blog_Reposts.user_id == current_user.id,
            Blog_Reposts.post_id == index,
            Blog_Reposts.target_user_id == target_user_id
        ).first()
    else:
        # 如果没有指定目标用户，检查是否已转发（没有目标用户的转发）
        repost = db.session.query(Blog_Reposts).filter(
            Blog_Reposts.user_id == current_user.id,
            Blog_Reposts.post_id == index,
            Blog_Reposts.target_user_id == None
        ).first()
    
    if repost:
        # 取消转发
        db.session.delete(repost)
        db.session.commit()
        update_reposts(-1)
        has_reposted = "false"
    else:
        # 添加转发
        repost = Blog_Reposts(
            user_id=current_user.id,
            post_id=index,
            target_user_id=target_user_id if target_user_id else None,
            comment=comment[:500] if comment else None
        )
        db.session.add(repost)
        db.session.commit()
        update_reposts(1)
        has_reposted = "true"
        
        # 如果转发给指定用户并添加了评论，则创建私信
        if target_user_id and comment and comment.strip():
            try:
                # 构建私信内容：包含转发信息和评论
                post_url = url_for('website.blog_post', index=index, _external=False)
                message_content = f"📤 {current_user.name} 向您转发了一篇文章：\n\n"
                message_content += f"《{post.title}》\n\n"
                message_content += f"💬 转发评论：{comment.strip()}\n\n"
                message_content += f"🔗 查看文章：{post_url}"
                
                # 创建私信
                message = Blog_Messages(
                    sender_id=current_user.id,
                    receiver_id=target_user_id,
                    content=message_content
                )
                db.session.add(message)
                db.session.commit()
                print(f"[Repost] 转发已作为私信发送给用户 {target_user_id}")
            except Exception as e:
                print(f"[Repost] 创建私信失败: {str(e)}")
                import traceback
                traceback.print_exc()
                # 私信创建失败不影响转发功能
                db.session.rollback()
    
    # 操作后重新查询转发数
    post_reposts = db.session.query(Blog_Reposts).filter(
        Blog_Reposts.post_id == index).all()
    
    return jsonify({
        "reposts": len(post_reposts),
        "user_reposted": has_reposted
    })

# 关注博主功能
@website.route("/follow_user/<int:user_id>", methods=["POST"])
@login_required
def follow_user(user_id):
    """关注/取消关注用户"""
    # 检查用户是否存在
    user_to_follow = Blog_User.query.get_or_404(user_id)
    
    # 不能关注自己
    if user_to_follow.id == current_user.id:
        return jsonify({"error": "不能关注自己"}), 400
    
    # 检查是否已经关注
    existing_follow = Blog_Follows.query.filter_by(
        follower_id=current_user.id,
        following_id=user_id
    ).first()
    
    if existing_follow:
        # 取消关注
        db.session.delete(existing_follow)
        db.session.commit()
        is_following = False
        message = "已取消关注"
    else:
        # 添加关注
        new_follow = Blog_Follows(
            follower_id=current_user.id,
            following_id=user_id
        )
        db.session.add(new_follow)
        db.session.commit()
        is_following = True
        message = "关注成功"
    
    # 获取关注数和粉丝数
    followers_count = Blog_Follows.query.filter_by(following_id=user_id).count()
    following_count = Blog_Follows.query.filter_by(follower_id=user_id).count()
    
    return jsonify({
        "is_following": is_following,
        "message": message,
        "followers_count": followers_count,
        "following_count": following_count
    })

# 获取用户关注状态
@website.route("/api/follow_status/<int:user_id>")
@login_required
def get_follow_status(user_id):
    """获取当前用户对指定用户的关注状态"""
    is_following = Blog_Follows.query.filter_by(
        follower_id=current_user.id,
        following_id=user_id
    ).first() is not None
    
    followers_count = Blog_Follows.query.filter_by(following_id=user_id).count()
    following_count = Blog_Follows.query.filter_by(follower_id=user_id).count()
    
    return jsonify({
        "is_following": is_following,
        "followers_count": followers_count,
        "following_count": following_count
    })

# 获取当前用户的关注和粉丝列表（API）
@website.route("/api/my_follows")
@login_required
def get_my_follows():
    """获取当前用户的关注和粉丝列表"""
    # 获取关注列表（我关注的人）
    following_users = db.session.query(Blog_User).join(
        Blog_Follows, Blog_User.id == Blog_Follows.following_id
    ).filter(Blog_Follows.follower_id == current_user.id).all()
    
    # 获取粉丝列表（关注我的人）
    followers = db.session.query(Blog_User).join(
        Blog_Follows, Blog_User.id == Blog_Follows.follower_id
    ).filter(Blog_Follows.following_id == current_user.id).all()
    
    following_list = [{
        "id": user.id,
        "name": user.name,
        "picture": user.picture,
        "about": user.about if user.about else "暂无简介"
    } for user in following_users]
    
    followers_list = [{
        "id": user.id,
        "name": user.name,
        "picture": user.picture,
        "about": user.about if user.about else "暂无简介"
    } for user in followers]
    
    return jsonify({
        "following": following_list,
        "followers": followers_list
    })

# 查看关注列表
@website.route("/following")
@login_required
def following_list():
    """查看我关注的人"""
    following_users = db.session.query(Blog_User).join(
        Blog_Follows, Blog_User.id == Blog_Follows.following_id
    ).filter(Blog_Follows.follower_id == current_user.id).all()
    
    return render_template('website/following.html', 
                         following_users=following_users,
                         logged_in=current_user.is_authenticated)

# 查看粉丝列表
@website.route("/followers")
@login_required
def followers_list():
    """查看我的粉丝"""
    followers = db.session.query(Blog_User).join(
        Blog_Follows, Blog_User.id == Blog_Follows.follower_id
    ).filter(Blog_Follows.following_id == current_user.id).all()
    
    return render_template('website/followers.html', 
                         followers=followers,
                         logged_in=current_user.is_authenticated)

# 用户主页：显示用户自己发布的文章
@website.route("/my_posts")
@login_required
def my_posts():
    """显示当前用户发布的所有文章，包含面板、评论、私信功能"""
    # 获取当前用户发布的所有文章（包括未审核的）
    my_blog_posts = db.session.query(Blog_Posts).filter(
        Blog_Posts.author_id == current_user.id
    ).order_by(desc(Blog_Posts.date_to_post)).all()
    
    # 处理简介
    intros = []
    for post in my_blog_posts:
        # 如果 intro 为空或只有空白字符，从 body 中提取文本
        intro_text = post.intro if post.intro and post.intro.strip() else ""
        if not intro_text and post.body:
            # 从 body 中提取纯文本（去除HTML标签）
            body_text = re.sub(r'<[^>]+>', '', post.body)
            body_text = body_text.strip()
            if body_text:
                intro_text = body_text[:300] + "..." if len(body_text) > 300 else body_text
            else:
                intro_text = ""
        
        if intro_text and len(intro_text) > 300:
            cut_intro_if_too_long = f"{intro_text[:300]}..."
            intros.append(cut_intro_if_too_long)
        else:
            intros.append(intro_text if intro_text else "")
    
    # 统计未读消息数
    unread_count = db.session.query(Blog_Messages).filter(
        Blog_Messages.receiver_id == current_user.id,
        Blog_Messages.read == "FALSE"
    ).count()
    
    # 获取面板数据（收藏的博客）
    latest_bookmarks = Blog_Bookmarks.query.filter_by(user_id=current_user.id).limit(9)
    if latest_bookmarks.count() == 0:
        latest_bookmarks = None
    
    # 获取评论数据（收件箱）
    users_comments = db.session.query(Blog_Comments).filter(
        Blog_Comments.user_id == current_user.id).order_by(desc(Blog_Comments.date_submitted)).limit(25)
    replies = Blog_Replies.query.filter(
        Blog_Replies.comment_id.in_([c.id for c in users_comments])).all()
    if users_comments.count() == 0:
        users_comments = None
    
    # 获取私信数据
    received_messages = db.session.query(Blog_Messages).filter(
        Blog_Messages.receiver_id == current_user.id
    ).order_by(desc(Blog_Messages.date_submitted)).all()
    
    sent_messages = db.session.query(Blog_Messages).filter(
        Blog_Messages.sender_id == current_user.id
    ).order_by(desc(Blog_Messages.date_submitted)).all()
    
    # 获取最新文章（用于面板）
    latest_posts = db.session.query(Blog_Posts).filter(
        Blog_Posts.admin_approved == "TRUE", Blog_Posts.date_to_post <= datetime.utcnow()).order_by(desc(Blog_Posts.date_to_post)).limit(3)
    
    # 获取关注列表（我关注的人）
    following_users = db.session.query(Blog_User).join(
        Blog_Follows, Blog_User.id == Blog_Follows.following_id
    ).filter(Blog_Follows.follower_id == current_user.id).all()
    
    # 获取粉丝列表（关注我的人）
    followers = db.session.query(Blog_User).join(
        Blog_Follows, Blog_User.id == Blog_Follows.follower_id
    ).filter(Blog_Follows.following_id == current_user.id).all()
    
    return render_template('website/my_posts.html', 
                         my_blog_posts=my_blog_posts,
                         intros=intros,
                         unread_count=unread_count,
                         latest_bookmarks=latest_bookmarks,
                         latest_posts=latest_posts,
                         users_comments=users_comments,
                         replies=replies,
                         received_messages=received_messages,
                         sent_messages=sent_messages,
                         following_users=following_users,
                         followers=followers,
                         logged_in=current_user.is_authenticated)

# 删除博客（从用户主页）
@website.route("/my_posts/delete/<int:post_id>", methods=["POST"])
@login_required
def delete_my_post(post_id):
    """删除用户自己的博客"""
    post_to_delete = Blog_Posts.query.get_or_404(post_id)
    
    # 检查权限：只能删除自己的博客
    if post_to_delete.author_id != current_user.id:
        flash("您无权删除他人的博客！")
        return redirect(url_for('website.my_posts'))
    
    try:
        # 删除相关的点赞
        post_likes = Blog_Likes.query.filter_by(post_id=post_id).all()
        for like in post_likes:
            db.session.delete(like)
            update_likes(-1)
        
        # 删除相关的评论和回复
        comments = Blog_Comments.query.filter_by(post_id=post_id).all()
        for comment in comments:
            replies = Blog_Replies.query.filter_by(comment_id=comment.id).all()
            for reply in replies:
                db.session.delete(reply)
            db.session.delete(comment)
        
        # 删除相关的收藏
        bookmarks = Blog_Bookmarks.query.filter_by(post_id=post_id).all()
        for bookmark in bookmarks:
            db.session.delete(bookmark)
            update_bookmarks(-1)
        
        # 删除博客图片
        from app.dashboard.helpers import delete_blog_img
        if post_to_delete.picture_v:
            delete_blog_img(post_to_delete.picture_v)
        if post_to_delete.picture_h:
            delete_blog_img(post_to_delete.picture_h)
        if post_to_delete.picture_s:
            delete_blog_img(post_to_delete.picture_s)
        
        # 删除博客
        db.session.delete(post_to_delete)
        db.session.commit()
        
        flash("博客删除成功！")
        return redirect(url_for('website.my_posts'))
    except Exception as e:
        db.session.rollback()
        flash(f"删除失败：{str(e)}")
        return redirect(url_for('website.my_posts'))

# 私信功能
@website.route("/my_posts/messages")
@login_required
def my_messages():
    """查看我的私信"""
    # 获取收到的私信
    received_messages = db.session.query(Blog_Messages).filter(
        Blog_Messages.receiver_id == current_user.id
    ).order_by(desc(Blog_Messages.date_submitted)).all()
    
    # 获取发送的私信
    sent_messages = db.session.query(Blog_Messages).filter(
        Blog_Messages.sender_id == current_user.id
    ).order_by(desc(Blog_Messages.date_submitted)).all()
    
    # 统计未读消息数
    unread_count = db.session.query(Blog_Messages).filter(
        Blog_Messages.receiver_id == current_user.id,
        Blog_Messages.read == "FALSE"
    ).count()
    
    return render_template('website/messages.html',
                         received_messages=received_messages,
                         sent_messages=sent_messages,
                         unread_count=unread_count,
                         logged_in=current_user.is_authenticated)

@website.route("/my_posts/send_message/<int:user_id>", methods=["GET", "POST"])
@login_required
def send_message(user_id):
    """发送私信"""
    receiver = Blog_User.query.get_or_404(user_id)
    
    if request.method == "POST":
        content = request.form.get('content', '').strip()
        if not content:
            flash("私信内容不能为空！")
            return redirect(url_for('website.send_message', user_id=user_id))
        
        try:
            message = Blog_Messages(
                sender_id=current_user.id,
                receiver_id=user_id,
                content=content
            )
            db.session.add(message)
            db.session.commit()
            flash("私信发送成功！")
            # 重定向到个人主页，让用户能看到更新的私信列表
            return redirect(url_for('website.my_posts') + '#messages')
        except Exception as e:
            db.session.rollback()
            flash(f"发送失败：{str(e)}")
            return redirect(url_for('website.send_message', user_id=user_id))
    
    return render_template('website/send_message.html',
                         receiver=receiver,
                         logged_in=current_user.is_authenticated)

@website.route("/my_posts/mark_message_read/<int:message_id>", methods=["POST"])
@login_required
def mark_message_read(message_id):
    """标记私信为已读"""
    message = Blog_Messages.query.get_or_404(message_id)
    
    # 只能标记自己收到的消息
    if message.receiver_id != current_user.id:
        return jsonify({"error": "无权操作"}), 403
    
    try:
        message.read = "TRUE"
        db.session.commit()
        return jsonify({"success": True})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

# 文章搜索功能
@website.route("/search")
def search():
    """搜索文章"""
    # 获取搜索关键词
    query = request.args.get('q', '').strip()
    
    # 如果没有搜索关键词，返回空结果
    if not query:
        return render_template('website/search_results.html', 
                             search_query='',
                             search_results=[],
                             intros=[],
                             logged_in=current_user.is_authenticated)
    
    # 使用 OR 条件搜索标题、简介和正文
    # 使用 LIKE 进行模糊匹配（不区分大小写）
    search_filter = or_(
        Blog_Posts.title.like(f'%{query}%'),
        Blog_Posts.intro.like(f'%{query}%'),
        Blog_Posts.body.like(f'%{query}%')
    )
    
    # 查询已批准且已发布的文章
    search_results = db.session.query(Blog_Posts).filter(
        Blog_Posts.admin_approved == "TRUE",
        Blog_Posts.date_to_post <= datetime.utcnow(),
        search_filter
    ).order_by(desc(Blog_Posts.date_to_post)).limit(50).all()
    
    # 处理简介，如果太长则截断
    intros = []
    for post in search_results:
        # 如果 intro 为空或只有空白字符，从 body 中提取文本
        intro_text = post.intro if post.intro and post.intro.strip() else ""
        if not intro_text and post.body:
            # 从 body 中提取纯文本（去除HTML标签）
            body_text = re.sub(r'<[^>]+>', '', post.body)
            body_text = body_text.strip()
            if body_text:
                intro_text = body_text[:300] + "..." if len(body_text) > 300 else body_text
            else:
                intro_text = ""
        
        if intro_text and len(intro_text) > 300:
            cut_intro_if_too_long = f"{intro_text[:300]}..."
            intros.append(cut_intro_if_too_long)
        else:
            intros.append(intro_text if intro_text else "")
    
    return render_template('website/search_results.html', 
                         search_query=query,
                         search_results=search_results,
                         intros=intros,
                         logged_in=current_user.is_authenticated)