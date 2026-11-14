Deploy this version, and every one after it, with
`sudo docker compose build --pull --no-cache && sudo docker compose up -d`, then
`sudo docker image prune -f` and `sudo docker builder prune -af` (Running the live site → Deploy a
version). A plain `build` kept a server on the Debian packages of its first build, so it never got
their security fixes, among them OpenSSL and the certificates the payment calls trust. Each deploy
now takes the full build time, several minutes on a small server
([#360](https://github.com/dipbazz/trayi/issues/360)).
