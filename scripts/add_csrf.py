import os
import re

template_dir = r'c:\Users\shara\OneDrive\Desktop\attendence app\templates'
token = '\n                    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}"/>'

# Regex to match form tags that are POST
form_regex = re.compile(r'(<form[^>]*method=[\'\"]POST[\'\"][^>]*>)', re.IGNORECASE)

count = 0
for root, dirs, files in os.walk(template_dir):
    for file in files:
        if file.endswith('.html'):
            filepath = os.path.join(root, file)
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            
            if 'csrf_token()' not in content:
                new_content, num_replacements = form_regex.subn(r'\g<1>' + token, content)
                if num_replacements > 0:
                    with open(filepath, 'w', encoding='utf-8') as f:
                        f.write(new_content)
                    count += 1
                    print(f'Updated {filepath} with {num_replacements} replacements.')
print(f'Total files updated: {count}')
