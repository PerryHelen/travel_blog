#/manage_users管理员才能访问的，应该可以删掉
from flask import Blueprint, render_template, request, redirect, flash, url_for, current_app
from app.extensions import db
from app.models.user import Blog_User
from app.models.posts import Blog_Posts
from app.dashboard.forms import The_Posts
from app.dashboard.helpers import check_blog_picture, delete_blog_img
from app.general_helpers.helpers import check_image_filename
from app.models.themes import Blog_Theme
from app.models.helpers import update_stats_users_active, update_approved_post_stats, change_authorship_of_all_post
from app.models.likes import Blog_Likes
from app.models.bookmarks import Blog_Bookmarks
from app.models.comments import Blog_Comments, Blog_Replies
from app.models.helpers import update_likes, update_bookmarks, delete_comment, delete_reply
from datetime import datetime
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
import os

dashboard = Blueprint('dashboard', __name__)


@dashboard.route("/dashboard/manage_users", methods=["GET", "POST"])
@login_required
def users_table():
    user_type = current_user.type
    if user_type == "admin" or user_type == "super_admin":
        all_blog_users = Blog_User.query.order_by(Blog_User.id)
        return render_template("dashboard/users_table.html", logged_in=current_user.is_authenticated, all_blog_users=all_blog_users)
    else:
        flash("拒绝访问：您不是管理员！")
        return redirect(url_for('website.home'))

# ***********************************************************************************************

