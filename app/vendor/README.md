# Vendored, not linked

Both libraries are inlined into every generated app by `compiler/app.py`.

An audit deliverable is opened from disk, often at a client site. A CDN
reference turns "open this file" into "open this file, on a machine with
internet, on a day the CDN is up" — so the file carries its own runtime and
makes no network request at load. A test holds that.

| File | Version | Licence | Source |
|---|---|---|---|
| `cytoscape.min.js` | 3.30.2 | MIT | cdnjs |
| `elk.bundled.js` | 0.9.3 | EPL-2.0 | unpkg (`elkjs`) |
| `cytoscape-elk.js` | 2.2.0 | MIT | unpkg (`cytoscape-elk`) |

Layout is ELK's `layered`: this is a DAG read top-down, and cytoscape's built-in
layouts scatter it. `elk.bundled.js` is 1.6 MB, which is most of a generated
app's size and is the price of it opening anywhere.
