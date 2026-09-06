# Third-party references and data

Auto FT8 Manager's application code is independently implemented and released
under the MIT license.

## WSJT-X / MSHV protocol

The program interoperates with the public WSJT-X-compatible UDP protocol.
WSJT-X and MSHV themselves contain GPL-licensed code; no WSJT-X/MSHV source code
is copied into this project.

## CTY.DAT

Optional DXCC/entity resolution uses the standard Big CTY / CTY.DAT data
maintained by Jim Reisert, AD1C. The CTY.DAT distribution carries a permissive
notice allowing use, copying, modification and redistribution provided its
copyright and permission notice are preserved. Auto FT8 normally downloads the
data at runtime rather than embedding a stale copy.

Reference project used during protocol research: `sbrunner-atx/wsjtx-mcp`
(MIT license). Auto FT8 contains an independent implementation and preserves
this research attribution here.


## Protocol interoperability

DXWeaver interoperates with the publicly documented WSJT-X-compatible UDP protocol and forwards ADIF UDP records. World Radio League, GridTracker, MSHV and Ham Radio Deluxe are trademarks/projects of their respective owners; DXWeaver is not affiliated with them.
