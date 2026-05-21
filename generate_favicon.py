import urllib.request
from PIL import Image, ImageDraw
import io

url = "https://www.cstcl.com.my/wp-content/uploads/2018/12/Logo-Perbadanan-Labuan.png"
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
with urllib.request.urlopen(req) as response:
    img_data = response.read()

img = Image.open(io.BytesIO(img_data)).convert("RGBA")

# Make a white background, but let's make it a circle!
size = max(img.size)
bg = Image.new("RGBA", (size, size), (255, 255, 255, 0))
draw = ImageDraw.Draw(bg)
draw.ellipse((0, 0, size, size), fill=(255, 255, 255, 255))

# Paste the logo in the center
offset = ((size - img.width) // 2, (size - img.height) // 2)
bg.paste(img, offset, img)

# Resize to standard favicon size for performance
bg.thumbnail((128, 128), Image.Resampling.LANCZOS)
bg.save("favicon_solid.png", "PNG")
print("Saved favicon_solid.png")