@dashboard.route("/dashboard/submit_new_post", methods=["GET", "POST"])
@login_required
def submit_post():
    if current_user.type not in ["author", "user", "admin", "super_admin"]:
        flash("您没有权限发布博客")
        return redirect(url_for('website.home'))
    themes_list = [(u.id, u.theme) for u in db.session.query(Blog_Theme).all()]
    form = The_Posts()
    form.theme.choices = [('', '-- 不选择主题（可选） --')] + themes_list

    if form.validate_on_submit():
        author = current_user.id
        # 验证：至少要有标题、内容、简介或图片中的一项
        has_title = form.title.data and form.title.data.strip()
        has_content = form.body.data and form.body.data.strip()
        has_intro = form.intro.data and form.intro.data.strip()
        
        # 检查是否有上传的图片（检查文件对象是否有文件名）
        has_picture = False
        if form.picture_v.data and hasattr(form.picture_v.data, 'filename') and form.picture_v.data.filename:
            has_picture = True
        elif form.picture_h.data and hasattr(form.picture_h.data, 'filename') and form.picture_h.data.filename:
            has_picture = True
        elif form.picture_s.data and hasattr(form.picture_s.data, 'filename') and form.picture_s.data.filename:
            has_picture = True
        
        if not has_title and not has_content and not has_intro and not has_picture:
            flash("请至少填写标题、内容、简介或上传一张图片")
            return render_template("dashboard/posts_submit_new.html", logged_in=current_user.is_authenticated, form=form)
        # 处理主题：如果未选择，使用第一个可用主题
        theme_id = form.theme.data if form.theme.data and form.theme.data != '' and form.theme.data is not None else None
        if not theme_id:
            first_theme = db.session.query(Blog_Theme).first()
            theme_id = first_theme.id if first_theme else 1
        
        # 如果没有标题，自动生成标题
        title = form.title.data if form.title.data and form.title.data.strip() else ""
        if not title:
            title = "无标题博客"
        
        # 处理picture_alt等字段，如果没有标题则使用默认值
        picture_alt_value = form.picture_alt.data if form.picture_alt.data else title
        meta_tag_value = form.meta_tag.data if form.meta_tag.data else title
        title_tag_value = form.title_tag.data if form.title_tag.data else title
        
        post = Blog_Posts(
            theme_id=theme_id,
            date_to_post=form.date.data if form.date.data else datetime.utcnow(), 
            title=title, 
            intro=form.intro.data if form.intro.data else "",
            body=form.body.data if form.body.data else "",
            picture_v=None,  # 初始化为None，上传成功后会更新
            picture_h=None,  # 初始化为None，上传成功后会更新
            picture_s=None,  # 初始化为None，上传成功后会更新
            picture_alt=picture_alt_value,
            meta_tag=meta_tag_value,
            title_tag=title_tag_value,
            author_id=author,
            admin_approved="TRUE"  # 自动通过审核，让大家都能看到
        )
        
        # add form information to database without the pictures:
        try:
            db.session.add(post)
            db.session.commit()
            
            # 生成AI摘要（异步，不阻塞发布流程）
            try:
                from app.services.deepseek_api import generate_summary
                print(f"[DeepSeek] 开始生成摘要，文章ID: {post.id}, 标题: {title}")
                summary = generate_summary(
                    title=title,
                    body=form.body.data if form.body.data else "",
                    intro=form.intro.data if form.intro.data else ""
                )
                if summary:
                    post.summary = summary
                    db.session.commit()
                    print(f"[DeepSeek] 摘要生成成功，文章ID: {post.id}")
                    print(f"[DeepSeek] 摘要内容: {summary[:100]}...")
                else:
                    print(f"[DeepSeek] 摘要生成返回None，文章ID: {post.id}")
            except Exception as e:
                print(f"[DeepSeek] 生成摘要失败: {str(e)}")
                import traceback
                traceback.print_exc()
                # 摘要生成失败不影响博客发布
                
        except Exception as e:
            flash(f"哎呀，保存博客文章时出错了：{str(e)}")
            db.session.rollback()
            return render_template("dashboard/posts_submit_new.html", logged_in=current_user.is_authenticated, form=form)

        # 如果当前用户是普通user，发布文章后自动转为author
        if current_user.type == "user":
            try:
                current_user.type = "author"  # 更新用户类型为作者
                db.session.commit()  # 提交修改
                flash(f"恭喜！您发布了第一篇文章，已自动升级为作者账号", "success")
            except Exception as e:
                db.session.rollback()
                flash(f"文章发布成功，但账号升级失败：{str(e)}", "warning")

        # checking images: one image at a time
        the_post_id = post.id

        submit_post_blog_img_provided = dict(v = False, h = False, s = False)
        submit_post_blog_img_status = dict(v=False, h=False, s=False)

        def submit_post_blog_img_handle (img_filename, img_format):
            accepted_img_format = ["v", "h", "s"]
            if img_format not in accepted_img_format:
                raise NameError(
                    "submit_post_blog_img_handle function was supplied an invalid img_format")
            new_img_name = check_blog_picture(
                the_post_id, img_filename, img_format)
            if new_img_name:
                new_img_format = "picture_" + img_format
                # 直接从form获取文件对象
                the_img = None
                if hasattr(form, new_img_format):
                    field = getattr(form, new_img_format)
                    if field.data:
                        the_img = field.data
                # 如果form中没有，尝试从request.files获取
                if not the_img:
                    the_img = request.files.get(new_img_format)
                
                # 如果还是没有，尝试直接使用form字段的data
                if not the_img and hasattr(form, new_img_format):
                    field = getattr(form, new_img_format)
                    if hasattr(field, 'data') and field.data:
                        the_img = field.data
                                
                if the_img and hasattr(the_img, 'filename') and the_img.filename:
                    try:
                        # 确保文件夹存在
                        img_folder = current_app.config["BLOG_IMG_FOLDER"]
                        if not os.path.exists(img_folder):
                            os.makedirs(img_folder)         
                        img_path = os.path.join(img_folder, new_img_name)                        
                        # 保存文件
                        the_img.save(img_path)
                        # 验证文件是否真的保存了
                        if os.path.exists(img_path):
                            file_size = os.path.getsize(img_path)
                            if img_format == "v":
                                post.picture_v = new_img_name
                            elif img_format == "h":
                                post.picture_h = new_img_name
                            else:
                                post.picture_s = new_img_name
                            db.session.commit()
                            submit_post_blog_img_status[img_format] = True
                        else:
                            print(f"[ERROR] Image file not found after save: {img_path}")
                            submit_post_blog_img_status[img_format] = False
                            flash(f"图片 {img_format} 保存失败")
                    except Exception as e:
                        print(f"[ERROR] Error saving image {img_format}: {e}")
                        import traceback
                        traceback.print_exc()
                        submit_post_blog_img_status[img_format] = False
                        flash(f"图片 {img_format} 上传出错: {str(e)}")
                else:
                    print(f"[DEBUG] No image file found for {new_img_format}, the_img: {the_img}")
                    submit_post_blog_img_status[img_format] = False
            else:
                print(f"[DEBUG] check_blog_picture returned False for {img_filename}")
                submit_post_blog_img_status[img_format] = False

        # checking picture vertical:
        if form.picture_v.data and hasattr(form.picture_v.data, 'filename') and form.picture_v.data.filename:
            # 检查文件大小（如果提供了size字段）
            if form.picture_v_size.data and form.picture_v_size.data.strip() and int(form.picture_v_size.data) >= 1500000:
                flash("垂直图片文件过大，请上传小于1.5MB的图片")
                submit_post_blog_img_provided["v"] = False
            else:
                img_v_filename_raw = form.picture_v.data.filename
                img_v_filename = secure_filename(img_v_filename_raw)
                if not img_v_filename:
                    img_v_filename = img_v_filename_raw.strip()
                
                if img_v_filename and check_image_filename(img_v_filename):
                    submit_post_blog_img_handle(img_v_filename, "v")
                    submit_post_blog_img_provided["v"] = True
                else:
                    flash(f"垂直图片格式不支持。支持格式：PNG, JPG, JPEG。文件名：{img_v_filename_raw}")
                    submit_post_blog_img_provided["v"] = False
        else:
            submit_post_blog_img_provided["v"] = False

        # checking picture horizontal:
        if form.picture_h.data and hasattr(form.picture_h.data, 'filename') and form.picture_h.data.filename:
            # 检查文件大小（如果提供了size字段）
            if form.picture_h_size.data and form.picture_h_size.data.strip() and int(form.picture_h_size.data) >= 1500000:
                flash("水平图片文件过大，请上传小于1.5MB的图片")
                submit_post_blog_img_provided["h"] = False
            else:
                img_h_filename_raw = form.picture_h.data.filename
                img_h_filename = secure_filename(img_h_filename_raw)
                if not img_h_filename:
                    img_h_filename = img_h_filename_raw.strip()
                
                if img_h_filename and check_image_filename(img_h_filename):
                    submit_post_blog_img_handle(img_h_filename, "h")
                    submit_post_blog_img_provided["h"] = True
                else:
                    flash(f"水平图片格式不支持。支持格式：PNG, JPG, JPEG。文件名：{img_h_filename_raw}")
                    submit_post_blog_img_provided["h"] = False
        else:
            submit_post_blog_img_provided["h"] = False

        # checking picture squared:
        if form.picture_s.data and hasattr(form.picture_s.data, 'filename') and form.picture_s.data.filename:
            # 检查文件大小（如果提供了size字段）
            if form.picture_s_size.data and form.picture_s_size.data.strip() and int(form.picture_s_size.data) >= 1500000:
                flash("方形图片文件过大，请上传小于1.5MB的图片")
                submit_post_blog_img_provided["s"] = False
            else:
                img_s_filename_raw = form.picture_s.data.filename
                img_s_filename = secure_filename(img_s_filename_raw)
                if not img_s_filename:
                    img_s_filename = img_s_filename_raw.strip()
                
                if img_s_filename and check_image_filename(img_s_filename):
                    submit_post_blog_img_handle(img_s_filename, "s")
                    submit_post_blog_img_provided["s"] = True
                else:
                    flash(f"方形图片格式不支持。支持格式：PNG, JPG, JPEG。文件名：{img_s_filename_raw}")
                    submit_post_blog_img_provided["s"] = False
        else:
            submit_post_blog_img_provided["s"] = False

        # inform the user of the status of the post
        submit_post_blog_missing_pic = False
        submit_post_blog_status_pic = False

        for key in submit_post_blog_img_provided:
            if submit_post_blog_img_provided[key] == False:
                submit_post_blog_missing_pic = True
        
        for key in submit_post_blog_img_provided:
            if submit_post_blog_img_status[key] == False:
                submit_post_blog_status_pic = True

        if submit_post_blog_missing_pic == True and submit_post_blog_status_pic == True:
            flash("博客文章提交成功，但有一张或多张图片缺失，且至少有一张图片无法上传。")
        elif submit_post_blog_missing_pic == True:
            flash("博客文章提交成功，但有一张或多张图片缺失。")
        elif submit_post_blog_status_pic == True:
            flash("博客文章提交成功，但有一张或多张图片无法上传。")
        else:
            if current_user.type == "author": 
                flash("博客发布成功！您已成为作者，可发布更多优质内容～", "success")
            else:
                flash("博客文章提交成功！")

        # clear form:
        form.theme.data = ""
        form.date.data = datetime.now
        form.title.data = ""
        form.intro.data = ""
        form.body.data = ""
        form.picture_v.data = ""
        form.picture_h.data = ""
        form.picture_s.data = ""
        form.picture_alt.data = ""
        form.meta_tag.data = ""
        form.title_tag.data = ""

        return redirect(url_for('account.dashboard'))
    return render_template("dashboard/posts_submit_new.html", logged_in=current_user.is_authenticated, form=form)


