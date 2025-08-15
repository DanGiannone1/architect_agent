# File: backend/cosmos_db.py

import os
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv
from azure.cosmos import CosmosClient, exceptions, PartitionKey
from azure.cosmos.container import ContainerProxy
from azure.cosmos.database import DatabaseProxy
from azure.identity import DefaultAzureCredential
from datetime import datetime, timezone, timedelta
import traceback

class CosmosDBManager:
    def __init__(self, cosmos_host=None, cosmos_database_id=None, cosmos_container_id=None):
        self._load_env_variables(cosmos_host, cosmos_database_id, cosmos_container_id)
        self.client = self._get_cosmos_client()
        self.database: Optional[DatabaseProxy] = None
        self.container: Optional[ContainerProxy] = None
        self._initialize_database_and_container()

    def _load_env_variables(self, cosmos_host=None, cosmos_database_id=None, cosmos_container_id=None):
        load_dotenv()
        self.cosmos_host = cosmos_host or os.environ.get("COSMOS_HOST")
        self.cosmos_database_id = cosmos_database_id or os.environ.get("COSMOS_DATABASE_ID")
        self.cosmos_container_id = cosmos_container_id or os.environ.get("COSMOS_CONTAINER_ID")
        self.tenant_id = os.environ.get("TENANT_ID", '16b3c013-d300-468d-ac64-7eda0820b6d3')

        if not all([self.cosmos_host, self.cosmos_database_id, self.cosmos_container_id]):
            raise ValueError("Cosmos DB configuration is incomplete")

    def _get_cosmos_client(self) -> CosmosClient:
        print("Initializing Cosmos DB client")
        print("Using DefaultAzureCredential for Cosmos DB authentication")
        credential = DefaultAzureCredential(
            interactive_browser_tenant_id=self.tenant_id,
            visual_studio_code_tenant_id=self.tenant_id,
            workload_identity_tenant_id=self.tenant_id,
            shared_cache_tenant_id=self.tenant_id
        )
        return CosmosClient(self.cosmos_host, credential=credential)

    def _initialize_database_and_container(self) -> None:
        try:
            self.database = self._create_or_get_database()
            self.container = self._create_or_get_container()
        except exceptions.CosmosHttpResponseError as e:
            print(f'An error occurred: {e.message}')
            raise

    def _create_or_get_database(self) -> DatabaseProxy:
        try:
            database = self.client.create_database(id=self.cosmos_database_id)
            print(f'Database with id \'{self.cosmos_database_id}\' created')
        except exceptions.CosmosResourceExistsError:
            database = self.client.get_database_client(self.cosmos_database_id)
            print(f'Database with id \'{self.cosmos_database_id}\' was found')
        return database

    def _create_or_get_container(self) -> ContainerProxy:
        try:
            container = self.database.create_container(
                id=self.cosmos_container_id, 
                partition_key=PartitionKey(path='/user_id')
            )
            print(f'Container with id \'{self.cosmos_container_id}\' created')
        except exceptions.CosmosResourceExistsError:
            container = self.database.get_container_client(self.cosmos_container_id)
            print(f'Container with id \'{self.cosmos_container_id}\' was found')
        return container

    # Core CRUD Operations
    def get_item_by_id(self, item_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        """Get a single item by its ID and user_id (partition key)."""
        try:
            item = self.container.read_item(item=item_id, partition_key=user_id)
            return item
        except exceptions.CosmosResourceNotFoundError:
            return None
        except Exception as e:
            print(f"Error retrieving item {item_id}: {str(e)}")
            raise

    def create_item(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new item in the container."""
        try:
            if 'user_id' not in item:
                raise ValueError("user_id (partition key) is required for create operation")
            
            # Ensure timestamps are set
            current_time = datetime.now(timezone.utc).isoformat()
            item['created_at'] = current_time
            item['updated_at'] = current_time
            
            created_item = self.container.create_item(body=item)
            print(f"Item created with id: {created_item['id']}")
            return created_item
        except exceptions.CosmosResourceExistsError:
            print(f"Item with id {item.get('id')} already exists")
            raise
        except Exception as e:
            print(f"Error creating item: {str(e)}")
            raise

    def update_item(self, item_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Update an existing item with new values."""
        try:
            # Get the existing item
            existing_item = self.get_item_by_id(item_id, updates['user_id'])
            if not existing_item:
                raise ValueError(f"Item with id {item_id} not found")

            # Update the item with new values
            existing_item.update(updates)
            existing_item['updated_at'] = datetime.now(timezone.utc).isoformat()

            # Replace the item in the container
            updated_item = self.container.replace_item(
                item=item_id,
                body=existing_item
            )
            return updated_item
        except Exception as e:
            print(f"Error updating item {item_id}: {str(e)}")
            raise

    def delete_item(self, item_id: str, user_id: str) -> bool:
        """Delete an item by its ID."""
        try:
            self.container.delete_item(item=item_id, partition_key=user_id)
            return True
        except exceptions.CosmosResourceNotFoundError:
            return False
        except Exception as e:
            print(f"Error deleting item {item_id}: {str(e)}")
            raise

    def get_user_data(self, user_id: str) -> Dict[str, List[Dict[str, Any]]]:
        """Get all data for a user (tasks, goals, categories, dashboard)."""
        try:
            query = """
            SELECT * FROM c 
            WHERE c.user_id = @user_id
            """
            items = list(self.container.query_items(
                query=query,
                parameters=[{"name": "@user_id", "value": user_id}],
                enable_cross_partition_query=False
            ))

            # Organize items by type
            result = {
                "tasks": [],
                "goals": [],
                "categories": [],
                "dashboard": None
            }

            for item in items:
                item_type = item.get("type")
                if item_type == "task":
                    result["tasks"].append(item)
                elif item_type == "goal":
                    result["goals"].append(item)
                elif item_type == "category":
                    result["categories"].append(item)
                elif item_type == "dashboard":
                    result["dashboard"] = item

            return result
        except Exception as e:
            print(f"Error getting user data: {str(e)}")
            raise

    def get_changes_since(self, user_id: str, since_timestamp: str) -> List[Dict[str, Any]]:
        """Get all items that have been updated since a given timestamp."""
        try:
            query = """
            SELECT * FROM c 
            WHERE c.user_id = @user_id 
            AND c.updated_at > @since_timestamp
            """
            items = list(self.container.query_items(
                query=query,
                parameters=[
                    {"name": "@user_id", "value": user_id},
                    {"name": "@since_timestamp", "value": since_timestamp}
                ],
                enable_cross_partition_query=False
            ))
            return items
        except Exception as e:
            print(f"Error getting changes since timestamp: {str(e)}")
            raise


