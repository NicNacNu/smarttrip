import requests
import certifi

response = requests.get("https://test.api.amadeus.com", verify=certifi.where())
print(response.status_code)
