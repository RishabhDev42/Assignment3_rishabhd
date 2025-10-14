from pymilvus import connections, list_collections, drop_collection

connections.connect()
for name in list_collections():
    drop_collection(name)
