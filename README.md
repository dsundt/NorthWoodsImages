# NorthWoodsImages# NorthWoodsImages

## Web UI (Upload & Run)

Visit **/ui/** on GitHub Pages for a browser-based uploader and runner:
- Upload your ZIP and logo (optional: captions.csv, order.txt)
- Enter brand details
- Paste a fine-grained PAT (Contents RW, Workflows RW)
- Click **Upload & Run**
- When complete, download artifacts directly and open the Pages output

Notes:
- Browser/API upload practical limit: ~95 MB per file. For larger uploads, commit via Git or split the ZIP.
- Uploads are saved under `input/uploads/<timestamp>/` to avoid overwrites.
