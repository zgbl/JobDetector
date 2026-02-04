"""
MongoDB Database Connection Manager
"""
import os
from typing import Optional
from pymongo import MongoClient
from pymongo.database import Database
from dotenv import load_dotenv
import logging

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)


class DatabaseManager:
    """MongoDB数据库连接管理器"""
    
    _instance: Optional['DatabaseManager'] = None
    _client: Optional[MongoClient] = None
    _db: Optional[Database] = None
    
    def __new__(cls):
        """单例模式"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        """初始化数据库连接"""
        if self._client is None:
            self.connect()
    
    def connect(self):
        """连接到MongoDB"""
        try:
            mongo_uri = os.getenv('MONGODB_URI')
            db_name = os.getenv('MONGODB_DATABASE', 'jobdetector')
            
            if not mongo_uri:
                raise ValueError("MONGODB_URI environment variable is not set")
            
            logger.info(f"Connecting to MongoDB: {db_name}")
            
            # Add SSL parameters for MongoDB Atlas connection
            # This helps with SSL certificate issues on some systems
            self._client = MongoClient(
                mongo_uri,
                tlsAllowInvalidCertificates=True  # For development only
            )
            self._db = self._client[db_name]
            
            # Test connection
            self._client.admin.command('ping')
            logger.info("✅ Successfully connected to MongoDB")
            
        except Exception as e:
            logger.error(f"❌ Failed to connect to MongoDB: {e}")
            raise
            
        except Exception as e:
            logger.error(f"❌ Failed to connect to MongoDB: {e}")
            raise
    
    def get_db(self) -> Database:
        """获取数据库实例"""
        if self._db is None:
            self.connect()
        return self._db
    
    def close(self):
        """关闭数据库连接"""
        if self._client:
            self._client.close()
            logger.info("Database connection closed")
            self._client = None
            self._db = None


# Global database instance
_db_manager = DatabaseManager()


def get_db() -> Database:
    """
    获取数据库实例的便捷函数
    
    Returns:
        Database: MongoDB数据库实例
    """
    return _db_manager.get_db()


def close_db():
    """关闭数据库连接"""
    _db_manager.close()
