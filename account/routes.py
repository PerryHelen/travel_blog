from flask import Blueprint, render_template, request, redirect, flash, url_for, current_app
from app.extensions import db, login_manager
from app.models.user import Blog_User
from app.models.posts import Blog_Posts
from app.account.forms import The_Accounts
from app.models.stats import Blog_Stats
from app.models.bookmarks import Blog_Bookmarks
from app.models.likes import Blog_Likes
from app.models.comments import Blog_Comments, Blog_Replies
from app.account.helpers import hash_pw
from app.models.helpers import  update_stats_users_total, update_stats_users_active, delete_comment, delete_reply, change_authorship_of_all_post, update_bookmarks, update_likes
from app.general_helpers.helpers import check_image_filename
from flask_login import login_user, login_required, current_user, logout_user
from werkzeug.security import check_password_hash  # used in login
from werkzeug.utils import secure_filename
from sqlalchemy import desc
from datetime import datetime
import uuid as uuid
import os

account = Blueprint('account', __name__)

# Pages: login, logout, signup, account
# Routes available for all registered users (all user types) + login and signup (available for all registered and non-registered users)

# ***********************************************************************************************
# LOGIN, SIGN UP, LOG OUT
@login_manager.user_loader
def load_user(user_id):
    return Blog_User.query.get(int(user_id))

@account.route("/signup", methods=["GET", "POST"])
def signup():
    # Future improvement tip: check if username is unique
    if request.method == "POST":
        username = request.form.get("username")  
        email = request.form.get("email")      
        user_by_name_and_email = Blog_User.query.filter_by(
            name=username, 
            email=email
        ).first()

        user_by_name = Blog_User.query.filter_by(name=username).first()
        user_by_email = Blog_User.query.filter_by(email=email).first()

        if user_by_name_and_email:
            flash("该用户已存在，请直接登录！")
            return redirect(url_for("account.login"))
        elif user_by_name:
            flash("名字已存在，请重命名！")
            return redirect(url_for("account.signup")) 
        elif user_by_email:
            flash("邮箱已被注册，请直接登录！")
            return redirect(url_for("account.login"))
        else:
            flash("注册成功！")
            new_user = Blog_User(
                name=request.form.get("username"),
                email=request.form.get("email"),
                password=hash_pw(request.form.get("password")),
                type="user"
            )
            db.session.add(new_user)
            db.session.commit()
            update_stats_users_total()
            update_stats_users_active(1)
            login_user(new_user)
            return redirect(url_for('account.dashboard'))
    return render_template('account/signup.html', logged_in=current_user.is_authenticated)


@account.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get('email')
        password = request.form.get('password')
        the_user = Blog_User.query.filter_by(email=email).first()
        # wrong email:
        if not the_user:
            flash("邮箱不存在！")
            return redirect(url_for("account.signup"))
        # wrong password:
        elif not check_password_hash(the_user.password, password):
            flash("密码错误，请重试！")
            return redirect(url_for("account.login"))
        # user is blocked:
        elif the_user.blocked == "TRUE":
            flash("账号被冻结！")
            return redirect(url_for("account.login"))
        # email exists and password is correct:
        else:
            login_user(the_user)
            return redirect(url_for('account.dashboard'))
    return render_template("account/login.html", logged_in=current_user.is_authenticated)


@account.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('website.home'))