@dashboard.route("/dashboard/manage_posts")
@login_required
def posts_table_author():
    if current_user.type not in ["author"]:
        flash("您还不是作者，请发布博客成为作者！")
        return redirect(url_for('website.home'))
    all_blog_posts_submitted = Blog_Posts.query.filter_by(author_id=current_user.id).order_by(Blog_Posts.id)
    return render_template("dashboard/posts_table_author.html", logged_in=current_user.is_authenticated, all_blog_posts_submitted=all_blog_posts_submitted)


@dashboard.route("/dashboard/manage_posts/approve_post/<int:id>", methods=["GET", "POST"])
@login_required
def approve_post(id):
    post_to_approve = Blog_Posts.query.get_or_404(id)
    if request.method == "POST":
        post_to_approve.admin_approved = "TRUE"
        try:
            db.session.commit()
            flash("这篇文章已通过管理员审核。")
            update_approved_post_stats(1)
            return redirect(url_for('dashboard.posts_table'))
        except:
            flash("审核这篇文章时出现问题。")
            return render_template("dashboard/posts_approve_post.html", logged_in=current_user.is_authenticated, post_to_approve=post_to_approve)
    else:
        return render_template("dashboard/posts_approve_post.html", logged_in=current_user.is_authenticated, post_to_approve=post_to_approve)



