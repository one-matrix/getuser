# -*- coding: utf-8 -*-
# Copyright (c) 2025 relakkes@gmail.com
#
# This file is part of MediaCrawler project.
# Repository: https://github.com/NanmiCoder/MediaCrawler/blob/main/database/models.py
# GitHub: https://github.com/NanmiCoder
# Licensed under NON-COMMERCIAL LEARNING LICENSE 1.1
#
# 声明：本代码仅供学习和研究目的使用。使用者应遵守以下原则：
# 1. 不得用于任何商业用途。
# 2. 使用时应遵守目标平台的使用条款和robots.txt规则。
# 3. 不得进行大规模爬取或对平台造成运营干扰。
# 4. 应合理控制请求频率，避免给目标平台带来不必要的负担。
# 5. 不得用于任何非法或不当的用途。
#
# 详细许可条款请参阅项目根目录下的LICENSE文件。
# 使用本代码即表示您同意遵守上述原则和LICENSE中的所有条款。

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    Float,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

Base = declarative_base()

class BilibiliVideo(Base):
    __tablename__ = 'bilibili_video'
    id = Column(Integer, primary_key=True, comment='主键ID')
    video_id = Column(BigInteger, nullable=False, index=True, unique=True, comment='视频ID')
    video_url = Column(Text, nullable=False, comment='视频URL')
    user_id = Column(BigInteger, index=True, comment='用户ID')
    nickname = Column(Text, comment='用户昵称')
    avatar = Column(Text, comment='用户头像')
    liked_count = Column(Integer, comment='点赞数')
    add_ts = Column(BigInteger, comment='添加时间戳')
    last_modify_ts = Column(BigInteger, comment='最后修改时间戳')
    video_coin_count = Column(String(255), default='0', comment='硬币数')
    video_danmaku = Column(String(255), default='0', comment='弹幕数')
    video_comment = Column(String(255), default='0', comment='评论数')
    video_cover_url = Column(Text, comment='视频封面URL')
    source_keyword = Column(Text, default='', comment='来源关键词')

class BilibiliVideoComment(Base):
    __tablename__ = 'bilibili_video_comment'
    id = Column(Integer, primary_key=True, comment='主键ID')
    user_id = Column(String(255), comment='用户ID')
    nickname = Column(Text, comment='用户昵称')
    sex = Column(String(255), default='', comment='性别')
    sign = Column(Text, comment='签名')
    avatar = Column(Text, comment='头像')
    add_ts = Column(BigInteger, comment='添加时间戳')
    last_modify_ts = Column(BigInteger, comment='最后修改时间戳')
    comment_id = Column(BigInteger, index=True, comment='评论ID')
    video_id = Column(BigInteger, index=True, comment='视频ID')
    content = Column(Text, comment='评论内容')
    create_time = Column(BigInteger, comment='创建时间戳')
    sub_comment_count = Column(String(255), default='0', comment='子评论数')
    parent_comment_id = Column(String(255), comment='父评论ID')
    like_count = Column(String(255), default='0', comment='点赞数')
    task_id = Column(String(255), index=True, default='', comment='任务ID')

class BilibiliUpInfo(Base):
    __tablename__ = 'bilibili_up_info'
    id = Column(Integer, primary_key=True, comment='主键ID')
    user_id = Column(BigInteger, index=True, comment='用户ID')
    nickname = Column(Text, comment='用户昵称')
    sex = Column(String(255), default='', comment='性别')
    sign = Column(Text, comment='签名')
    avatar = Column(Text, comment='头像')
    add_ts = Column(BigInteger, comment='添加时间戳')
    last_modify_ts = Column(BigInteger, comment='最后修改时间戳')
    total_fans = Column(Integer, comment='总粉丝数')
    total_liked = Column(Integer, comment='总获赞数')
    user_rank = Column(Integer, comment='用户等级')
    is_official = Column(Integer, comment='是否官方认证')

class BilibiliContactInfo(Base):
    __tablename__ = 'bilibili_contact_info'
    id = Column(Integer, primary_key=True, comment='主键ID')
    up_id = Column(BigInteger, index=True, comment='UP主ID')
    fan_id = Column(BigInteger, index=True, comment='粉丝ID')
    up_name = Column(Text, comment='UP主名称')
    fan_name = Column(Text, comment='粉丝名称')
    up_sign = Column(Text, comment='UP主签名')
    fan_sign = Column(Text, comment='粉丝签名')
    up_avatar = Column(Text, comment='UP主头像')
    fan_avatar = Column(Text, comment='粉丝头像')
    add_ts = Column(BigInteger, comment='添加时间戳')
    last_modify_ts = Column(BigInteger, comment='最后修改时间戳')

class BilibiliUpDynamic(Base):
    __tablename__ = 'bilibili_up_dynamic'
    id = Column(Integer, primary_key=True, comment='主键ID')
    dynamic_id = Column(BigInteger, index=True, comment='动态ID')
    user_id = Column(String(255), comment='用户ID')
    user_name = Column(Text, comment='用户名称')
    text = Column(Text, comment='动态内容')
    type = Column(String(255), default='', comment='动态类型')
    pub_ts = Column(BigInteger, comment='发布时间戳')
    total_comments = Column(Integer, comment='总评论数')
    total_forwards = Column(Integer, comment='总转发数')
    total_liked = Column(Integer, comment='总点赞数')
    add_ts = Column(BigInteger, comment='添加时间戳')
    last_modify_ts = Column(BigInteger, comment='最后修改时间戳')

class DouyinAweme(Base):
    __tablename__ = 'douyin_aweme'
    id = Column(Integer, primary_key=True, comment='主键ID')
    user_id = Column(String(255), comment='用户ID')
    sec_uid = Column(String(255), comment='安全用户ID')
    short_user_id = Column(String(255), comment='短用户ID')
    user_unique_id = Column(String(255), comment='用户唯一ID')
    nickname = Column(Text, comment='用户昵称')
    avatar = Column(Text, comment='用户头像')
    user_signature = Column(Text, comment='用户签名')
    ip_location = Column(String(255), default='', comment='IP地址位置')
    add_ts = Column(BigInteger, comment='添加时间戳')
    last_modify_ts = Column(BigInteger, comment='最后修改时间戳')
    aweme_id = Column(String(255), index=True, comment='作品ID')
    aweme_type = Column(String(255), default='', comment='作品类型')
    title = Column(Text, comment='作品标题')
    desc = Column(Text, comment='作品描述')
    create_time = Column(BigInteger, index=True, comment='创建时间戳')
    liked_count = Column(String(255), default='0', comment='点赞数')
    comment_count = Column(String(255), default='0', comment='评论数')
    share_count = Column(String(255), default='0', comment='分享数')
    collected_count = Column(String(255), default='0', comment='收藏数')
    aweme_url = Column(Text, comment='作品URL')
    cover_url = Column(Text, comment='封面URL')
    video_download_url = Column(Text, comment='视频下载URL')
    music_download_url = Column(Text, comment='音乐下载URL')
    note_download_url = Column(Text, comment='笔记下载URL')
    source_keyword = Column(Text, default='', comment='来源关键词')
    task_id = Column(String(255), index=True, default='', comment='任务ID')

class DouyinAwemeComment(Base):
    __tablename__ = 'douyin_aweme_comment'
    id = Column(Integer, primary_key=True, comment='主键ID')
    user_id = Column(String(255), comment='用户ID')
    sec_uid = Column(String(255), comment='安全用户ID')
    short_user_id = Column(String(255), comment='短用户ID')
    user_unique_id = Column(String(255), comment='用户唯一ID')
    nickname = Column(Text, comment='用户昵称')
    avatar = Column(Text, comment='用户头像')
    user_signature = Column(Text, comment='用户签名')
    ip_location = Column(Text, comment='IP地址位置')
    add_ts = Column(BigInteger, comment='添加时间戳')
    last_modify_ts = Column(BigInteger, comment='最后修改时间戳')
    comment_id = Column(String(255), index=True, comment='评论ID')
    aweme_id = Column(String(255), index=True, comment='作品ID')
    content = Column(Text, comment='评论内容')
    create_time = Column(BigInteger, comment='创建时间戳')
    sub_comment_count = Column(String(255), default='0', comment='子评论数')
    parent_comment_id = Column(String(255), comment='父评论ID')
    like_count = Column(String(255), default='0', comment='点赞数')
    pictures = Column(Text, default='', comment='图片')
    task_id = Column(String(255), index=True, default='', comment='任务ID')

class DyCreator(Base):
    __tablename__ = 'dy_creator'
    id = Column(Integer, primary_key=True, comment='主键ID')
    user_id = Column(String(255), comment='用户ID')
    nickname = Column(Text, comment='用户昵称')
    avatar = Column(Text, comment='用户头像')
    ip_location = Column(Text, comment='IP地址位置')
    add_ts = Column(BigInteger, comment='添加时间戳')
    last_modify_ts = Column(BigInteger, comment='最后修改时间戳')
    desc = Column(Text, comment='描述')
    gender = Column(String(255), default='', comment='性别')
    follows = Column(String(255), default='0', comment='关注数')
    fans = Column(String(255), default='0', comment='粉丝数')
    interaction = Column(String(255), default='0', comment='互动数')
    videos_count = Column(String(255), default='0', comment='视频数量')

class KuaishouVideo(Base):
    __tablename__ = 'kuaishou_video'
    id = Column(Integer, primary_key=True, comment='主键ID')
    user_id = Column(String(64), comment='用户ID')
    nickname = Column(Text, comment='用户昵称')
    avatar = Column(Text, comment='用户头像')
    add_ts = Column(BigInteger, comment='添加时间戳')
    last_modify_ts = Column(BigInteger, comment='最后修改时间戳')
    video_id = Column(String(255), index=True, comment='视频ID')
    video_type = Column(String(255), default='', comment='视频类型')
    title = Column(Text, comment='视频标题')
    desc = Column(Text, comment='视频描述')
    create_time = Column(BigInteger, index=True, comment='创建时间戳')
    liked_count = Column(String(255), default='0', comment='点赞数')
    viewd_count = Column(String(255), default='0', comment='观看数')
    video_url = Column(Text, comment='视频URL')
    video_cover_url = Column(Text, comment='视频封面URL')
    video_play_url = Column(Text, comment='视频播放URL')
    source_keyword = Column(Text, default='', comment='来源关键词')