# ***********************************************************************************************
# DASHBOARDs
# displaying user dashboard after log-in according to the account type: user, author, or admin
@account.route("/dashboard")
@login_required
def dashboard():
    if current_user.type == "user":
        latest_posts = db.session.query(Blog_Posts).filter(
            Blog_Posts.admin_approved == "TRUE", Blog_Posts.date_to_post <= datetime.utcnow()).order_by(desc(Blog_Posts.date_to_post)).limit(3)
        latest_bookmarks = Blog_Bookmarks.query.filter_by(user_id=current_user.id).limit(9)
        if latest_bookmarks.count() == 0:
            latest_bookmarks = None
        return render_template('account/dashboard_user.html', name=current_user.name, logged_in=True, latest_posts=latest_posts, latest_bookmarks=latest_bookmarks)
    elif current_user.type == "author":
        latest_posts = db.session.query(Blog_Posts).filter(
            Blog_Posts.admin_approved == "TRUE", Blog_Posts.date_to_post <= datetime.utcnow()).order_by(desc(Blog_Posts.date_to_post)).limit(3)
        latest_bookmarks = Blog_Bookmarks.query.filter_by(user_id=current_user.id).limit(9)
        if latest_bookmarks.count() == 0:
            latest_bookmarks = None
        posts_pending_admin = Blog_Posts.query.filter(Blog_Posts.admin_approved == "FALSE").filter(
            Blog_Posts.author_id == current_user.id).all()
        return render_template('account/dashboard_author_dash.html', name=current_user.name, latest_posts=latest_posts, latest_bookmarks=latest_bookmarks, logged_in=True, posts_pending_admin=posts_pending_admin)
    else:
        current_stats = Blog_Stats.query.get_or_404(1)
        posts_pending_approval = Blog_Posts.query.filter_by(
            admin_approved="FALSE").all()
        return render_template('account/dashboard_admin_dash.html', name=current_user.name, logged_in=True, posts_pending_approval=posts_pending_approval, current_stats=current_stats)

# ***********************************************************************************************
# OWN ACCOUNT MANAGEMENT, BOOKMARKS, HISTORY

# Managing own account information - available to all users
@account.route("/dashboard/manage_account")
@login_required
def manage_acct():
    return render_template("account/account_mgmt.html", logged_in=current_user.is_authenticated)

# Update own account information
@account.route("/dashboard/manage_account/update/<int:id>", methods=["GET", "POST"])
@login_required
def update_own_acct_info(id):
    form = The_Accounts()
    user_at_hand = Blog_User.query.get_or_404(id)

    if form.validate_on_submit():
        user_at_hand.name = form.username.data
        user_at_hand.email = form.email.data
        user_at_hand.about = form.about.data

        try:
            db.session.commit()
            flash("账户信息更新成功！")
            return redirect(url_for('account.manage_acct'))
        except:
            flash("哎呀，更新账户信息时出错了，请重试。")
            return redirect(url_for('account.manage_acct'))

    # filling out the form with saved post data
    form.username.data = user_at_hand.name
    form.email.data = user_at_hand.email
    form.about.data = user_at_hand.about
    return render_template("account/account_mgmt_update.html", logged_in=current_user.is_authenticated, form=form)

# Update account information: changing the picture
@account.route("/dashboard/manage_account/update_picture/<int:id>", methods=["GET", "POST"])
@login_required
def update_own_acct_picture(id):
    form = The_Accounts()
    user_at_hand = Blog_User.query.get_or_404(id)
    if user_at_hand.picture == "" or user_at_hand.picture == "Picture_default.jpg":
        profile_picture = None
    else:
        profile_picture = user_at_hand.picture

    if request.method == "POST":
        if form.picture.data and hasattr(form.picture.data, 'filename') and form.picture.data.filename:
            try:
                # get name from image file:
                pic_filename_raw = form.picture.data.filename
                
                # 先检查原始文件名格式
                if not check_image_filename(pic_filename_raw):
                    flash(f"抱歉，不支持该图片格式。支持格式：PNG, JPG, JPEG。您上传的文件：{pic_filename_raw}")
                    return redirect(url_for('account.update_own_acct_picture', id=id))
                
                pic_filename = secure_filename(pic_filename_raw)
                
                # 如果secure_filename处理后为空，使用原始文件名
                if not pic_filename:
                    pic_filename = pic_filename_raw.strip()
                
                # 再次检查处理后的文件名
                if not check_image_filename(pic_filename):
                    flash(f"抱歉，不支持该图片格式。支持格式：PNG, JPG, JPEG。")
                    return redirect(url_for('account.update_own_acct_picture', id=id))

                # insert a unique id to the filename to make sure there arent two pictures with the same name:
                pic_filename_unique = str(uuid.uuid1()) + "_" + pic_filename
                user_at_hand.picture = pic_filename_unique

                # get the new image
                the_img_file = request.files.get('picture')
                if not the_img_file:
                    the_img_file = form.picture.data
                
                # 确保文件夹存在
                img_folder = current_app.config["PROFILE_IMG_FOLDER"]
                if not os.path.exists(img_folder):
                    os.makedirs(img_folder)
                
                # save the img to folder and path to user
                img_path = os.path.join(img_folder, pic_filename_unique)
                the_img_file.save(img_path)
                
                # delete the old picture from folder
                if profile_picture != None and os.path.exists(os.path.join(current_app.config["PROFILE_IMG_FOLDER"], profile_picture)):
                    os.remove(os.path.join(
                        current_app.config["PROFILE_IMG_FOLDER"], profile_picture))

                db.session.commit()
                flash("头像更新成功！")
                return redirect(url_for('account.manage_acct'))
            except Exception as e:
                db.session.rollback()
                flash(f"哎呀，更新头像时出错了：{str(e)}，请重试。")
                return redirect(url_for('account.manage_acct'))
        else:
            flash("请选择要上传的图片文件。")
            return redirect(url_for('account.update_own_acct_picture', id=id))

    return render_template("account/account_mgmt_picture.html", logged_in=current_user.is_authenticated, form=form, profile_picture=profile_picture)