@dashboard.route("/dashboard/manage_posts/disallow_post/<int:id>", methods=["GET", "POST"])
@login_required
def disallow_post(id):
    post_to_disallow = Blog_Posts.query.get_or_404(id)
    if request.method == "POST":
        post_to_disallow.admin_approved = "FALSE"
        try:
            db.session.commit()
            flash("这篇文章已被管理员取消审核通过状态。")
            update_approved_post_stats(-1)
            return redirect(url_for('dashboard.posts_table'))
        except:
            flash("取消审核这篇文章时出现问题。")
            return render_template("dashboard/posts_disallow_post.html", logged_in=current_user.is_authenticated, post_to_disallow=post_to_disallow)
    else:
        return render_template("dashboard/posts_disallow_post.html", logged_in=current_user.is_authenticated, post_to_disallow=post_to_disallow)

# POST MANGEMENT -  ADMIN AND AUTHORS
# Previewing a post
@dashboard.route("/dashboard/manage_posts_author/preview_post/<int:id>", endpoint='preview_post_author')
@dashboard.route("/dashboard/manage_posts/preview_post/<int:id>")
@login_required
def preview_post(id):
    post_to_preview = Blog_Posts.query.get_or_404(id)
    return render_template("dashboard/posts_preview_post.html", logged_in=current_user.is_authenticated, post_to_preview=post_to_preview)