class KuaishouVideoComment(Base):
    __tablename__ = 'kuaishou_video_comment'
    id = Column(Integer, primary_key=True, comment='主键ID')
    user_id = Column(Text, comment='用户ID')
    nickname = Column(Text, comment='用户昵称')
    avatar = Column(Text, comment='用户头像')
    add_ts = Column(BigInteger, comment='添加时间戳')
    last_modify_ts = Column(BigInteger, comment='最后修改时间戳')
    comment_id = Column(BigInteger, index=True, comment='评论ID')
    video_id = Column(String(255), index=True, comment='视频ID')
    content = Column(Text, comment='评论内容')
    create_time = Column(BigInteger, comment='创建时间戳')
    sub_comment_count = Column(String(255), default='0', comment='子评论数')
    task_id = Column(String(255), index=True, default='', comment='任务ID')

class WeiboNote(Base):
    __tablename__ = 'weibo_note'
    id = Column(Integer, primary_key=True, comment='主键ID')
    user_id = Column(String(255), comment='用户ID')
    nickname = Column(Text, comment='用户昵称')
    avatar = Column(Text, comment='用户头像')
    gender = Column(String(255), default='', comment='性别')
    profile_url = Column(Text, comment='个人主页URL')
    ip_location = Column(Text, default='', comment='IP地址位置')
    add_ts = Column(BigInteger, comment='添加时间戳')
    last_modify_ts = Column(BigInteger, comment='最后修改时间戳')
    note_id = Column(BigInteger, index=True, comment='笔记ID')
    content = Column(Text, comment='笔记内容')
    create_time = Column(BigInteger, index=True, comment='创建时间戳')
    create_date_time = Column(String(255), index=True, comment='创建日期时间')
    liked_count = Column(String(255), default='0', comment='点赞数')
    comments_count = Column(String(255), default='0', comment='评论数')
    shared_count = Column(String(255), default='0', comment='分享数')
    note_url = Column(Text, comment='笔记URL')
    source_keyword = Column(Text, default='', comment='来源关键词')

class WeiboNoteComment(Base):
    __tablename__ = 'weibo_note_comment'
    id = Column(Integer, primary_key=True, comment='主键ID')
    user_id = Column(String(255), comment='用户ID')
    nickname = Column(Text, comment='用户昵称')
    avatar = Column(Text, comment='用户头像')
    gender = Column(String(255), default='', comment='性别')
    profile_url = Column(Text, comment='个人主页URL')
    ip_location = Column(Text, default='', comment='IP地址位置')
    add_ts = Column(BigInteger, comment='添加时间戳')
    last_modify_ts = Column(BigInteger, comment='最后修改时间戳')
    comment_id = Column(BigInteger, index=True, comment='评论ID')
    note_id = Column(BigInteger, index=True, comment='笔记ID')
    content = Column(Text, comment='评论内容')
    create_time = Column(BigInteger, comment='创建时间戳')
    create_date_time = Column(String(255), index=True, comment='创建日期时间')
    comment_like_count = Column(String(255), default='0', comment='评论点赞数')
    sub_comment_count = Column(String(255), default='0', comment='子评论数')
    parent_comment_id = Column(String(255), comment='父评论ID')
    task_id = Column(String(255), index=True, default='', comment='任务ID')

class WeiboCreator(Base):
    __tablename__ = 'weibo_creator'
    id = Column(Integer, primary_key=True, comment='主键ID')
    user_id = Column(String(255), comment='用户ID')
    nickname = Column(Text, comment='用户昵称')
    avatar = Column(Text, comment='用户头像')
    ip_location = Column(Text, comment='IP地址位置')
    add_ts = Column(BigInteger, comment='添加时间戳')
    last_modify_ts = Column(BigInteger, comment='最后修改时间戳')
    desc = Column(Text, comment='描述')
    gender = Column(String(255), default='', comment='性别')
    follows = Column(String(255), default='0', comment='关注数')
    fans = Column(String(255), default='0', comment='粉丝数')
    tag_list = Column(Text, comment='标签列表')

class XhsCreator(Base):
    __tablename__ = 'xhs_creator'
    id = Column(Integer, primary_key=True, comment='主键ID')
    user_id = Column(String(255), comment='用户ID')
    nickname = Column(Text, comment='用户昵称')
    avatar = Column(Text, comment='用户头像')
    ip_location = Column(Text, comment='IP地址位置')
    add_ts = Column(BigInteger, comment='添加时间戳')
    last_modify_ts = Column(BigInteger, comment='最后修改时间戳')
    desc = Column(Text, comment='描述')
    gender = Column(String(255), default='', comment='性别')
    follows = Column(String(255), default='0', comment='关注数')
    fans = Column(String(255), default='0', comment='粉丝数')
    interaction = Column(String(255), default='0', comment='互动数')
    tag_list = Column(Text, comment='标签列表')

class XhsNote(Base):
    __tablename__ = 'xhs_note'
    id = Column(Integer, primary_key=True, comment='主键ID')
    user_id = Column(String(255), comment='用户ID')
    nickname = Column(Text, comment='用户昵称')
    avatar = Column(Text, comment='用户头像')
    ip_location = Column(Text, comment='IP地址位置')
    add_ts = Column(BigInteger, comment='添加时间戳')
    last_modify_ts = Column(BigInteger, comment='最后修改时间戳')
    note_id = Column(String(255), index=True, comment='笔记ID')
    type = Column(String(255), default='', comment='笔记类型')
    title = Column(Text, comment='笔记标题')
    desc = Column(Text, comment='笔记描述')
    video_url = Column(Text, comment='视频URL')
    time = Column(BigInteger, index=True, comment='时间戳')
    last_update_time = Column(BigInteger, comment='最后更新时间戳')
    liked_count = Column(String(255), default='0', comment='点赞数')
    collected_count = Column(String(255), default='0', comment='收藏数')
    comment_count = Column(String(255), default='0', comment='评论数')
    share_count = Column(String(255), default='0', comment='分享数')
    image_list = Column(Text, comment='图片列表')
    tag_list = Column(Text, comment='标签列表')
    note_url = Column(Text, comment='笔记URL')
    source_keyword = Column(Text, default='', comment='来源关键词')
    xsec_token = Column(String(255), default='', comment='Xsec Token')
    task_id = Column(String(255), index=True, default='', comment='任务ID')

class XhsNoteComment(Base):
    __tablename__ = 'xhs_note_comment'
    id = Column(Integer, primary_key=True, comment='主键ID')
    user_id = Column(String(255), comment='用户ID')
    nickname = Column(Text, comment='用户昵称')
    avatar = Column(Text, comment='用户头像')
    ip_location = Column(Text, comment='IP地址位置')
    add_ts = Column(BigInteger, comment='添加时间戳')
    last_modify_ts = Column(BigInteger, comment='最后修改时间戳')
    comment_id = Column(String(255), index=True, comment='评论ID')
    create_time = Column(BigInteger, index=True, comment='创建时间戳')
    note_id = Column(String(255), comment='笔记ID')
    content = Column(Text, comment='评论内容')
    sub_comment_count = Column(Integer, comment='子评论数')
    pictures = Column(Text, comment='图片')
    parent_comment_id = Column(String(255), comment='父评论ID')
    like_count = Column(String(255), default='0', comment='点赞数')
    task_id = Column(String(255), index=True, default='', comment='任务ID')

class TiebaNote(Base):
    __tablename__ = 'tieba_note'
    id = Column(Integer, primary_key=True, comment='主键ID')
    note_id = Column(String(644), index=True, comment='笔记ID')
    title = Column(Text, comment='笔记标题')
    desc = Column(Text, comment='笔记描述')
    note_url = Column(Text, comment='笔记URL')
    publish_time = Column(String(255), index=True, comment='发布时间')
    user_link = Column(Text, default='', comment='用户链接')
    user_nickname = Column(Text, default='', comment='用户昵称')
    user_avatar = Column(Text, default='', comment='用户头像')
    tieba_id = Column(String(255), default='', comment='贴吧ID')
    tieba_name = Column(Text, comment='贴吧名称')
    tieba_link = Column(Text, comment='贴吧链接')
    total_replay_num = Column(Integer, default=0, comment='总回复数')
    total_replay_page = Column(Integer, default=0, comment='总回复页数')
    ip_location = Column(Text, default='', comment='IP地址位置')
    add_ts = Column(BigInteger, comment='添加时间戳')
    last_modify_ts = Column(BigInteger, comment='最后修改时间戳')
    source_keyword = Column(Text, default='', comment='来源关键词')

class TiebaComment(Base):
    __tablename__ = 'tieba_comment'
    id = Column(Integer, primary_key=True, comment='主键ID')
    comment_id = Column(String(255), index=True, comment='评论ID')
    parent_comment_id = Column(String(255), default='', comment='父评论ID')
    content = Column(Text, comment='评论内容')
    user_link = Column(Text, default='', comment='用户链接')
    user_nickname = Column(Text, default='', comment='用户昵称')
    user_avatar = Column(Text, default='', comment='用户头像')
    tieba_id = Column(String(255), default='', comment='贴吧ID')
    tieba_name = Column(Text, comment='贴吧名称')
    tieba_link = Column(Text, comment='贴吧链接')
    publish_time = Column(String(255), index=True, comment='发布时间')
    ip_location = Column(Text, default='', comment='IP地址位置')
    sub_comment_count = Column(Integer, default=0, comment='子评论数')
    note_id = Column(String(255), index=True, comment='笔记ID')
    note_url = Column(Text, comment='笔记URL')
    add_ts = Column(BigInteger, comment='添加时间戳')
    last_modify_ts = Column(BigInteger, comment='最后修改时间戳')
    task_id = Column(String(255), index=True, default='', comment='任务ID')

class TiebaCreator(Base):
    __tablename__ = 'tieba_creator'
    id = Column(Integer, primary_key=True, comment='主键ID')
    user_id = Column(String(64), comment='用户ID')
    user_name = Column(Text, comment='用户名')
    nickname = Column(Text, comment='用户昵称')
    avatar = Column(Text, comment='用户头像')
    ip_location = Column(Text, comment='IP地址位置')
    add_ts = Column(BigInteger, comment='添加时间戳')
    last_modify_ts = Column(BigInteger, comment='最后修改时间戳')
    gender = Column(String(255), default='', comment='性别')
    follows = Column(String(255), default='0', comment='关注数')
    fans = Column(String(255), default='0', comment='粉丝数')
    registration_duration = Column(String(255), default='', comment='注册时长')

