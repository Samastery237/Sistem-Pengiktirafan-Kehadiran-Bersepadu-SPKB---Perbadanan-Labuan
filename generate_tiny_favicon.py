import urllib.request
from PIL import Image, ImageDraw
import io
import base64

url = "https://www.cstcl.com.my/wp-content/uploads/2018/12/Logo-Perbadanan-Labuan.png"
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
with urllib.request.urlopen(req) as response:
    img_data = response.read()

img = Image.open(io.BytesIO(img_data)).convert("RGBA")

# Crop out any transparent padding that was pushing it off-center
bbox = img.getbbox()
if bbox:
    img = img.crop(bbox)

# Create a high-res base for the circle
size = 256
bg = Image.new("RGBA", (size, size), (255, 255, 255, 0))
draw = ImageDraw.Draw(bg)
draw.ellipse((0, 0, size, size), fill=(255, 255, 255, 255))

# Resize logo to be much larger inside the circle (85% of diameter)
target_logo_size = int(size * 0.85)
img.thumbnail((target_logo_size, target_logo_size), Image.Resampling.LANCZOS)

# Perfectly center the logo
offset = ((size - img.width) // 2, (size - img.height) // 2)
bg.paste(img, offset, img)

# Downscale for favicon to save space in HTML
bg.thumbnail((64, 64), Image.Resampling.LANCZOS)

buffer = io.BytesIO()
bg.save(buffer, format="PNG")
b64_str = base64.b64encode(buffer.getvalue()).decode("utf-8")
new_tag = f'<link rel="icon" type="image/png" href="data:image/png;base64,{b64_str}" />'

import re
files = ["index.html", "admin.html", "form.html", "success.html"]
for file in files:
    with open(file, "r", encoding="utf-8") as f:
        content = f.read()
    
    # Replace the existing favicon link with the new one using regex
    content = re.sub(r'<link rel="icon" type="image/png" href="data:image/png;base64,[^"]+" />', new_tag, content)
    
    with open(file, "w", encoding="utf-8") as f:
        f.write(content)
        
print("Updated all HTML files with cropped, centered, and enlarged base64 favicon.")