# Editing a post - ADMIN AND AUTHORS
@dashboard.route("/dashboard/manage_posts_author/edit_post/<int:id>", endpoint='edit_post_author', methods=["GET", "POST"])
@dashboard.route("/dashboard/manage_posts/edit_post/<int:id>", methods=["GET", "POST"])
@login_required
def edit_post(id):

    # getting post information
    post_to_edit = Blog_Posts.query.get_or_404(id)
    themes_list = [(u.id, u.theme) for u in db.session.query(Blog_Theme).all()]
    form = The_Posts(obj=post_to_edit)
    form.theme.choices = themes_list

    if (current_user.type == "author" and post_to_edit.author_id != current_user.id) and current_user.type not in ["admin", "super_admin"]:
        flash("您无权编辑他人的帖子！")
        return redirect(url_for('dashboard.posts_table_author'))

    # changing the post
    if form.validate_on_submit():
        post_to_edit.theme_id = form.theme.data
        post_to_edit.date_to_post = form.date.data
        post_to_edit.title = form.title.data
        post_to_edit.intro = form.intro.data
        post_to_edit.body = form.body.data
        post_to_edit.picture_alt = form.picture_alt.data
        post_to_edit.meta_tag = form.meta_tag.data
        post_to_edit.title_tag = form.title_tag.data

        # add form information to database without the pictures:
        try:
            db.session.commit()
        except Exception as e:
            flash(f"保存文字内容失败：{str(e)}")
            db.session.rollback()
        
        # 如果文章内容有更新，可以选择重新生成摘要
        # 这里不自动生成，让用户手动触发
        
        # checking images: one image at a time
        the_post_id = post_to_edit.id

        submit_post_blog_img_provided = dict(v=False, h=False, s=False)
        submit_post_blog_img_status = dict(v=False, h=False, s=False)

        def submit_post_blog_img_handle(img_filename, img_format):
            accepted_img_format = ["v", "h", "s"]
            if img_format not in accepted_img_format:
                raise NameError(
                    "submit_post_blog_img_handle function was supplied an invalid img_format")
            new_img_name = check_blog_picture(
                the_post_id, img_filename, img_format)
            if new_img_name:
                new_img_format = "picture_" + img_format
                # 修复：用get方法避免KeyError
                the_img = request.files.get(new_img_format)
                if not the_img or the_img.filename == "":
                    submit_post_blog_img_status[img_format] = False
                    return
                try:
                    if img_format == "v":
                        delete_blog_img(post_to_edit.picture_v)
                        post_to_edit.picture_v = new_img_name
                    elif img_format == "h":
                        delete_blog_img(post_to_edit.picture_h)
                        post_to_edit.picture_h = new_img_name
                    else:
                        delete_blog_img(post_to_edit.picture_s)
                        post_to_edit.picture_s = new_img_name
                    the_img.save(os.path.join(
                        current_app.config["BLOG_IMG_FOLDER"], new_img_name))
                    db.session.commit()
                    submit_post_blog_img_status[img_format] = True
                except Exception as e:
                    print(f"图片保存失败：{str(e)}")
                    submit_post_blog_img_status[img_format] = False

        img_size_not_accepted = False

        # checking picture vertical:
        if form.picture_v.data:
            # 先处理空值，再转整数
            pic_size_str = form.picture_v_size.data.strip() if form.picture_v_size.data else ""
            if pic_size_str:
                try:
                    pic_size = int(pic_size_str)
                    if pic_size < 1500000:
                        img_v_filename = secure_filename(form.picture_v.data.filename)
                        submit_post_blog_img_handle(img_v_filename, "v")
                        submit_post_blog_img_provided["v"] = True
                    else:
                        img_size_not_accepted = True
                except ValueError:
                    # 非数字值，标记为大小不接受
                    img_size_not_accepted = True
            else:
                # 空值 → 跳过大小校验，不处理图片
                submit_post_blog_img_provided["v"] = False

        # checking picture horizontal:
        if form.picture_h.data:
            pic_size_str = form.picture_h_size.data.strip() if form.picture_h_size.data else ""
            if pic_size_str:
                try:
                    pic_size = int(pic_size_str)
                    if pic_size < 1500000:
                        img_h_filename = secure_filename(form.picture_h.data.filename)
                        submit_post_blog_img_handle(img_h_filename, "h")
                        submit_post_blog_img_provided["h"] = True
                    else:
                        img_size_not_accepted = True
                except ValueError:
                    img_size_not_accepted = True
            else:
                submit_post_blog_img_provided["h"] = False

        # checking picture squared:
        if form.picture_s.data:
            pic_size_str = form.picture_s_size.data.strip() if form.picture_s_size.data else ""
            if pic_size_str:
                try:
                    pic_size = int(pic_size_str)
                    if pic_size < 1500000:
                        img_s_filename = secure_filename(form.picture_s.data.filename)
                        submit_post_blog_img_handle(img_s_filename, "s")
                        submit_post_blog_img_provided["s"] = True
                    else:
                        img_size_not_accepted = True
                except ValueError:
                    img_size_not_accepted = True
            else:
                submit_post_blog_img_provided["s"] = False


        # inform the user of the status of the post
        problem_with_img_download = False

        for key in submit_post_blog_img_provided:
            if submit_post_blog_img_provided[key] == True:
                if submit_post_blog_img_status[key] == False:
                    problem_with_img_download = True

        if img_size_not_accepted == True:
            flash("博客文字内容已保存，但部分图片因超过1.5MB限制未能上传！")
        elif problem_with_img_download == True:
            flash(
                "博客文字内容已保存，但部分图片格式错误未能上传，请检查图片格式！")
        else:
            flash("博客编辑成功！")

        if current_user.type == "admin" or current_user.type == "super_admin":
            return redirect(url_for("dashboard.posts_table", logged_in=current_user.is_authenticated))
        else:
            return redirect(url_for("dashboard.posts_table_author", logged_in=current_user.is_authenticated))
        
    # filling out the form with saved post data
    form.theme.data = post_to_edit.theme_id
    # 修复：先判断是否有author字段，避免AttributeError
    try:
        form.author.data = post_to_edit.author.name
    except AttributeError:
        pass
    form.date.data = post_to_edit.date_to_post
    form.title.data = post_to_edit.title
    form.intro.data = post_to_edit.intro
    form.body.data = post_to_edit.body
    form.picture_alt.data = post_to_edit.picture_alt
    form.meta_tag.data = post_to_edit.meta_tag
    form.title_tag.data = post_to_edit.title_tag
    return render_template('dashboard/posts_edit_post.html', logged_in=current_user.is_authenticated, form=form, post_to_edit=post_to_edit)