class ZhihuContent(Base):
    __tablename__ = 'zhihu_content'
    id = Column(Integer, primary_key=True, comment='主键ID')
    content_id = Column(String(64), index=True, comment='内容ID')
    content_type = Column(String(255), default='', comment='内容类型')
    content_text = Column(Text, comment='内容文本')
    content_url = Column(Text, comment='内容URL')
    question_id = Column(String(255), comment='问题ID')
    title = Column(Text, comment='标题')
    desc = Column(Text, comment='描述')
    created_time = Column(String(32), index=True, comment='创建时间')
    updated_time = Column(String(255), default='', comment='更新时间')
    voteup_count = Column(Integer, default=0, comment='赞同数')
    comment_count = Column(Integer, default=0, comment='评论数')
    source_keyword = Column(Text, comment='来源关键词')
    user_id = Column(String(255), comment='用户ID')
    user_link = Column(Text, comment='用户链接')
    user_nickname = Column(Text, comment='用户昵称')
    user_avatar = Column(Text, comment='用户头像')
    user_url_token = Column(String(255), default='', comment='用户URL Token')
    add_ts = Column(BigInteger, comment='添加时间戳')
    last_modify_ts = Column(BigInteger, comment='最后修改时间戳')

    # persist-1<persist1@126.com>
    # Reason: Fixed ORM model definition error, ensuring consistency with database table structure.
    # Side effects: None
    # Rollback strategy: Restore this line

class ZhihuComment(Base):
    __tablename__ = 'zhihu_comment'
    id = Column(Integer, primary_key=True, comment='主键ID')
    comment_id = Column(String(64), index=True, comment='评论ID')
    parent_comment_id = Column(String(64), comment='父评论ID')
    content = Column(Text, comment='评论内容')
    publish_time = Column(String(32), index=True, comment='发布时间')
    ip_location = Column(Text, comment='IP地址位置')
    sub_comment_count = Column(Integer, default=0, comment='子评论数')
    like_count = Column(Integer, default=0, comment='点赞数')
    dislike_count = Column(Integer, default=0, comment='点踩数')
    content_id = Column(String(64), index=True, comment='内容ID')
    content_type = Column(String(255), default='', comment='内容类型')
    user_id = Column(String(64), comment='用户ID')
    user_link = Column(Text, comment='用户链接')
    user_nickname = Column(Text, comment='用户昵称')
    user_avatar = Column(Text, comment='用户头像')
    add_ts = Column(BigInteger, comment='添加时间戳')
    last_modify_ts = Column(BigInteger, comment='最后修改时间戳')
    task_id = Column(String(255), index=True, default='', comment='任务ID')

class ZhihuCreator(Base):
    __tablename__ = 'zhihu_creator'
    id = Column(Integer, primary_key=True, comment='主键ID')
    user_id = Column(String(64), unique=True, index=True, comment='用户ID')
    user_link = Column(Text, comment='用户链接')
    user_nickname = Column(Text, comment='用户昵称')
    user_avatar = Column(Text, comment='用户头像')
    url_token = Column(String(255), default='', comment='URL Token')
    gender = Column(String(255), default='', comment='性别')
    ip_location = Column(Text, comment='IP地址位置')
    follows = Column(Integer, default=0, comment='关注数')
    fans = Column(Integer, default=0, comment='粉丝数')
    anwser_count = Column(Integer, default=0, comment='回答数')
    video_count = Column(Integer, default=0, comment='视频数')
    question_count = Column(Integer, default=0, comment='问题数')
    article_count = Column(Integer, default=0, comment='文章数')
    column_count = Column(Integer, default=0, comment='专栏数')
    get_voteup_count = Column(Integer, default=0, comment='获赞数')
    add_ts = Column(BigInteger, comment='添加时间戳')
    last_modify_ts = Column(BigInteger, comment='最后修改时间戳')


class TaskDataMapping(Base):
    """任务数据关联表 - 用于关联任务和爬取的数据"""
    __tablename__ = 'task_data_mapping'
    id = Column(Integer, primary_key=True, comment='主键ID')
    task_id = Column(String(255), index=True, comment='任务ID')
    platform = Column(String(20), comment='平台')
    data_type = Column(String(20), comment='数据类型: note, comment, video')
    data_id = Column(String(255), comment='数据ID')
    user_id = Column(String(255), comment='用户ID')
    nickname = Column(String(255), comment='用户昵称')
    title = Column(Text, comment='标题')
    content = Column(Text, comment='内容')
    url = Column(Text, comment='链接')
    add_ts = Column(BigInteger, comment='添加时间戳')

class CrawlerTaskModel(Base):
    """爬虫任务表 - 存储任务配置和状态"""
    __tablename__ = 'crawler_task'
    id = Column(String(255), primary_key=True, comment='任务ID')
    name = Column(String(255), nullable=False, comment='任务名称')
    platform = Column(String(20), nullable=False, comment='平台: xhs, douyin, kuaishou, weibo, zhihu, tieba, bilibili, x')
    keywords = Column(Text, default='', comment='关键词列表，JSON数组字符串')
    crawl_type = Column(String(20), default='search', comment='爬取类型: search, creator, trending, detail')
    data_types = Column(Text, default='["note","comment"]', comment='数据类型，JSON数组字符串')
    max_notes = Column(Integer, default=100, comment='预计获客数量')
    min_lead_score = Column(Integer, default=50, comment='最小线索评分')
    enable_lead_capture = Column(Integer, default=1, comment='是否启用获客')
    schedule_type = Column(String(20), default='once', comment='调度类型: once, interval, daily, weekly')
    schedule_time = Column(String(8), default='09:00', comment='调度执行时间(HH:MM),daily/weekly 类型生效')
    schedule_weekday = Column(Integer, default=1, comment='周几执行(1-7),weekly 类型生效')
    schedule_interval_seconds = Column(Integer, default=900, comment='间隔调度秒数,interval 类型生效')
    last_scheduled_ts = Column(BigInteger, default=0, comment='上次调度执行时间戳')
    next_scheduled_ts = Column(BigInteger, default=0, comment='下次调度执行时间戳')
    status = Column(String(20), default='pending', comment='状态: pending, running, paused, completed, failed, cancelled')
    total_crawled = Column(Integer, default=0, comment='已爬取数量')
    total_leads = Column(Integer, default=0, comment='已获客数量')
    created_ts = Column(BigInteger, comment='创建时间戳')
    updated_ts = Column(BigInteger, comment='更新时间戳')
    completed_ts = Column(BigInteger, comment='完成时间戳')
    error_message = Column(Text, default='', comment='错误信息')
    promo_config = Column(Text, default='', comment='推广配置JSON: 产品名称、推广链接、产品描述、价格信息、联系方式等')
    publish_time_type = Column(Integer, default=0, comment='发布时间过滤: 0=不限, 1=一天内, 7=一周内, 180=半年内')
    owner_user_id = Column(String(64), index=True, default='', comment='归属用户ID(数据隔离)')


class TaskLogModel(Base):
    """任务日志表 - 存储任务运行日志"""
    __tablename__ = 'task_log'
    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键ID')
    task_id = Column(String(255), index=True, nullable=False, comment='任务ID')
    level = Column(String(20), default='info', comment='日志级别: debug, info, warning, error, success')
    message = Column(Text, nullable=False, comment='日志内容')
    add_ts = Column(BigInteger, comment='添加时间戳')


class CustomerLead(Base):
    """获客线索表 - 存储识别出的潜在客户咨询"""
    __tablename__ = 'customer_lead'
    id = Column(Integer, primary_key=True, comment='主键ID')
    task_id = Column(String(255), index=True, comment='任务ID')
    platform = Column(String(20), comment='平台: xhs, douyin, kuaishou, weibo, zhihu, tieba, bilibili')
    data_type = Column(String(20), comment='数据类型: note, comment, video, answer')
    data_id = Column(String(255), comment='原始数据ID')
    user_id = Column(String(255), index=True, comment='用户ID')
    sec_uid = Column(String(255), default='', comment='安全用户ID（抖音等平台主页链接用）')
    nickname = Column(String(255), comment='用户昵称')
    avatar = Column(Text, comment='用户头像')
    ip_location = Column(String(255), default='', comment='IP地址位置')
    content = Column(Text, comment='咨询内容')
    title = Column(Text, comment='帖子标题')
    url = Column(Text, comment='链接')
    matched_keywords = Column(Text, comment='匹配到的关键词')
    intent_type = Column(String(50), comment='意图类型: inquiry, recommendation, comparison, purchase')
    lead_score = Column(Integer, default=0, comment='线索评分 0-100')
    status = Column(String(20), default='new', comment='状态: new, contacted, qualified, converted, ignored')
    notes = Column(Text, comment='备注')
    add_ts = Column(BigInteger, comment='添加时间戳')
    last_modify_ts = Column(BigInteger, comment='最后修改时间戳')
    create_time = Column(BigInteger, comment='评论真实创建时间戳(秒)')
    owner_user_id = Column(String(64), index=True, default='', comment='归属用户ID(数据隔离)')
    # 源视频/作品信息(评论场景下,记录该评论所属的视频/作品,方便回复评论时知道上下文)
    source_aweme_id = Column(String(255), default='', comment='源视频/作品ID')
    source_video_title = Column(Text, default='', comment='源视频标题')
    source_video_desc = Column(Text, default='', comment='源视频描述')
    source_video_url = Column(Text, default='', comment='源视频链接')
    source_cover_url = Column(Text, default='', comment='源视频封面URL')
    source_author_nickname = Column(String(255), default='', comment='源视频作者昵称')
    # 增强字段(客户需求:支持复制和打开链接)
    comment_url = Column(Text, default='', comment='原评论链接')
    profile_url = Column(Text, default='', comment='用户主页链接')
    platform_display_id = Column(String(255), default='', comment='平台内可搜索用户ID(如抖音号/小红书号)')


class OutreachRecord(Base):
    """触达记录表 - 存储私信发送记录"""
    __tablename__ = 'outreach_record'
    id = Column(Integer, primary_key=True, comment='主键ID')
    task_id = Column(String(255), index=True, comment='任务ID')
    outreach_task_id = Column(String(255), index=True, comment='触达任务ID')
    platform = Column(String(20), comment='平台: douyin, xhs, kuaishou, weibo')
    user_id = Column(String(255), index=True, comment='目标用户ID')
    sec_uid = Column(String(255), comment='安全用户ID')
    nickname = Column(String(255), comment='用户昵称')
    avatar = Column(Text, comment='用户头像')
    user_url = Column(Text, comment='用户主页链接')
    message_content = Column(Text, comment='发送的消息内容')
    status = Column(String(20), default='pending', comment='发送状态: pending, success, failed')
    error_message = Column(Text, comment='错误信息')
    screenshot = Column(String(255), comment='发送结果截图文件名')
    send_time = Column(BigInteger, comment='发送时间戳')
    add_ts = Column(BigInteger, comment='添加时间戳')
    owner_user_id = Column(String(64), index=True, default='', comment='归属用户ID(数据隔离)')


