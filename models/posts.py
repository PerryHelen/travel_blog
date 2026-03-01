from app.extensions import db
from datetime import datetime

class Blog_Posts(db.Model):
    __tablename__ = "blog_posts"
    id = db.Column(db.Integer, primary_key=True)
    date_submitted = db.Column(db.DateTime, default=datetime.utcnow)
    date_to_post = db.Column(db.DateTime, default=datetime.utcnow)
    title = db.Column(db.String(200), nullable=True, default="无标题博客")  # 改为可选
    intro = db.Column(db.String(200), nullable=True, default="")  # 改为可选
    body = db.Column(db.Text, nullable=True, default="")  # 改为可选
    summary = db.Column(db.Text, nullable=True)  # AI生成的摘要
    picture_v = db.Column(db.String(200))
    picture_h = db.Column(db.String(200))
    picture_s = db.Column(db.String(200))
    picture_alt = db.Column(db.String(200))
    meta_tag = db.Column(db.String(200))
    title_tag = db.Column(db.String(200))
    admin_approved = db.Column(db.String(5), default="FALSE")
    # featured is not being used at the moment, in the future can be used to 'feature' a post on a top modal, or similar
    featured = db.Column(db.String(5), default="FALSE")
    likes = db.relationship('Blog_Likes', backref='post')
    comments = db.relationship('Blog_Comments', backref='target_post')
    replies = db.relationship('Blog_Replies', backref='target_post')
    bookmarks = db.relationship('Blog_Bookmarks', backref='post')
    reposts = db.relationship('Blog_Reposts', backref='post')
    author_id = db.Column(db.Integer, db.ForeignKey('blog_user.id'))
    theme_id = db.Column(db.Integer, db.ForeignKey('blog_theme.id'))
    
    def __repr__(self):
        return f"<Post {self.id}: {self.title}, Theme: {self.theme_id}>"