# Delete account
# When an account is deleted, this changes the number of active users in the stats
# When this user is deleted, their picture, bookmarks, and likes are deleted as well.
# If this user is an author, the authorship of the post will be transfered to the blog team.
@account.route("/dashboard/manage_account/delete/<int:id>", methods=["GET", "POST"])
@login_required
def delete_own_acct(id):
    user_at_hand = Blog_User.query.get_or_404(id)
    if request.method == "POST":
        # impede the deletion of super_admin
        if id == 1:
            flash("权限不足：该用户无法被删除")
            return redirect(url_for('account.manage_acct'))
        else:
            try:
                # if user is author, transfer the authorship of the posts to the default author
                if user_at_hand.type == "author":
                    change_authorship_of_all_post(user_at_hand.id, 2)

                # if user has comments/replies, change ownership (to default user of id 3 and delete or mark as blocked ([deleted]).
                if user_at_hand.comments:
                    comments = Blog_Comments.query.filter_by(
                        user_id=user_at_hand.id).all()
                    for comment in comments:
                        comment.user_id = 3
                        delete_comment(comment.id)

                if user_at_hand.replies:
                    replies = comments = Blog_Replies.query.filter_by(
                        user_id=user_at_hand.id).all()
                    for reply in replies:
                        reply.user_id = 3
                        delete_reply(reply.id)
                
                # delete bookmarks and likes
                if user_at_hand.likes:
                    likes = Blog_Likes.query.filter_by(
                        user_id=user_at_hand.id).all()
                    for like in likes:
                        db.session.delete(like)
                        update_likes(-1)

                if user_at_hand.bookmarks:
                    bookmarks = Blog_Bookmarks.query.filter_by(
                        user_id=user_at_hand.id).all()
                    for bookmark in bookmarks:
                        db.session.delete(bookmark)
                        update_bookmarks(-1)

                # delete user's picture
                if user_at_hand.picture == "" or user_at_hand.picture == "Picture_default.jpg":
                    profile_picture = None
                else:
                    profile_picture = user_at_hand.picture

                if profile_picture != None and os.path.exists(os.path.join(current_app.config["PROFILE_IMG_FOLDER"], profile_picture)):
                    os.remove(os.path.join(
                        current_app.config["PROFILE_IMG_FOLDER"], profile_picture))
                    
                # delete user
                db.session.delete(user_at_hand)
                db.session.commit()
                flash("您的账户已删除！")
                update_stats_users_active(-1)
                return redirect(url_for("website.home"))
            except:
                flash("删除账户过程中遇到问题，未成功删除！")
                db.session.rollback()
                return redirect(url_for('account.manage_acct'))
    else:
        return render_template("account/account_mgmt_delete.html", logged_in=current_user.is_authenticated)

# INBOX
# User can see their comments and replies the comment received.
@account.route("/dashboard/inbox", methods=["GET", "POST"])
@login_required
def inbox():
    users_comments = db.session.query(Blog_Comments).filter(
        Blog_Comments.user_id == current_user.id).order_by(desc(Blog_Comments.date_submitted)).limit(25)

    replies = Blog_Replies.query.filter(
        Blog_Replies.comment_id.in_([c.id for c in users_comments])).all()
    
    if users_comments.count() == 0:
        users_comments = None

    return render_template("account/inbox.html", logged_in=current_user.is_authenticated, users_comments=users_comments, replies=replies)