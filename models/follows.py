"""
关注关系模型 - 实现用户关注博主功能
"""
from app.extensions import db
from datetime import datetime


class Blog_Follows(db.Model):
    """关注关系表"""
    __tablename__ = "blog_follows"
    
    id = db.Column(db.Integer, primary_key=True)
    follower_id = db.Column(db.Integer, db.ForeignKey('blog_user.id'), nullable=False)  # 关注者ID
    following_id = db.Column(db.Integer, db.ForeignKey('blog_user.id'), nullable=False)  # 被关注者ID
    date_created = db.Column(db.DateTime, default=datetime.utcnow)
    
    # 建立关系
    follower = db.relationship('Blog_User', foreign_keys=[follower_id], backref='following_list')
    following = db.relationship('Blog_User', foreign_keys=[following_id], backref='followers_list')
    
    # 确保不能重复关注同一个人
    __table_args__ = (db.UniqueConstraint('follower_id', 'following_id', name='unique_follow'),)
    
    def __repr__(self):
        return f"<Follow: {self.follower_id} -> {self.following_id}>"

