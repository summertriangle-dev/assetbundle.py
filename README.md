# assetbundle.py

This is a fork of the [asset bundle decoder from deresute.me](https://github.com/marcan/deresuteme/blob/master/decode.py) (thanks @marcan)
which basically adds...

- support for the "UnityFS" header format (and a hook point for other kinds of asset wrapping)
- extraction of texture2d using [libahff](https://github.com/summertriangle-dev/starlight_sync/tree/master/misc_utils/libahff) instead of the PIL
- compatibility with Idol Connect files 👌
- ported to python3

That's essentially it. Have fun.