class OutreachTaskModel(Base):
    """触达任务表 - 存储私信触达任务的完整状态"""
    __tablename__ = 'outreach_task'
    id = Column(String(64), primary_key=True, comment='触达任务ID')
    user_id = Column(String(255), index=True, comment='目标用户ID')
    sec_uid = Column(String(255), comment='安全用户ID')
    platform = Column(String(20), default='douyin', comment='平台: douyin, xhs')
    content = Column(Text, comment='发送的消息内容')
    nickname = Column(String(255), default='', comment='用户昵称')
    status = Column(String(20), default='pending', comment='状态: pending, running, success, failed, cancelled')
    error_message = Column(Text, default='', comment='错误信息')
    result = Column(Text, default='{}', comment='执行结果JSON')
    steps = Column(Text, default='[]', comment='步骤列表JSON')
    logs = Column(Text, default='[]', comment='日志列表JSON')
    screenshot = Column(String(255), default='', comment='结果截图文件名')
    created_at = Column(BigInteger, comment='创建时间戳')
    updated_at = Column(BigInteger, comment='更新时间戳')
    owner_user_id = Column(String(64), index=True, default='', comment='归属用户ID(数据隔离)')


class DouyinDmRecord(Base):
    """抖音私信发送记录表"""
    __tablename__ = 'douyin_dm_record'
    id = Column(Integer, primary_key=True, comment='主键ID')
    sec_uid = Column(String(255), index=True, comment='目标用户sec_uid')
    user_id = Column(String(255), comment='目标用户ID')
    nickname = Column(String(255), comment='用户昵称')
    message = Column(Text, comment='发送的私信内容')
    aweme_id = Column(String(255), comment='来源视频ID')
    success = Column(Integer, default=0, comment='是否发送成功: 0失败, 1成功')
    error = Column(Text, default='', comment='错误信息')
    task_id = Column(String(255), index=True, default='', comment='任务ID')
    add_ts = Column(BigInteger, comment='添加时间戳')


class AutoOutreachJobModel(Base):
    """自动获客任务表 - 持久化后台运行状态"""
    __tablename__ = 'auto_outreach_job'
    id = Column(Integer, primary_key=True, comment='主键ID')
    job_id = Column(String(64), unique=True, index=True, comment='任务唯一ID')
    task_id = Column(String(255), index=True, comment='关联的爬虫任务ID')
    platform = Column(String(20), default='douyin', comment='平台')
    intent_level = Column(String(20), default='high', comment='意向等级')
    status = Column(String(20), default='running', comment='状态: running, completed, cancelled, failed')
    total = Column(Integer, default=0, comment='总目标数')
    completed = Column(Integer, default=0, comment='已完成数')
    success = Column(Integer, default=0, comment='成功数')
    failed = Column(Integer, default=0, comment='失败数')
    skipped = Column(Integer, default=0, comment='跳过数')
    results = Column(Text, default='[]', comment='发送结果JSON')
    outreach_list = Column(Text, default='[]', comment='目标用户列表JSON')
    auto_send = Column(Integer, default=1, comment='是否自动发送')
    interval_seconds = Column(Integer, default=90, comment='发送间隔秒数')
    current_index = Column(Integer, default=0, comment='当前发送到第几个')
    error_message = Column(Text, default='', comment='错误信息')
    created_at = Column(BigInteger, comment='创建时间戳')
    finished_at = Column(BigInteger, default=0, comment='完成时间戳')
    updated_at = Column(BigInteger, comment='更新时间戳')
    data_source = Column(String(20), default='comment', comment='数据来源: customer_lead=客户线索, comment=评论分析')
    owner_user_id = Column(String(64), index=True, default='', comment='归属用户ID(数据隔离)')


# ==================== 线索商业化相关表 ====================

class BusinessUser(Base):
    """业务用户表 - 存储客户(家具公司)和销售人员信息"""
    __tablename__ = 'business_user'
    id = Column(String(64), primary_key=True, comment='业务用户ID')
    username = Column(String(255), unique=True, comment='登录账号')
    password_hash = Column(String(255), comment='密码哈希')
    nickname = Column(String(255), comment='显示名称')
    role = Column(String(20), default='customer', comment='角色: customer=客户(家具公司), sales=销售, admin=管理员')
    company_name = Column(String(255), default='', comment='公司名称(客户用)')
    contact_phone = Column(String(255), default='', comment='联系电话')
    contact_email = Column(String(255), default='', comment='联系邮箱')
    balance = Column(BigInteger, default=0, comment='账户余额(分,便于精确计算)')
    total_spent = Column(BigInteger, default=0, comment='累计消费(分)')
    status = Column(String(20), default='active', comment='状态: active, disabled, deleted')
    # 销售特有字段
    sales_region = Column(String(255), default='', comment='负责地域(销售用,逗号分隔)')
    sales_quota = Column(Integer, default=100, comment='每日线索配额(销售用)')
    # 客户特有字段
    webhook_url = Column(Text, default='', comment='Webhook推送地址(客户用)')
    api_key = Column(String(255), default='', comment='API密钥(客户用)')
    auto_push = Column(Integer, default=0, comment='是否自动推送新线索: 0关闭, 1开启')
    # 归属和统计
    owner_user_id = Column(String(64), index=True, default='', comment='归属系统用户ID')
    assigned_leads_count = Column(Integer, default=0, comment='已分配线索数')
    converted_leads_count = Column(Integer, default=0, comment='已转化线索数')
    created_ts = Column(BigInteger, comment='创建时间戳')
    updated_ts = Column(BigInteger, comment='更新时间戳')
    last_login_ts = Column(BigInteger, default=0, comment='最后登录时间戳')


class LeadPackage(Base):
    """线索包表 - 打包销售给客户的线索组合"""
    __tablename__ = 'lead_package'
    id = Column(String(64), primary_key=True, comment='线索包ID')
    name = Column(String(255), comment='包名')
    description = Column(Text, default='', comment='描述')
    platform = Column(String(20), default='', comment='平台筛选')
    task_id = Column(String(255), default='', comment='任务筛选')
    min_score = Column(Integer, default=0, comment='最低意向分')
    max_score = Column(Integer, default=100, comment='最高意向分')
    level = Column(String(20), default='', comment='意向等级: high/medium/low/all')
    ip_location = Column(String(255), default='', comment='地域筛选')
    keyword = Column(String(255), default='', comment='关键词筛选')
    total_count = Column(Integer, default=0, comment='线索总数')
    available_count = Column(Integer, default=0, comment='可售数量')
    sold_count = Column(Integer, default=0, comment='已售数量')
    price_per_lead = Column(Integer, default=0, comment='单价(分)')
    total_price = Column(Integer, default=0, comment='总价(分)')
    expire_days = Column(Integer, default=90, comment='有效期天数')
    status = Column(String(20), default='draft', comment='状态: draft/active/sold_out/discontinued')
    owner_user_id = Column(String(64), index=True, default='', comment='归属系统用户ID')
    created_ts = Column(BigInteger, comment='创建时间戳')
    updated_ts = Column(BigInteger, comment='更新时间戳')
    publish_ts = Column(BigInteger, default=0, comment='发布时间戳')


class LeadAssignment(Base):
    """线索分配记录表 - 记录线索分配给客户/销售的历史"""
    __tablename__ = 'lead_assignment'
    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键ID')
    lead_id = Column(Integer, index=True, comment='线索ID(CustomerLead.id)')
    package_id = Column(String(64), default='', comment='线索包ID')
    business_user_id = Column(String(64), index=True, comment='分配给的业务用户ID')
    assign_type = Column(String(20), default='purchase', comment='分配类型: purchase=购买, manual=手动分配, auto=自动分配')
    price_paid = Column(Integer, default=0, comment='支付金额(分)')
    status = Column(String(20), default='assigned', comment='状态: assigned/used/expired/refunded')
    expire_ts = Column(BigInteger, default=0, comment='过期时间戳')
    assigned_ts = Column(BigInteger, comment='分配时间戳')
    used_ts = Column(BigInteger, default=0, comment='使用时间戳')
    owner_user_id = Column(String(64), index=True, default='', comment='归属系统用户ID')


class FollowUpRecord(Base):
    """跟进记录表 - 销售跟进线索的记录"""
    __tablename__ = 'follow_up_record'
    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键ID')
    lead_id = Column(Integer, index=True, comment='线索ID')
    lead_assignment_id = Column(Integer, default=0, comment='分配记录ID')
    business_user_id = Column(String(64), index=True, comment='跟进人ID(销售)')
    action_type = Column(String(20), default='call', comment='跟进方式: call=电话, message=私信, visit=拜访, wechat=微信')
    action_ts = Column(BigInteger, comment='跟进时间戳')
    result = Column(String(20), default='pending', comment='跟进结果: pending=待跟进, contacted=已联系, interested=有意向, not_interested=无意向, converted=已成交, failed=失败')
    notes = Column(Text, default='', comment='跟进备注')
    next_follow_ts = Column(BigInteger, default=0, comment='下次跟进时间戳')
    created_ts = Column(BigInteger, comment='创建时间戳')
    owner_user_id = Column(String(64), index=True, default='', comment='归属系统用户ID')


class PurchaseOrder(Base):
    """购买订单表 - 客户购买线索包的订单"""
    __tablename__ = 'purchase_order'
    id = Column(String(64), primary_key=True, comment='订单ID')
    package_id = Column(String(64), index=True, comment='线索包ID')
    business_user_id = Column(String(64), index=True, comment='买家ID')
    lead_count = Column(Integer, default=0, comment='购买线索数')
    total_price = Column(Integer, default=0, comment='订单金额(分)')
    payment_method = Column(String(20), default='balance', comment='支付方式: balance=余额, offline=线下转账')
    status = Column(String(20), default='pending', comment='订单状态: pending/paid/completed/cancelled/refunded')
    paid_ts = Column(BigInteger, default=0, comment='支付时间戳')
    completed_ts = Column(BigInteger, default=0, comment='完成时间戳')
    created_ts = Column(BigInteger, comment='创建时间戳')
    owner_user_id = Column(String(64), index=True, default='', comment='归属系统用户ID')


class ApiClient(Base):
    """API客户端表 - 对接客户CRM系统的配置"""
    __tablename__ = 'api_client'
    id = Column(String(64), primary_key=True, comment='API客户端ID')
    name = Column(String(255), comment='客户端名称')
    business_user_id = Column(String(64), index=True, comment='关联业务用户ID')
    api_key = Column(String(255), unique=True, comment='API密钥')
    api_secret = Column(String(255), comment='API密钥密码')
    webhook_url = Column(Text, default='', comment='推送地址')
    callback_url = Column(Text, default='', comment='回调地址(接收客户状态更新)')
    # 筛选条件(JSON)
    filters = Column(Text, default='{}', comment='推送筛选条件JSON: platform/min_score/ip_location等')
    push_mode = Column(String(20), default='batch', comment='推送模式: batch=批量, realtime=实时')
    push_interval = Column(Integer, default=300, comment='批量推送间隔(秒)')
    status = Column(String(20), default='active', comment='状态: active/disabled')
    last_push_ts = Column(BigInteger, default=0, comment='最后推送时间戳')
    total_pushed = Column(Integer, default=0, comment='累计推送数')
    owner_user_id = Column(String(64), index=True, default='', comment='归属系统用户ID')
    created_ts = Column(BigInteger, comment='创建时间戳')
    updated_ts = Column(BigInteger, comment='更新时间戳')


