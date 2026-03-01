from datetime import datetime
from flask_wtf import FlaskForm 
from flask_wtf.file import FileField
from wtforms import StringField, SubmitField, DateTimeField, SelectField
from wtforms.validators import DataRequired, Optional
from flask_ckeditor import CKEditorField

def coerce_theme(value):
    """处理主题字段的转换，允许None值"""
    if value is None or value == '':
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None

class The_Posts(FlaskForm):
    theme = SelectField(u'主题', coerce=coerce_theme, validators=[Optional()])  # 主题可选
    author = StringField("作者")
    date = DateTimeField('日期', default=datetime.now, format='%Y-%m-%d', validators=[Optional()])
    title = StringField("标题", validators=[Optional()])  # 标题改为可选
    intro = StringField("简介", validators=[Optional()])  # 改为可选
    body = CKEditorField("正文", validators=[Optional()])  # 改为可选

    picture_v = FileField("竖版图片", validators=[Optional()])
    picture_v_size = StringField("竖版图片文件大小", validators=[Optional()])

    picture_h = FileField("横版图片", validators=[Optional()])
    picture_h_size = StringField("横版图片文件大小", validators=[Optional()])

    picture_s = FileField("方形图片", validators=[Optional()])
    picture_s_size = StringField("方形图片文件大小", validators=[Optional()])
    
    picture_alt = StringField("图片替代文本", validators=[Optional()])
    meta_tag = StringField("Meta 标签", validators=[Optional()])
    title_tag = StringField("标题标签", validators=[Optional()])
    submit = SubmitField("提交")
