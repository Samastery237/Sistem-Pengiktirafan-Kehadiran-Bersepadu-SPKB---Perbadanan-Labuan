import os

with open("favicon_base64.txt", "r") as f:
    base64_tag = f.read().strip()

files = ["index.html", "admin.html", "form.html", "success.html"]

for file in files:
    with open(file, "r", encoding="utf-8") as f:
        content = f.read()
    
    content = content.replace('<link rel="icon" type="image/png" href="favicon_v2.png" />', base64_tag)
    
    with open(file, "w", encoding="utf-8") as f:
        f.write(content)
        
print("Updated all HTML files with inline base64 favicon.")