class UserNeedAnalysis(Base):
    """用户需求分析表 - 持久化需求分析结果,支持历史回看"""
    __tablename__ = 'user_need_analysis'
    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键ID')
    lead_id = Column(Integer, index=True, comment='关联线索ID(CustomerLead.id)')
    task_id = Column(String(64), index=True, comment='关联任务ID')
    user_id = Column(String(128), index=True, comment='平台用户ID')
    nickname = Column(String(255), default='', comment='用户昵称')
    content = Column(Text, default='', comment='原始评论内容')
    need_type = Column(String(32), default='general', comment='需求类型: product_inquiry/price_sensitive/tutorial_request/cooperation/frustration/comparison/general')
    need_type_name = Column(String(64), default='', comment='需求类型中文名')
    pain_points = Column(Text, default='[]', comment='痛点列表JSON')
    need_summary = Column(Text, default='', comment='需求摘要')
    pitch = Column(Text, default='', comment='推荐话术')
    owner_user_id = Column(String(64), index=True, default='', comment='归属系统用户ID(数据隔离)')
    created_ts = Column(BigInteger, comment='创建时间戳')


class AdContent(Base):
    """广告内容表 - 持久化生成的文案结果,支持历史回看和复用"""
    __tablename__ = 'ad_content'
    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键ID')
    lead_id = Column(Integer, index=True, comment='关联线索ID')
    task_id = Column(String(64), index=True, comment='关联任务ID')
    user_id = Column(String(128), index=True, comment='平台用户ID')
    nickname = Column(String(255), default='', comment='用户昵称')
    need_type = Column(String(32), default='general', comment='需求类型')
    tone = Column(String(32), default='friendly', comment='语气: friendly/professional/passionate')
    direct_message = Column(Text, default='', comment='私信文案')
    comment_reply = Column(Text, default='', comment='评论回复文案')
    product_id = Column(String(64), default='', comment='关联产品ID(AdContentProduct.id)')
    product_name = Column(String(255), default='', comment='产品名称(冗余,便于历史展示)')
    promo_link = Column(Text, default='', comment='推广链接(已混淆)')
    used = Column(Boolean, default=False, comment='是否已用于触达')
    owner_user_id = Column(String(64), index=True, default='', comment='归属系统用户ID(数据隔离)')
    created_ts = Column(BigInteger, comment='创建时间戳')


class ProductInfo(Base):
    """产品库表 - 替代任务配置中的 promo_config,支持多产品管理和复用"""
    __tablename__ = 'product_info'
    id = Column(String(64), primary_key=True, comment='产品ID')
    name = Column(String(255), index=True, comment='产品名称')
    desc = Column(Text, default='', comment='产品描述')
    product_desc = Column(Text, default='', comment='详细产品说明(用于文案生成)')
    promo_link = Column(Text, default='', comment='推广链接')
    contact_wechat = Column(String(128), default='', comment='联系微信')
    price_info = Column(String(255), default='', comment='价格信息')
    discount_info = Column(String(255), default='', comment='优惠信息')
    free_quota = Column(String(128), default='', comment='免费额度')
    solution_desc = Column(Text, default='', comment='解决方案描述')
    tutorial_name = Column(String(255), default='', comment='教程名称')
    tutorial_desc = Column(Text, default='', comment='教程描述')
    cooperation_desc = Column(Text, default='', comment='合作描述')
    commission_rate = Column(String(64), default='', comment='佣金比例')
    category = Column(String(64), default='', comment='产品分类')
    status = Column(String(20), default='active', comment='状态: active/disabled')
    owner_user_id = Column(String(64), index=True, default='', comment='归属系统用户ID(数据隔离)')
    created_ts = Column(BigInteger, comment='创建时间戳')
    updated_ts = Column(BigInteger, comment='更新时间戳')


class Notification(Base):
    """站内消息表 - 系统通知/任务结果通知/线索提醒等"""
    __tablename__ = 'notification'
    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键ID')
    owner_user_id = Column(String(64), index=True, default='', comment='归属系统用户ID(数据隔离)')
    title = Column(String(255), nullable=False, comment='消息标题')
    content = Column(Text, default='', comment='消息内容')
    msg_type = Column(String(32), default='info', comment='消息类型: info/success/warning/error/lead/task')
    extra = Column(Text, default='{}', comment='附加数据JSON: lead_id/task_id/链接等')
    is_read = Column(Integer, default=0, comment='是否已读: 0=未读, 1=已读')
    created_ts = Column(BigInteger, comment='创建时间戳')


class IntentRule(Base):
    """意向识别规则表 - 替代 tasks.py 中的硬编码 STRONG_INTENT_SIGNALS/NOSTALGIA_PATTERNS 等

    支持运行时增删改查,无需重启服务即可调整评分规则。
    """
    __tablename__ = 'intent_rule'
    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键ID')
    rule_type = Column(String(32), index=True, nullable=False, comment='规则类型: strong_intent/industry_template/nostalgia/discussion/past_purchase')
    pattern = Column(String(255), nullable=False, comment='匹配模式(关键词/模板),模板用 {w} 占位核心词')
    action = Column(String(32), default='upgrade', comment='动作: upgrade=升级为高意向, downgrade=降级为低/中')
    target_level = Column(String(16), default='high', comment='目标等级: high/middle/low')
    score_delta = Column(Integer, default=0, comment='分数调整值(正=加分,负=减分)')
    score_cap = Column(Integer, default=0, comment='分数上限(降级规则用,0=不限制)')
    enabled = Column(Integer, default=1, comment='是否启用: 0=禁用, 1=启用')
    category = Column(String(64), default='general', comment='分类标签(便于管理)')
    note = Column(String(255), default='', comment='备注说明')
    owner_user_id = Column(String(64), index=True, default='', comment='归属系统用户ID(数据隔离)')
    created_ts = Column(BigInteger, comment='创建时间戳')
    updated_ts = Column(BigInteger, comment='更新时间戳')


class KeywordCategory(Base):
    """关键词分类表 - 关键词库,按分类组织,支持权重"""
    __tablename__ = 'keyword_category'
    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键ID')
    name = Column(String(128), nullable=False, comment='分类名称')
    keywords = Column(Text, default='[]', comment='关键词列表JSON')
    weight = Column(Integer, default=1, comment='权重(倍数)')
    category = Column(String(64), default='general', comment='上级分类')
    enabled = Column(Integer, default=1, comment='是否启用: 0=禁用, 1=启用')
    owner_user_id = Column(String(64), index=True, default='', comment='归属系统用户ID(数据隔离)')
    created_ts = Column(BigInteger, comment='创建时间戳')
    updated_ts = Column(BigInteger, comment='更新时间戳')


# ==================== X 官方 API 运营系统 ====================
#
# X 的外部 ID 均使用字符串，避免不同数据库对无符号大整数支持不一致。
# JSON 数据使用 Text 保存序列化字符串，确保 SQLite / MySQL / PostgreSQL
# 都可以通过当前 create_all 流程直接建表。


class XAccount(Base):
    """X OAuth 账号及写入审批状态。Token 字段只允许保存加密密文。"""
    __tablename__ = 'x_accounts'
    __table_args__ = (
        UniqueConstraint('owner_user_id', 'x_user_id', name='uq_x_accounts_owner_x_user'),
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment='内部账号ID')
    owner_user_id = Column(String(64), nullable=False, index=True, default='', comment='归属用户ID(数据隔离)')
    x_user_id = Column(String(64), nullable=False, index=True, comment='X用户ID')
    username = Column(String(255), nullable=False, default='', comment='X用户名')
    display_name = Column(String(255), default='', comment='X显示名称')
    account_type = Column(String(20), default='brand', comment='账号类型: brand/human/automated')
    access_token_encrypted = Column(Text, default='', comment='加密后的访问Token')
    refresh_token_encrypted = Column(Text, default='', comment='加密后的刷新Token')
    token_expires_at = Column(BigInteger, default=0, comment='Token过期时间戳(毫秒)')
    granted_scopes = Column(Text, default='[]', comment='OAuth授权范围JSON')
    automated_label_enabled = Column(Boolean, default=False, comment='是否启用自动账号标签')
    x_written_approval = Column(Boolean, default=False, comment='是否已录入X书面批准')
    approval_reference = Column(Text, default='', comment='批准工单、邮件或附件引用')
    write_enabled = Column(Boolean, default=False, comment='账号写入总开关')
    auto_reply_enabled = Column(Boolean, default=False, comment='账号自动回复开关')
    status = Column(String(20), default='active', comment='状态: active/revoked/disabled')
    last_sync_at = Column(BigInteger, default=0, comment='最后同步时间戳(毫秒)')
    last_error = Column(Text, default='', comment='最近一次账号或Token错误')
    created_at = Column(BigInteger, default=0, comment='创建时间戳(毫秒)')
    updated_at = Column(BigInteger, default=0, comment='更新时间戳(毫秒)')


class XRegion(Base):
    """X 趋势地域与读取预算配置。"""
    __tablename__ = 'x_regions'
    __table_args__ = (
        UniqueConstraint('owner_user_id', 'woeid', name='uq_x_regions_owner_woeid'),
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment='地域ID')
    owner_user_id = Column(String(64), nullable=False, index=True, default='', comment='归属用户ID(数据隔离)')
    woeid = Column(String(64), nullable=False, index=True, comment='X趋势地域WOEID')
    name = Column(String(255), nullable=False, comment='地域名称')
    country_code = Column(String(16), default='', comment='国家或地区代码')
    language = Column(String(32), default='', comment='主要语言')
    timezone = Column(String(64), default='UTC', comment='地域时区')
    poll_interval_seconds = Column(Integer, default=900, comment='趋势轮询间隔秒数')
    daily_request_budget = Column(Integer, default=0, comment='每日读取请求预算，0表示未单独限制')
    enabled = Column(Boolean, default=True, comment='是否启用轮询')
    last_polled_at = Column(BigInteger, default=0, comment='最后轮询时间戳(毫秒)')
    next_poll_at = Column(BigInteger, default=0, index=True, comment='下次轮询时间戳(毫秒)')
    last_error = Column(Text, default='', comment='最近一次轮询错误')
    created_at = Column(BigInteger, default=0, comment='创建时间戳(毫秒)')
    updated_at = Column(BigInteger, default=0, comment='更新时间戳(毫秒)')


