import csv
from pprint import pprint

group_csv = "data/exportGroup_2024-8-30.csv"
role_csv = "data/Roleassignments.csv"


reader = csv.DictReader(open(group_csv, encoding="utf-8"))
group_dict = {}
for row in reader:
    group_dict[row["displayName"]] = row["id"]


reader = csv.DictReader(open(role_csv, encoding="utf-8"))
role_array = []
for row in reader:
    if row["User Group Name"] in group_dict:
        role_array.append({
            "GroupName": row["User Group Name"],
            "RoleName": row["Role Name"],
            "GroupID": group_dict[row["User Group Name"]]
        })

pprint(role_array)
