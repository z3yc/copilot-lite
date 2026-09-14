"""ORM 模型汇总：确保所有模型在创建表 / 迁移时被注册。"""

from app.models.audit_log import AuditLog
from app.models.category import Category
from app.models.chat_session import ChatSession
from app.models.chunk import Chunk
from app.models.document import Document
from app.models.eval_run import EvalRun
from app.models.llm_setting import LLMSetting
from app.models.memory_fact import MemoryFact
from app.models.message import Message
from app.models.session_file import SessionFile
from app.models.todo import Todo
from app.models.user import User
from app.models.wiki import WikiLink, WikiPage, WikiSpace

__all__ = [
    "AuditLog",
    "Category",
    "ChatSession",
    "Chunk",
    "Document",
    "EvalRun",
    "LLMSetting",
    "MemoryFact",
    "Message",
    "SessionFile",
    "Todo",
    "User",
    "WikiLink",
    "WikiPage",
    "WikiSpace",
]
