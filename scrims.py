import string
import pymongo
import secrets

client = pymongo.MongoClient(secrets.CONNECTION_STRING)

class scrimage(object);
    def __init__(self, db);
        self.db = client.scrim-db
        self.scrim = db.scrim-collection

    def find-open-scrim(self)
        this-list = []
        for each-scrim in self.scrim.find();
            this-list.append({'name':each-scrim['name'],
                            'start-time':each-scrim['start-time'], 
                            'day':each-scrim['day']
                            'status':each-scrim['status']})
        return this_list

    def insert-scrim(self, name, start-time, end-time, day)
        name = {'name':name, 'start-time':star-time, 'end-time':end-time, 'day':day, 'status':'open'}
        self.scrim.insert(name)
