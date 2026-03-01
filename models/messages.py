from app.extensions import db
from datetime import datetime

class Blog_Messages(db.Model):
    __tablename__ = "blog_messages"
    id = db.Column(db.Integer, primary_key=True)
    date_submitted = db.Column(db.DateTime, default=datetime.utcnow)
    sender_id = db.Column(db.Integer, db.ForeignKey('blog_user.id'))
    receiver_id = db.Column(db.Integer, db.ForeignKey('blog_user.id'))
    content = db.Column(db.Text, nullable=False)
    read = db.Column(db.String(5), default="FALSE")  # "TRUE" or "FALSE"
    
    # 关系
    sender = db.relationship('Blog_User', foreign_keys=[sender_id], backref='sent_messages')
    receiver = db.relationship('Blog_User', foreign_keys=[receiver_id], backref='received_messages')

    def __repr__(self):
        return f"<Message: {self.sender_id} -> {self.receiver_id}>"

