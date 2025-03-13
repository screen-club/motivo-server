from peewee import *
import json
import os
from playhouse.migrate import SqliteMigrator, migrate

# Get the path to the public storage directory
from pathlib import Path
PUBLIC_STORAGE_DIR = str(Path(__file__).resolve().parents[3] / 'public' / 'storage')

# Database configuration - store the database in public/storage/db
DB_DIR = os.path.join(PUBLIC_STORAGE_DIR, 'db')
os.makedirs(DB_DIR, exist_ok=True)
db_path = os.path.join(DB_DIR, 'database.db')

db = SqliteDatabase(db_path, pragmas={'foreign_keys': 1})

class BaseModel(Model):
    class Meta:
        database = db

class Content(BaseModel):
    title = CharField()
    thumbnail = CharField()
    type = CharField(choices=[
        ('vibe', 'Vibe'),
        ('reward', 'Reward'),
        ('llm', 'LLM')
    ])
    data = TextField()  # JSON storage as text
    cache_file_path = CharField(null=True)
    tags = TextField(default='[]')  # Store tags as JSON array string
    users = TextField(default='[]')  # Store users as JSON array string

    def get_data(self):
        return json.loads(self.data)

    def set_data(self, data_dict):
        self.data = json.dumps(data_dict)

    def get_tags(self):
        return json.loads(self.tags)

    def set_tags(self, tags_list):
        self.tags = json.dumps(tags_list)
        
    def get_users(self):
        return json.loads(self.users)

    def set_users(self, users_list):
        self.users = json.dumps(users_list)

    @classmethod
    def get_all(cls):
        with db.connection_context():
            rows = cls.select()
            return [{
                "id": row.id,
                "title": row.title,
                "thumbnail": row.thumbnail,
                "type": row.type,
                "data": row.get_data(),
                "cache_file_path": row.cache_file_path,
                "tags": row.get_tags(),
                "users": row.get_users()
            } for row in rows]

    @classmethod
    def add(cls, title, thumbnail, type, data, cache_file_path=None, tags=None, users=None):
        with db.connection_context():
            content = Content.create(
                title=title,
                thumbnail=thumbnail,
                type=type,
                data=json.dumps(data),
                cache_file_path=cache_file_path,
                tags=json.dumps(tags or []),
                users=json.dumps(users or [])
            )
            return content.id

    @classmethod
    def update_content(cls, id, **kwargs):
        try:
            with db.atomic():
                content = Content.get(Content.id == id)
                
                # Handle special fields that need JSON conversion
                if 'data' in kwargs:
                    kwargs['data'] = json.dumps(kwargs['data'])
                if 'tags' in kwargs:
                    kwargs['tags'] = json.dumps(kwargs['tags'])
                if 'users' in kwargs:
                    kwargs['users'] = json.dumps(kwargs['users'])
                    
                # Update only the fields that are provided
                for field, value in kwargs.items():
                    setattr(content, field, value)
                
                Content.update(**kwargs).where(Content.id == id).execute()
        except Exception as e:
            db.rollback()  # Ensure transaction is rolled back on error
            raise e
            
    @classmethod
    def delete_item(cls, id):
        with db.connection_context():
            query = Content.delete().where(Content.id == id)
            query.execute()

def run_migration():
    """Run database migrations"""
    migrator = SqliteMigrator(db)
    
    try:
        # Add tags field if it doesn't exist
        migrate(
            migrator.add_column('content', 'tags', TextField(default='[]'))
        )
    except Exception as e:
        print(f"Migration error (can be ignored if field already exists): {e}")
        
    try:
        # Add users field if it doesn't exist
        migrate(
            migrator.add_column('content', 'users', TextField(default='[]'))
        )
    except Exception as e:
        print(f"Migration error (can be ignored if field already exists): {e}")

def initialize_database():
    """Initialize the database and create tables if they don't exist."""
    db.connect(reuse_if_open=True)
    db.create_tables([Content], safe=True)
    
    # Run migrations
    run_migration()
    
    db.close()