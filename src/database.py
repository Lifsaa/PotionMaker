import os
import dotenv
from sqlalchemy import create_engine,MetaData,Table,Column,Integer,String,Text,ForeignKey,DateTime,func,Index

def database_connection_url():
    dotenv.load_dotenv()
    return os.environ.get("POSTGRES_URI")
engine = create_engine(database_connection_url(), pool_pre_ping=True)
metadata = MetaData()

customer_info = Table('customer_info', metadata, autoload_with=engine)
potion_catalog = Table('potion_catalog', metadata, autoload_with=engine)
carts = Table('carts', metadata, autoload_with=engine)
carts_items = Table('carts_items', metadata, autoload_with=engine)