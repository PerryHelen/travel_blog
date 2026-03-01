from app.extensions import db
from datetime import datetime

class Blog_Reposts(db.Model):
    __tablename__ = "blog_reposts"
    id = db.Column(db.Integer, primary_key=True)
    date_submitted = db.Column(db.DateTime, default=datetime.utcnow)
    post_id = db.Column(db.Integer, db.ForeignKey('blog_posts.id'))
    user_id = db.Column(db.Integer, db.ForeignKey('blog_user.id'))  # 转发者
    target_user_id = db.Column(db.Integer, db.ForeignKey('blog_user.id'), nullable=True)  # 转发给谁（可选）
    # 转发时可以添加评论
    comment = db.Column(db.String(500), nullable=True)
    
    # 关系
    target_user = db.relationship('Blog_User', foreign_keys=[target_user_id], backref='received_reposts')

    def __repr__(self):
        return f"<Repost: User {self.user_id} reposted Post {self.post_id} to User {self.target_user_id}>"