# Deleting a post 
@dashboard.route("/dashboard/manage_posts_author/delete_post/<int:id>", endpoint='delete_post_author', methods=["GET", "POST"])
@dashboard.route("/dashboard/manage_posts/delete_post/<int:id>", methods=["GET", "POST"])
@login_required
def delete_post(id):
    # get post, and its associated likes and comments
    post_to_delete = Blog_Posts.query.get_or_404(id)
    # if current_user.type == "author" and post_to_delete.author_id != current_user.id:
    #     flash("您无权删除他人的帖子！")
    #     return redirect(url_for('dashboard.posts_table_author'))

    post_likes = db.session.query(Blog_Likes).filter(
        Blog_Likes.post_id == id).all()
    comments = db.session.query(Blog_Comments).filter(
        Blog_Comments.post_id == id).all()

    if request.method == "POST":
        try:
            # delete likes associated
            for like in post_likes:
                db.session.delete(like)

            # delete comments and replies associated
            for comment in comments:
                replies = Blog_Replies.query.filter_by(comment_id=comment.id).all()
                for reply in replies:
                    db.session.delete(reply)
                db.session.delete(comment)

            # delete bookmarks associated
            bookmarks = Blog_Bookmarks.query.filter_by(post_id=id).all()
            for bookmark in bookmarks:
                db.session.delete(bookmark)
            
            # delete the post and commit
            if post_to_delete.admin_approved == "TRUE":
                post_was_approved = True
            db.session.delete(post_to_delete)
            db.session.commit()

            # delete pictures associated
            delete_blog_img(post_to_delete.picture_v)
            delete_blog_img(post_to_delete.picture_h)
            delete_blog_img(post_to_delete.picture_s)

            # update stats
            if post_was_approved:
                update_approved_post_stats(-1)

            flash("文章删除成功。")
            if current_user.type == "author":
                return redirect(url_for('dashboard.posts_table_author'))
            else:
                return redirect(url_for('dashboard.posts_table'))
        except:
            db.session.rollback()
            flash("删除这篇文章及其关联数据时出现问题。")
            if current_user.type == "author":
                return redirect(url_for('dashboard.posts_table_author'))
            else:
                return redirect(url_for('dashboard.posts_table'))
    else:
        return render_template("dashboard/posts_delete_post.html", logged_in=current_user.is_authenticated, post_to_delete=post_to_delete, post_likes=post_likes, comments=comments)



