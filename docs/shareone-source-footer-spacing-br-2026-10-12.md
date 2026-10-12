# Remote-source attribution consumes excess space in viewport applications

The Northwind reader at https://s.shareone.vip/s/sudograph-northwind is a flex
application sized to its iframe viewport. Source attribution is useful and should
remain visible. The attribution injected by ShareOne adds document-style spacing
after the application's status footer, reducing the interactive canvas.

Read-only inspection identifies `SOURCE_ATTRIBUTION_TEMPLATE` in
`backend/services/remote_fetch_service.py`: an appended DIV has `margin-top:2em`
and `padding:12px 16px`, with a 12px font. At the tested widths, the margin is 24px.

Observed with ai-dev-browser in an anonymous browser:

| Outer viewport | Iframe height | App status footer ends | Attribution space |
| --- | ---: | ---: | ---: |
| 1680 x 1100 | 1062px | 994.41px | 67.59px |
| 390 x 844 | 806px | 719.81px | 86.19px |

The 24px gap is independent of Sudograph's canvas layout. The remaining space
includes attribution padding and, on the phone, its wrapped URL. No change was
made to ShareOne or to generated demo HTML.

Please support compact attribution for viewport applications, ideally through an
explicit page capability. Keep the source link and ordinary document spacing for
article pages. Verify desktop and phone views, comments open/closed, and window
resizing; preserve the iframe's usable height without another scrollable blank
region. The canvas itself may still have aspect-ratio fitting space: that is
separate from this measured footer gap.
