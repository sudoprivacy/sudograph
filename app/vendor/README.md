# Vendored, not linked

Both libraries are inlined into every generated app by `compiler/app.py`.

An audit deliverable is opened from disk, often at a client site. A CDN
reference turns "open this file" into "open this file, on a machine with
internet, on a day the CDN is up" — so the file carries its own runtime and
makes no network request at load. A test holds that.

| File | Version | Licence | Source |
|---|---|---|---|
| `cytoscape.min.js` | 3.30.2 | MIT (`cytoscape.LICENSE`) | unpkg (`cytoscape`) |
| `elk.bundled.js` | 0.9.3 | EPL-2.0 | unpkg (`elkjs`) |

ELK computes positions; Cytoscape renders the active graph using those positions.
DOM labels preserve text selection and application anchors locate canvas nodes.
Rows are paged separately instead of adding the entire database to the canvas.