# 生成AI摘要的API端点
@dashboard.route("/dashboard/generate_summary/<int:post_id>", methods=["POST"])
@login_required
def generate_summary_for_post(post_id):
    """为指定文章生成AI摘要 - 所有登录用户都可以使用"""
    from flask import jsonify
    from app.services.deepseek_api import generate_summary
    
    post = Blog_Posts.query.get_or_404(post_id)
    
    # 所有人都可以生成摘要，不需要权限检查
    
    try:
        print(f"[DeepSeek] 手动生成摘要，文章ID: {post_id}, 标题: {post.title}")
        summary = generate_summary(
            title=post.title if post.title else "",
            body=post.body if post.body else "",
            intro=post.intro if post.intro else ""
        )
        
        if summary:
            post.summary = summary
            db.session.commit()
            print(f"[DeepSeek] 摘要生成成功，文章ID: {post_id}")
            return jsonify({
                "success": True,
                "summary": summary,
                "message": "摘要生成成功！"
            })
        else:
            return jsonify({
                "success": False,
                "error": "摘要生成失败，请检查API配置或稍后重试"
            }), 500
            
    except Exception as e:
        print(f"[DeepSeek] 生成摘要时出错: {str(e)}")
        import traceback
        traceback.print_exc()
        db.session.rollback()
        return jsonify({
            "success": False,
            "error": f"生成摘要时出错: {str(e)}"
        }), 500

# POST MANGEMENT -  ADMIN
# View table with all posts and manage posts: Admin only
@dashboard.route("/dashboard/manage_all_posts")
@login_required
def posts_table():
    if current_user.type not in ["admin","super_admin"]:
        flash("拒绝访问：你不是管理员！")
        return redirect(url_for('website.home'))
    
    all_blog_posts_submitted = Blog_Posts.query.order_by(Blog_Posts.id)
    return render_template("dashboard/posts_table.html", logged_in=current_user.is_authenticated, all_blog_posts_submitted=all_blog_posts_submitted)