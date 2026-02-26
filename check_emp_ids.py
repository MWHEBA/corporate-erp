import json

with open('hr/fixtures/employees.json', 'r', encoding='utf-8') as f:
    data = json.load(f)
    ids = [e['pk'] for e in data]
    print(f'Employee IDs range: {min(ids)} to {max(ids)}')
    print(f'Total: {len(ids)} employees')
    print(f'First 5 IDs: {sorted(ids)[:5]}')