class XTopic(Base):
    """标准化后的 X 热点主题。"""
    __tablename__ = 'x_topics'
    __table_args__ = (
        UniqueConstraint(
            'owner_user_id',
            'normalized_name',
            'region_id',
            name='uq_x_topics_owner_name_region',
        ),
        Index('ix_x_topics_owner_status_last_seen', 'owner_user_id', 'status', 'last_seen_at'),
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment='主题ID')
    owner_user_id = Column(String(64), nullable=False, index=True, default='', comment='归属用户ID(数据隔离)')
    region_id = Column(Integer, nullable=False, index=True, comment='关联x_regions.id')
    raw_name = Column(Text, nullable=False, comment='X返回的原始主题名')
    normalized_name = Column(String(512), nullable=False, comment='规范化主题名')
    search_query = Column(Text, default='', comment='用于搜索帖子的X查询串')
    language = Column(String(32), default='', comment='主题主要语言')
    category = Column(String(64), default='general', comment='主题分类')
    relevance_score = Column(Float, default=0.0, comment='品牌相关度0-1')
    risk_score = Column(Float, default=0.0, comment='敏感风险0-1')
    is_sensitive = Column(Boolean, default=False, comment='是否仅监控而不生成回复')
    status = Column(String(20), default='monitoring', comment='状态: monitoring/selected/ignored/archived')
    first_seen_at = Column(BigInteger, default=0, comment='首次发现时间戳(毫秒)')
    last_seen_at = Column(BigInteger, default=0, index=True, comment='最后发现时间戳(毫秒)')
    created_at = Column(BigInteger, default=0, comment='创建时间戳(毫秒)')
    updated_at = Column(BigInteger, default=0, comment='更新时间戳(毫秒)')


