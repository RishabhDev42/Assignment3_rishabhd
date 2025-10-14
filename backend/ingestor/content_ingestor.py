import os

from langchain.schema import Document
from langchain_community.document_loaders import PyPDFLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.embeddings import HuggingFaceEmbeddings
from pymilvus import connections, FieldSchema, CollectionSchema, DataType, Collection, MilvusClient


class ContentIngestor:
    def __init__(self, collection_name="learning_portal"):
        self.collection_name = collection_name

        # Load embedding model
        model_name = "sentence-transformers/all-mpnet-base-v2"
        self.embedding_model = HuggingFaceEmbeddings(model_name=model_name)
        self.embedding_dim = 768

        # Connect to Milvus
        self.client = MilvusClient()
        connections.connect()

        # Ensure the collection exists
        self._ensure_collection_exists()



    def _ensure_collection_exists(self):
        """Creates the Milvus collection if it doesn't already exist."""
        if not self.client.has_collection(self.collection_name):
            fields = [
                FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True),
                FieldSchema(name="passage", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="source_type", dtype=DataType.VARCHAR, max_length=100),
                FieldSchema(name="source_identifier", dtype=DataType.VARCHAR, max_length=1000),
                FieldSchema(name="chunk_seq_id", dtype=DataType.INT64),
                FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=self.embedding_dim)
            ]
            schema = CollectionSchema(fields=fields, description="Collection for RAG content")
            self.client.create_collection(self.collection_name, schema=schema)
            self.collection = Collection(self.collection_name)

            # Create an index for the embedding field for faster searching
            index_params = {"metric_type": "L2", "index_type": "IVF_FLAT", "params": {"nlist": 128}}

            self.collection.create_index(field_name="embedding", index_params=index_params)
            print(f"✅ Collection '{self.collection_name}' created.")
        else:
            self.collection = Collection(self.collection_name)
            if not self.collection.has_index():
                index_params = {"metric_type": "L2", "index_type": "IVF_FLAT", "params": {"nlist": 128}}
                self.collection.create_index(field_name="embedding", index_params=index_params)
                print(f"✅ Index for 'embedding' field created.")
            print(f"✅ Collection '{self.collection_name}' already exists.")
            print(f"✅ Collection '{self.collection_name}' already exists.")

        # Load the collection into memory for searching
        self.collection.load()

    def _chunk_documents(self, docs):
        """Splits documents into smaller chunks."""
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=150)
        return text_splitter.split_documents(docs)

    def ingest_text(self, text: str, source_identifier: str = "manual_text"):
        """Chunks, embeds, and indexes pasted text."""
        try:
            print(f"Ingesting pasted text...")
            docs = [Document(page_content=text)]
            chunks = self._chunk_documents(docs)
            print(f"Split text into {len(chunks)} chunks.")

            data_to_insert = []
            for i, chunk in enumerate(chunks):
                embedding = self.embedding_model.embed_query(chunk.page_content)
                data_to_insert.append({
                    "passage": chunk.page_content,
                    "source_type": "text",
                    "source_identifier": source_identifier,
                    "chunk_seq_id": i,
                    "embedding": embedding
                })

            self.collection.insert(data_to_insert)
            self.collection.flush()
            print(f"✅ Successfully ingested {len(data_to_insert)} chunks from pasted text.")
            return len(data_to_insert)
        except Exception as e:
            print(f"Error ingesting text: {e}")
            return 0

    def ingest_pdf(self, file_path: str):
        """Loads, chunks, embeds, and indexes a PDF file."""
        try:
            file_name = os.path.basename(file_path)
            print(f"Ingesting PDF: {file_name}")
            loader = PyPDFLoader(file_path)
            documents = loader.load()

            chunks = self._chunk_documents(documents)
            print(f"Split PDF into {len(chunks)} chunks.")

            # Prepare data for Milvus
            data_to_insert = []
            for i, chunk in enumerate(chunks):
                embedding = self.embedding_model.embed_query(chunk.page_content)
                data_to_insert.append({
                    "passage": chunk.page_content,
                    "source_type": "pdf",
                    "source_identifier": file_name,
                    "chunk_seq_id": i,
                    "embedding": embedding
                })

            self.collection.insert(data_to_insert)
            self.collection.flush()
            print(f"✅ Successfully ingested {len(data_to_insert)} chunks from PDF.")
            return len(data_to_insert)
        except Exception as e:
            print(f"Error ingesting PDF: {e}")
            return 0