import os
import json

data = json.loads(os.environ["DATA"])
print(data["key"], data["key2"])
