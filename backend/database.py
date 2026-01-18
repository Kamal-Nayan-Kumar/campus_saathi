import os
from astrapy import DataAPIClient

class DatabaseManager:
    def __init__(self):
        self.astra_endpoint = os.getenv("ASTRA_DB_API_ENDPOINT")
        self.astra_token = os.getenv("ASTRA_DB_APPLICATION_TOKEN")
        
        if not all([self.astra_endpoint, self.astra_token]):
            raise ValueError("Missing Astra DB credentials")

        self.client = DataAPIClient(self.astra_token)
        self.db = self.client.get_database(self.astra_endpoint)

    def get_collection(self, collection_name="campus_saathi_docs"):
        """
        Returns the Astra DB collection object.
        Assumes the collection is created with Vectorize enabled on the server side.
        """
        return self.db.get_collection(collection_name)