#!/usr/bin/env bash
# Descarga los emojis de Apple (iPhone) en alta resolución a assets/emoji_apple/ (no se suben a git).
#  - emoji-image: PNG de 160 px por nombre corto (moneybag.png, rocket.png...)
#  - emoji-datasource-apple: tabla emoji -> nombre y PNG de 64 px para los que falten
set -e
cd "$(dirname "$0")/.."
D=assets/emoji_apple
[ -f "$D/emoji.json" ] && [ -d "$D/160" ] && exit 0
mkdir -p "$D" && T=$(mktemp -d)
curl -sSL -o "$T/a.tgz" https://registry.npmjs.org/emoji-image/-/emoji-image-10.13.1.tgz
curl -sSL -o "$T/b.tgz" https://registry.npmjs.org/emoji-datasource-apple/-/emoji-datasource-apple-16.0.0.tgz
tar xzf "$T/a.tgz" -C "$T" && rm -rf "$D/160" && mv "$T/package/images" "$D/160"
mkdir -p "$T/b" && tar xzf "$T/b.tgz" -C "$T/b" package/emoji.json package/img/apple/64
mv "$T/b/package/emoji.json" "$D/emoji.json" && rm -rf "$D/64" && mv "$T/b/package/img/apple/64" "$D/64"
rm -rf "$T"
echo "Emojis de Apple instalados en $D"
