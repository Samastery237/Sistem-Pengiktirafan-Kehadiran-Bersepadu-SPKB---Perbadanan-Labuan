const https = require('https');
const fs = require('fs');

https.get('https://www.cstcl.com.my/wp-content/uploads/2018/12/Logo-Perbadanan-Labuan.png', (res) => {
  const data = [];
  res.on('data', (chunk) => data.push(chunk));
  res.on('end', () => {
    const buffer = Buffer.concat(data);
    const base64 = buffer.toString('base64');
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
  <circle cx="50" cy="50" r="50" fill="white" />
  <image href="data:image/png;base64,${base64}" x="10" y="10" width="80" height="80" />
</svg>`;
    fs.writeFileSync('favicon.svg', svg);
    console.log('Saved favicon.svg');
  });
}).on('error', (err) => {
  console.error(err);
});
