The site now runs Django REST framework 3.18.3, Pillow 13.0.0, certifi 2026.10.23 and
soupsieve 4.1, past the security problems published for the versions before them. A crafted
request to the public page API (`/api/v2/`) could keep a web worker busy. Pillow reads the receipt
photo a supporter uploads on the pay page without signing in, and now only its JPEG, PNG and WebP
readers look at an upload. certifi, whose certificate list is used when an editor embeds a video,
drops certificates that were revoked. soupsieve isn't used on a live site; it's upgraded so
security scanners stop listing it ([#360](https://github.com/dipbazz/trayi/issues/360)).