class XTopicSnapshot(Base):
    """每轮趋势抓取的不可变排名与讨论量快照。"""
    __tablename__ = 'x_topic_snapshots'
    __table_args__ = (
        UniqueConstraint(
            'owner_user_id',
            'topic_id',
            'captured_at',
            name='uq_x_topic_snapshots_owner_topic_time',
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment='快照ID')
    owner_user_id = Column(String(64), nullable=False, index=True, default='', comment='归属用户ID(数据隔离)')
    topic_id = Column(Integer, nullable=False, index=True, comment='关联x_topics.id')
    region_id = Column(Integer, nullable=False, index=True, comment='关联x_regions.id')
    capture_batch_id = Column(String(64), default='', index=True, comment='本轮采集批次ID')
    rank = Column(Integer, default=0, comment='当前排名')
    rank_delta = Column(Integer, default=0, comment='相对上一轮排名变化')
    post_volume = Column(BigInteger, default=0, comment='X返回或估算的讨论量')
    volume_delta = Column(BigInteger, default=0, comment='相对上一轮讨论量变化')
    post_count_estimate = Column(BigInteger, default=0, comment='Counts接口估算帖子数')
    raw_payload_json = Column(Text, default='{}', comment='原始趋势数据JSON')
    captured_at = Column(BigInteger, nullable=False, index=True, comment='快照时间戳(毫秒)')
    created_at = Column(BigInteger, default=0, comment='创建时间戳(毫秒)')
    updated_at = Column(BigInteger, default=0, comment='更新时间戳(毫秒)')


class XPost(Base):
    """通过 X 浏览器页面采集的帖子、回复、引用和最小作者快照。"""
    __tablename__ = 'x_posts'
    __table_args__ = (
        UniqueConstraint('owner_user_id', 'x_post_id', name='uq_x_posts_owner_x_post'),
        Index('ix_x_posts_owner_conversation_created', 'owner_user_id', 'conversation_id', 'created_at_x'),
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment='内部帖子ID')
    owner_user_id = Column(String(64), nullable=False, index=True, default='', comment='归属用户ID(数据隔离)')
    x_post_id = Column(String(64), nullable=False, index=True, comment='X帖子ID')
    author_x_user_id = Column(String(64), nullable=False, index=True, comment='作者X用户ID')
    author_username = Column(String(255), default='', comment='作者用户名快照')
    author_display_name = Column(String(255), default='', comment='作者显示名称快照')
    text = Column(Text, default='', comment='帖子正文')
    lang = Column(String(32), default='', index=True, comment='帖子语言')
    created_at_x = Column(BigInteger, default=0, index=True, comment='X帖子发布时间戳(毫秒)')
    conversation_id = Column(String(64), default='', index=True, comment='X会话ID')
    parent_post_id = Column(String(64), default='', index=True, comment='父回复X帖子ID')
    post_type = Column(String(20), default='post', comment='类型: post/reply/quote/repost/mention')
    referenced_tweets_json = Column(Text, default='[]', comment='引用帖子关系JSON')
    public_metrics_json = Column(Text, default='{}', comment='公开互动指标JSON')
    author_public_metrics_json = Column(Text, default='{}', comment='作者公开指标快照JSON')
    entities_json = Column(Text, default='{}', comment='实体、话题和链接JSON')
    possibly_sensitive = Column(Boolean, default=False, comment='X敏感内容标记')
    reply_settings = Column(String(32), default='', comment='X回复权限设置')
    source_topic_id = Column(Integer, index=True, comment='来源热点主题ID')
    source_query = Column(Text, default='', comment='来源搜索查询')
    raw_payload_json = Column(Text, default='{}', comment='X原始响应JSON')
    compliance_status = Column(String(20), default='active', comment='状态: active/deleted/protected/withheld')
    last_hydrated_at = Column(BigInteger, default=0, comment='最后详情刷新时间戳(毫秒)')
    created_at = Column(BigInteger, default=0, comment='创建时间戳(毫秒)')
    updated_at = Column(BigInteger, default=0, comment='更新时间戳(毫秒)')


class XConversation(Base):
    """X 线程根帖、增量游标和本地树重建状态。"""
    __tablename__ = 'x_conversations'
    __table_args__ = (
        UniqueConstraint('owner_user_id', 'root_post_id', name='uq_x_conversations_owner_root'),
        Index('ix_x_conversations_owner_status_next', 'owner_user_id', 'status', 'next_refresh_at'),
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment='会话ID')
    owner_user_id = Column(String(64), nullable=False, index=True, default='', comment='归属用户ID(数据隔离)')
    account_id = Column(Integer, index=True, comment='关联x_accounts.id')
    topic_id = Column(Integer, index=True, comment='关联x_topics.id')
    root_post_id = Column(String(64), nullable=False, index=True, comment='根帖X帖子ID')
    x_conversation_id = Column(String(64), default='', index=True, comment='X conversation_id')
    language = Column(String(32), default='', comment='线程主要语言')
    status = Column(String(20), default='pending', comment='状态: pending/sampling/ready/analysed/archived/failed')
    sample_strategy = Column(String(32), default='balanced', comment='评论抽样策略')
    sample_limit = Column(Integer, default=100, comment='本轮最大抽样数')
    total_post_count = Column(Integer, default=0, comment='线程已知帖子数')
    sampled_post_count = Column(Integer, default=0, comment='已采样帖子数')
    max_depth = Column(Integer, default=0, comment='本地线程树最大深度')
    newest_post_at = Column(BigInteger, default=0, comment='线程最新帖子时间戳(毫秒)')
    pagination_token = Column(Text, default='', comment='增量抓取分页Token')
    last_collected_at = Column(BigInteger, default=0, comment='最后采集时间戳(毫秒)')
    next_refresh_at = Column(BigInteger, default=0, index=True, comment='下次刷新时间戳(毫秒)')
    last_error = Column(Text, default='', comment='最近一次采集错误')
    created_at = Column(BigInteger, default=0, comment='创建时间戳(毫秒)')
    updated_at = Column(BigInteger, default=0, comment='更新时间戳(毫秒)')


class XInteraction(Base):
    """品牌账号收到的 mention、引用或主动回复。"""
    __tablename__ = 'x_interactions'
    __table_args__ = (
        UniqueConstraint(
            'owner_user_id',
            'account_id',
            'interaction_post_id',
            name='uq_x_interactions_owner_account_post',
        ),
        Index('ix_x_interactions_owner_status_received', 'owner_user_id', 'status', 'received_at'),
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment='互动ID')
    owner_user_id = Column(String(64), nullable=False, index=True, default='', comment='归属用户ID(数据隔离)')
    account_id = Column(Integer, nullable=False, index=True, comment='关联x_accounts.id')
    conversation_id = Column(Integer, index=True, comment='关联x_conversations.id')
    interaction_post_id = Column(String(64), nullable=False, index=True, comment='触发互动的X帖子ID')
    actor_x_user_id = Column(String(64), nullable=False, index=True, comment='互动用户X ID')
    interaction_type = Column(String(20), nullable=False, comment='类型: mention/reply/quote/campaign_reply')
    status = Column(String(20), default='pending', comment='状态: pending/eligible/blocked/drafted/reviewed/published/failed')
    opt_in_evidence_json = Column(Text, default='{}', comment='用户主动互动证据JSON')
    eligibility_json = Column(Text, default='{}', comment='回复资格检查结果JSON')
    is_opted_out = Column(Boolean, default=False, comment='采集时是否已退出互动')
    replied_publish_job_id = Column(Integer, comment='成功或正在处理的发布任务ID')
    received_at = Column(BigInteger, default=0, index=True, comment='收到互动时间戳(毫秒)')
    processed_at = Column(BigInteger, default=0, comment='处理完成时间戳(毫秒)')
    created_at = Column(BigInteger, default=0, comment='创建时间戳(毫秒)')
    updated_at = Column(BigInteger, default=0, comment='更新时间戳(毫秒)')


class XThreadAnalysis(Base):
    """可追溯的线程结构化 AI 分析结果。"""
    __tablename__ = 'x_thread_analyses'
    __table_args__ = (
        UniqueConstraint(
            'owner_user_id',
            'conversation_id',
            'input_content_hash',
            'model_version',
            'prompt_version',
            name='uq_x_thread_analyses_input_model_prompt',
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment='分析ID')
    owner_user_id = Column(String(64), nullable=False, index=True, default='', comment='归属用户ID(数据隔离)')
    conversation_id = Column(Integer, nullable=False, index=True, comment='关联x_conversations.id')
    source_post_id = Column(Integer, index=True, comment='关联根帖x_posts.id')
    status = Column(String(20), default='pending', comment='状态: pending/running/succeeded/failed/blocked')
    input_content_hash = Column(String(128), nullable=False, comment='分析输入内容哈希')
    model_version = Column(String(128), nullable=False, default='', comment='模型版本')
    prompt_version = Column(String(128), nullable=False, default='', comment='Prompt版本')
    schema_version = Column(String(64), default='v1', comment='结构化输出Schema版本')
    summary = Column(Text, default='', comment='线程摘要')
    sentiment_json = Column(Text, default='{}', comment='情绪分析JSON')
    viewpoints_json = Column(Text, default='[]', comment='主要观点JSON')
    risks_json = Column(Text, default='[]', comment='风险和敏感点JSON')
    reply_recommendation = Column(String(32), default='human_review', comment='回复建议')
    output_json = Column(Text, default='{}', comment='完整结构化输出JSON')
    token_usage_json = Column(Text, default='{}', comment='LLM Token用量JSON')
    error_message = Column(Text, default='', comment='分析错误')
    analysed_at = Column(BigInteger, default=0, comment='分析完成时间戳(毫秒)')
    created_at = Column(BigInteger, default=0, comment='创建时间戳(毫秒)')
    updated_at = Column(BigInteger, default=0, comment='更新时间戳(毫秒)')


class XReplyCandidate(Base):
    """AI 生成并可由审核人编辑的回复候选。"""
    __tablename__ = 'x_reply_candidates'
    __table_args__ = (
        Index('ix_x_reply_candidates_owner_review_created', 'owner_user_id', 'review_status', 'created_at'),
        Index('ix_x_reply_candidates_owner_hash', 'owner_user_id', 'content_hash'),
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment='候选ID')
    owner_user_id = Column(String(64), nullable=False, index=True, default='', comment='归属用户ID(数据隔离)')
    account_id = Column(Integer, nullable=False, index=True, comment='关联x_accounts.id')
    thread_analysis_id = Column(Integer, index=True, comment='关联x_thread_analyses.id')
    source_post_id = Column(Integer, nullable=False, index=True, comment='关联x_posts.id')
    interaction_id = Column(Integer, index=True, comment='关联x_interactions.id')
    candidate_index = Column(Integer, default=0, comment='同批候选序号')
    generated_text = Column(Text, nullable=False, comment='模型生成文本')
    edited_text = Column(Text, default='', comment='人工编辑文本')
    style = Column(String(32), default='friendly', comment='回复风格')
    risk_level = Column(String(20), default='unknown', comment='风险等级: low/medium/high/blocked')
    confidence = Column(Float, default=0.0, comment='模型置信度0-1')
    requires_fact_check = Column(Boolean, default=False, comment='是否需要事实核查')
    model_version = Column(String(128), default='', comment='模型版本')
    prompt_version = Column(String(128), default='', comment='Prompt版本')
    content_hash = Column(String(128), nullable=False, comment='生成文本内容哈希')
    duplicate_score = Column(Float, default=0.0, comment='与历史回复最高相似度0-1')
    generation_metadata_json = Column(Text, default='{}', comment='生成参数和输入追踪JSON')
    review_status = Column(String(20), default='draft', comment='状态: draft/pending/approved/rejected/invalidated/published')
    created_at = Column(BigInteger, default=0, comment='创建时间戳(毫秒)')
    updated_at = Column(BigInteger, default=0, comment='更新时间戳(毫秒)')


class XReviewTask(Base):
    """回复候选的人工审核任务和批准内容哈希。"""
    __tablename__ = 'x_review_tasks'
    __table_args__ = (
        Index('ix_x_review_tasks_owner_status_created', 'owner_user_id', 'review_status', 'created_at'),
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment='审核任务ID')
    owner_user_id = Column(String(64), nullable=False, index=True, default='', comment='归属用户ID(数据隔离)')
    account_id = Column(Integer, nullable=False, index=True, comment='关联x_accounts.id')
    reply_candidate_id = Column(Integer, nullable=False, index=True, comment='关联x_reply_candidates.id')
    interaction_id = Column(Integer, index=True, comment='关联x_interactions.id')
    review_status = Column(String(20), default='pending', comment='状态: pending/in_review/approved/rejected/cancelled/published')
    priority = Column(Integer, default=0, comment='审核优先级')
    assigned_reviewer_user_id = Column(String(64), default='', index=True, comment='指定审核人系统用户ID')
    reviewed_by_user_id = Column(String(64), default='', index=True, comment='实际审核人系统用户ID')
    final_text = Column(Text, default='', comment='审核确认的最终文本')
    final_content_hash = Column(String(128), default='', comment='最终文本哈希')
    review_reason = Column(Text, default='', comment='批准、拒绝或编辑理由')
    assigned_at = Column(BigInteger, default=0, comment='分配时间戳(毫秒)')
    reviewed_at = Column(BigInteger, default=0, comment='审核完成时间戳(毫秒)')
    expires_at = Column(BigInteger, default=0, comment='审核有效期截止时间戳(毫秒)')
    created_at = Column(BigInteger, default=0, comment='创建时间戳(毫秒)')
    updated_at = Column(BigInteger, default=0, comment='更新时间戳(毫秒)')


class XPolicyDecision(Base):
    """发布前逐条策略规则的判定和证据。"""
    __tablename__ = 'x_policy_decisions'
    __table_args__ = (
        Index('ix_x_policy_decisions_owner_decision_time', 'owner_user_id', 'decision', 'evaluated_at'),
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment='策略判定ID')
    owner_user_id = Column(String(64), nullable=False, index=True, default='', comment='归属用户ID(数据隔离)')
    account_id = Column(Integer, nullable=False, index=True, comment='关联x_accounts.id')
    reply_candidate_id = Column(Integer, index=True, comment='关联x_reply_candidates.id')
    interaction_id = Column(Integer, index=True, comment='关联x_interactions.id')
    target_post_id = Column(String(64), default='', index=True, comment='目标X帖子ID')
    policy_version = Column(String(64), nullable=False, default='v1', comment='策略版本')
    decision = Column(String(20), nullable=False, default='blocked', comment='判定: allowed/review_required/blocked')
    rule_results_json = Column(Text, default='[]', comment='逐条规则通过或失败结果JSON')
    evidence_json = Column(Text, default='{}', comment='opt-in、账号审批和内容证据JSON')
    blocked_reason = Column(Text, default='', comment='阻断原因')
    input_content_hash = Column(String(128), default='', comment='判定时回复文本哈希')
    evaluated_at = Column(BigInteger, default=0, index=True, comment='策略评估时间戳(毫秒)')
    created_at = Column(BigInteger, default=0, comment='创建时间戳(毫秒)')
    updated_at = Column(BigInteger, default=0, comment='更新时间戳(毫秒)')


class XPublishJob(Base):
    """幂等的受控发布任务；重试通过结果表记录，不创建重复任务。"""
    __tablename__ = 'x_publish_jobs'
    __table_args__ = (
        UniqueConstraint('owner_user_id', 'idempotency_key', name='uq_x_publish_jobs_owner_key'),
        UniqueConstraint(
            'owner_user_id',
            'account_id',
            'target_post_id',
            'publish_mode',
            name='uq_x_publish_jobs_owner_account_target_mode',
        ),
        UniqueConstraint(
            'owner_user_id',
            'account_id',
            'interaction_id',
            name='uq_x_publish_jobs_owner_account_interaction',
        ),
        Index('ix_x_publish_jobs_claim', 'status', 'scheduled_at', 'lease_expires_at'),
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment='发布任务ID')
    owner_user_id = Column(String(64), nullable=False, index=True, default='', comment='归属用户ID(数据隔离)')
    account_id = Column(Integer, nullable=False, index=True, comment='关联x_accounts.id')
    reply_candidate_id = Column(Integer, nullable=False, index=True, comment='关联x_reply_candidates.id')
    review_task_id = Column(Integer, index=True, comment='关联x_review_tasks.id')
    interaction_id = Column(Integer, index=True, comment='关联x_interactions.id，自动回复时必填')
    policy_decision_id = Column(Integer, nullable=False, index=True, comment='关联最终x_policy_decisions.id')
    target_post_id = Column(String(64), nullable=False, index=True, comment='回复目标X帖子ID')
    target_user_id = Column(String(64), default='', index=True, comment='回复目标X用户ID')
    publish_mode = Column(String(32), nullable=False, default='manual_review', comment='模式: manual_review/auto_reply')
    reply_text = Column(Text, nullable=False, comment='锁定的待发布文本')
    approval_content_hash = Column(String(128), nullable=False, comment='审核批准文本哈希')
    opt_in_evidence_json = Column(Text, default='{}', comment='用户主动互动证据JSON')
    idempotency_key = Column(String(128), nullable=False, comment='租户内幂等键')
    status = Column(String(20), default='pending', comment='状态: pending/running/succeeded/retry_wait/failed/cancelled/blocked')
    priority = Column(Integer, default=0, comment='执行优先级')
    scheduled_at = Column(BigInteger, default=0, index=True, comment='计划执行时间戳(毫秒)')
    executed_at = Column(BigInteger, default=0, comment='最后执行时间戳(毫秒)')
    lease_owner = Column(String(128), default='', comment='领取任务的Worker')
    lease_expires_at = Column(BigInteger, default=0, index=True, comment='Worker租约到期时间戳(毫秒)')
    x_post_id = Column(String(64), default='', index=True, comment='发布成功后的X帖子ID')
    error_code = Column(String(128), default='', comment='最近一次错误码')
    error_message = Column(Text, default='', comment='最近一次错误信息')
    retry_count = Column(Integer, default=0, comment='已重试次数')
    max_retries = Column(Integer, default=3, comment='最大重试次数')
    created_at = Column(BigInteger, default=0, comment='创建时间戳(毫秒)')
    updated_at = Column(BigInteger, default=0, comment='更新时间戳(毫秒)')


class XPublishResult(Base):
    """每次调用 X 写入接口的结果，不覆盖历史失败。"""
    __tablename__ = 'x_publish_results'
    __table_args__ = (
        UniqueConstraint(
            'owner_user_id',
            'publish_job_id',
            'attempt_no',
            name='uq_x_publish_results_owner_job_attempt',
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment='发布结果ID')
    owner_user_id = Column(String(64), nullable=False, index=True, default='', comment='归属用户ID(数据隔离)')
    publish_job_id = Column(Integer, nullable=False, index=True, comment='关联x_publish_jobs.id')
    account_id = Column(Integer, nullable=False, index=True, comment='关联x_accounts.id')
    attempt_no = Column(Integer, nullable=False, default=1, comment='执行尝试序号')
    success = Column(Boolean, default=False, comment='是否发布成功')
    x_post_id = Column(String(64), default='', index=True, comment='X返回的帖子ID')
    http_status = Column(Integer, default=0, comment='X API HTTP状态码')
    x_error_code = Column(String(128), default='', comment='X API错误码')
    error_message = Column(Text, default='', comment='错误摘要，不保存Token')
    retryable = Column(Boolean, default=False, comment='错误是否可重试')
    rate_limit_reset_at = Column(BigInteger, default=0, comment='429重置时间戳(毫秒)')
    response_metadata_json = Column(Text, default='{}', comment='脱敏后的响应元数据JSON')
    request_id = Column(String(128), default='', index=True, comment='X或本系统请求ID')
    attempted_at = Column(BigInteger, default=0, index=True, comment='调用时间戳(毫秒)')
    created_at = Column(BigInteger, default=0, comment='创建时间戳(毫秒)')
    updated_at = Column(BigInteger, default=0, comment='更新时间戳(毫秒)')


class XUserOptOut(Base):
    """X 用户退出自动互动的即时生效记录。account_id=0 表示租户全局退出。"""
    __tablename__ = 'x_user_opt_outs'
    __table_args__ = (
        UniqueConstraint(
            'owner_user_id',
            'account_id',
            'x_user_id',
            name='uq_x_user_opt_outs_owner_account_user',
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment='退出记录ID')
    owner_user_id = Column(String(64), nullable=False, index=True, default='', comment='归属用户ID(数据隔离)')
    account_id = Column(Integer, nullable=False, default=0, index=True, comment='关联账号ID，0表示租户全局')
    x_user_id = Column(String(64), nullable=False, index=True, comment='要求退出的X用户ID')
    username_snapshot = Column(String(255), default='', comment='用户名快照')
    status = Column(String(20), default='active', comment='状态: active/revoked')
    source_interaction_id = Column(Integer, index=True, comment='触发退出的互动ID')
    source_post_id = Column(String(64), default='', index=True, comment='退出请求X帖子ID')
    detected_phrase = Column(Text, default='', comment='检测到的退出表述')
    evidence_json = Column(Text, default='{}', comment='退出证据JSON')
    detected_at = Column(BigInteger, default=0, index=True, comment='检测时间戳(毫秒)')
    revoked_at = Column(BigInteger, default=0, comment='人工撤销时间戳(毫秒)')
    created_at = Column(BigInteger, default=0, comment='创建时间戳(毫秒)')
    updated_at = Column(BigInteger, default=0, comment='更新时间戳(毫秒)')


class XJob(Base):
    """采集、分析和发布流程使用的轻量数据库任务队列。"""
    __tablename__ = 'x_jobs'
    __table_args__ = (
        UniqueConstraint('owner_user_id', 'job_id', name='uq_x_jobs_owner_job_id'),
        Index('ix_x_jobs_claim', 'status', 'scheduled_at', 'lease_expires_at', 'priority'),
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment='内部任务ID')
    owner_user_id = Column(String(64), nullable=False, index=True, default='', comment='归属用户ID(数据隔离)')
    job_id = Column(String(64), nullable=False, index=True, comment='业务任务唯一ID')
    job_type = Column(String(32), nullable=False, index=True, comment='类型: trends/search/thread/analysis/publish/compliance')
    account_id = Column(Integer, index=True, comment='关联x_accounts.id')
    region_id = Column(Integer, index=True, comment='关联x_regions.id')
    topic_id = Column(Integer, index=True, comment='关联x_topics.id')
    conversation_id = Column(Integer, index=True, comment='关联x_conversations.id')
    parent_job_id = Column(String(64), default='', index=True, comment='父任务业务ID')
    dedup_key = Column(String(255), default='', index=True, comment='调用方生成的去重键')
    payload_json = Column(Text, default='{}', comment='任务输入JSON')
    result_json = Column(Text, default='{}', comment='任务结果JSON')
    status = Column(String(20), default='pending', index=True, comment='状态: pending/running/succeeded/retry_wait/failed/cancelled')
    priority = Column(Integer, default=0, comment='优先级，数值越大越优先')
    attempt_count = Column(Integer, default=0, comment='已执行次数')
    max_attempts = Column(Integer, default=3, comment='最大执行次数')
    scheduled_at = Column(BigInteger, default=0, index=True, comment='计划执行时间戳(毫秒)')
    started_at = Column(BigInteger, default=0, comment='开始执行时间戳(毫秒)')
    finished_at = Column(BigInteger, default=0, comment='结束时间戳(毫秒)')
    lease_owner = Column(String(128), default='', comment='Worker标识')
    lease_expires_at = Column(BigInteger, default=0, index=True, comment='租约到期时间戳(毫秒)')
    last_error = Column(Text, default='', comment='最近一次错误')
    created_at = Column(BigInteger, default=0, comment='创建时间戳(毫秒)')
    updated_at = Column(BigInteger, default=0, comment='更新时间戳(毫秒)')


class XApiUsageDaily(Base):
    """按租户、账号、日期和来源汇总浏览器采集量与官方写入量。"""
    __tablename__ = 'x_api_usage_daily'
    __table_args__ = (
        UniqueConstraint(
            'owner_user_id',
            'account_id',
            'usage_date',
            'endpoint',
            name='uq_x_api_usage_owner_account_date_endpoint',
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment='用量记录ID')
    owner_user_id = Column(String(64), nullable=False, index=True, default='', comment='归属用户ID(数据隔离)')
    account_id = Column(Integer, nullable=False, default=0, index=True, comment='账号ID，0表示App-only读取')
    usage_date = Column(String(10), nullable=False, index=True, comment='UTC日期YYYY-MM-DD')
    endpoint = Column(String(255), nullable=False, comment='浏览器采集来源或官方写入Endpoint')
    request_count = Column(Integer, default=0, comment='请求次数')
    success_count = Column(Integer, default=0, comment='成功次数')
    error_count = Column(Integer, default=0, comment='失败次数')
    read_resource_count = Column(BigInteger, default=0, comment='浏览器采集资源数量')
    write_count = Column(Integer, default=0, comment='写入次数')
    estimated_cost_micros = Column(BigInteger, default=0, comment='估算费用，百万分之一货币单位')
    budget_limit_micros = Column(BigInteger, default=0, comment='该维度预算上限，0表示未限制')
    budget_exhausted = Column(Boolean, default=False, comment='是否已耗尽预算')
    created_at = Column(BigInteger, default=0, comment='创建时间戳(毫秒)')
    updated_at = Column(BigInteger, default=0, comment='更新时间戳(毫秒)')


class XRateLimitState(Base):
    """保存 X API 最新限流头，供调度器在 reset 后恢复任务。"""
    __tablename__ = 'x_rate_limit_state'
    __table_args__ = (
        UniqueConstraint(
            'owner_user_id',
            'account_id',
            'endpoint',
            'resource_key',
            name='uq_x_rate_limit_owner_account_endpoint_resource',
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment='限流状态ID')
    owner_user_id = Column(String(64), nullable=False, index=True, default='', comment='归属用户ID(数据隔离)')
    account_id = Column(Integer, nullable=False, default=0, index=True, comment='账号ID，0表示App-only读取')
    endpoint = Column(String(255), nullable=False, comment='规范化X API Endpoint')
    resource_key = Column(String(255), nullable=False, default='default', comment='限流资源或窗口标识')
    limit_total = Column(Integer, default=0, comment='窗口总额度')
    remaining = Column(Integer, default=0, comment='窗口剩余额度')
    reset_at = Column(BigInteger, default=0, index=True, comment='窗口重置时间戳(毫秒)')
    last_http_status = Column(Integer, default=0, comment='最近HTTP状态码')
    observed_at = Column(BigInteger, default=0, comment='最近观测时间戳(毫秒)')
    created_at = Column(BigInteger, default=0, comment='创建时间戳(毫秒)')
    updated_at = Column(BigInteger, default=0, comment='更新时间戳(毫秒)')


class XSystemControl(Base):
    """全局、账号、地域或关键词级开关和 Kill Switch。"""
    __tablename__ = 'x_system_controls'
    __table_args__ = (
        UniqueConstraint(
            'owner_user_id',
            'scope_type',
            'scope_key',
            'control_name',
            name='uq_x_system_controls_owner_scope_control',
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment='系统控制ID')
    owner_user_id = Column(String(64), nullable=False, index=True, default='', comment='归属用户ID(数据隔离)')
    scope_type = Column(String(20), nullable=False, default='global', comment='范围: global/account/region/keyword')
    scope_key = Column(String(255), nullable=False, default='*', comment='范围ID或关键词，*表示全局')
    control_name = Column(String(64), nullable=False, comment='控制名: read_enabled/write_enabled/auto_reply_enabled/kill_switch')
    enabled = Column(Boolean, default=False, comment='该控制的布尔值')
    value_json = Column(Text, default='{}', comment='附加控制参数JSON')
    reason = Column(Text, default='', comment='启停原因')
    changed_by_user_id = Column(String(64), default='', index=True, comment='最后修改人系统用户ID')
    expires_at = Column(BigInteger, default=0, comment='临时控制过期时间戳，0表示永久')
    created_at = Column(BigInteger, default=0, comment='创建时间戳(毫秒)')
    updated_at = Column(BigInteger, default=0, comment='更新时间戳(毫秒)')


class XAuditLog(Base):
    """X 采集、审核、策略和发布操作的不可变审计事实。"""
    __tablename__ = 'x_audit_logs'
    __table_args__ = (
        Index('ix_x_audit_logs_owner_action_time', 'owner_user_id', 'action', 'created_at'),
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment='审计日志ID')
    owner_user_id = Column(String(64), nullable=False, index=True, default='', comment='归属用户ID(数据隔离)')
    account_id = Column(Integer, index=True, comment='关联x_accounts.id')
    actor_user_id = Column(String(64), default='', index=True, comment='操作人系统用户ID，worker使用服务标识')
    actor_type = Column(String(20), default='user', comment='操作者类型: user/worker/system')
    action = Column(String(64), nullable=False, index=True, comment='动作名称')
    entity_type = Column(String(64), default='', comment='被操作实体类型')
    entity_id = Column(String(128), default='', index=True, comment='被操作实体ID')
    outcome = Column(String(20), default='success', comment='结果: success/blocked/failed')
    before_state_json = Column(Text, default='{}', comment='操作前脱敏状态JSON')
    after_state_json = Column(Text, default='{}', comment='操作后脱敏状态JSON')
    metadata_json = Column(Text, default='{}', comment='附加审计信息JSON，不保存Token')
    request_id = Column(String(128), default='', index=True, comment='请求或链路追踪ID')
    ip_address = Column(String(64), default='', comment='操作来源IP')
    created_at = Column(BigInteger, default=0, index=True, comment='创建时间戳(毫秒)')
    updated_at = Column(BigInteger, default=0, comment='更新时间戳(毫秒)')
