# Third-party notices

## egctl — protocol reference (ported into `pyegpm/`)

The native LAN protocol implemented in `pyegpm/protocol.py` and `pyegpm/const.py`
is a 1:1 port of **egctl** by Vitaly Sinilin, used under the MIT License.

- Source: https://github.com/unterwulf/egctl
- Files ported from: `egctl.c` (functions `consume_key`, `authorize`,
  `decrypt_status`, `send_controls`, `convert_*_state`, `establish_connection`,
  `close_session`).

```
Copyright (c) 2014, 2017, 2023 Vitaly Sinilin <vs@kp4.ru>

Permission is hereby granted, free of charge, to any person obtaining a
copy of this software and associated documentation files (the "Software"),
to deal in the Software without restriction, including without limitation
the rights to use, copy, modify, merge, publish, distribute, sublicense,
and/or sell copies of the Software, and to permit persons to whom the
Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
DEALINGS IN THE SOFTWARE.
```

## asig/energenie — cross-check only (no code copied)

`native.go` from https://github.com/asig/energenie (Andreas Signer, GPLv3) was
read **only** to cross-verify the arithmetic. No code from it was copied into
this project, so its GPL does not apply here.
