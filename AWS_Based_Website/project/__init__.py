import pymysql
from pymongo import MongoClient
from cs527_web_project.settings import DATABASES

pymysql.install_as_MySQLdb()
mongoClient = MongoClient(DATABASES["mongodb"]["HOST"], DATABASES["mongodb"]["PORT"], connect=False)
