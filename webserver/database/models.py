from peewee import *
import json
import os
from playhouse.migrate import SqliteMigrator, migrate

# Simple hardcoded path directly to storage/db.db
db_path = 'storage/db.db'
print(f"Using database at: {db_path}")

# Make sure the directory exists
os.makedirs(os.path.dirname(db_path), exist_ok=True)

db = SqliteDatabase(db_path, pragmas={'foreign_keys': 1})

class BaseModel(Model):
    class Meta:
        database = db

class GeminiMessage(BaseModel):
    """Model for storing Gemini chat messages with associated image data"""
    client_id = CharField()
    role = CharField(choices=[('user', 'User'), ('assistant', 'Assistant'), ('system', 'System')])
    content = TextField()
    image_path = CharField(null=True)
    image_timestamp = FloatField(null=True)
    timestamp = FloatField()
    is_complete = BooleanField(default=True)
    
    @classmethod
    def add_message(cls, client_id, role, content, image_path=None, image_timestamp=None, is_complete=True):
        """Add a new message to the history"""
        with db.connection_context():
            message = GeminiMessage.create(
                client_id=client_id,
                role=role,
                content=content,
                image_path=image_path,
                image_timestamp=image_timestamp,
                timestamp=float(os.path.getmtime(__file__) if image_timestamp is None else image_timestamp),
                is_complete=is_complete
            )
            return message.id
    
    @classmethod
    def get_conversation(cls, client_id, limit=50):
        """Get conversation history for a client"""
        with db.connection_context():
            messages = (GeminiMessage
                       .select()
                       .where(GeminiMessage.client_id == client_id)
                       .order_by(GeminiMessage.timestamp)
                       .limit(limit))
            
            return [{
                "id": msg.id,
                "role": msg.role,
                "content": msg.content,
                "image_path": msg.image_path,
                "image_timestamp": msg.image_timestamp,
                "timestamp": msg.timestamp,
                "is_complete": msg.is_complete
            } for msg in messages]

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
                "type": row.type,
                "data": row.get_data(),
                "cache_file_path": row.cache_file_path,
                "tags": row.get_tags(),
                "users": row.get_users()
            } for row in rows]
            
    @classmethod
    def get_lightweight(cls):
        """Return all presets with minimal data (no thumbnails) and reduced precision"""
        with db.connection_context():
            rows = cls.select()
            result = []
            
            for row in rows:
                # Get full data first
                data = row.get_data()
                
                # Process the data to reduce its size
                lightweight_data = {}
                
                # Handle pose data - reduce precision if present
                if 'pose' in data and isinstance(data['pose'], list):
                    # Round pose values to 3 decimal places
                    lightweight_data['pose'] = [
                        [round(value, 3) for value in pose] 
                        for pose in data['pose']
                    ]
                
                # Handle qpos data similarly if present
                if 'qpos' in data and isinstance(data['qpos'], list):
                    lightweight_data['qpos'] = [
                        [round(value, 3) for value in qpos]
                        for qpos in data['qpos']
                    ]
                
                # Include only minimal metadata
                if 'duration' in data:
                    lightweight_data['duration'] = data['duration']
                
                # For timeline presets, include just the references, not all nested data
                if row.type == 'timeline' and 'placedPresets' in data:
                    lightweight_data['placedPresets'] = [
                        {
                            'id': item.get('id'),
                            'startTime': item.get('startTime'),
                            'duration': item.get('duration')
                        }
                        for item in data.get('placedPresets', [])
                    ]
                
                # For other types of data, include them as is
                for key, value in data.items():
                    if key not in lightweight_data and key not in ['pose', 'qpos', 'placedPresets']:
                        lightweight_data[key] = value
                
                # Create the preset with lightweight data
                preset = {
                    "id": row.id,
                    "title": row.title,
                    "type": row.type,
                    "thumbnail": None,  # Don't include actual thumbnail data
                    "has_thumbnail": bool(row.thumbnail),  # Just indicate if a thumbnail exists
                    "data": lightweight_data,
                    "tags": row.get_tags(),
                    "users": row.get_users()
                }
                
                result.append(preset)
                
            return result

    @classmethod
    def get_by_id(cls, id):
        """Fetch a single content item by its ID, including thumbnail."""
        with db.connection_context():
            try:
                row = cls.get(Content.id == id)
                return {
                    "id": row.id,
                    "title": row.title,
                    "thumbnail": row.thumbnail,
                    "type": row.type,
                    "data": row.get_data(),
                    "cache_file_path": row.cache_file_path,
                    "tags": row.get_tags(),
                    "users": row.get_users()
                }
            except DoesNotExist:
                return None

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
    db.create_tables([Content, GeminiMessage], safe=True)
    
    # Run migrations
    run_migration()
    
    db.close()