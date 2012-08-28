#!/bin/python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

# Simple script that can be modified to backfill changes to data.json
# when updating the format
# Filter through 'python -mjson.tool' to beautify
import json
import uuid

def addUUID(obj, parent=None):
  startSize = len(obj)
  for key in obj:
    if key == "video" and ('uuid' in obj) == False:
      obj['uuid'] = uuid.uuid1().hex;
    if type(key) is dict:
      addUUID(key)
    elif type(obj[key]) is dict:
      addUUID(obj[key], obj)
    elif type(obj[key]) is list:
      addUUID(obj[key], obj)
    if startSize != len(obj):
      addUUID(obj, parent)
      return

f = open('data.json', 'r');
data = json.loads(f.read())
addUUID(data);
print json.dumps(data)
